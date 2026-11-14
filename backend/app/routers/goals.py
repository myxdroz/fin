"""Страница «Цели»: прогресс к целевому капиталу и целевому доходу + диаграмма по отраслям."""

import logging
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import Bond, Dividend, IndexWeight, Setting, Share
from ..moex.tinvest import TInvestDividends

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/goals", tags=["goals"])

CAPITAL_GOAL_KEY = "capital_goal"
DEFAULT_CAPITAL_GOAL = 1_400_000.0
INFLATION_KEY = "inflation_rate"
DEPOSIT_KEY = "deposit_rate"
DEFAULT_INFLATION = 7.0
DEFAULT_DEPOSIT = 16.0

# 60% облигации «класса ААА» (ОФЗ как безрисковый эквивалент) + 40% голубые фишки
BOND_SHARE = 0.6
SHARE_SHARE = 0.4

# Отраслевая карта голубых фишек (тикер -> отрасль из учёта пользователя)
SECTOR_MAP = {
    "LKOH": "Нефтегаз", "ROSN": "Нефтегаз", "TATN": "Нефтегаз", "TATNP": "Нефтегаз",
    "SNGS": "Нефтегаз", "SNGSP": "Нефтегаз", "GAZP": "Нефтегаз", "SIBN": "Нефтегаз",
    "NVTK": "Нефтегаз", "TRNFP": "Нефтегаз",
    "GMKN": "Добыча", "NLMK": "Добыча", "MAGN": "Добыча", "ALRS": "Добыча",
    "PLZL": "Добыча", "RUAL": "Добыча", "MTLR": "Добыча", "MTLRP": "Добыча", "CHMF": "Добыча",
    "PHOR": "Индустрия",
    "AFLT": "Потребление вторичное",
    "MGNT": "Потребление первичное", "FIXR": "Потребление первичное", "X5": "Потребление первичное",
    "MVID": "Потребление вторичное", "SELG": "Потребление первичное",
    "MDMG": "Здоровье",
    "SBER": "Финансы", "SBERP": "Финансы", "VTBR": "Финансы", "MOEX": "Финансы",
    "AFKS": "Финансы", "BSPB": "Финансы", "CBOM": "Финансы",
    "YDEX": "Технологии", "T": "Технологии", "OZON": "Технологии",
    "VK": "Технологии", "POSI": "Технологии",
    "MTSS": "Телеком и Медиа", "RTKM": "Телеком и Медиа", "RTKMP": "Телеком и Медиа",
    "HYDR": "Коммунальные", "IRAO": "Коммунальные", "FEES": "Коммунальные",
    "MSNG": "Коммунальные", "TGKA": "Коммунальные", "TGKB": "Коммунальные",
    "LSRG": "Недвижимость", "PIKK": "Недвижимость", "SAMO": "Недвижимость",
}
SECTOR_ORDER = [
    "Нефтегаз", "Добыча", "Индустрия", "Потребление вторичное", "Потребление первичное",
    "Здоровье", "Финансы", "Технологии", "Телеком и Медиа", "Коммунальные", "Недвижимость",
]


class CapitalGoalUpdate(BaseModel):
    value: float = Field(gt=0)


class BenchmarksUpdate(BaseModel):
    inflation: float = Field(ge=0, le=50)
    deposit: float = Field(ge=0, le=100)


def _get_setting(db: Session, key: str, default: float) -> float:
    row = db.get(Setting, key)
    return row.value if row else default


def _ofz_yield(db: Session) -> float:
    """Средняя доходность ОФЗ — прокси для «облигаций класса ААА»."""
    stmt = select(Bond).where(
        Bond.is_ofz == 1,
        Bond.yield_at_pricing > 0,
        Bond.duration <= 3650,
        Bond.val_today > 10_000_000,
    )
    rows = db.scalars(stmt).all()
    if not rows:
        return settings.key_rate
    return sum(b.yield_at_pricing for b in rows) / len(rows)


def _blue_chip_div_yield(db: Session) -> float:
    """Средняя дивидендная доходность акций из состава IMOEX за 12 мес."""
    secids = [w.secid for w in db.scalars(select(IndexWeight)).all()]
    if not secids:
        return 0.0
    shares = db.scalars(select(Share).where(Share.secid.in_(secids))).all()
    prices = {s.secid: s.last_price for s in shares if s.last_price > 0}
    divs = db.scalars(select(Dividend).where(Dividend.secid.in_(secids))).all()
    today = date.today()
    div_map: dict[str, float] = {}
    for d in divs:
        if d.ex_date and (today - d.ex_date).days <= 365:
            div_map[d.secid] = div_map.get(d.secid, 0.0) + d.value
    yields = [div_map[s] / prices[s] * 100 for s in prices if div_map.get(s)]
    return sum(yields) / len(yields) if yields else 0.0


def _goal_income(db: Session, capital_goal: float) -> dict:
    bond_yield = round(_ofz_yield(db), 2)
    div_yield = round(_blue_chip_div_yield(db), 2)
    blended = BOND_SHARE * bond_yield + SHARE_SHARE * div_yield
    monthly = capital_goal * blended / 100 / 12
    return {
        "monthly": round(monthly, 0),
        "annual_pct": round(blended, 2),
        "bond_yield": bond_yield,
        "share_div_yield": div_yield,
        "assumption": f"{int(BOND_SHARE * 100)}% ОФЗ ({bond_yield}% год.) + "
                      f"{int(SHARE_SHARE * 100)}% акции IMOEX ({div_yield}% год.)",
    }


def _sector_of(t: object, ticker: str, db: Session) -> str:
    if t == "share":
        return SECTOR_MAP.get(ticker, "Прочее")
    if t == "bond":
        bond = db.get(Bond, ticker)
        if bond:
            return "ОФЗ" if bond.is_ofz else "Корп. облигации"
        return "Корп. облигации"
    if t == "etf":
        return "ETF"
    if t == "currency":
        return "Валюта"
    return "Прочее"


def _current_state(db: Session) -> dict:
    """Текущая стоимость и доход из реального портфеля Т-Банка."""
    if not settings.tinvest_token:
        return {"value": None, "income_month": None,
                "error": "FIN_TINVEST_TOKEN не задан — текущие значения недоступны"}
    try:
        t = TInvestDividends(settings.tinvest_token)
    except Exception as e:
        return {"value": None, "income_month": None, "error": f"T-Invest: {e}"}
    try:
        accounts = t.accounts()
        if not accounts:
            return {"value": None, "income_month": None, "error": "Счета не найдены"}
        pf = t.portfolio(accounts[0]["id"])
        figi_map = t.instruments_by_figi()
        annual_income = 0.0
        sectors: dict[str, float] = {}
        for p in pf["positions"]:
            value = p["current_price"] * p["quantity"]
            ticker = figi_map.get(p["figi"], {}).get("ticker", "")
            if p["type"] == "currency":
                ticker = p["figi"][:3]
            sector = _sector_of(p["type"], ticker, db)
            sectors[sector] = sectors.get(sector, 0.0) + value
            if p["quantity"] <= 0:
                continue
            try:
                if p["type"] == "bond":
                    annual_income += sum(c["value"] for c in t.bond_coupons(p["figi"], 365)) * p["quantity"]
                elif p["type"] == "share":
                    annual_income += sum(d["value"] for d in t.dividends(p["figi"], years=1)) * p["quantity"]
            except Exception:
                log.warning("Income calc failed for %s", p["figi"])
        sector_items = [
            {"name": name, "value": round(v, 0)}
            for name, v in sorted(sectors.items(), key=lambda kv: -kv[1]) if v > 0
        ]
        for item in sector_items:
            item["pct"] = round(item["value"] / (pf["total"] or 1) * 100, 1)
        return {
            "value": round(pf["total"], 0),
            "income_month": round(annual_income / 12, 0),
            "sectors": sector_items,
        }
    except Exception as e:
        log.exception("Portfolio read failed")
        return {"value": None, "income_month": None, "error": str(e)[:200]}
    finally:
        t.close()


@router.get("")
def get_goals(db: Session = Depends(get_db)):
    capital_goal = _get_setting(db, CAPITAL_GOAL_KEY, DEFAULT_CAPITAL_GOAL)
    goal_income = _goal_income(db, capital_goal)
    current = _current_state(db)
    inflation = _get_setting(db, INFLATION_KEY, DEFAULT_INFLATION)
    deposit = _get_setting(db, DEPOSIT_KEY, DEFAULT_DEPOSIT)

    cur_value = current.get("value")
    cur_income = current.get("income_month")
    return {
        "capital_goal": capital_goal,
        "goal_income": goal_income,
        "current": current,
        "benchmarks": {
            "inflation": inflation,
            "deposit": deposit,
            # реальная доходность цели за вычетом инфляции
            "goal_real_pct": round(goal_income["annual_pct"] - inflation, 2),
            "deposit_real_pct": round(deposit - inflation, 2),
        },
        "progress_capital_pct": round(cur_value / capital_goal * 100, 1) if cur_value else None,
        "progress_income_pct": (
            round(cur_income / goal_income["monthly"] * 100, 1)
            if cur_income is not None and goal_income["monthly"] else None
        ),
    }


@router.put("/benchmarks")
def set_benchmarks(body: BenchmarksUpdate, db: Session = Depends(get_db)):
    for key, val in ((INFLATION_KEY, body.inflation), (DEPOSIT_KEY, body.deposit)):
        row = db.get(Setting, key)
        if not row:
            db.add(Setting(key=key, value=val))
        else:
            row.value = val
    db.commit()
    return {"inflation": body.inflation, "deposit": body.deposit}


@router.put("/capital")
def set_capital_goal(body: CapitalGoalUpdate, db: Session = Depends(get_db)):
    row = db.get(Setting, CAPITAL_GOAL_KEY)
    if not row:
        row = Setting(key=CAPITAL_GOAL_KEY, value=body.value)
        db.add(row)
    else:
        row.value = body.value
    db.commit()
    return {"capital_goal": body.value}
