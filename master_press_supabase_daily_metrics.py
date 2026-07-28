from __future__ import annotations

"""Queue the bounded Master Press daily score read model for Supabase."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "PoC" / "04-master-press"))

from master_press.config import Settings
from master_press.storage import Store
from master_press.supabase_daily_metrics import SupabaseDailyMetrics
from master_press.supabase_mirror import SupabaseMirror


def main() -> int:
    settings = Settings.from_env()
    settings.ensure_directories()
    store = Store(settings.database_path, initialize=False)
    result = SupabaseDailyMetrics(store, SupabaseMirror(settings, store)).run_once()
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] in {"queued", "disabled"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
