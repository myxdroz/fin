"""Провайдер дивидендов через T-Invest REST API (официальный источник, требует токена).

MOEX ISS больше не отдаёт историю дивидендов, Smart-Lab — неофициальный парсинг.
Этот провайдер используется, когда задан TINVEST_TOKEN (достаточно read-only scope).

Документация: https://developer.tbank.ru/invest/intro/intro
Эндпоинты: https://invest-public-api.tinkoff.ru/rest/tinkoff.public.invest.api.contract.v1.InstrumentsService/...
"""

import logging
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

BASE = "https://invest-public-api.tinkoff.ru/rest"
SERVICES = {
    "instruments": "tinkoff.public.invest.api.contract.v1.InstrumentsService",
    "users": "tinkoff.public.invest.api.contract.v1.UsersService",
    "operations": "tinkoff.public.invest.api.contract.v1.OperationsService",
}
# Нац. удостоверяющий центр Минцифры не входит в стандартные системные хранилища доверенных СА
RU_CA_BUNDLE = Path(__file__).parent / "certs" / "russian_trusted_root.pem"


def _iso(d: date) -> str:
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def _money(m) -> float:
    if not isinstance(m, dict):
        try:
            return float(m)
        except (TypeError, ValueError):
            return 0.0
    try:
        return int(m.get("units", 0)) + int(m.get("nano", 0)) / 1e9
    except (TypeError, ValueError):
        return 0.0


class TInvestDividends:
    def __init__(self, token: str, timeout: float = 20.0) -> None:
        self._http = httpx.Client(
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=timeout,
            verify=str(RU_CA_BUNDLE) if RU_CA_BUNDLE.exists() else True,
        )

    def close(self) -> None:
        self._http.close()

    def _post(self, service: str, method: str, body: dict) -> dict:
        url = f"{BASE}/{SERVICES[service]}/{method}"
        # T-Invest иногда отдаёт 500 на тяжёлых запросах — пробуем до 3 раз
        last = None
        for attempt in range(3):
            try:
                resp = self._http.post(url, json=body)
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as e:
                last = e
                if e.response.status_code < 500 or attempt == 2:
                    raise
                time.sleep(1.5 * (attempt + 1))
        raise last

    def shares_figi(self) -> dict[str, str]:
        """ticker -> figi по всем акциям, доступным брокеру."""
        d = self._post("instruments", "Shares", {"instrumentStatus": "INSTRUMENT_STATUS_BASE"})
        return {s["ticker"]: s["figi"] for s in d.get("instruments", [])}

    def instruments_by_figi(self) -> dict[str, dict]:
        """figi -> {ticker, name} по акциям, облигациям, ETF и валютам.

        GetInstrumentBy в REST-шлюзе работает нестабильно — берём из справочников.
        """
        result: dict[str, dict] = {}
        for method in ("Shares", "Bonds", "Etfs", "Currencies"):
            d = self._post("instruments", method, {"instrumentStatus": "INSTRUMENT_STATUS_BASE"})
            for i in d.get("instruments", []):
                result[i["figi"]] = {"ticker": i.get("ticker", ""), "name": i.get("name", "")}
        return result

    def dividends(self, figi: str, years: int = 3) -> list[dict]:
        """История дивидендов: дата фиксации реестра + сумма на акцию, за последние N лет."""
        now = date.today()
        return self._dividends(figi, now - timedelta(days=365 * years), now)

    def dividends_future(self, figi: str, days: int = 45) -> list[dict]:
        """Объявленные будущие дивиденды на ближайшие N дней."""
        now = date.today()
        return self._dividends(figi, now, now + timedelta(days=days))

    def _dividends(self, figi: str, d_from: date, d_to: date) -> list[dict]:
        d = self._post("instruments", "GetDividends", {
            "figi": figi,
            "from": _iso(d_from),
            "to": _iso(d_to),
        })
        result = []
        for item in d.get("dividends", []):
            if item.get("dividendType") == "Cancelled":
                continue
            record_date = item.get("recordDate", "")[:10]
            if not record_date:
                continue
            result.append({
                "ex_date": date.fromisoformat(record_date),
                "value": round(_money(item.get("dividendNet", {})), 4),
                "currency": item.get("dividendNet", {}).get("currency", "RUB"),
            })
        return result

    # --- раздел «Мой портфель» (нужен токен, счёт в Т-Банке) ---

    def accounts(self) -> list[dict]:
        d = self._post("users", "GetAccounts", {})
        return [
            {"id": a["id"], "name": a.get("name", ""), "type": a.get("type", "")}
            for a in d.get("accounts", [])
        ]

    def portfolio(self, account_id: str) -> dict:
        d = self._post("operations", "GetPortfolio", {"accountId": account_id})
        return {
            "total": _money(d.get("totalAmountPortfolio", {})),
            "total_shares": _money(d.get("totalAmountShares", {})),
            "total_bonds": _money(d.get("totalAmountBonds", {})),
            "total_etf": _money(d.get("totalAmountEtf", {})),
            "total_currencies": _money(d.get("totalAmountCurrencies", {})),
            "expected_yield": _money(d.get("expectedYield", {})),
            "daily_yield": _money(d.get("dailyYield", {})),
            "positions": [
                {
                    "figi": p["figi"],
                    "type": p.get("instrumentType", ""),
                    "quantity": _money(p.get("quantity", {})),
                    "avg_price": _money(p.get("averagePositionPrice", {})),
                    "current_price": _money(p.get("currentPrice", {})),
                    "expected_yield": _money(p.get("expectedYield", {})),
                }
                for p in d.get("positions", [])
            ],
        }

    def instrument(self, figi: str) -> dict:
        d = self._post("instruments", "GetInstrumentBy",
                       {"id_type": "ID_TYPE_FIGI", "id": figi})
        i = d.get("instrument", {})
        return {"name": i.get("name", ""), "ticker": i.get("ticker", "")}

    def bond_coupons(self, figi: str, days: int = 45) -> list[dict]:
        """Купоны облигации на ближайшие N дней (на 1 бумагу)."""
        now = date.today()
        d = self._post("instruments", "GetBondCoupons", {
            "figi": figi,
            "from": _iso(now),
            "to": _iso(now + timedelta(days=days)),
        })
        return [
            {
                "date": date.fromisoformat(e["couponDate"][:10]),
                "value": round(_money(e.get("payOneBond", {})), 4),
            }
            for e in d.get("events", [])
        ]
