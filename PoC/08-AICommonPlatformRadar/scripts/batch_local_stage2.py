from __future__ import annotations

import argparse
import json
import re
import time
from collections import Counter

import _bootstrap  # noqa: F401
import httpx
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.db import SessionLocal, init_db
from app.models import AnalysisRun, Notice
from app.schemas import SimpleAnalysis
from app.services.analyzer import (
    _input_hash, analyze_notice, enforce_explicit_ai_scope, get_analyzer, notice_context,
)
from app.services.supabase_store import get_supabase_store
from app.services.workflow_view import current_classification_run


AI_MARKER = re.compile(
    r"(?<![A-Za-z])AI(?![A-Za-z])|인공지능|생성형|(?<![A-Za-z])LLM(?![A-Za-z])|"
    r"(?<![A-Za-z])RAG(?![A-Za-z])|머신러닝|딥러닝|자연어\s*처리|컴퓨터\s*비전|지능형",
    re.IGNORECASE,
)


def _snippet(notice: Notice, limit: int = 420) -> str:
    text = "\n".join(item.text_excerpt or "" for item in notice.attachments)
    match = AI_MARKER.search(text)
    if match:
        start = max(0, match.start() - 220)
        body = text[start:start + limit]
    else:
        body = text[:limit]
    return re.sub(r"\s+", " ", body).strip()


def _pending(db, analyzer, *, refresh_ai_titles: bool = False) -> list[Notice]:
    notices = db.scalars(select(Notice).options(
        selectinload(Notice.attachments), selectinload(Notice.analysis_runs),
        selectinload(Notice.decision), selectinload(Notice.action),
    )).all()
    result = []
    for notice in notices:
        if current_classification_run(notice) and not (refresh_ai_titles and AI_MARKER.search(notice.title)):
            continue
        simple = next((
            run for run in sorted(notice.analysis_runs, key=lambda row: row.id or 0, reverse=True)
            if run.run_type == "simple_ai" and run.status == "success"
        ), None)
        expected_hash = _input_hash(
            notice_context(notice), "simple_ai", analyzer.simple_cache_fingerprint,
        )
        if simple and simple.input_hash == expected_hash:
            continue
        result.append(notice)
    return result


def _classify_batch(base_url: str, api_key: str, model: str, notices: list[Notice], timeout: int) -> dict[int, dict]:
    rows = [{"id": notice.id, "title": notice.title, "excerpt": _snippet(notice, 320)} for notice in notices]
    system = (
        "AI가 사업명이나 핵심 산출물의 직접 주제이면 1, 단순 참고 언급이면 0이다. "
        "AI 시스템뿐 아니라 AI 교육·행사·정책연구·감리·학습데이터 사업도 1이다. AAM·첨단·자동화만 있으면 0이다. "
        '추정하지 말고 같은 순서와 id로 짧은 JSON만 출력한다: {"items":[[id,0],[id,1]]}'
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(rows, ensure_ascii=False)},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0,
        "reasoning_effort": "none",
        "max_tokens": 300,
    }
    with httpx.Client(timeout=timeout) as client:
        response = client.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"}, json=payload,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
    parsed = json.loads(content)
    items = parsed.get("items", [])
    result = {}
    for item in items:
        if not isinstance(item, list) or len(item) < 2:
            continue
        notice_id, is_functional_ai = int(item[0]), bool(item[1])
        result[notice_id] = {
            "ai_relevance": "high" if is_functional_ai else "low",
            "needs_deep_review": is_functional_ai,
            "reason": "AI 추론 기능의 직접 구축·연계·운영 근거가 확인되었습니다."
            if is_functional_ai else "AI 기능을 직접 구축·연계·운영하는 사업으로 확인되지 않았습니다.",
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="외부 소형 모델 배치 2차 판정")
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--refresh-ai-titles", action="store_true")
    parser.add_argument("--no-sync", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    analyzer = get_analyzer(settings)
    init_db()

    with SessionLocal() as db:
        db.info["suppress_supabase_sync"] = True
        notices = _pending(db, analyzer, refresh_ai_titles=args.refresh_ai_titles)
        if args.limit:
            notices = notices[:args.limit]
        stats = Counter(requested=len(notices))
        errors = []
        for offset in range(0, len(notices), args.batch_size):
            if offset and settings.stage2_min_interval_seconds:
                time.sleep(settings.stage2_min_interval_seconds)
            batch = notices[offset:offset + args.batch_size]
            try:
                direct = [notice for notice in batch if AI_MARKER.search(notice.title)]
                llm_batch = [notice for notice in batch if notice not in direct]
                results = {
                    notice.id: {
                        "ai_relevance": "medium",
                        "needs_deep_review": True,
                        "reason": "사업명에 AI가 직접 명시되어 3차 기본조건 검토 대상으로 분류했습니다.",
                    }
                    for notice in direct
                }
                if llm_batch:
                    results.update(_classify_batch(
                        settings.stage2_base_url, settings.stage2_api_key, settings.stage2_model,
                        llm_batch, settings.stage2_timeout_seconds,
                    ))
            except Exception as exc:
                errors.append({"offset": offset, "error": f"{type(exc).__name__}: {str(exc)[:300]}"})
                stats["batch_failed"] += len(batch)
                print(json.dumps({"progress": offset + len(batch), **stats}, ensure_ascii=False), flush=True)
                continue

            for notice in batch:
                raw = results.get(notice.id)
                if raw is None:
                    stats["missing_result"] += 1
                    continue
                if AI_MARKER.search(notice.title):
                    raw = {
                        "ai_relevance": "medium",
                        "needs_deep_review": True,
                        "reason": "사업명에 AI가 직접 명시되어 3차 기본조건 검토 대상으로 분류했습니다.",
                    }
                try:
                    simple = SimpleAnalysis(
                        ai_relevance=str(raw.get("ai_relevance", "low")).lower(),
                        needs_deep_review=bool(raw.get("needs_deep_review", False)),
                        reason=str(raw.get("reason") or "로컬 배치 2차 판정"),
                        evidence=[],
                        confidence=0.78,
                    )
                    context = notice_context(notice)
                    simple = enforce_explicit_ai_scope(simple, context)
                    db.add(AnalysisRun(
                        notice_id=notice.id,
                        run_type="simple_ai",
                        model_name=settings.stage2_model,
                        input_hash=_input_hash(context, "simple_ai", analyzer.simple_cache_fingerprint),
                        status="success",
                        result_json=simple.model_dump_json(),
                        confidence=simple.confidence,
                        cost_prompt_tokens=0,
                        cost_completion_tokens=0,
                    ))
                    db.commit()
                    analyze_notice(db, notice, deep=True, force=False)
                    db.expire_all()
                    refreshed = db.scalar(select(Notice).where(Notice.id == notice.id).options(
                        selectinload(Notice.analysis_runs)
                    ))
                    stats["classified"] += int(bool(refreshed and current_classification_run(refreshed)))
                    stats["deep_candidate"] += int(simple.needs_deep_review)
                    stats["processed"] += 1
                except Exception as exc:
                    db.rollback()
                    stats["failed"] += 1
                    errors.append({"notice_id": notice.id, "error": f"{type(exc).__name__}: {str(exc)[:300]}"})
            print(json.dumps({"progress": offset + len(batch), **stats}, ensure_ascii=False), flush=True)

        db.info.pop("suppress_supabase_sync", None)
        if not args.no_sync:
            get_supabase_store().push_all(db)
        remaining = len(_pending(db, analyzer, refresh_ai_titles=args.refresh_ai_titles))
        print(json.dumps({"stats": dict(stats), "remaining_local_stage2": remaining, "errors": errors[:100]},
                         ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
