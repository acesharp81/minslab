from __future__ import annotations

"""Run a read-only Master Press Supabase replica reconciliation."""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from master_press.config import Settings
from master_press.storage import Store
from master_press.supabase_reconcile import SupabaseReconciler


def main() -> int:
    settings = Settings.from_env()
    settings.ensure_directories()
    result = SupabaseReconciler(settings, Store(settings.database_path, initialize=False)).run()
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] in {"ready", "disabled"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
