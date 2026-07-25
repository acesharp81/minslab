from __future__ import annotations

"""Run one bounded Master Press body-backfill attempt without the LLM pipeline."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT / "PoC" / "04-master-press"
sys.path.insert(0, str(PROJECT))

from master_press.collectors import NewsCollector
from master_press.config import Settings
from master_press.service import MasterPressService
from master_press.storage import Store


def main() -> int:
    settings = Settings.from_env()
    settings.ensure_directories()
    # Do not construct the normal service: its initializer can recover other
    # pipeline jobs. This object contains only the three dependencies used by
    # backfill_missing_article_bodies().
    service = object.__new__(MasterPressService)
    service.settings = settings
    service.store = Store(settings.database_path)
    service.collector = NewsCollector(settings)
    print(json.dumps(service.backfill_missing_article_bodies(), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
