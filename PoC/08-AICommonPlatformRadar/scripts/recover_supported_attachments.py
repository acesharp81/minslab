from __future__ import annotations

import json

import _bootstrap  # noqa: F401
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db import SessionLocal, init_db
from app.models import Attachment, AuditLog
from app.services.collector import _store_attachment, parse_preferred_attachments
from app.services.filename import extension_from_name
from app.services.g2b_client import G2BNotice


def main() -> None:
    init_db()
    stats = {"selected": 0, "downloaded": 0, "parsed": 0, "failed": 0}
    with SessionLocal() as db:
        db.info["suppress_supabase_sync"] = True
        rows = db.scalars(select(Attachment).where(
            Attachment.parse_status == "unsupported",
            Attachment.file_path.is_(None),
        ).options(selectinload(Attachment.notice))).all()
        for attachment in rows:
            if not extension_from_name(attachment.original_filename):
                continue
            stats["selected"] += 1
            notice = attachment.notice
            try:
                raw = json.loads(notice.raw_payload_json or "{}")
                item = G2BNotice(
                    stage=notice.stage, notice_no=notice.notice_no, bid_no=notice.bid_no,
                    agency_name=notice.agency_name, agency_code=notice.agency_code,
                    title=notice.title, budget_amount=notice.budget_amount,
                    posted_at=notice.posted_at, deadline_at=notice.deadline_at,
                    url=notice.url, raw=raw if isinstance(raw, dict) else {},
                )
                status = _store_attachment(
                    db, notice, item, 1, attachment.source_url, attachment.original_filename,
                )
                stats["downloaded"] += int(status == "pending")
                parse_preferred_attachments(db, notice, force=True)
                stats["parsed"] += int(attachment.parse_status == "parsed")
                stats["failed"] += int(attachment.parse_status != "parsed")
                db.commit()
            except Exception:
                db.rollback()
                stats["failed"] += 1
        db.add(AuditLog(
            event_type="newly_supported_attachments_recovered", actor="system",
            detail_json=json.dumps(stats, ensure_ascii=False),
        ))
        db.commit()
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
