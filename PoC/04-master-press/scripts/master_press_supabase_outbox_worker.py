from __future__ import annotations

"""Flush bounded Master Press Supabase outbox batches outside web requests."""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
from master_press.config import Settings
from master_press.storage import Store
from master_press.supabase_mirror import SupabaseMirror


def main() -> int:
    settings = Settings.from_env(); settings.ensure_directories()
    store = Store(settings.database_path, initialize=False); mirror = SupabaseMirror(settings)
    events = store.due_supabase_outbox(100)
    grouped: dict[tuple[str, str], list[dict]] = {}
    for event in events:
        grouped.setdefault((event["table_name"], event["conflict_key"]), []).append(event)
    completed = failed = retryable_failed = 0
    # Preserve foreign-key order even when SQLite returns events with the same timestamp.
    table_priority = {
        "master_press_organizations": 10,
        "master_press_cases": 20,
        "master_press_articles": 30,
        "master_press_scores": 40,
        "master_press_press_releases": 50,
        "master_press_press_release_chunks": 60,
        "master_press_article_press_matches": 70,
        "master_press_daily_metrics": 80,
        "master_press_daily_operations": 81,
        "master_press_daily_keyword_metrics": 82,
        "master_press_daily_model_metrics": 83,
    }
    for (table, conflict_key), items in sorted(grouped.items(), key=lambda group: (table_priority.get(group[0][0], 99), group[0])):
        rows = [json.loads(item["payload"]) for item in items]
        ok = mirror.upsert(table, rows, conflict_key)
        # 4xx validation/conflict responses need a data or schema correction.
        # Retrying them keeps the single SQLite writer busy without a chance of
        # succeeding, so retain them as failed records for admin inspection.
        retryable = not (400 <= int(mirror.last_status or 0) < 500)
        for item in items:
            settled = store.finish_supabase_outbox(
                item["id"], ok, "" if ok else mirror.last_error,
                expected_payload=item["payload"], retryable=retryable,
            )
            completed += 1 if ok and settled else 0
            if not ok and settled:
                failed += 1
                retryable_failed += int(retryable)
    print(json.dumps({"selected": len(events), "completed": completed, "failed": failed, "retryable_failed": retryable_failed, "status": store.supabase_outbox_status()}, ensure_ascii=False))
    return 0 if not retryable_failed else 1

if __name__ == "__main__":
    raise SystemExit(main())
