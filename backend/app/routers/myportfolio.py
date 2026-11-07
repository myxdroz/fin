"""Раздел «Мой портфель»: реальные позиции и календарь выплат по счёту Т-Банка."""

import logging
from datetime import date

from fastapi import APIRouter, HTTPException, Query

from ..config import settings
from ..moex.tinvest import TInvestDividends

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
