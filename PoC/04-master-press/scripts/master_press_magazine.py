from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from master_press.config import Settings
from master_press.kakao import KakaoClient
from master_press.magazine import SLOT_LABELS
from master_press.service import MasterPressService
from master_press.storage import KST, Store

def main() -> int:
    parser = argparse.ArgumentParser(description="Publish shared Master Press magazine editions.")
    parser.add_argument("slot", nargs="?", choices=sorted(SLOT_LABELS), default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    settings = Settings.from_env()
    settings.ensure_directories()
    slot = args.slot or {7: "morning", 12: "lunch", 18: "evening"}.get(datetime.now(KST).hour, "")
    if not slot:
        parser.error("slot을 지정하거나 KST 07시, 12시, 18시에 실행해야 합니다.")
    # The long-running application services own base-schema migrations. This
    # scheduled publisher must not rerun historical backfills while pipeline
    # workers are writing to SQLite.
    store = Store(settings.database_path, initialize=False)
    service = object.__new__(MasterPressService)
    service.settings = settings
    service.store = store
    service.kakao = KakaoClient(settings, store)
    result = service.publish_magazine_slot(slot, force=args.force)
    print(json.dumps(result, ensure_ascii=False, default=str), flush=True)
    return 1 if int((result.get("delivery") or {}).get("failed") or 0) else 0

if __name__ == "__main__":
    raise SystemExit(main())
