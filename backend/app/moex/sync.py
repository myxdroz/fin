"""Синхронизация данных с MOEX ISS в локальную БД."""

import logging
import time
from datetime import date, datetime

from sqlalchemy import delete

from ..config import settings
from ..database import SessionLocal
from ..models import Bond, Dividend, Share
from .client import BOND_BOARDS, SHARE_BOARDS, MoexClient

log = logging.getLogger(__name__)


def _parse_date(value) -> date | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _num(value, default=0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def sync_bonds(client: MoexClient, db) -> int:
    """Тянем облигации со всех режимов, для каждого SECID берём самый ликвидный режим."""
    best: dict[str, dict] = {}
    for board in BOND_BOARDS:
        for row in client.get_bonds(board):
            secid = row["SECID"]
            if secid not in best or _num(row.get("MD_VALTODAY")) > _num(best[secid].get("MD_VALTODAY")):
                best[secid] = row

    db.execute(delete(Bond))
    for secid, r in best.items():
        reg = str(r.get("REGNUMBER") or "")
        bond_type = str(r.get("BONDTYPE") or "")
        bond_subtype = str(r.get("BONDSUBTYPE") or "")
        yield_ = _num(r.get("MD_YIELD"))
        if yield_ <= 0:
            yield_ = _num(r.get("MD_YIELDATWAPRICE"))
        db.add(Bond(
            secid=secid,
            shortname=str(r.get("SHORTNAME") or ""),
            isin=str(r.get("ISIN") or ""),
            regnumber=reg,
            face_value=_num(r.get("FACEVALUE")),
            face_unit=str(r.get("FACEUNIT") or "SUR"),
            prev_price=_num(r.get("PREVPRICE")),
            last_price=_num(r.get("MD_LAST") or r.get("MD_LASTBID") or r.get("PREVPRICE")),
            yield_at_pricing=yield_,
            duration=_num(r.get("MD_DURATION")),
            coupon_value=_num(r.get("COUPONVALUE")),
            coupon_percent=_num(r.get("COUPONPERCENT")),
            coupon_period=int(_num(r.get("COUPONPERIOD"))),
            accr_int=_num(r.get("ACCRUEDINT")),
            mat_date=_parse_date(r.get("MATDATE")),
            offer_date=_parse_date(r.get("OFFERDATE")),
            offer_flag=1 if bond_subtype.startswith("До оферты") else 0,
            amort_flag=1 if "Амортизируемая" in bond_type else 0,
            floating_flag=1 if "плавающим" in bond_type else 0,
            perpetual_flag=1 if bond_subtype == "Бессрочные" else 0,
            issue_size=_num(r.get("ISSUESIZE")),
            list_level=int(_num(r.get("LISTLEVEL"))),
            is_ofz=1 if str(r.get("SHORTNAME") or "").startswith("ОФЗ") else 0,
            val_today=_num(r.get("MD_VALTODAY")),
            num_trades=int(_num(r.get("MD_NUMTRADES"))),
        ))
    db.commit()
    return len(best)


def sync_shares(client: MoexClient, db) -> int:
    best: dict[str, dict] = {}
    for board in SHARE_BOARDS:
        for row in client.get_shares(board):
            secid = row["SECID"]
            if secid not in best or _num(row.get("MD_VALTODAY")) > _num(best[secid].get("MD_VALTODAY")):
                best[secid] = row

    db.execute(delete(Share))
    share_objs = []
    for secid, r in best.items():
        share_objs.append(Share(
            secid=secid,
            shortname=str(r.get("SHORTNAME") or ""),
            isin=str(r.get("ISIN") or ""),
            regnumber=str(r.get("REGNUMBER") or ""),
            prev_price=_num(r.get("PREVPRICE")),
            last_price=_num(r.get("MD_LAST") or r.get("PREVPRICE")),
            lot_size=int(_num(r.get("LOTSIZE"), 1)),
            issue_size=_num(r.get("ISSUESIZE")),
            list_level=int(_num(r.get("LISTLEVEL"))),
            val_today=_num(r.get("MD_VALTODAY")),
            num_trades=int(_num(r.get("MD_NUMTRADES"))),
        ))
    db.add_all(share_objs)
    db.commit()

    # Дивиденды: T-Invest API (официально), при отсутствии токена — Smart-Lab
    db.execute(delete(Dividend))
    targets = [s for s in share_objs if s.list_level == 1 and s.last_price > 0][:120]
    figi_map: dict[str, str] = {}
    tinvest = None
    if settings.tinvest_token:
        try:
            from .tinvest import TInvestDividends

            tinvest = TInvestDividends(settings.tinvest_token)
            figi_map = tinvest.shares_figi()
            log.info("T-Invest: figi получены для %d акций", len(figi_map))
        except Exception:
            log.exception("T-Invest API недоступен, откатываемся на Smart-Lab")
            tinvest = None

    log.info("Fetching dividends for %d shares...", len(targets))
    ok = 0
    for share in targets:
        try:
            figi = figi_map.get(share.secid)
            if tinvest and figi:
                rows = tinvest.dividends(figi)
                time.sleep(0.15)
            else:
                rows = client.get_dividends(share.secid)
                time.sleep(0.25)  # не ддосим smart-lab
        except Exception:
            log.warning("Dividends fetch failed for %s", share.secid)
            continue
        ok += 1
        for d in rows:
            db.add(Dividend(
                secid=share.secid,
                ex_date=d["ex_date"],
                value=d["value"],
                currency=d.get("currency", "SUR"),
            ))
    db.commit()
    if tinvest:
        tinvest.close()
    log.info("Dividends fetched for %d/%d shares", ok, len(targets))
    return len(best)


def sync_all() -> dict:
    client = MoexClient()
    db = SessionLocal()
    try:
        bonds = sync_bonds(client, db)
        shares = sync_shares(client, db)
        key_rate = client.get_key_rate()
        if key_rate:
            settings.key_rate = key_rate
        log.info("Sync done: %d bonds, %d shares, key_rate=%s", bonds, shares, key_rate)
        return {"bonds": bonds, "shares": shares, "key_rate": key_rate}
    finally:
        db.close()
