from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..moex.sync import sync_all
from ..screener.filters import BondFilter, ShareFilter, screen_bonds, screen_shares
from ..screener.portfolio import PROFILES, PortfolioRequest, build_portfolio

router = APIRouter(prefix="/api")


@router.get("/health")
def health():
    import os
    return {"status": "ok", "key_rate": settings.key_rate,
            "version": os.environ.get("APP_VERSION", "dev")}


@router.post("/sync")
def trigger_sync():
    return sync_all()


@router.get("/profiles")
def profiles():
    return {
        name: {"label": p["label"], "description": p["description"]}
        for name, p in PROFILES.items()
    }


@router.post("/bonds")
def bonds(f: BondFilter, db: Session = Depends(get_db)):
    return {"count": None, "items": screen_bonds(db, f), "key_rate": settings.key_rate}


@router.post("/shares")
def shares(f: ShareFilter, db: Session = Depends(get_db)):
    return {"items": screen_shares(db, f)}


@router.post("/portfolio")
def portfolio(req: PortfolioRequest, db: Session = Depends(get_db)):
    return build_portfolio(db, req)


@router.get("/index/imoex")
def index_imoex(db: Session = Depends(get_db)):
    """Актуальный состав индекса IMOEX с весами (обновляется при синхронизации)."""
    from ..models import IndexWeight
    from sqlalchemy import select

    rows = db.scalars(select(IndexWeight)).all()
    items = [
        {"secid": w.secid, "shortname": w.shortname,
         "weight": round(w.weight, 2), "tradedate": w.tradedate.isoformat() if w.tradedate else None}
        for w in sorted(rows, key=lambda x: -x.weight)
    ]
    return {"index": "IMOEX", "count": len(items), "items": items}


# --- watchlist ---

class WatchItemIn(BaseModel):
    secid: str
    price: float = 0.0


@router.get("/watchlist")
def watchlist_get(db: Session = Depends(get_db)):
    from ..models import Watchlist
    from sqlalchemy import select

    rows = db.scalars(select(Watchlist)).all()
    return {"items": [{"secid": w.secid, "price": w.added_price,
                       "added_at": w.created_at.isoformat() if w.created_at else None}
                      for w in rows]}


@router.put("/watchlist")
def watchlist_add(item: WatchItemIn, db: Session = Depends(get_db)):
    from ..models import Watchlist

    if not db.get(Watchlist, item.secid):
        db.add(Watchlist(secid=item.secid, added_price=item.price))
        db.commit()
    return {"added": item.secid}


@router.delete("/watchlist/{secid}")
def watchlist_remove(secid: str, db: Session = Depends(get_db)):
    from ..models import Watchlist

    row = db.get(Watchlist, secid)
    if row:
        db.delete(row)
        db.commit()
    return {"removed": secid}


@router.post("/watchlist/check")
def watchlist_check(db: Session = Depends(get_db)):
    """Сравнение watchlist с текущими котировками (для ручной проверки и алертов)."""
    from ..models import Share, Bond, Watchlist

    rows = db.scalars(select(Watchlist)).all()
    out = []
    for w in rows:
        bond = db.get(Bond, w.secid)
        share = None if bond else db.get(Share, w.secid)
        cur = bond.last_price if bond else (share.last_price if share else 0)
        out.append({
            "secid": w.secid,
            "added_price": w.added_price,
            "current_price": round(cur, 2),
            "change_pct": round((cur / w.added_price - 1) * 100, 1) if w.added_price else None,
        })
    return {"items": out}
