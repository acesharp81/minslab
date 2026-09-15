from __future__ import annotations

import argparse
import json

import _bootstrap  # noqa: F401
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db import SessionLocal, init_db
from app.models import ActionItem, AnalysisRun, Notice, NoticeDecision
from app.schemas import DeepAnalysis, SimpleAnalysis
from app.services.analyzer import (
    _input_hash,
    enforce_common_platform_gates,
    get_analyzer,
    notice_context,
    preserve_deep_ai_scope,
)
from app.services.supabase_store import get_supabase_store
from app.services.workflow_view import current_classification_run


def main() -> None:
    parser = argparse.ArgumentParser(description="3차에서 비AI로 잘못 하향된 AI 사업 결과 교정")
    parser.add_argument("--no-sync", action="store_true")
    args = parser.parse_args()
    init_db()
    analyzer = get_analyzer()
    repaired = []
    with SessionLocal() as db:
        db.info["suppress_supabase_sync"] = True
        notices = db.scalars(select(Notice).options(
            selectinload(Notice.attachments), selectinload(Notice.analysis_runs),
            selectinload(Notice.decision), selectinload(Notice.action),
        )).all()
        for notice in notices:
            context = notice_context(notice)
            simple_hash = _input_hash(context, "simple_ai", analyzer.simple_cache_fingerprint)
            simple_run = next((
                run for run in sorted(notice.analysis_runs, key=lambda row: row.id or 0, reverse=True)
                if run.run_type == "simple_ai" and run.status == "success"
                and run.input_hash == simple_hash
            ), None)
            current = current_classification_run(notice)
            if simple_run is None or current is None:
                continue
            simple = SimpleAnalysis.model_validate_json(simple_run.result_json)
            result = DeepAnalysis.model_validate_json(current.result_json)
            corrected = preserve_deep_ai_scope(result, simple)
            if corrected.ai_relevance == result.ai_relevance:
                continue
            corrected = enforce_common_platform_gates(corrected, context)
            deep_hash = _input_hash(context, "deep_ai", analyzer.deep_cache_fingerprint)
            db.add(AnalysisRun(
                notice_id=notice.id, run_type="deep_ai",
                model_name="postprocess:ai-scope-v2", input_hash=deep_hash,
                status="success", result_json=corrected.model_dump_json(),
                confidence=corrected.confidence, cost_prompt_tokens=0,
                cost_completion_tokens=0,
            ))
            decision = notice.decision or NoticeDecision(notice_id=notice.id)
            decision.final_grade = corrected.final_grade
            decision.ai_relevance = corrected.ai_relevance
            decision.common_platform_fit = corrected.common_platform_fit
            decision.usage_mentioned = corrected.usage_mentioned
            decision.priority_score = corrected.priority_score
            decision.recommended_action = corrected.recommended_action
            decision.summary = corrected.summary
            decision.possible_functions_json = json.dumps(
                corrected.possible_common_platform_functions, ensure_ascii=False,
            )
            decision.key_evidence_json = json.dumps(
                [item.model_dump() for item in corrected.evidence], ensure_ascii=False,
            )
            decision.check_questions_json = json.dumps(corrected.check_questions, ensure_ascii=False)
            decision.caveats_json = json.dumps(corrected.caveats, ensure_ascii=False)
            if notice.decision is None:
                db.add(decision)
            if notice.action is None:
                db.add(ActionItem(notice_id=notice.id))
            db.commit()
            repaired.append(notice.id)

        db.info.pop("suppress_supabase_sync", None)
        if not args.no_sync:
            get_supabase_store().push_all(db)
    print(json.dumps({"repaired": len(repaired), "notice_ids": repaired}, ensure_ascii=False))


if __name__ == "__main__":
    main()
