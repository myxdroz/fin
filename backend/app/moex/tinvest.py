"""Провайдер дивидендов через T-Invest REST API (официальный источник, требует токена).

MOEX ISS больше не отдаёт историю дивидендов, Smart-Lab — неофициальный парсинг.
Этот провайдер используется, когда задан TINVEST_TOKEN (достаточно read-only scope).

Документация: https://developer.tbank.ru/invest/intro/intro
Эндпоинты: https://invest-public-api.tinkoff.ru/rest/tinkoff.public.invest.api.contract.v1.InstrumentsService/...
"""

import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

BASE = "https://invest-public-api.tinkoff.ru/rest/tinkoff.public.invest.api.contract.v1.InstrumentsService"
# Нац. удостоверяющий центр Минцифры не входит в стандартные системные хранилища доверенных СА
RU_CA_BUNDLE = Path(__file__).parent / "certs" / "russian_trusted_root.pem"


def _iso(d: date) -> str:
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def _money(m: dict) -> float:
    try:
        return int(m.get("units", 0)) + int(m.get("nano", 0)) / 1e9
    except (TypeError, ValueError):
        return 0.0


class TInvestDividends:
    def __init__(self, token: str, timeout: float = 20.0) -> None:
        self._http = httpx.Client(
            base_url=BASE,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=timeout,
            verify=str(RU_CA_BUNDLE) if RU_CA_BUNDLE.exists() else True,
        )

    def close(self) -> None:
        self._http.close()

    def shares_figi(self) -> dict[str, str]:
        """ticker -> figi по всем акциям, доступным брокеру."""
        resp = self._http.post("/Shares", json={"instrumentStatus": "INSTRUMENT_STATUS_BASE"})
        resp.raise_for_status()
        return {s["ticker"]: s["figi"] for s in resp.json().get("instruments", [])}

    def dividends(self, figi: str, years: int = 3) -> list[dict]:
        """История дивидендов: дата фиксации реестра + сумма на акцию, за последние N лет."""
        now = date.today()
        resp = self._http.post("/GetDividends", json={
            "figi": figi,
            "from": _iso(now - timedelta(days=365 * years)),
            "to": _iso(now),
        })
        resp.raise_for_status()
        result = []
        for d in resp.json().get("dividends", []):
            if d.get("dividendType") == "Cancelled":
                continue
            record_date = d.get("recordDate", "")[:10]
            if not record_date:
                continue
            result.append({
                "ex_date": date.fromisoformat(record_date),
                "value": round(_money(d.get("dividendNet", {})), 4),
                "currency": d.get("dividendNet", {}).get("currency", "RUB"),
            })
        return result
