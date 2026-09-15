from __future__ import annotations

import json

import _bootstrap  # noqa: F401
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db import SessionLocal, init_db
from app.models import Notice
from app.services.collector import parse_preferred_attachments


def main() -> None:
    init_db()
    summary = {
        "notices": 0,
        "parsed": 0,
        "failed": 0,
        "unsupported": 0,
        "skipped": 0,
        "skipped_duplicate": 0,
    }
    with SessionLocal() as db:
        notices = db.scalars(
            select(Notice).options(selectinload(Notice.attachments)).order_by(Notice.id)
        ).all()
        for notice in notices:
            summary["notices"] += 1
            statuses = parse_preferred_attachments(db, notice)
            for status in statuses.values():
                if status in summary:
                    summary[status] += 1
        db.commit()
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
