"""Скринер облигаций и акций: фильтрация по параметрам ликвидности и риска."""

from datetime import date

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Bond, Dividend, Share


class BondFilter(BaseModel):
    min_yield: float = 0.0          # мин. доходность к погашению/оферте, %
    max_yield: float = 0.0          # макс. доходность, % (0 = без ограничения; страховка от мусорных данных)
    max_duration: int = 3650        # макс. дюрация, дней
    mat_before: date | None = None  # погашение не позже этой даты
    monthly_coupon: bool = False    # только ежемесячный купон
    min_liquidity: float = 1_000_000  # мин. дневной оборот, руб
    list_level: int = 0             # 0 = любой, иначе уровень листинга <= N
    only_ofz: bool = False
    exclude_offers: bool = False    # без оферт
    exclude_floating: bool = False  # без флоатеров
    exclude_amort: bool = False     # без амортизации
    max_price: float = 105.0        # макс. цена, % от номинала (защита от риска)
    limit: int = Field(default=100, le=500)


class ShareFilter(BaseModel):
    min_div_yield: float = 0.0      # мин. див. доходность за 12 мес, %
    min_liquidity: float = 50_000_000  # мин. дневной оборот, руб
    list_level: int = 1
    limit: int = Field(default=50, le=200)


def bond_red_flags(b: Bond, key_rate: float) -> list[str]:
    """Красные флаги риска — «почему НЕ покупать». Не вердикт, а повод проверить."""
    flags = []
    if not b.is_ofz:
        if b.list_level == 3:
            flags.append("3-й уровень листинга")
        elif b.list_level == 0:
            flags.append("нет уровня листинга")
        if b.val_today < 1_000_000:
            flags.append("низкий оборот (<1 млн ₽/день)")
        if b.issue_size and b.issue_size * b.face_value < 500_000_000:
            flags.append("малый выпуск (<500 млн ₽)")
        if b.yield_at_pricing > key_rate + 10:
            flags.append(f"доходность на {b.yield_at_pricing - key_rate:.0f} п.п. выше ставки — высокий кредитный риск")
    if b.duration > 7 * 365:
        flags.append("высокая дюрация (>7 лет)")
    if b.last_price > 100:
        flags.append("цена выше номинала")
    if b.floating_flag:
        flags.append("плавающий купон")
    if b.amort_flag:
        flags.append("амортизация номинала")
    if b.offer_flag:
        flags.append("есть оферта")
    return flags


def bond_reliability(b: Bond, key_rate: float) -> int:
    """Прокси кредитного качества 1–5 на данных MOEX (5 = ОФЗ). Не рейтинг рейтингового агентства."""
    if b.is_ofz:
        score = 5
    elif b.list_level == 1:
        score = 4
    elif b.list_level == 2:
        score = 3
    elif b.list_level == 3:
        score = 2
    else:
        score = 1
    if not b.is_ofz and b.yield_at_pricing > key_rate + 10:
        score -= 1  # «мусорная» премия к ставке
    return max(score, 1)


def screen_bonds(db: Session, f: BondFilter) -> list[dict]:
    stmt = select(Bond).where(
        Bond.yield_at_pricing >= f.min_yield,
        Bond.duration <= f.max_duration,
        Bond.val_today >= f.min_liquidity,
        Bond.last_price > 0,
        Bond.last_price <= f.max_price,
        Bond.face_unit == "SUR",
        Bond.perpetual_flag == 0,
        Bond.mat_date.isnot(None),
        Bond.mat_date > date.today(),
    )
    if f.max_yield > 0:
        stmt = stmt.where(Bond.yield_at_pricing <= f.max_yield)
    if f.mat_before:
        stmt = stmt.where(Bond.mat_date <= f.mat_before)
    if f.monthly_coupon:
        stmt = stmt.where(Bond.coupon_period > 0, Bond.coupon_period <= 35)
    if f.list_level:
        stmt = stmt.where(Bond.list_level <= f.list_level, Bond.list_level > 0)
    if f.only_ofz:
        stmt = stmt.where(Bond.is_ofz == 1)
    if f.exclude_offers:
        stmt = stmt.where(Bond.offer_flag == 0)
    if f.exclude_floating:
        stmt = stmt.where(Bond.floating_flag == 0)
    if f.exclude_amort:
        stmt = stmt.where(Bond.amort_flag == 0)

    rows = db.execute(stmt).scalars().all()
    # Ранжируем: доходность выше ключевой ставки ценится, но штрафуем за риск-дюрацию
    result = [
        {
            "secid": b.secid,
            "shortname": b.shortname,
            "is_ofz": bool(b.is_ofz),
            "price": round(b.last_price, 2),
            "yield": round(b.yield_at_pricing, 2),
            "yield_after_tax": round(b.yield_at_pricing * 0.87, 2),
            "duration_years": round(b.duration / 365, 2),
            "coupon_percent": b.coupon_percent,
            "coupon_period_days": b.coupon_period,
            "accr_int": b.accr_int,
            "mat_date": b.mat_date.isoformat() if b.mat_date else None,
            "offer_date": b.offer_date.isoformat() if b.offer_date else None,
            "list_level": b.list_level,
            "face_value": b.face_value,
            "val_today": b.val_today,
            "reliability": bond_reliability(b, settings.key_rate),
            "red_flags": bond_red_flags(b, settings.key_rate),
            "flags": {
                "offer": bool(b.offer_flag),
                "floating": bool(b.floating_flag),
                "amort": bool(b.amort_flag),
            },
        }
        for b in rows
    ]
    result.sort(key=lambda x: (-x["yield"], x["duration_years"]))
    return result[: f.limit]


def screen_shares(db: Session, f: ShareFilter) -> list[dict]:
    stmt = select(Share).where(
        Share.val_today >= f.min_liquidity,
        Share.last_price > 0,
        Share.list_level <= f.list_level,
        Share.list_level > 0,
    )
    rows = db.execute(stmt).scalars().all()
    secids = [s.secid for s in rows]
    div_map: dict[str, float] = {}
    if secids:
        divs = db.execute(select(Dividend).where(Dividend.secid.in_(secids))).scalars().all()
        today = date.today()
        for d in divs:
            if d.ex_date and (today - d.ex_date).days <= 365:
                div_map[d.secid] = div_map.get(d.secid, 0.0) + d.value

    result = []
    for s in rows:
        div_yield = div_map.get(s.secid, 0.0) / s.last_price * 100 if s.last_price else 0.0
        if div_yield < f.min_div_yield:
            continue
        result.append({
            "secid": s.secid,
            "shortname": s.shortname,
            "price": s.last_price,
            "div_yield_12m": round(div_yield, 2),
            "dividends_12m": round(div_map.get(s.secid, 0.0), 2),
            "lot_size": s.lot_size,
            "lot_cost": round(s.last_price * s.lot_size, 2),
            "list_level": s.list_level,
            "val_today": s.val_today,
        })
    result.sort(key=lambda x: -x["div_yield_12m"])
    return result[: f.limit]
