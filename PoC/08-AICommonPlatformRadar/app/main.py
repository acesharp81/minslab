from __future__ import annotations

import asyncio
import base64
import json
import logging
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select

from .config import get_settings
from .db import SessionLocal, init_db
from .logging_config import configure_logging
from .models import AuditLog, Notice, PipelineRun
from .routers import actions, collector, dashboard, extension_install, health, notices, reports, settings as settings_router
from .services.collector import run_collection
from .services.batch_lock import BatchAlreadyRunning
from .services.supabase_store import get_supabase_store
from .services.runtime_settings import verify_admin_session
from .services.opinion_tracker import refresh_tracked_opinions_cached


settings = get_settings()
logger = logging.getLogger(__name__)


async def _refresh_opinion_tracking_loop() -> None:
    """Refresh reply badges centrally instead of on every dashboard visit."""
    await asyncio.sleep(30)
    while True:
        try:
            with SessionLocal() as db:
                await refresh_tracked_opinions_cached(
                    db, min_interval=timedelta(minutes=10),
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Scheduled pre-notice opinion refresh failed")
        await asyncio.sleep(15 * 60)


def format_number(value) -> str:
    """Render dashboard numbers with thousands separators without changing API values."""
    try:
        number = float(value)
        if number.is_integer():
            return f"{int(number):,}"
        return f"{number:,.1f}"
    except (TypeError, ValueError):
        return str(value)


def _authorized(request: Request) -> bool:
    if verify_admin_session(request.cookies.get("poc08_admin_session", "")):
        return True
    supplied_proxy_token = request.headers.get("x-poc08-proxy-token", "")
    if settings.proxy_token and supplied_proxy_token and secrets.compare_digest(
        supplied_proxy_token, settings.proxy_token,
    ):
        return True
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
    local_notice_count = 0
    with SessionLocal() as db:
        interrupted = db.scalars(select(PipelineRun).where(PipelineRun.status == "running")).all()
        if interrupted:
            now = datetime.now(timezone.utc)
            for run in interrupted:
                run.status = "failed"
                run.finished_at = now
                run.error_message = "서비스 재시작으로 실행이 중단되었습니다. 다음 조건부 배치에서 재시도합니다."
                db.add(AuditLog(
                    event_type="pipeline_interrupted", entity_type="pipeline_run", entity_id=str(run.id),
                    detail_json=json.dumps({"reason": "service_restart"}, ensure_ascii=False),
                ))
            db.commit()
        # Prime the append-only dashboard classification projection once at
        # startup so the first operator request does not parse run history.
        notices.current_classification_notice_ids(db)
        local_notice_count = int(db.scalar(select(func.count(Notice.id))) or 0)
    statistics_prewarm_task = None
    if settings.g2b_mode == "live":
        # Make the default statistics page hot before accepting user traffic.
        # Less common ranges are prepared in the background.
        reports.prewarm_statistics(("30d",))
        statistics_prewarm_task = asyncio.create_task(asyncio.to_thread(
            reports.prewarm_statistics, ("month", "year", "all"),
        ))
        app.state.statistics_prewarm_task = statistics_prewarm_task
    reconcile_task = None
    opinion_refresh_task = asyncio.create_task(_refresh_opinion_tracking_loop())
    app.state.opinion_refresh_task = opinion_refresh_task
    if settings.supabase_enabled and local_notice_count == 0:
        def reconcile_cache() -> None:
            with SessionLocal() as db:
                get_supabase_store().reconcile(db)

        # Restore only an empty local cache. Normal commits and collection
        # batches already push their deltas, so a full merge on every restart
        # only competes with PoC7 for memory and disk bandwidth.
        reconcile_task = asyncio.create_task(asyncio.to_thread(reconcile_cache))
        app.state.supabase_reconcile_task = reconcile_task
    if settings.auto_seed_sample and settings.g2b_mode == "mock":
        with SessionLocal() as db:
            if (db.scalar(select(func.count(Notice.id))) or 0) == 0:
                await run_collection(db, settings.collect_lookback_days, analyze=True)
    yield
    if not opinion_refresh_task.done():
        opinion_refresh_task.cancel()
    await asyncio.gather(opinion_refresh_task, return_exceptions=True)
    if reconcile_task and not reconcile_task.done():
        reconcile_task.cancel()
    if statistics_prewarm_task and not statistics_prewarm_task.done():
        statistics_prewarm_task.cancel()


app = FastAPI(
    title="조달췤! | 범정부 AI 공통기반 edition",
    version="0.1.0",
    description="나라장터 공고를 AI 서비스 사업과 비AI 서비스 사업으로 분류하고 범정부 AI 공통기반 활용 여부까지 점검하는 서비스",
    lifespan=lifespan,
)
app.state.templates = Jinja2Templates(directory=str(settings.project_root / "app" / "templates"))
app.state.templates.env.filters["number"] = format_number
app.mount("/static", StaticFiles(directory=str(settings.project_root / "app" / "static")), name="static")


@app.middleware("http")
async def authentication(request: Request, call_next):
    forwarded_prefix = request.headers.get("x-forwarded-prefix", "").rstrip("/")
    if forwarded_prefix == "/poc/ai-common-platform-radar":
        request.scope["app_root_path"] = forwarded_prefix
    route_path = request.scope.get("path", "")
    if (
        request.method.upper() in {"GET", "HEAD", "OPTIONS"}
        or route_path in {"/health", "/settings/login"}
        or route_path.startswith("/static/")
        or not settings.auth_enabled
    ):
        return await call_next(request)
    if not _authorized(request):
        return Response("인증이 필요합니다.", status_code=401, headers={"WWW-Authenticate": 'Basic realm="AI Common Platform Radar"'})
    return await call_next(request)


@app.exception_handler(RuntimeError)
async def runtime_error(_request: Request, exc: RuntimeError):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.exception_handler(BatchAlreadyRunning)
async def batch_already_running(_request: Request, exc: BatchAlreadyRunning):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


for router in (health.router, dashboard.router, notices.router, reports.router, collector.router, actions.router, settings_router.router, extension_install.router):
    app.include_router(router)
