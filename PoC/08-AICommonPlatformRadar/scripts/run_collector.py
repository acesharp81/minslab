from __future__ import annotations

import argparse
import asyncio
import json

import _bootstrap  # noqa: F401

from app.db import SessionLocal, init_db
from app.services.collector import run_collection


def main() -> None:
    parser = argparse.ArgumentParser(description="나라장터 사전규격·본공고 수집 및 후보 분석")
    parser.add_argument("--lookback-days", type=int, default=None)
    parser.add_argument("--no-analyze", action="store_true")
    args = parser.parse_args()
    init_db()
    with SessionLocal() as db:
        result = asyncio.run(run_collection(db, args.lookback_days, analyze=not args.no_analyze))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

