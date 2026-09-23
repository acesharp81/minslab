from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import time
from datetime import datetime, date
from threading import Lock
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..models import AnalysisRun, Notice


logger = logging.getLogger(__name__)

JEV_RUN_TYPE = "jev_shadow"
JEV_SCHEMA_VERSION = "poc08-jev-shadow-v2-jevai"
_circuit_lock = Lock()
_retry_after_monotonic = 0.0
_authentication_rejected = False
_EMAIL = re.compile(r"(?i)(?<![A-Z0-9._%+-])[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}")
_PHONE = re.compile(r"(?<!\d)(?:0\d{1,2}[-.\s]?\d{3,4}[-.\s]?\d{4})(?!\d)")
_CONTACT_LINE = re.compile(
    r"(?im)^[ \t]*(?:계약|업무|사업)?담당자[ \t]*[:：\t][^\n]*$|"
    r"^[ \t]*(?:연락처|전화번호|휴대전화|핸드폰|이메일|전자우편|팩스|FAX)[ \t]*[:：\t][^\n]*$"
)
BUSINESS_TYPES = {
    "ai_service",
    "ai_related_out_of_scope",
    "non_ai_service",
    "uncertain",
}

BUSINESS_TYPE_CRITERIA = {
    "ai_service": (
        "AI 기능을 이용자가 실제 사용하는 서비스·정보시스템으로 직접 구축, 개발, 고도화, "
        "운영하거나 그 구축을 직접 준비하는 BPR·ISP·ISMP·연구용역"
    ),
    "ai_related_out_of_scope": (
        "AI 교육, 행사, 홍보, 단순 자문·감리, 데이터 구매·가공처럼 AI와 관련은 있지만 "
        "AI 서비스 구축 자체가 목적은 아닌 사업"
    ),
    "non_ai_service": "AI 서비스 또는 AI 기능의 직접 구축·개발·고도화와 무관한 사업",
    "uncertain": "제공된 문서가 부족하거나 서로 충돌해 위 범주를 신뢰성 있게 결정할 수 없음",
}


def _finite_probability(value: Any, *, field: str) -> float:
    number = float(value)
    if not math.isfinite(number) or not 0 <= number <= 1:
        raise ValueError(f"{field}는 0~1 사이의 유한한 값이어야 합니다.")
    return number


def _scoped_context(context: str, settings: Settings) -> str:
    # JevAI caps the full JSON body at 32 KiB, including Korean UTF-8 text.
    scoped = context[:settings.jev_max_input_chars]
    scoped = _CONTACT_LINE.sub("[담당자 연락정보 생략]", scoped)
    scoped = _EMAIL.sub("[이메일 생략]", scoped)
    scoped = _PHONE.sub("[전화번호 생략]", scoped)
    return scoped.encode("utf-8")[:24_576].decode("utf-8", "ignore")


def jev_shadow_state(settings: Settings) -> str:
    if not settings.jev_shadow_enabled:
        return "disabled"
    if not settings.jev_api_key:
        return "missing_key"
    if settings.jev_shadow_end_date:
        try:
            if datetime.now(ZoneInfo(settings.app_timezone)).date() > date.fromisoformat(settings.jev_shadow_end_date):
                return "expired"
        except ValueError:
            return "invalid_end_date"
    with _circuit_lock:
        if _authentication_rejected:
            return "authentication_rejected"
        if time.monotonic() < _retry_after_monotonic:
            return "rate_limited"
    return "ready"


def _note_api_failure(exc: Exception) -> None:
    global _retry_after_monotonic, _authentication_rejected
    if not isinstance(exc, httpx.HTTPStatusError):
        return
    with _circuit_lock:
        if exc.response.status_code in {401, 403}:
            _authentication_rejected = True
        elif exc.response.status_code == 429:
            try:
                seconds = float(exc.response.headers.get("retry-after", "900"))
            except ValueError:
                seconds = 900.0
            _retry_after_monotonic = time.monotonic() + max(60.0, min(seconds, 3600.0))


def _payload(context: str, settings: Settings) -> dict[str, Any]:
    return {
        "model": settings.jev_model,
        "state": _scoped_context(context, settings),
        "questions": {
            "business_type": {
                "type": "choice",
                "instructions": (
                    "조달 공고의 실제 과업 목적을 기준으로 분류하세요. 제목의 AI 키워드만으로 "
                    "판단하지 말고, 구축 대상과 산출물 및 이용자가 사용할 기능을 함께 보세요."
                ),
                "criteria": BUSINESS_TYPE_CRITERIA,
            },
            "needs_deep_review": {
                "type": "noul",
                "instructions": (
                    "이 사업이 범정부 AI 공통기반 적용 가능성을 판정하기 위한 망·업무·모델·현행 "
                    "플랫폼 사용 여부의 심층 검토 대상입니까?"
                ),
                "criteria": {
                    "true": "AI 서비스 구축 사업이거나 자료가 불명확해 심층 확인이 필요함",
                    "false": "비AI 사업 또는 명확한 적용범위 외 사업이라 심층 확인이 불필요함",
                },
            },
        },
    }


def evaluate_jev_shadow(
    context: str,
    settings: Settings | None = None,
    *,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Run the JevAI community Decisions API and normalize its response."""
    settings = settings or get_settings()
    if not settings.jev_api_key:
        raise RuntimeError("JEV_API_KEY가 설정되지 않았습니다.")

    owned_client = client is None
    active_client = client or httpx.Client(timeout=settings.jev_timeout_seconds)
    try:
        response = active_client.post(
            f"{settings.jev_base_url}/api/v1/decisions",
            headers={
                "Authorization": f"Bearer {settings.jev_api_key}",
                "Content-Type": "application/json",
            },
            json=_payload(context, settings),
        )
        response.raise_for_status()
        raw = response.json()
    finally:
        if owned_client:
            active_client.close()

    if not isinstance(raw, dict) or raw.get("code") != 0:
        raise ValueError(f"JevAI 응답 실패: {str(raw.get('message', 'invalid response'))[:160] if isinstance(raw, dict) else 'invalid response'}")
    data = raw.get("data")
    if not isinstance(data, dict):
        raise ValueError("JevAI 응답에 data 객체가 없습니다.")
    answers = data.get("answers")
    if not isinstance(answers, dict):
        raise ValueError("JEV 응답에 answers 객체가 없습니다.")
    business = answers.get("business_type")
    deep = answers.get("needs_deep_review")
    if not isinstance(business, dict) or business.get("type") != "choice":
        raise ValueError("JEV business_type 응답 형식이 올바르지 않습니다.")
    if not isinstance(deep, dict) or deep.get("type") != "noul":
        raise ValueError("JEV needs_deep_review 응답 형식이 올바르지 않습니다.")

    choice = str(business.get("choice") or "")
    if choice not in BUSINESS_TYPES:
        raise ValueError(f"알 수 없는 JEV 사업 분류: {choice}")
    probabilities = business.get("probabilities")
    if not isinstance(probabilities, dict):
        raise ValueError("JEV business_type 확률 분포가 없습니다.")
    normalized_probabilities = {
        key: _finite_probability(value, field=f"probabilities.{key}")
        for key, value in probabilities.items()
        if key in BUSINESS_TYPES
    }
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    return {
        "schema_version": JEV_SCHEMA_VERSION,
        "provider": "jevai",
        "model": str(data.get("model") or settings.jev_model),
        "business_type": choice,
        "business_type_confidence": _finite_probability(
            business.get("confidence"), field="business_type.confidence",
        ),
        "business_type_probabilities": normalized_probabilities,
        "needs_deep_review_probability": _finite_probability(
            deep.get("noul"), field="needs_deep_review.noul",
        ),
        "usage": {
            "input_tokens": int(usage.get("input_tokens") or 0),
            "output_tokens": int(usage.get("output_tokens") or 0),
        },
    }


def record_jev_shadow(
    db: Session,
    notice: Notice,
    context: str,
    *,
    reference_business_type: str,
    reference_needs_deep_review: bool,
    reference_ai_relevance: str,
    settings: Settings | None = None,
) -> bool:
    """Persist a non-blocking shadow classification without changing production output."""
    settings = settings or get_settings()
    if jev_shadow_state(settings) != "ready":
        return False

    fingerprint = f"{JEV_SCHEMA_VERSION}|{settings.jev_base_url}|{settings.jev_model}"
    input_hash = hashlib.sha256(
        f"{JEV_RUN_TYPE}|{fingerprint}|{_scoped_context(context, settings)}".encode("utf-8")
    ).hexdigest()
    existing = db.scalar(select(AnalysisRun.id).where(
        AnalysisRun.notice_id == notice.id,
        AnalysisRun.run_type == JEV_RUN_TYPE,
        AnalysisRun.input_hash == input_hash,
        AnalysisRun.status == "success",
    ).limit(1))
    if existing:
        return False

    started = time.monotonic()
    try:
        result = evaluate_jev_shadow(context, settings)
        jev_needs_deep = result["needs_deep_review_probability"] >= 0.5
        result.update({
            "latency_ms": round((time.monotonic() - started) * 1000),
            "reference": {
                "business_type": reference_business_type,
                "needs_deep_review": reference_needs_deep_review,
                "ai_relevance": reference_ai_relevance,
            },
            "agreement": result["business_type"] == reference_business_type,
            "deep_review_agreement": jev_needs_deep == reference_needs_deep_review,
            "record_only": True,
        })
        usage = result["usage"]
        db.add(AnalysisRun(
            notice_id=notice.id,
            run_type=JEV_RUN_TYPE,
            model_name=f"jevai:{result['model']}",
            input_hash=input_hash,
            status="success",
            result_json=json.dumps(result, ensure_ascii=False),
            confidence=result["business_type_confidence"],
            cost_prompt_tokens=usage["input_tokens"],
            cost_completion_tokens=usage["output_tokens"],
        ))
    except Exception as exc:  # Shadow failures must never interrupt the production classifier.
        _note_api_failure(exc)
        logger.warning("JEV 병행 분류를 기록하지 못했습니다: %s", exc)
        db.add(AnalysisRun(
            notice_id=notice.id,
            run_type=JEV_RUN_TYPE,
            model_name=f"jevai:{settings.jev_model}",
            input_hash=input_hash,
            status="failed",
            result_json="{}",
            error_message=f"{type(exc).__name__}: {str(exc)[:1000]}",
        ))
    return True
