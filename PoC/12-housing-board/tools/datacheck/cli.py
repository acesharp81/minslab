"""명령줄 진입점."""
from __future__ import annotations

import argparse
import tempfile
import zipfile
from datetime import date
from pathlib import Path

from .readers import extract_zip, find_region_dirs
from .report import build_report, exit_code, write_report
from .spec import SPEC_PATH, load_spec
from .validate import validate_region


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="validate_input", description="팀원이 제출한 입력(폴더 또는 ZIP)을 검증한다.")
    ap.add_argument("path", help="입력 폴더 또는 ZIP")
    ap.add_argument("--out", default="validation_out", help="리포트를 쓸 폴더 (기본: ./validation_out)")
    ap.add_argument("--today", help="검증일 YYYY-MM-DD (기본: 오늘)")
    ap.add_argument("--strict", action="store_true", help="warn이 있어도 종료 코드 1")
    ap.add_argument("--spec", default=str(SPEC_PATH), help=argparse.SUPPRESS)
    args = ap.parse_args(argv)

    try:
        today = date.fromisoformat(args.today) if args.today else date.today()
    except ValueError:
        print(f"오류: --today 형식이 올바르지 않음: {args.today} (예: 2026-10-04)")
        return 2
    src = Path(args.path)
    if not src.exists():
        print(f"오류: 경로가 없음: {src}")
        return 2
    spec = load_spec(args.spec)

    with tempfile.TemporaryDirectory() as tmp:
        fallback = None
        base = src
        if src.is_file():
            if src.suffix.lower() != ".zip":
                print("오류: 폴더 또는 .zip 파일을 넘겨 주세요")
                return 2
            try:
                base = extract_zip(src, Path(tmp))
            except (ValueError, zipfile.BadZipFile) as e:
                print(f"오류: ZIP을 열 수 없음: {e}")
                return 2
            fallback = src.stem  # ZIP 최상위에 파일이 바로 있으면 ZIP 이름이 지역 이름
        regions = find_region_dirs(base, set(spec.files), fallback)
        if not regions:
            print("오류: 지역 폴더를 찾지 못함 (regions.csv 등이 든 폴더가 있어야 함)")
            return 2
        results = [validate_region(path, spec, today, slug=slug) for slug, path in regions]
        report = build_report(results, spec, today, str(src))
        write_report(report, results, Path(args.out))

    for reg in report["regions"]:
        print(f"{'거부' if reg['rejected'] else '완료'}  {reg['slug']}")
    s = report["summary"]
    print(f"error {s['error']} · warn {s['warn']} · info {s['info']}")
    print(f"리포트: {Path(args.out) / 'validation_report.md'}")
    return exit_code(report, args.strict)
