from __future__ import annotations

"""Queue one safe batch of historical Master Press metadata for Supabase."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "PoC" / "04-master-press"))

from master_press.config import Settings
from master_press.storage import Store
from master_press.supabase_mirror import SupabaseMirror
from master_press.supabase_seed import SupabaseSeed


def main() -> int:
    settings = Settings.from_env()
    settings.ensure_directories()
    store = Store(settings.database_path, initialize=False)
    result = SupabaseSeed(store, SupabaseMirror(settings, store)).run_once()
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
