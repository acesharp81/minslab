from fastapi import APIRouter
from sqlalchemy import text

from ..config import get_settings
from ..db import engine
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
    }
