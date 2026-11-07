from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..moex.sync import sync_all
from ..screener.filters import BondFilter, ShareFilter, screen_bonds, screen_shares
from ..screener.portfolio import PROFILES, PortfolioRequest, build_portfolio

router = APIRouter(prefix="/api")


@router.get("/health")
def health():
    return {"status": "ok", "key_rate": settings.key_rate}


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
