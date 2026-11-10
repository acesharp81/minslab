from __future__ import annotations

import argparse
import json

import _bootstrap  # noqa: F401

from app.db import SessionLocal, init_db
from app.services.attachment_retention import purge_attachments_by_policy


def main() -> None:
    parser = argparse.ArgumentParser(description="PoC08 판정별 첨부파일 보존 정책 적용")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    init_db()
    with SessionLocal() as db:
        result = purge_attachments_by_policy(db, dry_run=args.dry_run)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
