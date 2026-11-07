"""Клиент MOEX ISS API: https://www.moex.com/a2193 """

from datetime import date, timedelta

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

# Итоги последнего торгового дня — запасной вариант, когда marketdata пуст (выходные)
HISTORY_BOND_COLUMNS = "SECID,CLOSE,VALUE,NUMTRADES,YIELD,DURATION"
HISTORY_SHARE_COLUMNS = "SECID,CLOSE,VALUE,NUMTRADES"


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

    def _history_latest(self, market: str, board: str, columns: str) -> dict[str, dict]:
        """Итоги последнего торгового дня: идём назад до 5 дней, пока не найдём данные."""
        url = f"{self.base}/history/engines/stock/markets/{market}/boards/{board}/securities.json"
        for back in range(1, 6):
            day = (date.today() - timedelta(days=back)).isoformat()
            result: dict[str, dict] = {}
            start = 0
            while True:
                rows = _fetch_block(url, "history", columns, {"date": day, "start": start})
                if not rows:
                    break
                for r in rows:
                    result[r["SECID"]] = r
                if len(rows) < 100:
                    break
                start += 100
            if result:
                return result
        return {}

    def _merge_marketdata(self, url: str, market: str, board: str,
                          sec_cols: str, md_cols: str, hist_cols: str) -> list[dict]:
        securities = _fetch_block(url, "securities", sec_cols)
        marketdata = {
            r["SECID"]: r
            for r in _fetch_block(url, "marketdata", md_cols)
        }
        for row in securities:
            row.update({f"MD_{k}": v for k, v in marketdata.get(row["SECID"], {}).items()})
        # В выходные marketdata пуст — подставляем итоги последнего торгового дня
        if not any(r.get("MD_VALTODAY") for r in securities):
            hist = self._history_latest(market, board, hist_cols)
            for row in securities:
                h = hist.get(row["SECID"])
                if h:
                    row.update({f"H_{k}": v for k, v in h.items()})
        return securities

    def get_bonds(self, board: str) -> list[dict]:
        url = f"{self.base}/engines/stock/markets/bonds/boards/{board}/securities.json"
        return self._merge_marketdata(url, "bonds", board,
                                      BOND_SECURITY_COLUMNS, BOND_MARKETDATA_COLUMNS,
                                      HISTORY_BOND_COLUMNS)

    def get_shares(self, board: str) -> list[dict]:
        url = f"{self.base}/engines/stock/markets/shares/boards/{board}/securities.json"
        return self._merge_marketdata(url, "shares", board,
                                      SHARE_SECURITY_COLUMNS, SHARE_MARKETDATA_COLUMNS,
                                      HISTORY_SHARE_COLUMNS)

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
