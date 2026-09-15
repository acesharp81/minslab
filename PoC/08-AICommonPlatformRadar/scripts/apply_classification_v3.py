from __future__ import annotations

import json

import _bootstrap  # noqa: F401
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db import SessionLocal, init_db
from app.models import Notice
from app.services.analyzer import record_non_ai_screen
from app.services.attachment_policy import select_preferred_documents
from app.services.collector import _needs_backlog_analysis, can_rule_screen_non_ai
from app.services.filter_rules import evaluate_notice
from app.services.supabase_store import get_supabase_store


def main() -> None:
    init_db()
    stats = {"classified_non_ai": 0, "ai_candidates": 0, "insufficient_text": 0, "already_current": 0}
    with SessionLocal() as db:
        db.info["suppress_supabase_sync"] = True
        notices = db.scalars(select(Notice).options(
            selectinload(Notice.attachments), selectinload(Notice.analysis_runs),
        )).all()
        for notice in notices:
            if not _needs_backlog_analysis(notice):
                stats["already_current"] += 1
                continue
            documents = select_preferred_documents(notice.attachments, name=lambda row: row.original_filename)
            rule = evaluate_notice(
                title=notice.title,
                agency=notice.agency_name,
                budget_amount=notice.budget_amount,
                attachment_names=[row.original_filename for row in documents],
                text_excerpt="\n".join(row.text_excerpt or "" for row in documents),
            )
            if rule.score > 0:
                stats["ai_candidates"] += 1
            elif can_rule_screen_non_ai(notice, rule) and record_non_ai_screen(db, notice, rule):
                stats["classified_non_ai"] += 1
            else:
                stats["insufficient_text"] += 1
        db.info.pop("suppress_supabase_sync", None)
        get_supabase_store().push_all(db)
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
