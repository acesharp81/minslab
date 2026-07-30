from __future__ import annotations

"""Verify the latest compact-history window after the outbox has drained."""

import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "PoC" / "04-master-press"))

from master_press.config import Settings
from master_press.history_metrics import SupabaseHistoryMetrics
from master_press.storage import KST, Store, now_iso
from master_press.supabase_mirror import SupabaseMirror


TABLES = {
    "operations": "master_press_daily_operations",
    "keywords": "master_press_daily_keyword_metrics",
    "models": "master_press_daily_model_metrics",
}


def remote_count(settings: Settings, table: str, since: str) -> int:
    params = urllib.parse.urlencode({"dataset": "eq.production", "metric_date": f"gte.{since}", "select": "id", "limit": 1})
    request = urllib.request.Request(
        f"{settings.supabase_url.rstrip('/')}/rest/v1/{table}?{params}",
        headers={"apikey": settings.supabase_service_role_key, "Authorization": f"Bearer {settings.supabase_service_role_key}", "Prefer": "count=exact"},
    )
    with urllib.request.urlopen(request, timeout=min(10, settings.request_timeout_seconds)) as response:
        return int(str(response.headers.get("Content-Range", "*/0")).rsplit("/", 1)[-1])


def main() -> int:
    settings = Settings.from_env()
    settings.ensure_directories()
    store = Store(settings.database_path, initialize=False)
    try:
        days = max(1, min(14, int(store.get_setting("supabase_history_last_window_days", "2") or 2)))
    except ValueError:
        days = 2
    metrics = SupabaseHistoryMetrics(store, SupabaseMirror(settings, store))
    expected = {name: len(rows) for name, rows in metrics.payload(days, dataset="production").items()}
    since = (datetime.now(KST) - timedelta(days=days - 1)).date().isoformat()
    result = {"status": "disabled", "days": days, "since": since, "expected": expected, "remote": {}}
    if settings.supabase_url and settings.supabase_service_role_key:
        try:
            result["remote"] = {name: remote_count(settings, table, since) for name, table in TABLES.items()}
            result["status"] = "ready" if result["remote"] == expected else "pending"
        except Exception as error:
            result["status"] = "unavailable"
            result["error"] = type(error).__name__
    store.set_setting("supabase_history_last_verify_at", now_iso())
    store.set_setting("supabase_history_last_verify_status", result["status"])
    store.set_setting("supabase_history_last_verify_result", json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
