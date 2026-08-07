#!/usr/bin/env python3
"""Earth Engine의 전체 VIIRS 월을 북한 한정 압축 데이터로 병렬 수집한다."""

from __future__ import annotations

import argparse
import concurrent.futures
import gzip
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from generate_map import VIIRS_COLLECTION, initialize_earth_engine, load_runtime_environment


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "output" / "data"


def available_months(project: str | None) -> list[str]:
    ee = initialize_earth_engine(project)
    timestamps = (
        ee.ImageCollection(VIIRS_COLLECTION)
        .sort("system:time_start")
        .aggregate_array("system:time_start")
        .getInfo()
    )
    return sorted({datetime.fromtimestamp(value / 1000).strftime("%Y-%m") for value in timestamps})


def collect_month(month: str, project: str | None, force: bool) -> tuple[str, bool, str]:
    destination = DATA_DIR / f"north_korea_viirs_{month}.json.gz"
    if destination.is_file() and destination.stat().st_size > 0 and not force:
        try:
            with gzip.open(destination, "rb") as stream:
                while stream.read(1024 * 1024):
                    pass
            return month, True, "기존 파일 건너뜀"
        except (OSError, EOFError):
            destination.unlink(missing_ok=True)
    command = [
        sys.executable,
        str(ROOT / "generate_map.py"),
        "--month",
        month,
        "--data-output",
        str(destination),
        "--no-html",
    ]
    if project:
        command.extend(["--project", project])
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    if result.returncode != 0 and "cf_cvg > 0인 북한 격자가 없습니다." in result.stderr:
        return month, True, "북한 내 유효 관측 0건 · 제외"
    message = (result.stdout if result.returncode == 0 else result.stderr).strip().splitlines()
    return month, result.returncode == 0, message[-1] if message else f"exit={result.returncode}"


def main() -> int:
    load_runtime_environment()
    parser = argparse.ArgumentParser(description="VIIRS 전체 월을 북한 한정 JSON.gz로 수집합니다.")
    parser.add_argument("--project", default=os.getenv("GEE_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT"))
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--start", help="시작 월 YYYY-MM")
    parser.add_argument("--end", help="종료 월 YYYY-MM")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    months = [month for month in available_months(args.project) if (not args.start or month >= args.start) and (not args.end or month <= args.end)]
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Earth Engine {len(months)}개월 · 북한 경계만 · workers={args.workers}", flush=True)
    failures = []
    completed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = {executor.submit(collect_month, month, args.project, args.force): month for month in months}
        for future in concurrent.futures.as_completed(futures):
            month, success, message = future.result()
            completed += 1
            print(f"[{completed}/{len(months)}] {month} {'완료' if success else '실패'} · {message}", flush=True)
            if not success:
                failures.append(month)
    if failures:
        print("실패 월: " + ", ".join(sorted(failures)), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
