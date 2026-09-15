from __future__ import annotations

import json
from urllib.parse import quote_plus

from ..models import AnalysisRun, Notice
from .analyzer import CLASSIFICATION_LABELS, is_current_deep_result
from .attachment_policy import select_preferred_documents
from .filter_rules import evaluate_notice


ACTION_REQUIRED_CODES = {"2", "3", "4"}


def json_object(value: str | None) -> dict:
    try:
        parsed = json.loads(value or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


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


def g2b_opinion_url(notice: Notice) -> str | None:
    """Build the official G2B pre-notice detail/opinion route from the public API id."""
    if notice.stage != "prenotice":
        return notice.url
    payload = json_object(notice.raw_payload_json)
    registration_no = payload.get("bfSpecRgstNo") or notice.notice_no
    if not registration_no:
        return notice.url
    return (
        "https://www.g2b.go.kr/link/PNPE027_01/single/"
        f"?bfSpecRgstNo={quote_plus(str(registration_no))}"
    )


def finding_details(result: dict) -> list[dict]:
    """Translate gate results into operator-facing findings and required checks."""
    findings: list[dict] = []
    network = result.get("network_scope", "unclear")
    task = result.get("task_scope", "unclear")
    model = result.get("model_fit", "unclear")
    usage = result.get("platform_usage", "unclear")
    remediation = result.get("remediation_feasibility", "unclear")

    if network not in {"internal_or_connected", "hybrid"}:
        findings.append({
            "gate": "망·데이터",
            "problem": "내부·업무망 또는 연계망에서 처리되는 서비스인지 확인되지 않았습니다."
            if network == "unclear" else "인터넷망에서 완결되는 서비스로 분석되었습니다.",
            "action": "처리 데이터의 위치와 내부망 연계 범위를 명시하도록 요청합니다.",
        })
    if task not in {"government", "delegated_government"}:
        findings.append({
            "gate": "국가사무",
            "problem": "국가사무 또는 위탁 국가사무라는 근거가 확인되지 않았습니다."
            if task == "unclear" else "기관 자체 내부업무 또는 비국가사무로 분석되었습니다.",
            "action": "법령·위임·위탁 근거와 실제 수행 사무의 범위를 확인합니다.",
        })
    if model != "platform_llm_or_rag":
        findings.append({
            "gate": "모델·기능",
            "problem": "공통기반의 LLM·RAG로 처리 가능한지 확인되지 않았습니다."
            if model == "unclear" else "독자모델 또는 풀파인튜닝 요구로 별도 협의가 필요합니다.",
            "action": "공통기반 제공 모델·RAG로 대체 가능한 범위를 명시하도록 요청합니다.",
        })
    if usage != "uses" and result.get("classification_code") in {"2", "3"}:
        findings.append({
            "gate": "공통기반 활용",
            "problem": "기본조건 충족 가능성이 있으나 공통기반 활용이 반영되지 않았습니다.",
            "action": "사전규격에 공통기반 활용 범위와 연계 방식을 반영하도록 의견을 냅니다.",
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
    return {
        "classification_code": code or None,
        "classification_label": CLASSIFICATION_LABELS.get(code, "미분류"),
        "result": result,
        "findings": findings,
        "issue_labels": list(dict.fromkeys(item["gate"] for item in findings)),
        "guidance_message": result.get("guidance_message", ""),
        "action_required": code in ACTION_REQUIRED_CODES,
        "action_status": notice.action.status if notice.action else "new",
        "opinion_url": g2b_opinion_url(notice),
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
        deep_detail, deep_status = "비AI 규칙 제외로 심층 LLM 호출 없이 6유형으로 확정했습니다.", "complete"
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
