from __future__ import annotations

import json
import re

from ..models import AnalysisRun, Notice
from .analyzer import CLASSIFICATION_LABELS, is_current_deep_result
from .attachment_policy import select_preferred_documents
from .filter_rules import evaluate_notice
from .opinion_guidance import build_opinion_guidance, opinion_template_type
from .platform_usage import has_optional_platform_usage


ACTION_REQUIRED_CODES = {"2", "3", "4"}
ACTION_STATUS_LABELS = {
    "new": "권고 대기", "reviewing": "검토중", "in_progress": "조치중",
    "completed_non_ai": "비AI 사업",
    "completed_uses": "조치완료 · 이용", "completed_not_used": "조치완료 · 미이용",
    "completed_ineligible": "조치완료 · 부적합", "contacted": "조치중",
    "reflected": "조치완료 · 이용", "not_reflected": "조치중", "closed": "조치완료",
}
ACTION_STATUS_NORMALIZED = {
    "contacted": "in_progress",
    "reflected": "completed_uses",
    "not_reflected": "in_progress",
    "closed": "completed_not_used",
}


def json_object(value: str | None) -> dict:
    try:
        parsed = json.loads(value or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def guidance_sections(message: str) -> list[dict]:
    """Present old structured messages and new human prose as compact visual sections."""
    if re.search(r"(?m)^(분석 내용|검토 요청)\s*$", message or ""):
        parts = re.split(r"(?m)^\s*(분석 내용|검토 요청)\s*$", message or "")
        introduction = [part.strip() for part in re.split(r"\n\s*\n", parts[0]) if part.strip()]
        sections = [{"title": "인사·의견 요지", "entries": introduction}]
        for index in range(1, len(parts), 2):
            title = parts[index].strip()
            body = parts[index + 1] if index + 1 < len(parts) else ""
            entries = [
                line[2:].strip() if line.startswith("- ") else line.strip()
                for line in body.splitlines() if line.strip()
            ]
            sections.append({"title": title, "entries": entries})
        return sections
    if "[" not in (message or ""):
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", message or "") if part.strip()]
        titles = ("의견 요지", "현재 확인된 내용", "보완·확인 시 활용 가능", "검토 요청", "관련 법적 근거")
        return [
            {"title": titles[index] if index < len(titles) else "추가 안내", "entries": [paragraph]}
            for index, paragraph in enumerate(paragraphs)
        ]
    sections: list[dict] = []
    current: dict | None = None
    for raw_line in (message or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            current = {"title": line[1:-1], "entries": []}
            sections.append(current)
            continue
        if current is None:
            current = {"title": "인사·의견 요지", "entries": []}
            sections.append(current)
        current["entries"].append(line[2:] if line.startswith("- ") else line)
    return sections


def notice_contact(notice: Notice) -> dict:
    if notice.stage != "bid_notice":
        return {}
    payload = json_object(notice.raw_payload_json)
    name = next((str(payload.get(key) or "").strip() for key in (
        "ntceInsttOfclNm", "dminsttOfclNm", "ofclNm", "chrgprsnNm",
    ) if str(payload.get(key) or "").strip()), "")
    phone = next((str(payload.get(key) or "").strip() for key in (
        "ntceInsttOfclTelNo", "dminsttOfclTelNo", "ofclTelNo", "chrgprsnTelNo",
    ) if str(payload.get(key) or "").strip()), "")
    tel_value = re.sub(r"[^0-9+]", "", phone)
    return {
        "name": name,
        "phone": phone,
        "tel_url": f"tel:{tel_value}" if tel_value else None,
        "available": bool(name or phone),
    }


def opinion_tracking(notice: Notice) -> dict:
    payload = json_object(notice.raw_payload_json)
    tracking = payload.get("_poc08_opinion_tracking")
    if isinstance(tracking, dict) and tracking.get("status"):
        if (
            tracking.get("status") == "not_submitted"
            and notice.action
            and notice.action.status in {"in_progress", "completed_uses", "completed_not_used", "completed_ineligible", "completed_non_ai", "contacted", "reflected", "not_reflected"}
        ):
            return {**tracking, "status": "not_checked", "status_label": "답변 확인 전"}
        return tracking
    if notice.action and notice.action.status in {"in_progress", "completed_uses", "completed_not_used", "completed_ineligible", "completed_non_ai", "contacted", "reflected", "not_reflected"}:
        return {"status": "not_checked", "status_label": "답변 확인 전"}
    return {"status": "not_submitted", "status_label": "의견 등록 전"}


def current_classification_run(notice: Notice) -> AnalysisRun | None:
    """Return the newest valid six-category result, ignoring later retry failures."""
    ordered = sorted(notice.analysis_runs, key=lambda row: row.id or 0, reverse=True)
    classification = next((
        run for run in sorted(notice.analysis_runs, key=lambda row: row.id or 0, reverse=True)
        if run.run_type == "deep_ai"
        and is_current_deep_result(run.result_json)
        and (
            run.status == "success"
            or (run.status == "skipped" and run.model_name == "rule-gate")
        )
    ), None)
    latest_simple = next((
        run for run in ordered
        if run.run_type == "simple_ai" and run.status == "success"
    ), None)
    if classification and latest_simple and (classification.id or 0) < (latest_simple.id or 0):
        return None
    return classification


def current_deep_success(notice: Notice) -> AnalysisRun | None:
    return next((
        run for run in sorted(notice.analysis_runs, key=lambda row: row.id or 0, reverse=True)
        if run.run_type == "deep_ai" and run.status == "success"
        and is_current_deep_result(run.result_json)
    ), None)


def latest_run(notice: Notice, run_type: str) -> AnalysisRun | None:
    return next((
        run for run in sorted(notice.analysis_runs, key=lambda row: row.id or 0, reverse=True)
        if run.run_type == run_type
    ), None)


def g2b_registration_no(notice: Notice) -> str | None:
    if notice.stage != "prenotice":
        return None
    payload = json_object(notice.raw_payload_json)
    registration_no = payload.get("bfSpecRgstNo") or notice.notice_no
    return str(registration_no).strip() or None


def g2b_opinion_url(notice: Notice) -> str | None:
    """Return a reliable G2B entry point for a pre-notice opinion.

    Every /link/*/single screen tested by this service requires internal G2B
    navigation state, including the list screen itself. External callers must
    enter through the G2B home page, navigate to the pre-notice list, and paste
    the separately exposed public registration number.
    """
    if notice.stage != "prenotice":
        return notice.url
    if not g2b_registration_no(notice):
        return notice.url
    return "https://www.g2b.go.kr/"


def finding_details(result: dict) -> list[dict]:
    """Translate gate results into operator-facing findings and required checks."""
    if result.get("service_scope") == "non_target":
        return []
    findings: list[dict] = []
    network = result.get("network_scope", "unclear")
    task = result.get("task_scope", "unclear")
    model = result.get("model_fit", "unclear")
    usage = result.get("platform_usage", "unclear")
    remediation = result.get("remediation_feasibility", "unclear")
    optional_usage = has_optional_platform_usage(result)

    if network not in {"internal_or_connected", "hybrid"}:
        findings.append({
            "gate": "망·데이터",
            "problem": (
                "내부·업무망 또는 연계망에서 처리되는지 공개 문서로 확인할 수 없습니다."
                if network == "unclear"
                else "폐쇄망은 확인됐지만 행정망·업무망 연계 여부가 확인되지 않았습니다."
                if network == "other_closed_network"
                else "인터넷망에서 완결되는 서비스로 명시되었습니다."
            ),
            "action": (
                "폐쇄망과 행정망·업무망의 연결 가능 여부 및 데이터 처리 경계를 담당자에게 확인합니다."
                if network == "other_closed_network"
                else "처리 데이터의 위치와 행정망·업무망 연계 범위를 명시하도록 요청합니다."
            ),
        })
    if task not in {"government", "delegated_government"}:
        findings.append({
            "gate": "국가사무",
            "problem": "공개 문서만으로 국가사무 여부를 확정할 수 없습니다. 불충족 판정이 아닙니다."
            if task == "unclear" else "기관 자체 내부업무 또는 비국가사무로 판정되었습니다.",
            "action": "발주·주무기관과 국가사무·위임·위탁 근거 및 실제 수행 사무의 범위를 담당자에게 확인합니다."
            if task == "unclear" else "비국가사무 판정 근거를 기록하고 공통기반 직접 활용 안내 대상에서는 제외합니다.",
        })
    if model != "platform_llm_or_rag":
        findings.append({
            "gate": "모델·기능",
            "problem": "공통기반의 LLM·RAG로 처리 가능한지 확인되지 않았습니다."
            if model == "unclear" else "독자모델 또는 풀파인튜닝 요구로 별도 협의가 필요합니다.",
            "action": "독자모델·풀파인튜닝을 공개 파운데이션 모델·RAG로 대체 가능한 범위까지 담당자에게 확인합니다.",
        })
    if usage != "uses" and result.get("classification_code") in {"2", "3"}:
        findings.append({
            "gate": "공통기반 활용",
            "problem": (
                "공통기반이 여러 인프라 대안 중 하나로만 제시되어, 다른 방안보다 "
                "우선 검토했는지 확인하도록 하는 장치가 부족합니다."
                if optional_usage else
                "기본조건 충족 가능성이 있으나 공통기반을 우선 검토하고 그 결과를 "
                "사업 문서에 반영하도록 하는 장치가 부족합니다."
            ),
            "action": (
                "다른 대안을 선택하기 전에 공통기반 적용 가능성을 우선 검토하고, 채택 여부와 "
                "미채택 사유를 사전규격에 명시하도록 의견을 냅니다."
                if optional_usage else
                "공통기반 적용 가능성을 우선 검토하고, 검토 결과와 활용 범위·연계 방식을 "
                "사전규격에 반영하도록 의견을 냅니다."
            ),
        })
    if result.get("classification_code") == "4" and usage == "uses":
        findings.append({
            "gate": "활용 조건 불일치",
            "problem": "공통기반 사용은 명시됐지만 기본조건 중 미충족·미확인 항목이 있습니다.",
            "action": "사용 문구를 유지하되 미충족 게이트의 설계·근거를 보완하도록 요청합니다.",
        })
    if remediation == "feasible" and result.get("classification_code") == "3":
        findings.append({
            "gate": "전환 가능성",
            "problem": "현재 설계는 직접 이용 조건과 다르지만 망 또는 모델 변경이 가능한 것으로 보입니다.",
            "action": "망 배치 또는 모델 구성을 공통기반 요건에 맞추는 대안을 검토합니다.",
        })
    if not findings and result.get("classification_code") in ACTION_REQUIRED_CODES:
        findings.append({
            "gate": "세부조건",
            "problem": "조치 대상 유형으로 분류됐으나 공개 문서의 세부 근거가 제한적입니다.",
            "action": "심층분석 근거와 확인 질문을 바탕으로 발주기관에 조건을 확인합니다.",
        })
    return findings


def workflow_summary(notice: Notice) -> dict:
    classification_run = current_classification_run(notice)
    result = json_object(classification_run.result_json if classification_run else None)
    code = str(result.get("classification_code") or "")
    findings = finding_details(result) if result else []
    guidance = (
        build_opinion_guidance(notice, result)
        if result and code in ACTION_REQUIRED_CODES
        else result.get("guidance_message", "")
    )
    template_type = opinion_template_type(notice) if result and code in ACTION_REQUIRED_CODES else None
    raw_action_status = notice.action.status if notice.action else "new"
    return {
        "classification_code": code or None,
        "classification_label": CLASSIFICATION_LABELS.get(code, "미분류"),
        "result": result,
        "findings": findings,
        "issue_labels": list(dict.fromkeys(item["gate"] for item in findings)),
        "guidance_message": guidance,
        "guidance_sections": guidance_sections(guidance),
        "opinion_template_type": template_type,
        "opinion_template_label": (
            "계획·ISP·연구용역" if template_type == "planning" else "구축사업" if template_type else None
        ),
        "action_required": code in ACTION_REQUIRED_CODES,
        "action_status": ACTION_STATUS_LABELS.get(raw_action_status, "권고 대기"),
        "action_state": ACTION_STATUS_NORMALIZED.get(raw_action_status, raw_action_status),
        "opinion_url": g2b_opinion_url(notice),
        "g2b_registration_no": g2b_registration_no(notice),
        "opinion_tracking": opinion_tracking(notice),
        "contact": notice_contact(notice),
    }


def analysis_trace(notice: Notice) -> list[dict]:
    documents = select_preferred_documents(notice.attachments, name=lambda row: row.original_filename)
    parsed = sum(item.parse_status == "parsed" for item in documents)
    rule = evaluate_notice(
        title=notice.title,
        agency=notice.agency_name,
        budget_amount=notice.budget_amount,
        attachment_names=[item.original_filename for item in documents],
        text_excerpt="\n".join(item.text_excerpt or "" for item in documents),
    )
    simple = latest_run(notice, "simple_ai")
    deep = current_deep_success(notice)
    latest_deep = latest_run(notice, "deep_ai")
    classification = current_classification_run(notice)
    simple_result = json_object(simple.result_json if simple else None)
    deep_result = json_object(classification.result_json if classification else None)

    if simple and simple.status == "success":
        simple_detail = simple_result.get("reason") or simple_result.get("summary") or "AI 관련도와 심층 필요 여부를 판정했습니다."
        simple_status = "complete"
    elif simple:
        simple_detail, simple_status = simple.error_message or "2차 분석에 실패했습니다.", "error"
    else:
        simple_detail, simple_status = "규칙 후보가 되면 소형 모델이 AI 관련도를 검증합니다.", "pending"

    if deep:
        deep_detail, deep_status = "3대 기본조건과 공통기반 사용 여부를 근거 문장으로 검증했습니다.", "complete"
    elif classification and classification.model_name == "rule-gate":
        if deep_result.get("service_scope") == "non_target":
            deep_detail = "검사 범위 비대상으로 심층 LLM 호출 없이 5유형으로 확정했습니다."
        else:
            deep_detail = "비AI 규칙 제외로 심층 LLM 호출 없이 6유형으로 확정했습니다."
        deep_status = "complete"
    elif latest_deep and latest_deep.status == "failed":
        deep_detail, deep_status = latest_deep.error_message or "심층 분석에 실패했습니다.", "error"
    else:
        deep_detail, deep_status = "2차 통과 사업을 대형 모델이 심층 검증합니다.", "pending"

    return [
        {"number": 1, "label": "수집·문서", "status": "complete",
         "detail": f"사업 문서 {len(documents)}건 중 {parsed}건 파싱 완료"},
        {"number": 2, "label": "규칙 선별", "status": "complete",
         "detail": f"{rule.reason} · 후보점수 {rule.score}점"},
        {"number": 3, "label": "2차 AI 검증", "status": simple_status,
         "detail": simple_detail, "model": simple.model_name if simple else None},
        {"number": 4, "label": "3차 기본조건", "status": deep_status,
         "detail": deep_detail, "model": (deep or classification or latest_deep).model_name if (deep or classification or latest_deep) else None},
        {"number": 5, "label": "유형·조치", "status": "complete" if classification else "pending",
         "detail": (
             f"{deep_result.get('classification_code')}유형 · "
             f"{CLASSIFICATION_LABELS.get(str(deep_result.get('classification_code')), '미분류')}"
             if classification else "심층 결과 확정 후 조치 대상을 생성합니다."
         )},
    ]
