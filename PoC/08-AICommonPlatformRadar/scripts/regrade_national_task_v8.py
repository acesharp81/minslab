from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter

import _bootstrap  # noqa: F401
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db import SessionLocal
from app.models import ActionItem, AnalysisRun, AuditLog, Notice, NoticeDecision
from app.schemas import DeepAnalysis
from app.services.analyzer import (
    CURRENT_CRITERIA_VERSION,
    enforce_common_platform_gates,
    enforce_public_task_policy,
    notice_context,
    update_decision_projection,
)
from app.services.supabase_store import get_supabase_store


POLICY_NAME = "national-task-evidence-v8"


def _current_or_source(notice: Notice) -> tuple[AnalysisRun | None, AnalysisRun | None]:
    current = None
    source = None
    for run in sorted(notice.analysis_runs, key=lambda row: row.id or 0, reverse=True):
        if run.run_type != "deep_ai" or not (
            run.status == "success" or (run.status == "skipped" and run.model_name == "rule-gate")
        ):
            continue
        try:
            version = json.loads(run.result_json or "{}").get("criteria_version")
        except (json.JSONDecodeError, AttributeError):
            continue
        if version == CURRENT_CRITERIA_VERSION:
            current = run
            break
        if source is None and version:
            source = run
    return current, source


def main() -> None:
    parser = argparse.ArgumentParser(description="국가사무·과업별 위임 증빙 기준으로 기존 분석을 재분류")
    parser.add_argument("--apply", action="store_true", help="새 분석 이력과 현재 결정을 저장합니다.")
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--no-sync", action="store_true")
    args = parser.parse_args()
    if args.batch_size < 1:
        parser.error("--batch-size는 1 이상이어야 합니다.")

    counts = Counter()
    code_transitions = Counter()
    task_transitions = Counter()
    examples: list[dict] = []
    named: list[dict] = []
    errors: list[dict] = []
    store = get_supabase_store()

    with SessionLocal() as db:
        db.info["suppress_supabase_sync"] = True
        notice_ids = list(db.scalars(select(Notice.id).order_by(Notice.id)))
        if args.limit:
            notice_ids = notice_ids[:args.limit]
        for offset in range(0, len(notice_ids), args.batch_size):
            batch = db.scalars(select(Notice).where(
                Notice.id.in_(notice_ids[offset:offset + args.batch_size])
            ).options(
                selectinload(Notice.attachments),
                selectinload(Notice.analysis_runs),
                selectinload(Notice.decision),
                selectinload(Notice.action),
            )).all()
            sync_rows: list[object] = []
            for notice in batch:
                current, source = _current_or_source(notice)
                if current is not None:
                    counts["already_current"] += 1
                    if args.apply and not args.no_sync:
                        sync_rows.extend([current, *([notice.decision] if notice.decision else [])])
                    continue
                if source is None:
                    counts["no_source"] += 1
                    continue
                confirmed = bool(
                    source.model_name.startswith("manual-")
                    or (notice.action and notice.action.status in {
                        "completed_uses", "completed_not_used", "completed_ineligible",
                        "completed_non_ai", "reflected", "closed",
                    })
                )
                if confirmed:
                    payload = json.loads(source.result_json or "{}")
                    payload["criteria_version"] = CURRENT_CRITERIA_VERSION
                    counts["confirmed_preserved"] += 1
                    code = str(payload.get("classification_code") or "")
                    task = str(payload.get("task_scope") or "")
                    code_transitions[f"{code}->{code}"] += 1
                    task_transitions[f"{task}->{task}"] += 1
                    if "안양시" in notice.agency_name:
                        named.append({
                            "id": notice.id, "agency": notice.agency_name,
                            "title": notice.title[:100],
                            "code": f"{code}->{code}", "task": f"{task}->{task}",
                            "confirmed": True,
                        })
                    if args.apply:
                        digest = hashlib.sha256(
                            f"{POLICY_NAME}|preserve|{notice.id}|{source.id}".encode("utf-8")
                        ).hexdigest()
                        run = AnalysisRun(
                            notice_id=notice.id, run_type="deep_ai",
                            model_name=f"policy-preserve:{POLICY_NAME}",
                            input_hash=digest, status=source.status,
                            result_json=json.dumps(payload, ensure_ascii=False),
                            confidence=source.confidence,
                            cost_prompt_tokens=0, cost_completion_tokens=0,
                        )
                        db.add(run)
                        db.flush()
                        sync_rows.append(run)
                    continue
                try:
                    old = DeepAnalysis.model_validate_json(source.result_json)
                    context = notice_context(notice)
                    new = old.model_copy(update={"criteria_version": CURRENT_CRITERIA_VERSION})
                    if (
                        source.status == "success"
                        and old.ai_relevance != "low"
                        and old.classification_code != "6"
                        and old.service_scope != "non_target"
                    ):
                        task = enforce_public_task_policy(old, context)
                        if task.task_scope != old.task_scope:
                            new = enforce_common_platform_gates(
                                old, context,
                                service_scope_override=(old.service_scope, old.service_scope_reason),
                            )
                        else:
                            new = new.model_copy(update={
                                "task_scope_reason": task.task_scope_reason,
                                "task_scope_evidence": task.task_scope_evidence,
                            })
                except (ValidationError, ValueError, json.JSONDecodeError) as exc:
                    counts["invalid_source"] += 1
                    errors.append({"notice_id": notice.id, "error": f"{type(exc).__name__}: {str(exc)[:160]}"})
                    continue

                counts["regraded"] += 1
                code_transitions[f"{old.classification_code}->{new.classification_code}"] += 1
                task_transitions[f"{old.task_scope}->{new.task_scope}"] += 1
                if old.task_scope != new.task_scope:
                    counts["task_changed"] += 1
                if old.classification_code != new.classification_code:
                    counts["classification_changed"] += 1
                    if len(examples) < 60:
                        examples.append({
                            "id": notice.id, "agency": notice.agency_name,
                            "title": notice.title[:100],
                            "code": f"{old.classification_code}->{new.classification_code}",
                            "task": f"{old.task_scope}->{new.task_scope}",
                        })
                if notice.id in {7315, 7207, 7182, 3294} or "안양시" in notice.agency_name:
                    named.append({
                        "id": notice.id, "agency": notice.agency_name,
                        "title": notice.title[:100],
                        "code": f"{old.classification_code}->{new.classification_code}",
                        "task": f"{old.task_scope}->{new.task_scope}",
                    })
                if not args.apply:
                    continue
                digest = hashlib.sha256(
                    f"{POLICY_NAME}|{notice.id}|{source.id}|{context}".encode("utf-8")
                ).hexdigest()
                run = AnalysisRun(
                    notice_id=notice.id, run_type="deep_ai",
                    model_name="rule-gate" if source.status == "skipped" else f"policy-regrade:{POLICY_NAME}",
                    input_hash=digest, status=source.status,
                    result_json=new.model_dump_json(), confidence=new.confidence,
                    cost_prompt_tokens=0, cost_completion_tokens=0,
                )
                db.add(run)
                update_decision_projection(db, notice, new)
                db.flush()
                decision = notice.decision or db.scalar(select(NoticeDecision).where(
                    NoticeDecision.notice_id == notice.id
                ))
                action = notice.action or db.scalar(select(ActionItem).where(
                    ActionItem.notice_id == notice.id
                ))
                sync_rows.extend([run, *([decision] if decision else []), *([action] if action else [])])

            if args.apply:
                db.commit()
                if not args.no_sync and sync_rows and store.enabled:
                    if not store.push_changes(sync_rows, []):
                        raise RuntimeError(
                            f"Supabase 동기화 실패: {offset + len(batch)}건까지 로컬 저장. "
                            "같은 명령을 다시 실행하면 v8 결과를 재동기화합니다."
                        )
            if (offset // args.batch_size + 1) % 10 == 0:
                print(json.dumps({
                    "progress": min(offset + args.batch_size, len(notice_ids)),
                    "total": len(notice_ids),
                    "regraded": counts["regraded"],
                }, ensure_ascii=False), flush=True)

        summary = {
            "policy": POLICY_NAME, "applied": args.apply,
            "notices": len(notice_ids), "counts": dict(counts),
            "code_transitions": dict(sorted(code_transitions.items())),
            "task_transitions": dict(sorted(task_transitions.items())),
            "named": named, "examples": examples,
            "errors": errors[:30],
            "remote_sync": bool(args.apply and not args.no_sync and store.enabled),
        }
        if args.apply:
            audit = AuditLog(
                event_type="national_task_policy_regrade",
                entity_type="policy", entity_id=POLICY_NAME, actor="system",
                detail_json=json.dumps({key: value for key, value in summary.items() if key != "examples"}, ensure_ascii=False),
            )
            db.add(audit)
            db.commit()
            if not args.no_sync and store.enabled and not store.push_changes([audit], []):
                raise RuntimeError("분석 결과는 저장됐지만 정책 변경 감사기록의 원격 동기화에 실패했습니다.")
        print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
