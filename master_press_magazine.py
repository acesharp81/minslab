from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "PoC" / "04-master-press"))

from master_press.config import Settings
from master_press.magazine import MagazinePublisher, SLOT_LABELS
from master_press.storage import KST, Store

def main() -> int:
    parser = argparse.ArgumentParser(description="Publish shared Master Press magazine editions.")
    parser.add_argument("slot", nargs="?", choices=sorted(SLOT_LABELS), default="")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    settings = Settings.from_env()
    settings.ensure_directories()
    slot = args.slot or {8: "morning", 12: "lunch", 18: "evening"}.get(datetime.now(KST).hour, "")
    if not slot:
        parser.error("slot을 지정하거나 KST 08시, 12시, 18시에 실행해야 합니다.")
    publisher = MagazinePublisher(Store(settings.database_path))
    editions = publisher.publish_for_slot(slot, force=args.force)
    print(json.dumps({"slot": slot, "published": len(editions), "editions": editions}, ensure_ascii=False, default=str))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
