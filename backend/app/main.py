import base64
import logging
import secrets
import threading
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from .config import settings
from .database import init_db
from .moex.sync import sync_all
from .routers import api, goals, myportfolio, strategy

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
        # синхронизация в фоне: сервер начинает отвечать сразу,
        # данные подтягиваются за 3–4 минуты
        threading.Thread(target=_initial_sync, daemon=True).start()
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
app.include_router(goals.router)
app.include_router(strategy.router)
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.middleware("http")
async def basic_auth(request: Request, call_next):
    """Basic auth для всего сервиса, кроме /api/health. Пустые логин/пароль = выключено."""
    if not (settings.auth_login and settings.auth_password):
        return await call_next(request)
    if request.url.path == "/api/health":
        return await call_next(request)
    ok = False
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Basic "):
        try:
            login, pwd = base64.b64decode(auth[6:]).decode("utf-8").split(":", 1)
            ok = (secrets.compare_digest(login, settings.auth_login)
                  and secrets.compare_digest(pwd, settings.auth_password))
        except Exception:
            ok = False
    if not ok:
        return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="fin"'})
    return await call_next(request)


@app.middleware("http")
async def no_cache_frontend(request, call_next):
    """Не кешировать фронтенд — чтобы обновления доезжали без Ctrl+F5."""
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static"):
        response.headers["Cache-Control"] = "no-cache"
    return response


@app.get("/", response_class=HTMLResponse)
def index():
    with open("app/templates/index.html", encoding="utf-8") as f:
        return f.read()
