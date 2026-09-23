from __future__ import annotations

import ctypes
from datetime import date
import gc
import logging
from pathlib import Path
from threading import Lock, Thread

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import SessionLocal, get_db
from ..models import ActionItem, AnalysisRun, Attachment, AuditLog, Notice
from ..schemas import ReportRequest
from ..services.report_builder import build_daily_report, get_daily_report
from ..services.statistics_builder import build_statistics


router = APIRouter()
logger = logging.getLogger(__name__)
_statistics_cache: dict[str, tuple[tuple, dict]] = {}
_statistics_cache_lock = Lock()
_statistics_refreshing: set[str] = set()


def _release_statistics_memory() -> None:
    """Return short-lived ORM graphs after an aggregate snapshot is built."""
    gc.collect()
    try:
        malloc_trim = ctypes.CDLL(None).malloc_trim
        malloc_trim.argtypes = [ctypes.c_size_t]
        malloc_trim.restype = ctypes.c_int
        malloc_trim(0)
    except (AttributeError, OSError):
        pass


def _statistics_source_version(db: Session) -> tuple:
    """Return only source versions that can change the statistics output."""
    return db.execute(select(
        select(func.max(Notice.updated_at)).scalar_subquery(),
        select(func.max(AnalysisRun.id)).scalar_subquery(),
        select(func.max(Attachment.updated_at)).scalar_subquery(),
        select(func.max(ActionItem.updated_at)).scalar_subquery(),
        select(func.max(AuditLog.id))
        .where(AuditLog.event_type == "action_updated")
        .scalar_subquery(),
    )).one()


def _store_statistics(period: str, version: tuple, result: dict) -> dict:
    with _statistics_cache_lock:
        _statistics_cache[period] = (version, result)
    return result


def _refresh_statistics(period: str) -> None:
    try:
        with SessionLocal() as db:
            result = build_statistics(db, period=period)
            version = _statistics_source_version(db)
        _store_statistics(period, version, result)
    except Exception:
        logger.exception("PoC08 statistics cache refresh failed", extra={"period": period})
    finally:
        _release_statistics_memory()
        with _statistics_cache_lock:
            _statistics_refreshing.discard(period)


def _schedule_statistics_refresh(period: str) -> None:
    with _statistics_cache_lock:
        if period in _statistics_refreshing:
            return
        _statistics_refreshing.add(period)
    Thread(
        target=_refresh_statistics,
        args=(period,),
        name=f"poc08-statistics-{period}",
        daemon=True,
    ).start()


def prewarm_statistics(periods: tuple[str, ...] = ("30d",)) -> None:
    """Build snapshots before users open the statistics page."""
    for period in periods:
        with SessionLocal() as db:
            result = build_statistics(db, period=period)
            version = _statistics_source_version(db)
        _store_statistics(period, version, result)
        _release_statistics_memory()


def _cached_statistics(db: Session, period: str) -> dict:
    """Serve a snapshot immediately and refresh changed data off-request."""
    period = period if period in {"30d", "month", "year", "all"} else "30d"
    version = _statistics_source_version(db)
    with _statistics_cache_lock:
        cached = _statistics_cache.get(period)
    if cached is not None:
        cached_version, result = cached
        if cached_version != version:
            _schedule_statistics_refresh(period)
        return result
    result = build_statistics(db, period=period)
    return _store_statistics(period, _statistics_source_version(db), result)


@router.get("/reports/daily", response_class=HTMLResponse)
def report_page(
    request: Request, report_date: date | None = None, period: str = "30d",
    db: Session = Depends(get_db),
):
    return request.app.state.templates.TemplateResponse(
        request, "daily_report.html", {"stats": _cached_statistics(db, period)},
    )


@router.get("/api/statistics")
def statistics_api(period: str = "30d", db: Session = Depends(get_db)):
    return _cached_statistics(db, period)


@router.get("/api/reports/daily")
def report_api(report_date: date | None = None, db: Session = Depends(get_db)):
    artifact = get_daily_report(db, report_date)
    return artifact.as_dict(include_markdown=True)


@router.post("/api/reports/daily/generate")
def generate_report(payload: ReportRequest, db: Session = Depends(get_db)):
    artifact = build_daily_report(db, payload.report_date, finalized=True)
    return artifact.as_dict()


@router.get("/api/reports/daily/download/{report_date}/{format_name}")
def download_report(report_date: date, format_name: str, db: Session = Depends(get_db)):
    if format_name not in {"md", "html", "json"}:
        raise HTTPException(400, "md, html 또는 json만 지원합니다.")
    artifact = get_daily_report(db, report_date)
    paths = {"md": artifact.markdown_path, "html": artifact.html_path, "json": artifact.json_path}
    media_types = {"md": "text/markdown", "html": "text/html", "json": "application/json"}
    path = paths[format_name]
    media = media_types[format_name]
    return FileResponse(path, media_type=media, filename=Path(path).name)
