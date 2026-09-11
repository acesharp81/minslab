from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import _bootstrap  # noqa: F401

from sqlalchemy import text

from app.config import get_settings
from app.db import engine
from app.services.supabase_store import get_supabase_store


def main() -> int:
    settings = get_settings()
    checks: dict[str, object] = {
        "python": sys.version.split()[0],
        "python_supported": sys.version_info >= (3, 11),
        "dependencies": {name: importlib.util.find_spec(name) is not None for name in (
            "fastapi", "uvicorn", "sqlalchemy", "psycopg", "pydantic", "httpx", "jinja2", "yaml", "pypdf", "docx"
        )},
        "g2b_mode": settings.g2b_mode,
        "database_backend": settings.database_backend,
        "llm": {
            "stage2": {"provider": settings.stage2_provider, "model": settings.stage2_model, "credential_ready": settings.stage2_provider == "mock" or bool(settings.stage2_api_key)},
            "stage3_primary": {"provider": settings.stage3_primary_provider, "model": settings.stage3_primary_model, "credential_ready": settings.stage3_primary_provider == "mock" or bool(settings.stage3_primary_api_key)},
            "stage3_fallback": {"provider": settings.stage3_fallback_provider, "model": settings.stage3_fallback_model, "credential_ready": settings.stage3_fallback_provider == "mock" or bool(settings.stage3_fallback_api_key)},
        },
        "configuration_problems": settings.validate_runtime(),
    }
    try:
        settings.ensure_directories()
        probe = settings.data_dir / ".write-probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        checks["data_directory_writable"] = True
    except OSError as exc:
        checks["data_directory_writable"] = False
        checks["data_directory_error"] = str(exc)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        checks["database_connection"] = "ok"
    except Exception as exc:
        checks["database_connection"] = "error"
        checks["database_error"] = f"{type(exc).__name__}: {str(exc)[:300]}"
    if settings.supabase_enabled:
        store = get_supabase_store()
        checks["supabase_rest"] = "ok" if store.health() else "error"
        if store.last_error:
            checks["supabase_error"] = store.last_error
    else:
        checks["supabase_rest"] = "disabled"
    dependencies_ok = all(checks["dependencies"].values())
    ok = bool(
        checks["python_supported"]
        and dependencies_ok
        and checks["data_directory_writable"]
        and checks["database_connection"] == "ok"
        and checks["supabase_rest"] != "error"
        and not checks["configuration_problems"]
    )
    checks["ready"] = ok
    print(json.dumps(checks, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
