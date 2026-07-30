from __future__ import annotations

"""Build a bounded, no-body Supabase history trial from the last 14 days."""

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
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--queue", action="store_true", help="Queue trial rows only after the Supabase history schema is installed.")
    args = parser.parse_args()
    settings = Settings.from_env()
    settings.ensure_directories()
    store = Store(settings.database_path, initialize=False)
    result = SupabaseHistoryMetrics(store, SupabaseMirror(settings, store)).trial(max(1, min(31, args.days)), queue=args.queue)
    if result["status"] == "preview":
        result["sample"] = {name: rows[:2] for name, rows in result.pop("payload").items()}
    print(json.dumps(result, ensure_ascii=False, default=str))
    return 0 if result["status"] in {"preview", "queued", "disabled"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
