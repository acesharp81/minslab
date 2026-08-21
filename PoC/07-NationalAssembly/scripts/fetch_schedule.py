#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


PROJECT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_DIR / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.adapters.national_assembly.client import NationalAssemblyClient
from app.adapters.national_assembly.schedule import ScheduleAdapter
from app.storage.raw_store import RawStore


def load_api_key() -> str:
    env_path = PROJECT_DIR / ".env"
    if not env_path.is_file():
        raise RuntimeError("프로젝트 .env가 없습니다. .env.example을 복사하고 API 키를 설정하세요.")
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("NATIONAL_ASSEMBLY_API_KEY="):
            value = line.split("=", 1)[1].strip().strip("'").strip('"')
            if value:
                return value
    raise RuntimeError("NATIONAL_ASSEMBLY_API_KEY가 설정되지 않았습니다.")


def main() -> int:
    parser = argparse.ArgumentParser(description="검증된 국회일정 API 한 페이지를 raw로 보존합니다.")
    parser.add_argument(
        "--date",
        default=datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat(),
        help="조회일 YYYY-MM-DD (기본값: 오늘 KST)",
    )
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--page-size", type=int, default=100)
    args = parser.parse_args()

    client = NationalAssemblyClient(load_api_key())
    payload = client.fetch(
        "assembly_schedule",
        page=args.page,
        page_size=args.page_size,
        filters={"SCH_DT": args.date},
    )
    adapter = ScheduleAdapter()
    artifact = RawStore(PROJECT_DIR / "data" / "raw").save(
        payload,
        parser_version=adapter.parser_version,
    )
    records = adapter.parse(payload)
    print(json.dumps({
        "source": payload.source_key,
        "date": args.date,
        "records": len(records),
        "content_hash": artifact.content_hash,
        "duplicate": artifact.duplicate,
        "content_path": str(artifact.content_path.relative_to(PROJECT_DIR)),
        "manifest_path": str(artifact.manifest_path.relative_to(PROJECT_DIR)),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
