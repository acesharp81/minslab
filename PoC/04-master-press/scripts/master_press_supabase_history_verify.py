from __future__ import annotations

"""Verify the latest compact-history window after the outbox has drained."""

import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from master_press.config import Settings
from master_press.history_metrics import SupabaseHistoryMetrics
from master_press.storage import KST, Store, now_iso
from master_press.supabase_mirror import SupabaseMirror


TABLES = {
    "operations": "master_press_daily_operations",
    "keywords": "master_press_daily_keyword_metrics",
    "models": "master_press_daily_model_metrics",
}


def remote_ids(settings: Settings, table: str, since: str, updated_at: str = "") -> set[str]:
    """Read all IDs for one immutable transfer snapshot, independent of API row caps."""
    if not updated_at:
        return set()
    result: set[str] = set()
    limit = 1000
    for offset in range(0, 10000, limit):
        params = urllib.parse.urlencode({
            "dataset": "eq.production", "metric_date": f"gte.{since}", "updated_at": f"eq.{updated_at}",
            "select": "id", "order": "id", "limit": limit, "offset": offset,
        })
        request = urllib.request.Request(
            f"{settings.supabase_url.rstrip('/')}/rest/v1/{table}?{params}",
            headers={"apikey": settings.supabase_service_role_key, "Authorization": f"Bearer {settings.supabase_service_role_key}"},
        )
        with urllib.request.urlopen(request, timeout=min(10, settings.request_timeout_seconds)) as response:
            rows = json.loads(response.read().decode("utf-8"))
        result.update(str(row.get("id") or "") for row in rows if isinstance(row, dict) and row.get("id"))
        if len(rows) < limit:
            break
    return result


def main() -> int:
    settings = Settings.from_env()
    settings.ensure_directories()
    store = Store(settings.database_path, initialize=False)
    try:
        days = max(1, min(14, int(store.get_setting("supabase_history_last_window_days", "2") or 2)))
    except ValueError:
        days = 2
    metrics = SupabaseHistoryMetrics(store, SupabaseMirror(settings, store))
    today = datetime.now(KST).date().isoformat()
    snapshot_ready = (
        store.get_setting("supabase_history_last_snapshot_at", "").startswith(today)
        and store.get_setting("supabase_history_last_snapshot_days", "") == str(days)
    )
    try:
        snapshot = json.loads(store.get_setting("supabase_history_last_snapshot", "{}")) if snapshot_ready else {}
    except (TypeError, ValueError):
        snapshot = {}
    snapshot_ids = snapshot.get("ids") if isinstance(snapshot, dict) else None
    snapshot_times = snapshot.get("updated_at") if isinstance(snapshot, dict) else None
    if not isinstance(snapshot_ids, dict) or not isinstance(snapshot_times, dict) or not all(isinstance(snapshot_ids.get(name), list) for name in TABLES):
        snapshot_ready = False
        payload = metrics.payload(days, dataset="production")
        snapshot_ids = {name: [str(row["id"]) for row in rows] for name, rows in payload.items()}
        snapshot_times = {name: "" for name in TABLES}
    expected_ids = {name: {str(value) for value in snapshot_ids[name]} for name in TABLES}
    expected = {name: len(values) for name, values in expected_ids.items()}
    since = (datetime.now(KST) - timedelta(days=days - 1)).date().isoformat()
    result = {"status": "disabled", "days": days, "since": since, "snapshot_ready": snapshot_ready,
              "expected": expected, "remote": {}, "missing": {}, "unexpected": {}}
    if settings.supabase_url and settings.supabase_service_role_key:
        try:
            if snapshot_ready:
                remote = {name: remote_ids(settings, table, since, str(snapshot_times.get(name) or "")) for name, table in TABLES.items()}
                result["remote"] = {name: len(values) for name, values in remote.items()}
                result["missing"] = {name: len(expected_ids[name] - remote[name]) for name in TABLES}
                result["unexpected"] = {name: len(remote[name] - expected_ids[name]) for name in TABLES}
                result["status"] = "ready" if not any(result["missing"].values()) and not any(result["unexpected"].values()) else "pending"
            else:
                result["status"] = "pending"
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
