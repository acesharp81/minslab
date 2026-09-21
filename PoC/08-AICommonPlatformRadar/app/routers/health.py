from fastapi import APIRouter
from sqlalchemy import select, text

from ..config import get_settings
from ..db import SessionLocal, engine
from ..models import PipelineRun
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
    except Exception as exc:
        latest_batch = {"state": "unknown", "label": "조회 실패", "error": str(exc)[:300]}
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
            "daily_deep_limit": settings.stage3_daily_limit,
        },
        "configuration_problems": problems,
        "schedule": {"timezone": settings.app_timezone, "primary": "03:10", "retry": "04:40", "report": "07:00"},
        "latest_batch": latest_batch,
    }
