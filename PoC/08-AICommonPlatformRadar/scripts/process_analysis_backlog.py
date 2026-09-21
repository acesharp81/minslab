from __future__ import annotations

import argparse
import json
from collections import Counter

import _bootstrap  # noqa: F401
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db import SessionLocal, init_db
from app.models import Notice
from app.services.analyzer import (
    LLMRateLimitExceeded,
    analyze_notice,
    record_non_ai_screen,
)
from app.services.collector import can_rule_screen_non_ai, _needs_backlog_analysis, _notice_priority
from app.services.filter_rules import evaluate_notice


def _rule(notice: Notice):
    return evaluate_notice(
        title=notice.title,
        agency=notice.agency_name,
        budget_amount=notice.budget_amount,
        attachment_names=[item.original_filename for item in notice.attachments],
        text_excerpt="\n".join(item.text_excerpt or "" for item in notice.attachments),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="PoC08 미분석·심층대기 적체 재처리")
    parser.add_argument("--limit", type=int, default=0, help="0이면 전체 적체 처리")
    args = parser.parse_args()
    init_db()
    counts = Counter()
    failures: list[dict[str, str | int]] = []
    with SessionLocal() as db:
        notices = db.scalars(select(Notice).options(
            selectinload(Notice.attachments), selectinload(Notice.analysis_runs),
            selectinload(Notice.decision), selectinload(Notice.action),
        )).all()
        backlog = sorted(
            (notice for notice in notices if _needs_backlog_analysis(notice)),
            key=_notice_priority,
            reverse=True,
        )
        if args.limit > 0:
            backlog = backlog[:args.limit]
        counts["target"] = len(backlog)
        for position, notice in enumerate(backlog, start=1):
            try:
                rule = _rule(notice)
                if rule.score <= 0 and can_rule_screen_non_ai(notice, rule):
                    if record_non_ai_screen(db, notice, rule):
                        counts["rule_screened"] += 1
                    else:
                        counts["already_complete"] += 1
                else:
                    result = analyze_notice(db, notice, deep=True, force=False)
                    counts[f"classification_{result.classification_code}"] += 1
                    counts["analyzed"] += 1
            except LLMRateLimitExceeded as exc:
                db.rollback()
                failures.append({"notice_id": notice.id, "error": str(exc)[:500]})
                counts["rate_limited"] += 1
                print(json.dumps({
                    "progress": position, "total": len(backlog), "notice_id": notice.id,
                    "state": "rate_limited", "error": str(exc)[:300],
                }, ensure_ascii=False), flush=True)
                break
            except Exception as exc:  # keep independent notices moving
                db.rollback()
                failures.append({
                    "notice_id": notice.id,
                    "error": f"{type(exc).__name__}: {str(exc)[:500]}",
                })
                counts["failed"] += 1
            if position % 10 == 0 or position == len(backlog):
                print(json.dumps({
                    "progress": position, "total": len(backlog), "counts": dict(counts),
                }, ensure_ascii=False), flush=True)
    print(json.dumps({"counts": dict(counts), "failures": failures}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
