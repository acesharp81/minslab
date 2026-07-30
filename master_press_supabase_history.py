from __future__ import annotations

"""Queue compact Master Press production history during the quiet window."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "PoC" / "04-master-press"))

from master_press.config import Settings
from master_press.history_metrics import SupabaseHistoryMetrics
from master_press.storage import Store
from master_press.supabase_mirror import SupabaseMirror


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=0, help="Override the scheduled range with this many recent KST dates (1-14).")
    args = parser.parse_args()
    settings = Settings.from_env()
    settings.ensure_directories()
    store = Store(settings.database_path, initialize=False)
    initial_backfill = store.get_setting("supabase_history_initial_backfill_completed", "0") != "1"
    days = max(1, min(14, args.days or (14 if initial_backfill else 2)))
    result = SupabaseHistoryMetrics(store, SupabaseMirror(settings, store)).run(days)
    store.set_setting("supabase_history_last_window_days", str(days))
    if initial_backfill and not args.days and result["status"] == "queued":
        store.set_setting("supabase_history_initial_backfill_completed", "1")
        result["initial_backfill_completed"] = True
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] in {"queued", "disabled"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
