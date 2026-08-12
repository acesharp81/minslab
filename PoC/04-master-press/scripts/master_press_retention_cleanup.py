from __future__ import annotations

"""Run bounded short-retention cleanup after the Supabase history verification."""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from master_press.config import Settings
from master_press.storage import KST, Store, now_iso


def adaptive_article_limit(first_run: bool, configured: int, completed_limit: int = 0, duration_ms: int = 0) -> int:
    """Ramp cleanup throughput only when the previous completed run had enough headroom."""
    if first_run:
        return 100
    limit = max(500, min(1000, int(configured or 800)))
    if duration_ms > 120_000:
        return 500
    if completed_limit <= 500 and 0 < duration_ms <= 60_000:
        return max(limit, 800)
    if completed_limit == 800 and 0 < duration_ms <= 90_000:
        return 1000
    return limit


def main() -> int:
    settings = Settings.from_env()
    settings.ensure_directories()
    store = Store(settings.database_path, initialize=False)
    today = datetime.now(KST).date().isoformat()
    verify_at = store.get_setting("supabase_history_last_verify_at", "")
    verify_status = store.get_setting("supabase_history_last_verify_status", "")
    if verify_status != "ready" or not verify_at.startswith(today):
        result = {"status": "skipped", "reason": "history_verification_not_ready", "verify_status": verify_status, "verify_at": verify_at}
    else:
        first_run = store.get_setting("short_retention_initial_cleanup_completed", "0") != "1"
        try:
            configured_limit = int(store.get_setting("short_retention_article_limit", "800") or 800)
        except ValueError:
            configured_limit = 800
        try:
            completed_limit = int(store.get_setting("short_retention_last_completed_limit", "0") or 0)
            completed_duration_ms = int(store.get_setting("short_retention_last_completed_duration_ms", "0") or 0)
        except ValueError:
            completed_limit = completed_duration_ms = 0
        article_limit = adaptive_article_limit(first_run, configured_limit, completed_limit, completed_duration_ms)
        store.set_setting("short_retention_article_limit", str(article_limit))
        started = time.monotonic()
        result = store.cleanup_short_retention(7, 8, article_limit, max(10, article_limit // 10), settings.data_dir / "press_releases" / "mois")
        duration_ms = round((time.monotonic() - started) * 1000)
        result.update({"status": "completed", "article_limit": article_limit, "first_run": first_run, "duration_ms": duration_ms})
        store.set_setting("short_retention_last_completed_limit", str(article_limit))
        store.set_setting("short_retention_last_completed_duration_ms", str(duration_ms))
        deleted_key = f"short_retention_deleted:{datetime.now(KST).strftime('%Y%m%d')}"
        try:
            deleted_before = int(store.get_setting(deleted_key, "0") or 0)
        except ValueError:
            deleted_before = 0
        store.set_setting(deleted_key, str(deleted_before + int(result.get("source_deleted_articles") or 0)))
        if first_run:
            store.set_setting("short_retention_initial_cleanup_completed", "1")
    store.set_setting("short_retention_last_cleanup_at", now_iso())
    store.set_setting("short_retention_last_cleanup_result", json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
