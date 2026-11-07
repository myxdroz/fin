"""Раздел «Мой портфель»: реальные позиции и календарь выплат по счёту Т-Банка."""

import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..moex.tinvest import TInvestDividends, _money

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/my", tags=["my"])

TYPE_LABELS = {
    "share": "Акция",
    "bond": "Облигация",
    "etf": "ETF",
    "currency": "Валюта",
    "futures": "Фьючерс",
}


def _client() -> TInvestDividends:
    if not settings.tinvest_token:
        raise HTTPException(
            status_code=400,
            detail="T-Invest токен не настроен. Задайте FIN_TINVEST_TOKEN в .env на сервере.",
        )
    return TInvestDividends(settings.tinvest_token)


@router.get("/accounts")
def get_accounts():
    t = _client()
    try:
        return {"accounts": t.accounts()}
    finally:
        t.close()


@router.get("/portfolio")
def get_portfolio(account_id: str = Query(..., description="ID счёта из /api/my/accounts")):
    t = _client()
    try:
        pf = t.portfolio(account_id)
        total = pf["total"] or 1.0
        figi_map = t.instruments_by_figi()

        for p in pf["positions"]:
            info = figi_map.get(p["figi"], {"ticker": "", "name": p["figi"]})
            if p["type"] == "currency" and not info["ticker"]:
                # у валют в справочнике нет тикера: USD000UTSTOM -> USD
                info = {"ticker": p["figi"][:3], "name": info["name"] or p["figi"][:3]}
            p["name"] = info["name"]
            p["ticker"] = info["ticker"]
            value = p["current_price"] * p["quantity"]
            cost = p["avg_price"] * p["quantity"]
            p["value"] = round(value, 0)
            p["weight"] = round(value / total * 100, 1)
            p["pnl"] = round(p["expected_yield"], 0)
            p["pnl_pct"] = round(p["expected_yield"] / cost * 100, 1) if cost else 0.0
            p["type_label"] = TYPE_LABELS.get(p["type"], p["type"])
        pf["positions"].sort(key=lambda x: -x["value"])
        return pf
    finally:
        t.close()


@router.get("/income")
def get_income(account_id: str = Query(...), days: int = Query(45, le=90)):
    """Календарь ближайших выплат: купоны по облигациям + объявленные дивиденды."""
    t = _client()
    events = []
    try:
        figi_map = t.instruments_by_figi()
        pf = t.portfolio(account_id)
        for p in pf["positions"]:
            if p["quantity"] <= 0 or p["type"] not in ("bond", "share"):
                continue
            ticker = figi_map.get(p["figi"], {}).get("ticker", "")
            try:
                if p["type"] == "bond":
                    for c in t.bond_coupons(p["figi"], days):
                        events.append({
                            "date": c["date"].isoformat(),
                            "kind": "Купон",
                            "ticker": ticker,
                            "amount": round(c["value"] * p["quantity"], 0),
                        })
                else:
                    for d in t.dividends_future(p["figi"], days):
                        events.append({
                            "date": d["ex_date"].isoformat(),
                            "kind": "Дивиденд",
                            "ticker": ticker,
                            "amount": round(d["value"] * p["quantity"], 0),
                        })
            except Exception:
                log.warning("Income calendar failed for %s", p["figi"])
            import time

            time.sleep(0.15)  # не ддосим API
        events.sort(key=lambda e: e["date"])
        return {"events": events, "total": round(sum(e["amount"] for e in events), 0)}
    finally:
        t.close()


@router.get("/taxes")
def get_taxes(account_id: str = Query(...)):
    """НДФЛ с инвестиционного дохода + подсказки по ИИС."""
    t = _client()
    try:
        pf = t.portfolio(account_id)
        figi_map = t.instruments_by_figi()
        annual = 0.0
        for p in pf["positions"]:
            if p["quantity"] <= 0 or p["type"] not in ("bond", "share"):
                continue
            try:
                if p["type"] == "bond":
                    annual += sum(c["value"] for c in t.bond_coupons(p["figi"], 365)) * p["quantity"]
                else:
                    annual += sum(d["value"] for d in t.dividends(p["figi"], years=1)) * p["quantity"]
            except Exception:
                log.warning("Tax calc failed for %s", p["figi"])
        annual = round(annual, 0)
        # прогрессивная шкала 2025: 13% до 2.4 млн, 15% свыше
        low = min(annual, 2_400_000)
        high = max(annual - 2_400_000, 0)
        tax = round(low * 0.13 + high * 0.15, 0)
        return {
            "annual_income": annual,
            "ndfl_13_base": round(low, 0),
            "ndfl_15_base": round(high, 0),
            "tax_est": tax,
            "iis_a_hint": "ИИС типа А: вычет 13% с пополнений (максимум 52 000 ₽/год при взносе 400 000 ₽)",
            "iis_b_hint": "ИИС типа Б: освобождение от НДФЛ с дохода по счёту при закрытии",
        }
    finally:
        t.close()


@router.get("/history")
def get_history(db: Session = Depends(get_db)):
    """История стоимости портфеля (ежедневные снимки после синхронизации)."""
    from ..models import PortfolioSnapshot

    rows = db.scalars(select(PortfolioSnapshot).order_by(PortfolioSnapshot.date)).all()
    return {"points": [
        {"date": r.date.isoformat(), "total": r.total, "cash": r.cash} for r in rows
    ]}


@router.get("/lots")
def get_lots(account_id: str = Query(...)):
    """Разбивка позиций на лоты: каждая покупка с датой и ценой, P&L лота сейчас.

    Продажи вычитаются из самых старых лотов (FIFO).
    """
    t = _client()
    try:
        pf = t.portfolio(account_id)
        figi_map = t.instruments_by_figi()
        current = {p["figi"]: p["current_price"] for p in pf["positions"]}

        # вся история операций с 2021 года, с пагинацией
        ops = []
        cursor = ""
        while True:
            d = t._post("operations", "GetOperationsByCursor", {
                "accountId": account_id,
                "from": "2021-01-01T00:00:00Z",
                "to": date.today().isoformat() + "T23:59:59Z",
                "cursor": cursor, "limit": 1000,
                "state": "OPERATION_STATE_EXECUTED",
            })
            items = d.get("items", [])
            ops.extend(items)
            nxt = d.get("nextCursor", "")
            if not items or not nxt or nxt == cursor:
                break
            cursor = nxt

        # очередь покупок по каждому figi, вычет продаж FIFO
        from collections import deque

        lots: dict[str, deque] = {}
        REDUCE_TYPES = ("OPERATION_TYPE_SELL", "OPERATION_TYPE_BOND_REPAYMENT",
                        "OPERATION_TYPE_AMORTIZATION")
        for op in sorted(ops, key=lambda o: o.get("date", "")):
            figi = op.get("figi", "")
            if not figi or op.get("instrumentType") not in ("share", "bond", "etf"):
                continue
            qty = _money(op.get("quantity", {}))
            price = _money(op.get("price", {}))
            if op.get("type") == "OPERATION_TYPE_BUY" and qty > 0 and price > 0:
                lots.setdefault(figi, deque()).append(
                    {"date": op["date"][:10], "price": price, "qty": qty})
            elif op.get("type") in REDUCE_TYPES and qty > 0:
                queue = lots.setdefault(figi, deque())
                rest = qty
                while rest > 0 and queue:
                    lot = queue[0]
                    take = min(lot["qty"], rest)
                    lot["qty"] -= take
                    rest -= take
                    if lot["qty"] <= 1e-9:
                        queue.popleft()
                if rest > 0:
                    queue.clear()  # продали больше, чем видно в истории

        # показываем только то, что реально есть в портфеле сейчас
        positions = []
        for figi, queue in lots.items():
            if not queue or figi not in current or current[figi] <= 0:
                continue
            info = figi_map.get(figi, {})
            cur = current.get(figi, 0)
            lot_rows = []
            total_qty = 0
            total_invested = 0.0
            for lot in queue:
                invested = lot["price"] * lot["qty"]
                total_qty += lot["qty"]
                total_invested += invested
                lot_rows.append({
                    "date": lot["date"],
                    "price": round(lot["price"], 4),
                    "qty": round(lot["qty"], 4),
                    "invested": round(invested, 0),
                    "pnl_pct": round((cur / lot["price"] - 1) * 100, 1) if lot["price"] and cur else None,
                })
            positions.append({
                "ticker": info.get("ticker", ""),
                "name": info.get("name", ""),
                "current_price": cur,
                "total_qty": round(total_qty, 4),
                "total_invested": round(total_invested, 0),
                "avg_price": round(total_invested / total_qty, 4) if total_qty else 0,
                "lots": lot_rows,
            })
        positions.sort(key=lambda p: -p["total_invested"])
        return {"positions": positions}
    finally:
        t.close()
