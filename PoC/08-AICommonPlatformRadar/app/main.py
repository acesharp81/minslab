from __future__ import annotations

import asyncio
import base64
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select

from .config import get_settings
from .db import SessionLocal, init_db
from .logging_config import configure_logging
from .models import Notice
from .routers import actions, collector, dashboard, health, notices, reports
from .services.collector import run_collection
from .services.supabase_store import get_supabase_store


settings = get_settings()


def _authorized(request: Request) -> bool:
    if not settings.auth_enabled:
        return True
    authorization = request.headers.get("authorization", "")
    if settings.admin_token and authorization.startswith("Bearer "):
        return secrets.compare_digest(authorization[7:], settings.admin_token)
    if settings.admin_username and settings.admin_password and authorization.startswith("Basic "):
        try:
            decoded = base64.b64decode(authorization[6:], validate=True).decode("utf-8")
            username, password = decoded.split(":", 1)
            return secrets.compare_digest(username, settings.admin_username) and secrets.compare_digest(password, settings.admin_password)
        except (ValueError, UnicodeDecodeError):
            return False
    return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.ensure_directories()
    configure_logging()
    init_db()
    if settings.supabase_enabled:
        with SessionLocal() as db:
            get_supabase_store().reconcile(db)
    if settings.auto_seed_sample and settings.g2b_mode == "mock":
        with SessionLocal() as db:
            if (db.scalar(select(func.count(Notice.id))) or 0) == 0:
                await run_collection(db, settings.collect_lookback_days, analyze=True)
    yield


app = FastAPI(
    title="나라장터 AI 공통기반 활용 적합도 레이더",
    version="0.1.0",
    description="공개 조달자료에 대한 근거 기반 후보 선별 PoC",
    lifespan=lifespan,
)
app.state.templates = Jinja2Templates(directory=str(settings.project_root / "app" / "templates"))
app.mount("/static", StaticFiles(directory=str(settings.project_root / "app" / "static")), name="static")


@app.middleware("http")
async def authentication(request: Request, call_next):
    if request.url.path == "/health" or request.url.path.startswith("/static/") or not settings.auth_enabled:
        return await call_next(request)
    if not _authorized(request):
        return Response("인증이 필요합니다.", status_code=401, headers={"WWW-Authenticate": 'Basic realm="AI Common Platform Radar"'})
    return await call_next(request)


@app.exception_handler(RuntimeError)
async def runtime_error(_request: Request, exc: RuntimeError):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


for router in (health.router, dashboard.router, notices.router, reports.router, collector.router, actions.router):
    app.include_router(router)
