"""Telegram-уведомления: высокодоходные облигации и выбывшие из индекса акции."""

import logging
from datetime import date

import httpx
from sqlalchemy import select

from .config import settings
from .models import Bond, IndexWeight

log = logging.getLogger(__name__)


def send_message(text: str) -> bool:
    if not settings.telegram_token or not settings.telegram_chat:
        return False
    url = f"https://api.telegram.org/bot{settings.telegram_token}/sendMessage"
    try:
        resp = httpx.post(url, json={
            "chat_id": settings.telegram_chat,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }, timeout=15)
        resp.raise_for_status()
        return True
    except Exception:
        log.exception("Telegram send failed")
        return False


def maybe_notify(db) -> None:
    """Вызывается после синхронизации. Шлёт сообщение, если есть что сообщить."""
    if not settings.telegram_token or not settings.telegram_chat:
        return
    parts = []

    # 1. облигации с аномально высокой доходностью (ставка + порог)
    rows = db.scalars(select(Bond).where(
        Bond.yield_at_pricing >= settings.key_rate + settings.notify_bond_premium,
        Bond.yield_at_pricing <= settings.key_rate + 45,
        Bond.val_today >= 5_000_000,
        Bond.list_level <= 2,
        Bond.floating_flag == 0,
    )).all()
    if rows:
        rows = sorted(rows, key=lambda b: -b.yield_at_pricing)[:5]
        lines = "\n".join(
            f"• {b.shortname} ({b.secid}): <b>{b.yield_at_pricing:.1f}%</b>, "
            f"дюрация {b.duration / 365:.1f} г."
            for b in rows
        )
        parts.append(
            f"📈 Облигации с доходностью ≥ {settings.key_rate + settings.notify_bond_premium:.0f}% "
            f"(ставка {settings.key_rate:.0f}% + {settings.notify_bond_premium:.0f} п.п.):\n{lines}"
        )

    # 2. акции из вашего портфеля, выбывшие из IMOEX (нужен токен T-Invest)
    if settings.tinvest_token:
        try:
            from .moex.tinvest import TInvestDividends

            t = TInvestDividends(settings.tinvest_token)
            try:
                accounts = t.accounts()
                pf = t.portfolio(accounts[0]["id"]) if accounts else {"positions": []}
                figi_map = t.instruments_by_figi()
            finally:
                t.close()
            index_members = {w.secid for w in db.scalars(select(IndexWeight)).all()}
            exited = []
            for p in pf.get("positions", []):
                if p["type"] != "share":
                    continue
                ticker = figi_map.get(p["figi"], {}).get("ticker", "")
                if ticker and ticker not in index_members:
                    exited.append(ticker)
            if exited:
                parts.append(
                    "⚠️ Эти акции есть у вас в портфеле, но вышли из состава IMOEX:\n"
                    + "\n".join(f"• {x}" for x in exited)
                    + "\nПроверьте вкладку «Мой портфель» → Ребалансировка."
                )
        except Exception:
            log.exception("Index-exit check failed")

    # 3. watchlist: купоны/оферты/дивиденды ближайшие две недели + падение цены
    from ..models import Share, Watchlist

    watched = db.scalars(select(Watchlist)).all()
    if watched:
        today = date.today()
        wl_lines = []
        try:
            from .moex.tinvest import TInvestDividends
            import time as _time

            t = TInvestDividends(settings.tinvest_token)
            try:
                figi_map = t.shares_figi()          # ticker -> figi для акций
                ticker_figi = t.figi_by_ticker()    # ticker(=ISIN) -> figi для всех
                for w in watched:
                    bond = db.get(Bond, w.secid)
                    if bond:
                        if bond.offer_date and 0 <= (bond.offer_date - today).days <= 21:
                            wl_lines.append(
                                f"• {bond.shortname}: оферта {bond.offer_date} "
                                f"(через {(bond.offer_date - today).days} дн.)")
                        if w.added_price and bond.last_price < w.added_price * 0.93:
                            drop = (bond.last_price / w.added_price - 1) * 100
                            wl_lines.append(f"• {bond.shortname}: падение {drop:.1f}% от цены добавления")
                        # купоны ближайшие 14 дней (тикер облигации = ISIN)
                        figi = ticker_figi.get(w.secid)
                        if figi:
                            try:
                                for c in t.bond_coupons(figi, 14):
                                    wl_lines.append(f"• {bond.shortname}: купон {c['value']} ₽ {c['date']}")
                            except Exception:
                                pass
                        continue
                    figi = figi_map.get(w.secid)
                    if not figi:
                        continue
                    try:
                        for d in t.dividends_future(figi, 14):
                            wl_lines.append(
                                f"• {w.secid}: дивидендная отсечка {d['ex_date']}, {d['value']} ₽/акцию")
                        share = db.get(Share, w.secid)
                        if w.added_price and share and share.last_price < w.added_price * 0.93:
                            drop = (share.last_price / w.added_price - 1) * 100
                            wl_lines.append(f"• {w.secid}: падение {drop:.1f}% от цены добавления")
                    except Exception:
                        pass
                    _time.sleep(0.12)
            finally:
                t.close()
        except Exception:
            log.exception("Watchlist check failed")
        if wl_lines:
            parts.append("👀 Watchlist:\n" + "\n".join(wl_lines[:15]))

    if parts:
        send_message("\n\n".join(parts))
