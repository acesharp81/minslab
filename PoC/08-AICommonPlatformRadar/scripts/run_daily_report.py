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
    args = parser.parse_args()
    init_db()
    with SessionLocal() as db:
        artifact = build_daily_report(db, args.date)
    print(json.dumps({
        "date": artifact.report_date.isoformat(), "summary": artifact.summary,
        "markdown": artifact.markdown_path, "html": artifact.html_path,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

