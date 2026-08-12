from __future__ import annotations

"""Read-only shadow comparison for Master Press Supabase daily metrics."""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from master_press.config import Settings
from master_press.storage import Store
from master_press.supabase_daily_metrics import SupabaseDailyMetrics
from master_press.supabase_mirror import SupabaseMirror


def main() -> int:
    settings = Settings.from_env()
    settings.ensure_directories()
    result = SupabaseDailyMetrics(Store(settings.database_path, initialize=False), SupabaseMirror(settings)).shadow_compare()
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] in {"ready", "disabled"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
