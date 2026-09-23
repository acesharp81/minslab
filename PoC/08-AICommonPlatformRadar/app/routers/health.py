from fastapi import APIRouter
from sqlalchemy import func, select, text

from ..config import get_settings
from ..db import SessionLocal, engine
from ..models import AnalysisRun, PipelineRun
from ..services.jev_shadow import jev_shadow_state
from ..services.report_builder import _batch_data
from ..services.supabase_store import get_supabase_store


router = APIRouter()


@router.get("/health")
def health() -> dict:
    settings = get_settings()
    database = "ok"
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        database = "error"
    problems = settings.validate_runtime()
    supabase = "disabled"
    if settings.supabase_enabled:
        supabase = "ok" if get_supabase_store().health() else "error"
    try:
        with SessionLocal() as db:
            latest_batch = _batch_data(db.scalar(
                select(PipelineRun).where(PipelineRun.run_kind == "collect").order_by(PipelineRun.started_at.desc())
            ))
            jev_records = dict(db.execute(select(
                AnalysisRun.status,
                func.count(AnalysisRun.id),
            ).where(
                AnalysisRun.run_type == "jev_shadow",
            ).group_by(AnalysisRun.status)).all())
    except Exception as exc:
        latest_batch = {"state": "unknown", "label": "조회 실패", "error": str(exc)[:300]}
        jev_records = {}
    return {
        "status": "ok" if database == "ok" and supabase != "error" and not problems else "degraded",
        "database": database,
        "database_backend": settings.database_backend,
        "supabase_rest": supabase,
        "g2b_mode": settings.g2b_mode,
        "llm": {
            "stage2": {
                "provider": settings.stage2_provider,
                "model": settings.stage2_model,
                "credential_ready": settings.stage2_provider == "mock" or bool(settings.stage2_api_key),
            },
            "stage2_fallback": {
                "provider": settings.stage2_fallback_provider,
                "model": settings.stage2_fallback_model,
                "credential_ready": settings.stage2_fallback_provider == "mock" or bool(settings.stage2_fallback_api_key),
            },
            "jev_shadow": {
                "enabled": settings.jev_shadow_enabled,
                "mode": "record_only",
                "provider": "jevai",
                "model": settings.jev_model,
                "api_base_url": settings.jev_base_url,
                "status": jev_shadow_state(settings),
                "valid_until": settings.jev_shadow_end_date,
                "credential_ready": bool(settings.jev_api_key),
                "records_success": int(jev_records.get("success", 0)),
                "records_failed": int(jev_records.get("failed", 0)),
            },
            "stage3_primary": {
                "provider": settings.stage3_primary_provider,
                "model": settings.stage3_primary_model,
                "credential_ready": settings.stage3_primary_provider == "mock" or bool(settings.stage3_primary_api_key),
            },
            "stage3_fallback": {
                "provider": settings.stage3_fallback_provider,
                "model": settings.stage3_fallback_model,
                "credential_ready": settings.stage3_fallback_provider == "mock" or bool(settings.stage3_fallback_api_key),
            },
            "stage3_routing_mode": settings.stage3_routing_mode,
            "daily_deep_limit": settings.stage3_daily_limit,
        },
        "configuration_problems": problems,
        "schedule": {
            "timezone": settings.app_timezone,
            "primary": "03:10",
            "retry": "04:35",
            "report": "06:20",
            "midday": "12:00",
            "midday_retry": "12:40",
            "collection_deadline": "13:00",
        },
        "latest_batch": latest_batch,
    }
