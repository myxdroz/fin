"""Клиент MOEX ISS API: https://www.moex.com/a2193 """

import httpx

from ..config import settings

BOND_SECURITY_COLUMNS = (
    "SECID,BOARDID,SHORTNAME,ISIN,REGNUMBER,FACEVALUE,FACEUNIT,"
    "PREVPRICE,COUPONVALUE,COUPONPERCENT,COUPONPERIOD,"
    "ACCRUEDINT,MATDATE,OFFERDATE,ISSUESIZE,LISTLEVEL,"
    "BONDTYPE,BONDSUBTYPE"
)
# YIELD и DURATION живут в marketdata, а не в securities
BOND_MARKETDATA_COLUMNS = "SECID,LAST,LASTBID,YIELD,YIELDATWAPRICE,DURATION,VALTODAY,NUMTRADES"

SHARE_SECURITY_COLUMNS = (
    "SECID,BOARDID,SHORTNAME,ISIN,REGNUMBER,PREVPRICE,LOTSIZE,ISSUESIZE,LISTLEVEL"
)
SHARE_MARKETDATA_COLUMNS = "SECID,LAST,VALTODAY,NUMTRADES"

# Основные режимы торгов: Т0 (основной) + Т+ (деальные), берём лучшую ликвидность
BOND_BOARDS = ("TQOB", "TQIR", "TQCB", "TQOD")  # ОФЗ, муниципальные, корпоративные, облигации Д
SHARE_BOARDS = ("TQBR",)


def _fetch_block(url: str, block: str, columns: str, params: dict | None = None) -> list[dict]:
    query = {"iss.meta": "off", "iss.only": block, f"{block}.columns": columns}
    if params:
        query.update(params)
    resp = httpx.get(url, params=query, timeout=settings.http_timeout)
    resp.raise_for_status()
    data = resp.json()[block]
    colnames = data["columns"]
    return [dict(zip(colnames, row)) for row in data["data"]]


class MoexClient:
    def __init__(self) -> None:
        self.base = settings.moex_base_url

    def get_bonds(self, board: str) -> list[dict]:
        url = f"{self.base}/engines/stock/markets/bonds/boards/{board}/securities.json"
        securities = _fetch_block(url, "securities", BOND_SECURITY_COLUMNS)
        marketdata = {
            r["SECID"]: r
            for r in _fetch_block(url, "marketdata", BOND_MARKETDATA_COLUMNS)
        }
        for row in securities:
            row.update({f"MD_{k}": v for k, v in marketdata.get(row["SECID"], {}).items()})
        return securities

    def get_shares(self, board: str) -> list[dict]:
        url = f"{self.base}/engines/stock/markets/shares/boards/{board}/securities.json"
        securities = _fetch_block(url, "securities", SHARE_SECURITY_COLUMNS)
        marketdata = {
            r["SECID"]: r
            for r in _fetch_block(url, "marketdata", SHARE_MARKETDATA_COLUMNS)
        }
        for row in securities:
            row.update({f"MD_{k}": v for k, v in marketdata.get(row["SECID"], {}).items()})
        return securities

    def get_dividends(self, secid: str) -> list[dict]:
        """Дивиденды по тикеру (источник: Smart-Lab, т.к. MOEX ISS их убрал)."""
        from .dividends import fetch_dividends

        return fetch_dividends(secid)

    def get_key_rate(self) -> float | None:
        """Ключевая ставка ЦБ: ставка стояния по 1-дневному прямому РЕПО (state/rates, блок fixed)."""
        url = f"{self.base}/statistics/engines/state/rates.json"
        try:
            rows = _fetch_block(url, "fixed", "DAYS,DIRECT_REPO_RATE,DIRECT_REPO_TRADEDATE")
        except Exception:
            return None
        for row in rows:
            if row.get("DAYS") == "1_DAY" and row.get("DIRECT_REPO_RATE"):
                return float(row["DIRECT_REPO_RATE"])
        return None
