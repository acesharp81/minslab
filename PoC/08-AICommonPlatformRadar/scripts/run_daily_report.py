from __future__ import annotations

import argparse
import json
from datetime import date

import _bootstrap  # noqa: F401

from app.db import SessionLocal, init_db
from app.services.report_builder import build_daily_report


def main() -> None:
    parser = argparse.ArgumentParser(description="일일 레이더 리포트 생성")
    parser.add_argument("--date", type=date.fromisoformat, default=None)
    parser.add_argument("--finalize", action="store_true", help="완료 배치 기반 최종본으로 표시")
    parser.add_argument("--require-successful-batch", action="store_true", help="완료 배치가 없으면 실패 처리")
    args = parser.parse_args()
    init_db()
    with SessionLocal() as db:
        artifact = build_daily_report(db, args.date, finalized=args.finalize,
                                      require_successful_batch=args.require_successful_batch)
    print(json.dumps({
        "date": artifact.report_date.isoformat(), "summary": artifact.summary,
        "status": artifact.status, "finalized": artifact.finalized,
        "markdown": artifact.markdown_path, "html": artifact.html_path, "json": artifact.json_path,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
