from __future__ import annotations

"""Run bounded short-retention cleanup after the Supabase history verification."""

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "PoC" / "04-master-press"))

from master_press.config import Settings
from master_press.storage import KST, Store, now_iso


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
        article_limit = 100 if first_run else 500
        result = store.cleanup_short_retention(7, 8, article_limit, max(10, article_limit // 10), settings.data_dir / "press_releases" / "mois")
        result.update({"status": "completed", "article_limit": article_limit, "first_run": first_run})
        if first_run:
            store.set_setting("short_retention_initial_cleanup_completed", "1")
    store.set_setting("short_retention_last_cleanup_at", now_iso())
    store.set_setting("short_retention_last_cleanup_result", json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
