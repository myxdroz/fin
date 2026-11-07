"""История дивидендов со Smart-Lab (MOEX ISS больше не отдаёт дивиденды).

Парсим таблицу «Выплаченные дивиденды» со страницы /q/{ticker}/dividend/.
Возвращает список dict: ex_date (date), value (float, руб на акцию).
"""

import logging
import re
from datetime import date, datetime

import httpx

log = logging.getLogger(__name__)

TABLE_RE = re.compile(
    r'<table class="simple-little-table financials dividends sort-table".*?</table>', re.S
)
ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
CELL_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
TAG_RE = re.compile(r"<[^>]+>")


def _parse_rows(html: str) -> list[dict]:
    m = TABLE_RE.search(html)
    if not m:
        return []
    result = []
    for row in ROW_RE.findall(m.group(0)):
        cells = [TAG_RE.sub("", c).strip() for c in CELL_RE.findall(row)]
        if len(cells) < 5:
            continue
        try:
            ex_date = datetime.strptime(cells[1], "%d.%m.%Y").date()
        except ValueError:
            continue
        raw = cells[4].replace("₽", "").replace("руб", "").replace("\xa0", "").replace(" ", "").replace(",", ".")
        try:
            value = float(raw)
        except ValueError:
            continue
        result.append({"ex_date": ex_date, "value": value})
    return result


def fetch_dividends(ticker: str, timeout: float = 15.0) -> list[dict]:
    url = f"https://smart-lab.ru/q/{ticker}/dividend/"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; fin-strategy/1.0)"}
    resp = httpx.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return _parse_rows(resp.text)
