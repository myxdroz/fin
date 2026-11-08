"""Сохранённая стратегия пользователя + ребалансировка против реального портфеля."""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import IndexWeight, Strategy
from ..moex.tinvest import TInvestDividends
from ..screener.portfolio import PROFILES, PortfolioRequest, build_portfolio

log = logging.getLogger(__name__)
router = APIRouter(tags=["strategy"])

# бумаги с разницей меньше порога считаем совпавшими (погрешность цен/лотов)
MIN_DIFF_RUB = 500


class StrategyIn(BaseModel):
    profile: str = Field(pattern="^(conservative|moderate|aggressive|bluechips|monthly)$")
    amount: float = Field(gt=0)


def _active_strategy(db: Session) -> Strategy | None:
    return db.scalars(select(Strategy).where(Strategy.active == 1)).first()


@router.get("/api/strategy")
def get_strategy(db: Session = Depends(get_db)):
    s = _active_strategy(db)
    if not s:
        return {"strategy": None}
    return {"strategy": {
        "profile": s.profile,
        "profile_label": PROFILES[s.profile]["label"],
        "amount": s.amount,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }}


@router.put("/api/strategy")
def save_strategy(body: StrategyIn, db: Session = Depends(get_db)):
    db.execute(update(Strategy).values(active=0))
    s = Strategy(profile=body.profile, amount=body.amount, active=1)
    db.add(s)
    db.commit()
    return {"saved": True, "profile": body.profile, "amount": body.amount}


@router.get("/api/my/rebalance")
def rebalance(db: Session = Depends(get_db)):
    """Целевая стратегия vs реальный счёт Т-Банка: что купить, что продать, что держать."""
    strat = _active_strategy(db)
    if not strat:
        raise HTTPException(status_code=400, detail="Сначала сохраните стратегию на вкладке «Портфель»")
    if not settings.tinvest_token:
        raise HTTPException(status_code=400, detail="FIN_TINVEST_TOKEN не задан — данные брокера недоступны")

    target = build_portfolio(db, PortfolioRequest(profile=strat.profile, amount=strat.amount))

    t = TInvestDividends(settings.tinvest_token)
    try:
        accounts = t.accounts()
        if not accounts:
            raise HTTPException(status_code=400, detail="Счета не найдены")
        pf = t.portfolio(accounts[0]["id"])
        figi_map = t.instruments_by_figi()
    finally:
        t.close()

    # реальные позиции по тикеру (для облигаций тикер Т-Инвеста = ISIN = наш secid)
    real: dict[str, dict] = {}
    cash = 0.0
    for p in pf["positions"]:
        ticker = figi_map.get(p["figi"], {}).get("ticker", "")
        if p["type"] == "currency":
            cash += p["current_price"] * p["quantity"]
            continue
        if not ticker:
            continue
        real[ticker] = {
            "ticker": ticker,
            "name": figi_map.get(p["figi"], {}).get("name", ""),
            "type": p["type"],
            "value": p["current_price"] * p["quantity"],
            "qty": p["quantity"],
        }

    # целевые позиции единым списком
    target_pos: dict[str, dict] = {}
    for b in target["bonds"]:
        target_pos[b["secid"]] = {"ticker": b["secid"], "name": b["shortname"],
                                  "type": "bond", "amount": b["amount"],
                                  "price": b["price"], "face_value": b["face_value"],
                                  "lot_size": 1, "target_qty": b["approx_qty"]}
    for s in target["shares"]:
        target_pos[s["secid"]] = {"ticker": s["secid"], "name": s["shortname"],
                                  "type": "share", "amount": s["amount"],
                                  "price": s["price"], "face_value": 1,
                                  "lot_size": s["lot_size"], "target_qty": s["approx_qty"]}

    index_members = {w.secid for w in db.scalars(select(IndexWeight)).all()}

    def qty_for(tpos: dict, amount: float) -> int:
        """Сумма → количество бумаг (с учётом лота/номинала)."""
        if tpos["type"] == "bond":
            unit = tpos["price"] / 100 * tpos["face_value"]
        else:
            unit = tpos["price"] * tpos["lot_size"]
        if unit <= 0:
            return 0
        lots = int(amount // unit)
        return lots * (tpos["lot_size"] if tpos["type"] == "share" else 1)

    actions = []
    for tid, tpos in target_pos.items():
        cur = real.get(tid)
        if cur is None:
            actions.append({**tpos, "action": "BUY",
                            "amount": round(tpos["amount"], 0),
                            "held_qty": 0,
                            "qty": tpos["target_qty"],
                            "note": "новая позиция в стратегии"})
        else:
            diff = tpos["amount"] - cur["value"]
            if diff > MIN_DIFF_RUB:
                actions.append({**tpos, "action": "BUY",
                                "amount": round(diff, 0),
                                "held_qty": round(cur["qty"], 4),
                                "qty": qty_for(tpos, diff),
                                "note": f"есть {cur['qty']:g} шт, докупить"})
            elif diff < -MIN_DIFF_RUB:
                unit_price = cur["current_price"] or tpos["price"]
                actions.append({**tpos, "action": "SELL",
                                "amount": round(-diff, 0),
                                "held_qty": round(cur["qty"], 4),
                                "qty": round(-diff / unit_price) if unit_price else 0,
                                "note": "перевес против стратегии"})
            else:
                actions.append({**tpos, "action": "HOLD", "amount": 0,
                                "held_qty": round(cur["qty"], 4), "qty": 0,
                                "note": "в пределах нормы"})

    for rticker, rpos in real.items():
        if rticker in target_pos:
            continue
        if rpos["type"] == "share" and strat.profile == "bluechips" and rticker not in index_members:
            note = "вышла из состава IMOEX — заменить"
        elif rpos["type"] == "share":
            note = "акция вне целевого набора стратегии"
        elif rpos["type"] == "etf":
            note = "ETF вне стратегии"
        else:
            note = "облигация вне стратегии"
        actions.append({**rpos, "action": "SELL", "amount": round(rpos["value"], 0),
                        "held_qty": round(rpos["qty"], 4),
                        "qty": round(rpos["qty"], 4),
                        "lot_size": 1, "target_qty": 0, "note": note})

    # кандидаты на замену: члены индекса, которых нет ни в цели, ни в портфеле
    replacement_candidates = []
    if strat.profile == "bluechips":
        held_or_target = set(real) | set(target_pos)
        wmap = {w.secid: w for w in db.scalars(select(IndexWeight)).all()}
        for secid in sorted(index_members - held_or_target, key=lambda x: -wmap[x].weight)[:3]:
            replacement_candidates.append({"ticker": secid, "name": wmap[secid].shortname,
                                           "weight": round(wmap[secid].weight, 2)})

    order = {"SELL": 0, "BUY": 1, "HOLD": 2}
    actions.sort(key=lambda a: (order[a["action"]], -a["amount"]))
    return {
        "strategy": {"profile": strat.profile,
                     "profile_label": PROFILES[strat.profile]["label"],
                     "amount": strat.amount},
        "real_total": round(pf["total"], 0),
        "cash": round(cash, 0),
        "target_expected_yield": target["expected_yield"],
        "actions": actions,
        "replacement_candidates": replacement_candidates,
        "buy_total": round(sum(a["amount"] for a in actions if a["action"] == "BUY"), 0),
        "sell_total": round(sum(a["amount"] for a in actions if a["action"] == "SELL"), 0),
    }
