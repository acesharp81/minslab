from __future__ import annotations

import asyncio
import json
import logging
import threading
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import SessionLocal, get_db
from ..models import AuditLog, PipelineRun
from ..services.collector import reparse_failed, run_collection
from ..services.report_builder import _batch_data


router = APIRouter()
logger = logging.getLogger(__name__)
_manual_job_guard = threading.Lock()
_reparse_job_guard = threading.Lock()


def _run_in_background(lookback_days: int | None, analyze: bool) -> None:
    try:
        with SessionLocal() as db:
            asyncio.run(run_collection(db, lookback_days, analyze=analyze))
    except Exception:
        logger.exception("수동 수집·후보판정 백그라운드 작업 실패")
    finally:
        _manual_job_guard.release()


def _run_reparse_in_background() -> None:
    try:
        with SessionLocal() as db:
            run = PipelineRun(run_kind="reparse", mode="maintenance", status="running")
            db.add(run)
            db.commit()
            run_id = run.id
            try:
                stats = reparse_failed(db)
                run.status = "success"
                run.stats_json = json.dumps(stats, ensure_ascii=False)
                run.finished_at = datetime.now(timezone.utc)
                db.add(AuditLog(
                    event_type="reparse_job_finished", entity_type="pipeline_run", entity_id=str(run.id),
                    detail_json=run.stats_json,
                ))
                db.commit()
            except Exception as exc:
                db.rollback()
                run = db.get(PipelineRun, run_id)
                if run:
                    run.status = "failed"
                    run.error_message = f"{type(exc).__name__}: {str(exc)[:1000]}"
                    run.finished_at = datetime.now(timezone.utc)
                    db.commit()
                logger.exception("문서 오류 재처리 작업 실패")
    except Exception:
        logger.exception("문서 오류 재처리 작업을 시작하지 못했습니다.")
    finally:
        _reparse_job_guard.release()


@router.post("/api/collect/run", status_code=202)
def collect_run(
    background_tasks: BackgroundTasks,
    lookback_days: int | None = Query(default=None, ge=1, le=31),
    analyze: bool = True,
    db: Session = Depends(get_db),
):
    if not _manual_job_guard.acquire(blocking=False):
        raise HTTPException(409, "수동 수집·후보판정 작업이 이미 실행 중입니다.")
    previous = db.scalar(select(PipelineRun).order_by(PipelineRun.id.desc()))
    background_tasks.add_task(_run_in_background, lookback_days, analyze)
    return {
        "status": "accepted",
        "message": "수집·후보판정을 백그라운드에서 시작했습니다.",
        "previous_run_id": previous.id if previous else None,
    }


@router.get("/api/collect/status")
def collect_status(db: Session = Depends(get_db)):
    latest = db.scalar(select(PipelineRun).where(PipelineRun.run_kind == "collect").order_by(PipelineRun.id.desc()))
    return _batch_data(latest)


@router.post("/api/maintenance/reparse", status_code=202)
def maintenance_reparse(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    if not _reparse_job_guard.acquire(blocking=False):
        raise HTTPException(409, "문서 오류 재처리 작업이 이미 실행 중입니다.")
    previous = db.scalar(select(PipelineRun).where(
        PipelineRun.run_kind == "reparse"
    ).order_by(PipelineRun.id.desc()))
    background_tasks.add_task(_run_reparse_in_background)
    return {
        "status": "accepted", "message": "문서 오류 재처리를 시작했습니다.",
        "previous_run_id": previous.id if previous else None,
    }


@router.get("/api/maintenance/reparse/status")
def maintenance_reparse_status(db: Session = Depends(get_db)):
    run = db.scalar(select(PipelineRun).where(
        PipelineRun.run_kind == "reparse"
    ).order_by(PipelineRun.id.desc()))
    if not run:
        return {"id": None, "state": "missing", "stats": {}, "error": None}
    try:
        stats = json.loads(run.stats_json or "{}")
    except json.JSONDecodeError:
        stats = {}
    return {"id": run.id, "state": run.status, "stats": stats, "error": run.error_message}
