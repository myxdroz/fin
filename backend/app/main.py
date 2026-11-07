import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .database import init_db
from .moex.sync import sync_all
from .routers import api, myportfolio

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)


def _initial_sync():
    try:
        sync_all()
    except Exception:
        log.exception("Initial MOEX sync failed; app will serve stale/empty data until next sync")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    if settings.sync_on_startup:
        _initial_sync()
    scheduler = None
    if settings.scheduler_enabled:
        scheduler = BackgroundScheduler()
        scheduler.add_job(
            sync_all,
            CronTrigger(hour=settings.sync_hour_utc, minute=settings.sync_minute_utc),
        )
        scheduler.start()
    yield
    if scheduler:
        scheduler.shutdown()


app = FastAPI(title="Fin Strategy", lifespan=lifespan)
app.include_router(api.router)
app.include_router(myportfolio.router)
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/", response_class=HTMLResponse)
def index():
    with open("app/templates/index.html", encoding="utf-8") as f:
        return f.read()
