from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import BoundedSemaphore, Lock
from typing import Any, Protocol, TypeVar

import httpx
from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..models import ActionItem, AnalysisRun, Notice, NoticeDecision
from ..schemas import DeepAnalysis, Evidence, SimpleAnalysis
from .filter_rules import FilterResult, evaluate_notice


T = TypeVar("T", bound=BaseModel)
Usage = dict[str, int | str | bool]
KST = timezone(timedelta(hours=9))


def _json_object(value: str) -> dict[str, Any]:
    cleaned = value.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.I)
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end < start:
        raise ValueError("LLM 응답에서 JSON 객체를 찾을 수 없습니다.")
    return json.loads(cleaned[start:end + 1])


def _evidence_is_grounded(evidence: list[Evidence], source_text: str) -> bool:
    # 공고명·기관명 같은 공개 메타데이터도 분석 입력의 직접 근거가 될 수 있다.
    compact_source = re.sub(r"\s+", " ", source_text).casefold()
    return all(re.sub(r"\s+", " ", item.quote).casefold() in compact_source for item in evidence)


def validate_grounded(model: T, source_text: str) -> T:
    evidence = getattr(model, "evidence", [])
    if evidence and not _evidence_is_grounded(evidence, source_text):
        raise ValueError("AI 근거 인용이 입력 원문과 일치하지 않습니다.")
    return model


def _first_evidence(text: str, keywords: list[str]) -> Evidence | None:
    document_text = text.split("추출 본문:\n", 1)[-1]
    for line in (part.strip() for part in re.split(r"[\n。]", document_text)):
        if line and any(keyword.casefold() in line.casefold() for keyword in keywords):
            return Evidence(quote=line[:1000], section="추출 본문", interpretation="AI 기능 또는 공통기반 관련 명시")
    return None


def _possible_functions(text: str) -> list[str]:
    mapping = {
        "LLM API": ["llm", "거대언어모델", "생성형 ai", "챗봇"],
        "RAG/공통 참조데이터": ["rag", "검색증강", "벡터db", "지식검색", "질의응답"],
        "GPU inference": ["gpu", "추론 서버", "모델 서빙"],
        "Agent builder": ["ai 에이전트", "업무 에이전트", "에이전트 빌더"],
    }
    folded = text.casefold()
    return [name for name, keywords in mapping.items() if any(key in folded for key in keywords)]


def _truncate_context(context: str, maximum: int) -> str:
    if len(context) <= maximum:
        return context
    marker = "추출 본문:\n"
    if marker not in context:
        return context[:maximum]
    metadata, document = context.split(marker, 1)
    available = max(0, maximum - len(metadata) - len(marker))
    return f"{metadata}{marker}{document[:available]}"


def _usage(model: str, provider: str, prompt: int = 0, completion: int = 0, *, fallback: bool = False) -> Usage:
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "model_name": model,
        "provider": provider,
        "fallback_used": fallback,
    }


class Analyzer(Protocol):
    simple_model_name: str
    deep_model_name: str
    cache_fingerprint: str

    def simple(self, context: str, rule: FilterResult) -> tuple[SimpleAnalysis, Usage]: ...
    def deep(self, context: str, simple: SimpleAnalysis, rule: FilterResult) -> tuple[DeepAnalysis, Usage]: ...


class MockAnalyzer:
    simple_model_name = "mock-deterministic-v1"
    deep_model_name = "mock-deterministic-v1"
    cache_fingerprint = "mock-deterministic-v1"

    def simple(self, context: str, rule: FilterResult) -> tuple[SimpleAnalysis, Usage]:
        relevance = "high" if rule.score >= 55 else "medium" if rule.score >= 20 else "low"
        evidence = _first_evidence(context, rule.matched_include_keywords) if rule.matched_include_keywords else None
        result = SimpleAnalysis(
            ai_relevance=relevance,
            needs_deep_review=not rule.skip and (relevance != "low" or rule.needs_sample_review),
            reason=rule.reason,
            evidence=[evidence] if evidence else [],
            confidence=0.88 if rule.matched_include_keywords else 0.55,
        )
        return result, _usage(self.simple_model_name, "mock")

    def deep(self, context: str, simple: SimpleAnalysis, rule: FilterResult) -> tuple[DeepAnalysis, Usage]:
        folded = context.casefold()
        usage_mentioned = any(key in folded for key in ("범정부 ai 공통기반", "ai 공통기반", "공통 ai 기반"))
        functions = _possible_functions(context)
        evidence_item = _first_evidence(context, rule.matched_include_keywords + ["인공지능", "생성형", "자연어", "머신러닝"])
        if usage_mentioned:
            grade, fit, action, score = "A", "high", "watch", max(70, rule.score)
        elif simple.ai_relevance == "high" and len(functions) >= 2:
            grade, fit, action, score = "B", "high", "contact", min(99, rule.score + 15)
        elif simple.ai_relevance in {"high", "medium"} and functions:
            grade, fit, action, score = "C", "partial", "contact", min(90, rule.score + 10)
        else:
            grade, fit, action, score = "D", "uncertain", "manual_review", max(20, rule.score)
        questions = [] if grade == "A" else ["범정부 AI 공통기반의 제공 기능을 활용할 수 있는지 검토했는지 확인 필요"]
        if "GPU inference" in functions:
            questions.append("별도 GPU 서버 도입 범위와 공통 추론 인프라 대체 가능성을 확인 필요")
        result = DeepAnalysis(
            final_grade=grade,
            ai_relevance=simple.ai_relevance,
            common_platform_fit=fit,
            usage_mentioned="yes" if usage_mentioned else "unclear",
            possible_common_platform_functions=functions,
            summary=(
                "문서에 공통기반 활용 검토가 명시되어 후속 이용 여부를 확인할 대상입니다."
                if usage_mentioned
                else "AI 기능이 확인되며 공통기반 적용 범위는 문서만으로 확정할 수 없어 담당자 확인이 필요합니다."
            ),
            evidence=[evidence_item] if evidence_item else [],
            check_questions=questions,
            recommended_action=action,
            priority_score=score,
            confidence=0.84 if evidence_item else 0.5,
            caveats=["공개 문서만으로 보안등급과 실제 구축환경을 확정할 수 없습니다."],
        )
        return result, _usage(self.deep_model_name, "mock")


@dataclass(frozen=True)
class ChatEndpoint:
    provider: str
    base_url: str
    api_key: str
    model: str
    timeout_seconds: int
    reasoning_effort: str = ""


class OpenAIChatClient:
    """Gemini/OpenAI/NVIDIA의 OpenAI 호환 Chat Completions 최소 공통 어댑터."""

    def __init__(self, endpoint: ChatEndpoint):
        self.endpoint = endpoint

    def call(self, system: str, context: str, schema: type[T]) -> tuple[T, Usage]:
        endpoint = self.endpoint
        payload: dict[str, Any] = {
            "model": endpoint.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": context},
            ],
        }
        if endpoint.provider == "nvidia":
            payload.update({"temperature": 1.0, "top_p": 0.95, "max_tokens": 8_000})
        elif endpoint.provider == "openai":
            payload.update({
                "response_format": {"type": "json_object"},
                "reasoning_effort": endpoint.reasoning_effort or "medium",
                "max_completion_tokens": 8_000,
            })
        else:
            payload.update({"response_format": {"type": "json_object"}, "temperature": 0, "max_tokens": 8_000})

        headers = {"Authorization": f"Bearer {endpoint.api_key}", "Content-Type": "application/json"}
        last_error: Exception | None = None
        with httpx.Client(timeout=endpoint.timeout_seconds) as client:
            for attempt in range(3):
                try:
                    response = client.post(f"{endpoint.base_url}/chat/completions", headers=headers, json=payload)
                    response.raise_for_status()
                    raw = response.json()
                    content = raw["choices"][0]["message"]["content"]
                    if not isinstance(content, str):
                        raise ValueError("LLM 응답 content가 문자열이 아닙니다.")
                    model = schema.model_validate(_json_object(content))
                    validate_grounded(model, context)
                    tokens = raw.get("usage", {})
                    return model, _usage(
                        str(raw.get("model") or endpoint.model),
                        endpoint.provider,
                        int(tokens.get("prompt_tokens", 0)),
                        int(tokens.get("completion_tokens", 0)),
                    )
                except (httpx.HTTPError, ValidationError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
                    last_error = exc
                    if attempt < 2:
                        time.sleep(0.5 * (2**attempt))
        raise RuntimeError(f"{endpoint.provider} LLM 분석 3회 실패: {type(last_error).__name__}") from last_error


class RoutedAnalyzer:
    _semaphores: dict[int, BoundedSemaphore] = {}
    _semaphores_lock = Lock()

    def __init__(self, settings: Settings):
        self.settings = settings
        prompt_root = Path(__file__).resolve().parent.parent / "prompts"
        self.simple_prompt = (prompt_root / "simple_review.md").read_text(encoding="utf-8")
        self.deep_prompt = (prompt_root / "deep_review.md").read_text(encoding="utf-8")
        self.mock = MockAnalyzer()
        self.simple_endpoint = ChatEndpoint(
            settings.stage2_provider,
            settings.stage2_base_url,
            settings.stage2_api_key,
            settings.stage2_model,
            settings.stage2_timeout_seconds,
        )
        self.primary_endpoint = ChatEndpoint(
            settings.stage3_primary_provider,
            settings.stage3_primary_base_url,
            settings.stage3_primary_api_key,
            settings.stage3_primary_model,
            settings.stage3_timeout_seconds,
            settings.stage3_primary_reasoning_effort,
        )
        self.fallback_endpoint = ChatEndpoint(
            settings.stage3_fallback_provider,
            settings.stage3_fallback_base_url,
            settings.stage3_fallback_api_key,
            settings.stage3_fallback_model,
            settings.stage3_timeout_seconds,
        )
        self.simple_model_name = f"{self.simple_endpoint.provider}:{self.simple_endpoint.model}"
        self.deep_model_name = f"{self.primary_endpoint.provider}:{self.primary_endpoint.model}"
        self.cache_fingerprint = hashlib.sha256(
            "|".join((
                self.simple_model_name,
                self.deep_model_name,
                f"{self.fallback_endpoint.provider}:{self.fallback_endpoint.model}",
                self.simple_prompt,
                self.deep_prompt,
            )).encode("utf-8")
        ).hexdigest()
        with self._semaphores_lock:
            self.deep_semaphore = self._semaphores.setdefault(
                settings.stage3_max_concurrency,
                BoundedSemaphore(settings.stage3_max_concurrency),
            )

    def simple(self, context: str, rule: FilterResult) -> tuple[SimpleAnalysis, Usage]:
        scoped = _truncate_context(context, self.settings.stage2_max_input_chars)
        if self.simple_endpoint.provider == "mock":
            return self.mock.simple(scoped, rule)
        return OpenAIChatClient(self.simple_endpoint).call(self.simple_prompt, scoped, SimpleAnalysis)

    def deep(self, context: str, simple: SimpleAnalysis, rule: FilterResult) -> tuple[DeepAnalysis, Usage]:
        scoped = _truncate_context(context, self.settings.stage3_max_input_chars)
        acquired = self.deep_semaphore.acquire(timeout=self.settings.stage3_timeout_seconds)
        if not acquired:
            raise RuntimeError("3차 분석 동시성 대기시간을 초과했습니다.")
        try:
            if self.primary_endpoint.provider == "mock":
                return self.mock.deep(scoped, simple, rule)
            try:
                return OpenAIChatClient(self.primary_endpoint).call(self.deep_prompt, scoped, DeepAnalysis)
            except RuntimeError as primary_error:
                if self.fallback_endpoint.provider == "mock":
                    raise primary_error
                result, usage = OpenAIChatClient(self.fallback_endpoint).call(self.deep_prompt, scoped, DeepAnalysis)
                usage["fallback_used"] = True
                return result, usage
        finally:
            self.deep_semaphore.release()


def get_analyzer(settings: Settings | None = None) -> Analyzer:
    return RoutedAnalyzer(settings or get_settings())


def notice_context(notice: Notice) -> str:
    text = "\n\n".join(attachment.text_excerpt or "" for attachment in notice.attachments)
    filenames = ", ".join(attachment.original_filename for attachment in notice.attachments)
    return f"사업명: {notice.title}\n기관: {notice.agency_name}\n예산: {notice.budget_amount or '미상'}\n첨부: {filenames}\n\n추출 본문:\n{text}"


def _input_hash(context: str, run_type: str, fingerprint: str) -> str:
    return hashlib.sha256(f"{run_type}|{fingerprint}|{context}".encode("utf-8")).hexdigest()


def _stage3_used_today(db: Session) -> int:
    now = datetime.now(timezone.utc)
    local_start = now.astimezone(KST).replace(hour=0, minute=0, second=0, microsecond=0)
    utc_start = local_start.astimezone(timezone.utc)
    return int(db.scalar(select(func.count(AnalysisRun.id)).where(
        AnalysisRun.run_type == "deep_ai",
        AnalysisRun.status == "success",
        AnalysisRun.created_at >= utc_start,
    )) or 0)


def _quota_result(simple: SimpleAnalysis, rule: FilterResult) -> DeepAnalysis:
    return DeepAnalysis(
        final_grade="D",
        ai_relevance=simple.ai_relevance,
        common_platform_fit="uncertain",
        usage_mentioned="unclear",
        summary="오늘의 자동 심층검증 한도에 도달하여 다음 실행 또는 수동 검토가 필요합니다.",
        evidence=[],
        check_questions=["3차 분석 일일 한도 초기화 후 심층검증을 다시 실행할 필요"],
        recommended_action="manual_review",
        priority_score=max(20, rule.score),
        confidence=min(simple.confidence, 0.5),
        caveats=["비용 보호를 위해 3차 LLM 호출을 수행하지 않았습니다."],
    )


def analyze_notice(db: Session, notice: Notice, *, deep: bool = True, force: bool = False) -> DeepAnalysis | SimpleAnalysis:
    settings = get_settings()
    context = notice_context(notice)
    rule = evaluate_notice(
        title=notice.title,
        agency=notice.agency_name,
        budget_amount=notice.budget_amount,
        attachment_names=[item.original_filename for item in notice.attachments],
        text_excerpt=context,
    )
    analyzer = get_analyzer(settings)
    simple_hash = _input_hash(context, "simple_ai", analyzer.cache_fingerprint)
    deep_hash = _input_hash(context, "deep_ai", analyzer.cache_fingerprint)
    requested_type = "deep_ai" if deep else "simple_ai"

    if not force:
        cached = db.scalar(select(AnalysisRun).where(
            AnalysisRun.notice_id == notice.id,
            AnalysisRun.run_type == requested_type,
            AnalysisRun.input_hash == (deep_hash if deep else simple_hash),
            AnalysisRun.status == "success",
        ).order_by(AnalysisRun.id.desc()))
        if cached:
            return (DeepAnalysis if deep else SimpleAnalysis).model_validate_json(cached.result_json)

    active_run_type = "simple_ai"
    try:
        simple_cached = None if force else db.scalar(select(AnalysisRun).where(
            AnalysisRun.notice_id == notice.id,
            AnalysisRun.run_type == "simple_ai",
            AnalysisRun.input_hash == simple_hash,
            AnalysisRun.status == "success",
        ).order_by(AnalysisRun.id.desc()))
        if simple_cached:
            simple = SimpleAnalysis.model_validate_json(simple_cached.result_json)
        else:
            simple, simple_usage = analyzer.simple(context, rule)
            db.add(AnalysisRun(
                notice_id=notice.id,
                run_type="simple_ai",
                model_name=str(simple_usage["model_name"]),
                input_hash=simple_hash,
                status="success",
                result_json=simple.model_dump_json(),
                confidence=simple.confidence,
                cost_prompt_tokens=int(simple_usage["prompt_tokens"]),
                cost_completion_tokens=int(simple_usage["completion_tokens"]),
            ))
        if not deep:
            db.commit()
            return simple

        active_run_type = "deep_ai"
        if not simple.needs_deep_review:
            result = DeepAnalysis(
                final_grade="D",
                ai_relevance=simple.ai_relevance,
                common_platform_fit="uncertain",
                usage_mentioned="unclear",
                summary="규칙상 우선 심층검토 대상은 아니며 표본 검토가 필요합니다.",
                evidence=[],
                check_questions=["AI 기능 포함 여부를 담당자가 표본 확인할 필요"],
                recommended_action="manual_review",
                priority_score=rule.score,
                confidence=simple.confidence,
                caveats=["자동 제외가 아닌 낮은 우선순위 후보입니다."],
            )
            deep_usage = _usage("rule-gate", "local")
            deep_status = "skipped"
        elif _stage3_used_today(db) >= settings.stage3_daily_limit:
            result = _quota_result(simple, rule)
            deep_usage = _usage("daily-quota-guard", "local")
            deep_status = "skipped"
        else:
            result, deep_usage = analyzer.deep(context, simple, rule)
            deep_status = "success"

        db.add(AnalysisRun(
            notice_id=notice.id,
            run_type="deep_ai",
            model_name=str(deep_usage["model_name"]),
            input_hash=deep_hash,
            status=deep_status,
            result_json=result.model_dump_json(),
            confidence=result.confidence,
            cost_prompt_tokens=int(deep_usage["prompt_tokens"]),
            cost_completion_tokens=int(deep_usage["completion_tokens"]),
            error_message="primary provider failed; fallback used" if deep_usage.get("fallback_used") else None,
        ))
        decision = notice.decision or NoticeDecision(notice_id=notice.id)
        decision.final_grade = result.final_grade
        decision.ai_relevance = result.ai_relevance
        decision.common_platform_fit = result.common_platform_fit
        decision.usage_mentioned = result.usage_mentioned
        decision.priority_score = result.priority_score
        decision.recommended_action = result.recommended_action
        decision.summary = result.summary
        decision.possible_functions_json = json.dumps(result.possible_common_platform_functions, ensure_ascii=False)
        decision.key_evidence_json = json.dumps([item.model_dump() for item in result.evidence], ensure_ascii=False)
        decision.check_questions_json = json.dumps(result.check_questions, ensure_ascii=False)
        decision.caveats_json = json.dumps(result.caveats, ensure_ascii=False)
        if notice.decision is None:
            db.add(decision)
        if notice.action is None:
            db.add(ActionItem(notice_id=notice.id))
        db.commit()
        return result
    except Exception as exc:
        db.rollback()
        db.add(AnalysisRun(
            notice_id=notice.id,
            run_type=active_run_type,
            model_name=analyzer.deep_model_name if active_run_type == "deep_ai" else analyzer.simple_model_name,
            input_hash=deep_hash if active_run_type == "deep_ai" else simple_hash,
            status="failed",
            error_message=f"{type(exc).__name__}: {str(exc)[:1000]}",
        ))
        db.commit()
        raise
