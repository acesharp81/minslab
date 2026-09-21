from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..models import AuditLog, Notice
from .analyzer import is_current_deep_result
from .attachment_policy import select_preferred_documents
from .ineligible_reasons import INELIGIBLE_REASON_META, ineligible_reason_key, manual_ineligible_reason
from .workflow_view import ACTION_REQUIRED_CODES, current_classification_run, json_object


ACTION_IN_PROGRESS_STATES = {"in_progress", "contacted", "not_reflected"}
ACTION_COMPLETED_STATES = {
    "completed_uses", "completed_not_used", "completed_ineligible", "completed_non_ai", "reflected", "closed",
}
ACTION_PERFORMED_STATES = ACTION_IN_PROGRESS_STATES | ACTION_COMPLETED_STATES
KST = timezone(timedelta(hours=9))
PERIOD_LABELS = {"30d": "최근 30일", "month": "이번 달", "year": "이번 해", "all": "전체 기간"}
def _percent(numerator: int, denominator: int) -> float:
    return round(numerator / denominator * 100, 1) if denominator else 0.0


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _period_window(period: str, now: datetime | None = None) -> dict[str, Any]:
    period = period if period in PERIOD_LABELS else "30d"
    now = _aware(now or datetime.now(timezone.utc))
    local_now = now.astimezone(KST)
    if period == "30d":
        start = now - timedelta(days=30)
        previous_start, previous_end = start - timedelta(days=30), start
    elif period == "month":
        local_start = local_now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        previous_end = local_start.astimezone(timezone.utc)
        previous_month_last = local_start - timedelta(days=1)
        previous_start = previous_month_last.replace(day=1, hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
        start = previous_end
    elif period == "year":
        local_start = local_now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        start = local_start.astimezone(timezone.utc)
        previous_start = local_start.replace(year=local_start.year - 1).astimezone(timezone.utc)
        previous_end = start
    else:
        start = previous_start = previous_end = None
    return {
        "key": period, "label": PERIOD_LABELS[period], "start": start, "end": now,
        "previous_start": previous_start, "previous_end": previous_end,
        "display": "전체 수집 기간" if start is None else f"{start.astimezone(KST):%Y.%m.%d} ~ {now.astimezone(KST):%Y.%m.%d}",
        "previous_label": "이전 동일 기간" if period == "30d" else {"month": "지난 달", "year": "지난 해", "all": "비교 없음"}[period],
        "options": [{"key": key, "label": label} for key, label in PERIOD_LABELS.items()],
    }


def _in_window(value: datetime | None, start: datetime | None, end: datetime | None) -> bool:
    value = _aware(value)
    return bool(value and (start is None or value >= start) and (end is None or value < end))


def _history_codes(notice: Notice) -> set[str]:
    codes: set[str] = set()
    for run in notice.analysis_runs:
        if run.run_type != "deep_ai" or run.status not in {"success", "skipped"}:
            continue
        payload = json_object(run.result_json)
        code = str(payload.get("classification_code") or "")
        if code and is_current_deep_result(run.result_json):
            codes.add(code)
    return codes


def final_status_key(notice: Notice, result: dict[str, Any] | None = None) -> str:
    """Collapse detailed classifications and confirmed actions into final operator states."""
    result = result if result is not None else _current_result(notice)
    action_status = notice.action.status if notice.action else ""
    if action_status == "completed_non_ai":
        return "non_ai"
    if action_status == "completed_ineligible" and manual_ineligible_reason(notice) == "non_ai":
        return "non_ai"
    if action_status in {"completed_uses", "reflected"}:
        return "eligible_uses"
    if action_status in {"completed_not_used", "closed"}:
        return "eligible_not_used"
    if action_status == "completed_ineligible":
        return "ineligible"
    return {
        "1": "eligible_uses", "2": "eligible_not_used", "3": "review",
        "4": "review", "5": "ineligible", "6": "non_ai",
    }.get(str(result.get("classification_code") or ""), "pending")


def _ineligible_reason_breakdown(
    notices: list[Notice], states: dict[int, str],
) -> dict[str, Any]:
    counts = Counter(
        ineligible_reason_key(notice, _current_result(notice))
        for notice in notices
        if states[id(notice)] == "ineligible"
    )
    total = sum(counts.values())
    raw_items = [
        {"key": key, "label": label, "color": color, "count": counts[key]}
        for key, label, color in INELIGIBLE_REASON_META
    ]
    displayed = []
    used_percent = 0.0
    for index, item in enumerate(raw_items):
        percent = (
            round(100.0 - used_percent, 1)
            if total and index == len(raw_items) - 1
            else _percent(item["count"], total)
        )
        used_percent = round(used_percent + percent, 1)
        displayed.append({
            **item,
            "percent": percent,
            "start_percent": round(used_percent - percent, 1),
            "end_percent": used_percent,
        })
    return {
        "total": total,
        "items": displayed,
        "task_end": displayed[0]["end_percent"] if displayed else 0,
        "network_end": displayed[1]["end_percent"] if len(displayed) > 1 else 0,
    }


def build_final_status_snapshot(notices: list[Notice]) -> dict[str, Any]:
    states = {id(notice): final_status_key(notice) for notice in notices}
    values = Counter(states.values())
    pending_reasons = Counter()
    for notice in notices:
        if states[id(notice)] != "pending":
            continue
        ordered = sorted(notice.analysis_runs, key=lambda row: row.id or 0, reverse=True)
        latest_deep = next((row for row in ordered if row.run_type == "deep_ai"), None)
        latest_run = ordered[0] if ordered else None
        if latest_deep and latest_deep.status == "skipped" and latest_deep.model_name == "daily-quota-guard":
            pending_reasons["deep"] += 1
        elif latest_run and latest_run.status == "failed":
            pending_reasons["failed"] += 1
        else:
            pending_reasons["unanalyzed"] += 1
    eligible = values["eligible_uses"] + values["eligible_not_used"]
    ai = eligible + values["review"] + values["ineligible"]
    collected = len(notices)
    ineligible_reasons = _ineligible_reason_breakdown(notices, states)
    return {
        "collected": collected, "non_ai": values["non_ai"], "ai": ai,
        "eligible": eligible, "eligible_uses": values["eligible_uses"],
        "eligible_not_used": values["eligible_not_used"], "review": values["review"],
        "ineligible": values["ineligible"], "pending": values["pending"],
        "ineligible_reasons": ineligible_reasons,
        "pending_deep": pending_reasons["deep"],
        "pending_failed": pending_reasons["failed"],
        "pending_unanalyzed": pending_reasons["unanalyzed"],
        "closed": values["non_ai"] + ai,
        "coverage_rate": _percent(values["non_ai"] + ai, collected),
        "segments": [
            {"key": key, "label": label, "count": values[key], "percent": _percent(values[key], collected)}
            for key, label in (("non_ai", "비AI 사업"), ("eligible_uses", "적합·이용"),
                ("eligible_not_used", "적합·미이용"), ("review", "검토 필요"),
                ("ineligible", "부적합"), ("pending", "최종판정 대기"))
        ],
    }


def _resolution_events(db: Session, notices: list[Notice]) -> list[dict[str, Any]]:
    by_action = {notice.action.id: notice for notice in notices if notice.action and notice.action.id}
    completed = {"completed_uses", "completed_not_used", "completed_ineligible", "completed_non_ai", "reflected", "closed"}
    events: list[dict[str, Any]] = []
    seen: set[tuple[int, str]] = set()
    for log in db.scalars(select(AuditLog).where(AuditLog.event_type == "action_updated")).all():
        try:
            action_id = int(log.entity_id or 0)
        except ValueError:
            continue
        notice = by_action.get(action_id)
        status = str(json_object(log.detail_json).get("status") or "")
        if not notice or status not in completed:
            continue
        events.append({"notice": notice, "status": status, "at": _aware(log.created_at)})
        seen.add((notice.id, status))
    for notice in notices:
        if not notice.action or notice.action.status not in completed:
            continue
        key = (notice.id, notice.action.status)
        if key not in seen:
            events.append({"notice": notice, "status": notice.action.status, "at": _aware(notice.action.updated_at)})
    return events


def _achievement_counts(events: list[dict[str, Any]], start: datetime | None, end: datetime | None) -> dict[str, int]:
    review_to_eligible: set[int] = set()
    unused_to_used: set[int] = set()
    review_to_ineligible: set[int] = set()
    for event in events:
        if not _in_window(event["at"], start, end):
            continue
        codes, status, notice_id = _history_codes(event["notice"]), event["status"], event["notice"].id
        if codes & {"3", "4"} and status in {"completed_uses", "completed_not_used", "reflected", "closed"}:
            review_to_eligible.add(notice_id)
        if (
            codes & {"3", "4"}
            and status == "completed_ineligible"
            and final_status_key(event["notice"]) == "ineligible"
        ):
            review_to_ineligible.add(notice_id)
        if "2" in codes and status in {"completed_uses", "reflected"}:
            unused_to_used.add(notice_id)
    return {"review_to_eligible": len(review_to_eligible), "review_to_ineligible": len(review_to_ineligible), "unused_to_used": len(unused_to_used)}


def _trend_rows(notices: list[Notice], events: list[dict[str, Any]], period: dict[str, Any]) -> list[dict[str, Any]]:
    monthly = period["key"] in {"year", "all"}
    rows: dict[str, Counter] = defaultdict(Counter)

    def key(value: datetime | None) -> str | None:
        value = _aware(value)
        if not value:
            return None
        local = value.astimezone(KST)
        return local.strftime("%Y-%m") if monthly else local.strftime("%m.%d")

    for notice in notices:
        bucket = key(notice.created_at)
        if bucket:
            rows[bucket]["collected"] += 1
    for event in events:
        if not _in_window(event["at"], period["start"], period["end"]):
            continue
        bucket, codes, status = key(event["at"]), _history_codes(event["notice"]), event["status"]
        if not bucket:
            continue
        if codes & {"3", "4"} and status in {"completed_uses", "completed_not_used", "reflected", "closed"}:
            rows[bucket]["review_to_eligible"] += 1
        if "2" in codes and status in {"completed_uses", "reflected"}:
            rows[bucket]["unused_to_used"] += 1
    result = [{"label": label, **counts} for label, counts in sorted(rows.items())][-31:]
    maximum = max((row.get("review_to_eligible", 0) + row.get("unused_to_used", 0) for row in result), default=1) or 1
    for row in result:
        row["review_height"] = round(row.get("review_to_eligible", 0) / maximum * 100)
        row["usage_height"] = round(row.get("unused_to_used", 0) / maximum * 100)
    return result


def _month_key(value: datetime | None) -> str | None:
    value = _aware(value)
    return value.astimezone(KST).strftime("%Y-%m") if value else None


def _current_result(notice: Notice) -> dict[str, Any]:
    run = current_classification_run(notice)
    return json_object(run.result_json if run else None)


def _historical_action_ids(notices: list[Notice]) -> set[int]:
    """Return notices ever classified as 2/3/4 under the current criteria version."""
    detected: set[int] = set()
    for notice in notices:
        for run in notice.analysis_runs:
            if run.run_type != "deep_ai" or run.status not in {"success", "skipped"}:
                continue
            result = json_object(run.result_json)
            if is_current_deep_result(run.result_json) and str(result.get("classification_code")) in ACTION_REQUIRED_CODES:
                detected.add(notice.id)
                break
    return detected


def _conversion_rows(
    notices: list[Notice], results: dict[int, dict[str, Any]], historical_action_ids: set[int],
) -> list[dict[str, Any]]:
    prenotices = {notice.notice_no: notice for notice in notices if notice.stage == "prenotice"}
    converted: list[dict[str, Any]] = []
    for bid in notices:
        if bid.stage != "bid_notice":
            continue
        payload = json_object(bid.raw_payload_json)
        pre_no = str(payload.get("bfSpecRgstNo") or "").strip()
        pre = prenotices.get(pre_no)
        if not pre or pre.id not in historical_action_ids or not pre.action or not pre.action.contacted_at:
            continue
        contacted_at = _aware(pre.action.contacted_at)
        bid_posted_at = _aware(bid.posted_at)
        if bid_posted_at and contacted_at and bid_posted_at < contacted_at:
            continue
        result = results.get(bid.id, {})
        if result.get("platform_usage") != "uses":
            continue
        converted.append({
            "prenotice_id": pre.id,
            "bid_notice_id": bid.id,
            "title": bid.title,
            "agency_name": bid.agency_name,
            "prenotice_no": pre.notice_no,
            "bid_notice_no": bid.notice_no,
            "contacted_at": contacted_at.astimezone(KST).isoformat(timespec="minutes"),
            "bid_posted_at": bid_posted_at.astimezone(KST).isoformat(timespec="minutes") if bid_posted_at else None,
            "classification_code": str(result.get("classification_code") or ""),
            "eligible_and_uses": str(result.get("classification_code") or "") == "1",
        })
    return sorted(converted, key=lambda row: row["bid_posted_at"] or "", reverse=True)


def build_statistics(
    db: Session, period: str = "30d", now: datetime | None = None,
) -> dict[str, Any]:
    period_data = _period_window(period, now)
    all_notices = db.scalars(select(Notice).options(
        selectinload(Notice.attachments), selectinload(Notice.analysis_runs),
        selectinload(Notice.decision), selectinload(Notice.action),
    )).all()
    notices = [
        notice for notice in all_notices
        if _in_window(notice.created_at, period_data["start"], period_data["end"])
    ]
    results = {notice.id: _current_result(notice) for notice in notices}
    status_snapshot = build_final_status_snapshot(notices)
    resolution_events = _resolution_events(db, all_notices)
    current_achievements = _achievement_counts(
        resolution_events, period_data["start"], period_data["end"],
    )
    previous_achievements = _achievement_counts(
        resolution_events, period_data["previous_start"], period_data["previous_end"],
    ) if period_data["previous_start"] is not None else {
        "review_to_eligible": 0, "review_to_ineligible": 0, "unused_to_used": 0,
    }
    review_compare_max = max(
        current_achievements["review_to_eligible"], previous_achievements["review_to_eligible"], 1,
    )
    usage_compare_max = max(
        current_achievements["unused_to_used"], previous_achievements["unused_to_used"], 1,
    )
    achievements = {
        **current_achievements,
        "previous_review_to_eligible": previous_achievements["review_to_eligible"],
        "previous_unused_to_used": previous_achievements["unused_to_used"],
        "review_delta": current_achievements["review_to_eligible"] - previous_achievements["review_to_eligible"],
        "usage_delta": current_achievements["unused_to_used"] - previous_achievements["unused_to_used"],
        "review_current_width": round(current_achievements["review_to_eligible"] / review_compare_max * 100),
        "review_previous_width": round(previous_achievements["review_to_eligible"] / review_compare_max * 100),
        "usage_current_width": round(current_achievements["unused_to_used"] / usage_compare_max * 100),
        "usage_previous_width": round(previous_achievements["unused_to_used"] / usage_compare_max * 100),
    }
    classified = [notice for notice in notices if results[notice.id].get("classification_code")]
    codes = Counter(str(results[notice.id].get("classification_code")) for notice in classified)
    ai_notices = [
        notice for notice in classified
        if results[notice.id].get("ai_relevance") in {"high", "medium"}
    ]
    non_ai_count = len(classified) - len(ai_notices)
    ai_ids = {notice.id for notice in ai_notices}

    current_action_targets = [
        notice for notice in classified
        if str(results[notice.id].get("classification_code")) in ACTION_REQUIRED_CODES
    ]
    historical_action_ids = _historical_action_ids(notices)
    action_targets = [notice for notice in notices if notice.id in historical_action_ids]
    reclassified_excluded = sum(
        str(results[notice.id].get("classification_code") or "") in {"5", "6"}
        for notice in action_targets
    )
    actions_started = sum(bool(notice.action and notice.action.status != "new") for notice in action_targets)
    actions_performed = sum(bool(
        notice.action and (
            notice.action.contacted_at or notice.action.status in ACTION_PERFORMED_STATES
        )
    ) for notice in action_targets)
    actions_in_progress = sum(bool(
        notice.action and notice.action.status in ACTION_IN_PROGRESS_STATES
    ) for notice in action_targets)
    actions_completed = sum(bool(
        notice.action and notice.action.status in ACTION_COMPLETED_STATES
    ) for notice in action_targets)
    completed_uses = sum(bool(
        notice.action and notice.action.status in {"completed_uses", "reflected"}
    ) for notice in action_targets)
    completed_not_used = sum(bool(
        notice.action and notice.action.status in {"completed_not_used", "closed"}
    ) for notice in action_targets)
    completed_ineligible = sum(bool(
        notice.action and notice.action.status == "completed_ineligible"
        and manual_ineligible_reason(notice) != "non_ai"
    ) for notice in action_targets)
    completed_non_ai = sum(bool(
        notice.action and (
            notice.action.status == "completed_non_ai"
            or (
                notice.action.status == "completed_ineligible"
                and manual_ineligible_reason(notice) == "non_ai"
            )
        )
    ) for notice in action_targets)
    replied = sum(
        json_object(notice.raw_payload_json).get("_poc08_opinion_tracking", {}).get("status") == "replied"
        for notice in action_targets if notice.stage == "prenotice"
    )
    converted = _conversion_rows(notices, results, historical_action_ids)
    converted_eligible = sum(row["eligible_and_uses"] for row in converted)

    relevant = [notice for notice in classified if str(results[notice.id].get("classification_code")) != "6"]
    network_values = Counter(results[notice.id].get("network_scope", "unclear") for notice in relevant)
    task_values = Counter(results[notice.id].get("task_scope", "unclear") for notice in relevant)
    service_values = Counter(results[notice.id].get("service_scope", "unclear") for notice in relevant)
    model_values = Counter(results[notice.id].get("model_fit", "unclear") for notice in relevant)
    reason_groups = [
        {
            "key": "network", "label": "망 조건", "count": sum(network_values[key] for key in (
                "external_complete", "other_closed_network", "unclear",
            )),
            "description": "외부망 완결, 별도 폐쇄망 또는 운영망 미확인",
            "details": [
                ("외부망 완결", network_values["external_complete"]),
                ("폐쇄망 연계 확인", network_values["other_closed_network"]),
                ("망 구성 미확인", network_values["unclear"]),
            ],
        },
        {
            "key": "user", "label": "이용대상·업무", "count": sum(task_values[key] for key in (
                "public_institution_internal", "non_government", "unclear",
            )),
            "description": "공공기관 내부업무, 비국가사무 또는 국가사무 미확인",
            "details": [
                ("기관 자체 내부업무", task_values["public_institution_internal"]),
                ("비국가사무", task_values["non_government"]),
                ("국가사무 미확인", task_values["unclear"]),
            ],
        },
        {
            "key": "service", "label": "서비스 유형", "count": (
                service_values["non_target"]
                + sum(model_values[key] for key in ("custom_model_or_full_finetuning", "unclear"))
                - sum(
                    1 for notice in relevant
                    if results[notice.id].get("service_scope") == "non_target"
                    and results[notice.id].get("model_fit") in {"custom_model_or_full_finetuning", "unclear"}
                )
            ),
            "description": "구축 범위 밖 용역 또는 제공 LLM·RAG 적용 곤란·미확인",
            "details": [
                ("구축 범위 비대상", service_values["non_target"]),
                ("독자모델·풀파인튜닝", model_values["custom_model_or_full_finetuning"]),
                ("모델 적용 미확인", model_values["unclear"]),
            ],
        },
    ]

    documents = [
        item for notice in notices
        for item in select_preferred_documents(notice.attachments, name=lambda row: row.original_filename)
    ]
    parsed_documents = sum(item.parse_status == "parsed" for item in documents)
    evidence_count = sum(bool(results[notice.id].get("evidence")) for notice in ai_notices)

    agency_stats: dict[str, Counter] = defaultdict(Counter)
    for notice in ai_notices:
        code = str(results[notice.id].get("classification_code") or "")
        agency_stats[notice.agency_name or "기관 미상"]["ai"] += 1
        agency_stats[notice.agency_name or "기관 미상"]["action"] += int(code in ACTION_REQUIRED_CODES)
        agency_stats[notice.agency_name or "기관 미상"]["uses"] += int(code == "1")
    top_agencies = [
        {"agency_name": agency, **values}
        for agency, values in sorted(
            agency_stats.items(), key=lambda item: (-item[1]["ai"], -item[1]["action"], item[0]),
        )[:10]
    ]

    month_stats: dict[str, Counter] = defaultdict(Counter)
    for notice in notices:
        month = _month_key(notice.posted_at or notice.created_at)
        if not month:
            continue
        month_stats[month]["collected"] += 1
        if notice.id in ai_ids:
            month_stats[month]["ai"] += 1
        if notice.id in historical_action_ids:
            month_stats[month]["action"] += 1
    for row in converted:
        if row["bid_posted_at"]:
            month_stats[row["bid_posted_at"][:7]]["converted"] += 1
    monthly = [
        {"month": month, **values}
        for month, values in sorted(month_stats.items())[-6:]
    ]
    monthly_max = max((row.get("collected", 0) for row in monthly), default=1) or 1
    for row in monthly:
        row["height"] = round(row.get("collected", 0) / monthly_max * 100)

    return {
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "period": period_data,
        "status": status_snapshot,
        "achievements": achievements,
        "trend": _trend_rows(notices, resolution_events, period_data),
        "overview": {
            "collected": len(notices),
            "analyzed": len(classified),
            "coverage_rate": _percent(len(classified), len(notices)),
            "ai": len(ai_notices),
            "non_ai": non_ai_count,
            "ai_rate": _percent(len(ai_notices), len(classified)),
        },
        "platform": {
            "eligible_uses": codes["1"],
            "eligible_not_used": codes["2"],
            "eligible_not_used_actioned": sum(bool(
                notice.action and (notice.action.contacted_at or notice.action.status in ACTION_PERFORMED_STATES)
            ) for notice in classified if str(results[notice.id].get("classification_code")) == "2"),
            "transition_review": codes["3"],
            "uses_condition_issue": codes["4"],
            "out_of_scope": codes["5"],
            "non_ai": codes["6"],
        },
        "quality": {
            "document_total": len(documents),
            "document_parsed": parsed_documents,
            "document_parse_rate": _percent(parsed_documents, len(documents)),
            "evidence_count": evidence_count,
            "evidence_rate": _percent(evidence_count, len(ai_notices)),
        },
        "actions": {
            "detected": len(action_targets),
            "reclassified_excluded": reclassified_excluded,
            "current_detected": len(current_action_targets),
            "current_pending": sum(bool(
                not notice.action or notice.action.status in {"new", "reviewing"}
            ) for notice in current_action_targets),
            "started": actions_started,
            "acted": actions_performed,
            "in_progress": actions_in_progress,
            "completed": actions_completed,
            "contacted": actions_performed,
            "replied": replied,
            "reflected": completed_uses,
            "not_reflected": completed_not_used,
            "completed_uses": completed_uses,
            "completed_not_used": completed_not_used,
            "completed_ineligible": completed_ineligible,
            "completed_non_ai": completed_non_ai,
            "converted": len(converted),
            "converted_eligible": converted_eligible,
            "start_rate": _percent(actions_started, len(action_targets)),
            "contact_rate": _percent(actions_performed, len(action_targets)),
            "completion_rate": _percent(actions_completed, len(action_targets)),
            "conversion_rate": _percent(len(converted), actions_performed),
        },
        "reason_groups": reason_groups,
        "conversions": converted[:100],
        "top_agencies": top_agencies,
        "monthly": monthly,
        "classification_distribution": {str(code): codes[str(code)] for code in range(1, 7)},
        "methodology_note": (
            "정답셋이 아직 없으므로 정확도 대신 전량 분류율, 사업문서 파싱률, AI 판정의 원문근거 보유율을 표시합니다. "
            "조치 필요 검출은 현행 기준에서 한 번이라도 2·3·4유형으로 판정된 누적 사업이며, 현재 판정 건수와 구분합니다. "
            "전환 실적은 의견·연락 일시가 기록된 사전규격과 나라장터 bfSpecRgstNo로 직접 연결된 후속 본공고에서 "
            "연락 이후 공통기반 사용 문구가 확인된 경우만 집계하며, 인과관계가 아닌 확인 가능한 후속 실적입니다."
        ),
    }
