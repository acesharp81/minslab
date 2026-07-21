from __future__ import annotations

import json
import os
import threading
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .collectors import NewsCollector, case_excluded_match, organization_candidate_match, quick_candidate_match
from .config import Settings
from .kakao import KakaoClient
from .matching import article_topic_fields, expanded_case_terms, term_in_text
from .press_releases import PressReleaseManager
from .scoring import GroqError, OpenRouterError, RelevanceEngine, calibrated_semantic_score, case_retrieval_text, cosine_similarity
from .storage import KST, Store, now_iso
from .supabase_mirror import SupabaseMirror


COLLECTION_LOCK = threading.Lock()
COMMON_LLM_LOCK = threading.Lock()
LOCAL_EMBEDDING_LOCK = threading.Lock()
REMOTE_CASE_SEMAPHORE = threading.BoundedSemaphore(2)
DELIVERY_LOCK = threading.Lock()


def parse_clock(value: str) -> tuple[int, int] | None:
    try:
        hour_text, minute_text = str(value).strip().split(":", 1)
        hour, minute = int(hour_text), int(minute_text)
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return hour, minute
    except (ValueError, TypeError):
        pass
    return None


def next_time_slot(values: list[str], now: datetime | None = None) -> datetime:
    current = now or datetime.now(KST)
    slots = [slot for value in values if (slot := parse_clock(value))]
    if not slots:
        return current
    candidates = [current.replace(hour=hour, minute=minute, second=0, microsecond=0) for hour, minute in slots]
    future = [candidate for candidate in candidates if candidate > current]
    return min(future) if future else min(candidates) + timedelta(days=1)


def next_collection_at(case: dict, now: datetime | None = None) -> str:
    current = now or datetime.now(KST)
    if case.get("collection_mode") == "times":
        return next_time_slot(case.get("collection_times", []), current).isoformat(timespec="seconds")
    minutes = max(1, int(case.get("collection_interval_minutes", 30)))
    return (current + timedelta(minutes=minutes)).isoformat(timespec="seconds")


def delivery_at(case: dict, urgent: bool, now: datetime | None = None) -> str:
    current = now or datetime.now(KST)
    if urgent or case.get("send_relevant_immediately", True) or case.get("delivery_mode") == "immediate":
        return current.isoformat(timespec="seconds")
    return next_time_slot(case.get("delivery_times", []), current).isoformat(timespec="seconds")


def publisher_allowed(case: dict, publisher: str) -> bool:
    target = str(publisher or "").casefold()
    included = [str(value).casefold() for value in case.get("include_publishers", []) if str(value).strip()]
    excluded = [str(value).casefold() for value in case.get("exclude_publishers", []) if str(value).strip()]
    if excluded and any(value in target for value in excluded):
        return False
    return not included or any(value in target for value in included)


NEGATIVE_CASE_HINTS = ("부정", "비판", "비난", "시정요구", "문제 제기", "논란", "책임", "질타")
NEGATIVE_ARTICLE_HINTS = (
    "비판", "비난", "논란", "질타", "지적", "문제", "부실", "책임", "반발", "우려",
    "시정", "감사", "징계", "고발", "수사", "의혹", "불만", "실패", "늑장", "혼선",
)


def _case_has_negative_intent(case: dict) -> bool:
    text = " ".join([
        str(case.get("name") or ""),
        str(case.get("topic_search_prompt") or ""),
        str(case.get("topic_description") or ""),
    ]).casefold()
    return any(value in text for value in NEGATIVE_CASE_HINTS)


def _article_has_negative_signal(article: dict, analysis: dict | None = None) -> bool:
    if str((analysis or {}).get("tone") or "") == "부정적":
        return True
    text = " ".join([
        *article_topic_fields(article),
        str((analysis or {}).get("summary") or ""),
        " ".join(str(value) for value in (analysis or {}).get("classification_tags", [])),
        " ".join(str(value) for value in (analysis or {}).get("topic_concepts", [])),
    ]).casefold()
    return any(value in text for value in NEGATIVE_ARTICLE_HINTS)


def case_candidate_gate(case: dict, article: dict, analysis: dict | None,
                        semantic_score: float, semantic_threshold: float) -> tuple[bool, str]:
    """Cheap deterministic gate before spending a case-judgment LLM call."""
    if not publisher_allowed(case, article.get("publisher", "")):
        return False, "publisher_filtered"
    if case_excluded_match(case, article):
        return False, "exclude_terms_matched"

    common_text = " ".join([
        str((analysis or {}).get("summary") or ""),
        str((analysis or {}).get("article_type") or ""),
        str((analysis or {}).get("tone") or ""),
        " ".join(str(value) for value in (analysis or {}).get("classification_tags", [])),
        " ".join(str(value) for value in (analysis or {}).get("entities", [])),
        " ".join(str(value) for value in (analysis or {}).get("topic_concepts", [])),
    ])
    fields = (*article_topic_fields(article), common_text)
    expanded = expanded_case_terms(case)

    def matched(term: str) -> bool:
        return any(term_in_text(variant, field) for variant in expanded.get(term, [term]) for field in fields)

    required = [str(value).strip() for value in case.get("required_terms", []) if str(value).strip()]
    missing_required = [term for term in required if not matched(term)]
    if missing_required:
        return False, "required_terms_missing"

    included = [str(value).strip() for value in case.get("include_terms", []) if str(value).strip()]
    include_matched = any(matched(term) for term in included)
    high_semantic_rescue = max(80.0, float(semantic_threshold) + 25.0)
    if included and not include_matched and float(semantic_score) < high_semantic_rescue:
        return False, "include_terms_missing"

    if not included and not required and _case_has_negative_intent(case):
        if not _article_has_negative_signal(article, analysis) and float(semantic_score) < high_semantic_rescue:
            return False, "negative_signal_missing"

    keyword_candidate = quick_candidate_match(case, article)
    if keyword_candidate or float(semantic_score) >= float(semantic_threshold):
        return True, "keyword_or_semantic_candidate"
    return False, "semantic_below_threshold"


class MasterPressService:
    def __init__(self, settings: Settings, store: Store):
        self.settings = settings
        self.store = store
        self.collector = NewsCollector(settings)
        self.scoring = RelevanceEngine(settings, store)
        self.scoring.ollama.embedding_model = self.selected_embedding_model()
        self.mirror = SupabaseMirror(settings)
        self.press_releases = PressReleaseManager(settings, store, self.scoring.ollama, self.mirror)
        self.kakao = KakaoClient(settings, store)
        self.recovered_llm_jobs = self.store.activate_worker_session(str(os.getpid()))
        self.recovered_pipeline_jobs = self.store.recover_incomplete_pipeline_jobs()
        self.recovered_llm_jobs += sum(self.recovered_pipeline_jobs.values())

    def selected_common_llm_model(self) -> str:
        default = getattr(getattr(self, "settings", None), "groq_common_model", "llama-3.1-8b-instant")
        return self.store.get_setting("common_llm_model", default)

    def selected_llm_model(self) -> str:
        """Backward-compatible name for the shared analysis model."""
        return self.selected_common_llm_model()

    def selected_case_llm_model(self) -> str:
        default = getattr(getattr(self, "settings", None), "openrouter_case_model", "google/gemma-4-26b-a4b-it:free")
        return self.store.get_setting("case_llm_model", default)

    def selected_reserve1_model(self) -> str:
        default = getattr(getattr(self, "settings", None), "worker_ai_model", "@cf/google/gemma-4-26b-a4b-it")
        return self.store.get_setting("reserve1_llm_model", default)

    def selected_reserve2_model(self) -> str:
        default = getattr(getattr(self, "settings", None), "gemini_model", "gemini-3.5-flash-lite")
        return self.store.get_setting("reserve2_llm_model", default)

    def selected_case_batch_size(self) -> int:
        try:
            return max(1, min(10, int(self.store.get_setting("case_batch_size", "10"))))
        except ValueError:
            return 10

    def selected_embedding_model(self) -> str:
        default = getattr(getattr(self, "settings", None), "embedding_model", "nomic-embed-text:latest")
        return self.store.get_setting("embedding_model", default)

    def available_common_llm_models(self) -> list[str]:
        try:
            return self.scoring.common_llm.models()
        except Exception:
            return [self.selected_common_llm_model()] if self.selected_common_llm_model() else []

    def available_llm_models(self) -> list[str]:
        return self.available_common_llm_models()

    def available_case_llm_models(self) -> list[str]:
        try:
            return self.scoring.case_llm.models()
        except Exception:
            return [self.selected_case_llm_model()] if self.selected_case_llm_model() else []

    def available_reserve1_models(self) -> list[str]:
        models = [self.selected_reserve1_model(), getattr(self.settings, "worker_ai_model", "@cf/google/gemma-4-26b-a4b-it")]
        return list(dict.fromkeys(value for value in models if value))

    def available_reserve2_models(self) -> list[str]:
        models = [self.selected_reserve2_model(), getattr(self.settings, "gemini_model", "gemini-3.5-flash-lite"), "gemini-3.5-flash", "gemini-3.1-flash-lite"]
        return list(dict.fromkeys(value for value in models if value))

    def available_embedding_models(self) -> list[str]:
        try:
            return self.scoring.ollama.embedding_models()
        except Exception:
            return [self.selected_embedding_model()] if self.selected_embedding_model() else []

    def groq_status(self, probe: bool = False) -> dict:
        since = (datetime.now(KST) - timedelta(hours=24)).isoformat(timespec="seconds")
        usage = self.store.provider_usage_since(
            "groq", since, self.settings.groq_daily_request_soft_limit, self.settings.groq_daily_token_soft_limit, "common"
        )
        status = self.scoring.common_llm.key_status() if probe else {"connected": bool(self.settings.groq_api_key)}
        reset_at = self.store.get_setting("llm_provider_reset_at:groq", "")
        raw = self.store.get_setting("llm_provider_reset_raw:groq", "")
        result = {**status, **usage, "model": self.selected_common_llm_model(), "provider": "groq",
                  "period": "rolling 24h", "day_start": since, "reset_basis": "Groq rate-limit header",
                  "reset_at": reset_at, "reset_label": "Groq 응답 헤더 기준" + (f" · {raw}" if raw else " · 최근 응답 대기")}
        return self._attach_provider_guard(result)

    def openrouter_status(self, probe: bool = False) -> dict:
        usage = self.store.openrouter_usage_today(self.settings.openrouter_daily_soft_limit)
        status = self.scoring.case_llm.key_status() if probe else {"connected": bool(self.settings.openrouter_api_key)}
        result = {**status, **usage, "model": self.selected_case_llm_model(), "provider": "openrouter", "reset_basis": "UTC 00:00", "reset_at": self._utc_day_window_kst()[1], "reset_label": "한국시간 09:00"}
        return self._attach_provider_guard(result)

    def cloudflare_status(self, probe: bool = False) -> dict:
        since, reset_at = self._utc_day_window_kst()
        usage = self.store.provider_usage_since("cloudflare", since, getattr(self.settings, "worker_ai_daily_request_soft_limit", 3000), 0)
        has_key = bool(getattr(self.settings, "worker_ai_key", ""))
        has_account = bool(getattr(self.settings, "worker_ai_account_id", ""))
        connected = bool(has_key and has_account)
        if probe:
            status = self.scoring.reserve1_llm.key_status()
        else:
            status = {"connected": connected, "error": "" if connected else ("Cloudflare API 키 미설정" if not has_key else "Cloudflare Account ID 미설정")}
        result = {**status, **usage, "model": self.selected_reserve1_model(), "provider": "cloudflare",
                  "neuron_soft_limit": getattr(self.settings, "worker_ai_daily_neuron_soft_limit", 10000),
                  "reset_basis": "UTC 00:00", "reset_at": reset_at,
                  "reset_label": "한국시간 09:00"}
        return self._attach_provider_guard(result)

    def gemini_status(self, probe: bool = False) -> dict:
        since, reset_at = self._pacific_day_window_kst()
        usage = self.store.provider_usage_since("gemini", since, getattr(self.settings, "gemini_daily_request_soft_limit", 1000), getattr(self.settings, "gemini_daily_token_soft_limit", 0))
        status = self.scoring.reserve2_llm.key_status() if probe else {"connected": bool(getattr(self.settings, "gemini_api_key", ""))}
        pacific_name = datetime.now(ZoneInfo("America/Los_Angeles")).tzname() or "PT"
        result = {**status, **usage, "model": self.selected_reserve2_model(), "provider": "gemini",
                  "reset_basis": "Pacific 00:00", "reset_at": reset_at,
                  "reset_label": f"한국시간 {datetime.fromisoformat(reset_at).astimezone(KST).strftime('%H:%M')}"}
        return self._attach_provider_guard(result)

    def ollama_embedding_status(self, probe: bool = False) -> dict:
        selected = self.selected_embedding_model()
        models = self.available_embedding_models() if probe else ([selected] if selected else [])
        usage = self.store.provider_usage_today("ollama", "embedding", 0)
        total_usage = self.store.provider_usage_total("ollama", "embedding")
        day_start = str(usage.get("day_start") or "")
        with self.store.connect() as connection:
            inferred = connection.execute(
                "SELECT (SELECT COUNT(*) FROM article_embeddings WHERE updated_at>=?) + "
                "(SELECT COUNT(*) FROM case_embeddings WHERE updated_at>=?) value",
                (day_start, day_start),
            ).fetchone()
        usage["embedding_outputs_today"] = int(inferred["value"] or 0) if inferred else 0
        usage["total_attempts"] = int(total_usage.get("attempts") or 0)
        usage["total_completed"] = int(total_usage.get("completed") or 0)
        usage["total_failed"] = int(total_usage.get("failed") or 0)
        return {
            "connected": bool(models), "provider": "ollama", "model": selected,
            "models": models, "probed": bool(probe), **usage,
        }

    @staticmethod
    def _next_kst_midnight_iso() -> str:
        now = datetime.now(KST)
        return (now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)).isoformat(timespec="seconds")

    @staticmethod
    def _utc_day_window_kst() -> tuple[str, str]:
        now = datetime.now(timezone.utc)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        return start.astimezone(KST).isoformat(timespec="seconds"), end.astimezone(KST).isoformat(timespec="seconds")

    @staticmethod
    def _pacific_day_window_kst() -> tuple[str, str]:
        pacific = ZoneInfo("America/Los_Angeles")
        now = datetime.now(pacific)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        return start.astimezone(KST).isoformat(timespec="seconds"), end.astimezone(KST).isoformat(timespec="seconds")

    def _provider_disabled_until(self, provider: str) -> str:
        return self.store.get_setting(f"llm_provider_disabled_until:{provider}", "")

    def _mark_provider_exhausted(self, provider: str, retry_after: str = "", reason: str = "") -> None:
        retry_after = retry_after or self._provider_reset_at(provider)
        self.store.set_setting(f"llm_provider_disabled_until:{provider}", retry_after)
        self.store.set_setting(f"llm_provider_disabled_reason:{provider}", str(reason)[:300])

    def _provider_reset_at(self, provider: str) -> str:
        if provider in {"cloudflare", "openrouter"}:
            return self._utc_day_window_kst()[1]
        if provider == "gemini":
            return self._pacific_day_window_kst()[1]
        if provider == "groq":
            return self.store.get_setting("llm_provider_reset_at:groq", "") or (datetime.now(KST) + timedelta(hours=24)).isoformat(timespec="seconds")
        return self._next_kst_midnight_iso()

    def _attach_provider_guard(self, status: dict) -> dict:
        provider = str(status.get("provider") or "")
        disabled_until = self._provider_disabled_until(provider) if provider else ""
        status["disabled_until"] = disabled_until
        status["disabled_reason"] = self.store.get_setting(f"llm_provider_disabled_reason:{provider}", "") if provider else ""
        status["exhausted"] = bool(disabled_until and disabled_until > now_iso())
        if int(status.get("soft_limit") or 0) and int(status.get("attempts") or 0) >= int(status.get("soft_limit") or 0):
            status["exhausted"] = True
        if int(status.get("token_soft_limit") or 0) and int(status.get("tokens") or 0) >= int(status.get("token_soft_limit") or 0):
            status["exhausted"] = True
        status["available"] = bool(status.get("connected") and not status.get("exhausted"))
        return status

    @staticmethod
    def _is_provider_quota_error(error: Exception) -> bool:
        lowered = str(error or "").casefold()
        return str(error) in {"groq_daily_request_soft_limit", "groq_daily_token_soft_limit", "openrouter_daily_soft_limit",
                              "cloudflare_daily_request_soft_limit", "gemini_daily_request_soft_limit", "gemini_daily_token_soft_limit"} or any(
            marker in lowered for marker in ("quota", "rate limit exceeded", "free-models-per-day", "daily_soft_limit",
                                             "neurons", "allocation", "resource_exhausted", "token_soft_limit")
        )

    @staticmethod
    def _is_common_daily_limit(error: Exception) -> bool:
        return MasterPressService._is_provider_quota_error(error)

    def _remote_provider_chain(self, include_openrouter: bool = False) -> list[tuple[str, str]]:
        chain = []
        if include_openrouter:
            chain.append(("openrouter", self.selected_case_llm_model()))
        chain.extend([("cloudflare", self.selected_reserve1_model()), ("gemini", self.selected_reserve2_model())])
        return [(provider, model) for provider, model in chain if model and not (self._provider_disabled_until(provider) and self._provider_disabled_until(provider) > now_iso())]

    def _remember_provider_failure(self, provider: str, error: Exception) -> None:
        if isinstance(error, OpenRouterError) and self._is_provider_quota_error(error):
            reason = str(error)
            lowered = reason.casefold()
            daily_like = any(marker in lowered for marker in ("free-models-per-day", "daily_soft_limit", "daily request", "daily token", "resource_exhausted", "quota"))
            retry_after = self._provider_reset_at(provider) if daily_like else (error.retry_after or self._provider_reset_at(provider))
            self._mark_provider_exhausted(provider, retry_after, reason)

    def _try_common_reserve(self, article: dict) -> tuple[str, str, dict]:
        last_error: Exception | None = None
        for provider, model in self._remote_provider_chain(include_openrouter=False):
            try:
                return provider, model, self.scoring.analyze_article_common_with_provider(provider, article, model)
            except json.JSONDecodeError as error:
                last_error = error
                continue
            except OpenRouterError as error:
                last_error = error
                self._remember_provider_failure(provider, error)
                continue
        if last_error:
            raise last_error
        raise OpenRouterError("reserve_llm_unavailable", status=503, retryable=True, retry_after=self._next_kst_midnight_iso(), deferred=True)

    def _evaluate_cases_with_provider_chain(self, cases: list[dict], article: dict, analysis: dict) -> tuple[str, str, dict[str, dict]]:
        last_error: Exception | None = None
        for provider, model in self._remote_provider_chain(include_openrouter=True):
            try:
                if hasattr(self.scoring, "evaluate_cases_with_common_provider"):
                    results = self.scoring.evaluate_cases_with_common_provider(provider, cases, article, analysis, model)
                elif provider == "openrouter" and hasattr(self.scoring, "evaluate_cases_with_common"):
                    results = self.scoring.evaluate_cases_with_common(cases, article, analysis, model)
                else:
                    raise OpenRouterError(f"{provider}_client_unavailable", status=503, retryable=True)
                return provider, model, results
            except OpenRouterError as error:
                last_error = error
                self._remember_provider_failure(provider, error)
                if self._is_provider_quota_error(error) or error.status in {408, 429, 500, 502, 503, 504}:
                    continue
                raise
            except json.JSONDecodeError as error:
                last_error = error
                continue
        if last_error:
            raise last_error
        raise OpenRouterError("case_llm_providers_unavailable", status=503, retryable=True, retry_after=self._next_kst_midnight_iso(), deferred=True)

    def pipeline_provider_status(self) -> dict:
        common = {**self.groq_status(False), "concurrency": 1}
        reserve1 = self.cloudflare_status(False)
        reserve2 = self.gemini_status(False)
        case = {**self.openrouter_status(False), "concurrency": 1, "burst_concurrency": 2, "burst_threshold": 10, "batch_size": self.selected_case_batch_size()}
        common_daily_exhausted = int(common.get("attempts") or 0) >= int(common.get("soft_limit") or 0)
        common_token_exhausted = bool(int(common.get("token_soft_limit") or 0) and int(common.get("tokens") or 0) >= int(common.get("token_soft_limit") or 0))
        if common_daily_exhausted or common_token_exhausted:
            fallback = next((item for item in (reserve1, reserve2) if item.get("available")), {})
            common["fallback_provider"] = fallback.get("provider", "")
            common["fallback_active"] = bool(fallback)
            common["fallback_model"] = fallback.get("model", "")
            common["state_label"] = f"{fallback.get('provider','예비')} 예비 사용 중" if fallback else "공통분석 충전 대기"
        chain_item = lambda item: {key: value for key, value in item.items() if key != "chain"}
        common["chain"] = [chain_item(common), chain_item(reserve1), chain_item(reserve2)]
        case["chain"] = [chain_item(case), chain_item(reserve1), chain_item(reserve2)]
        common_available = bool(common.get("connected") and not (common_daily_exhausted or common_token_exhausted)) or any(item.get("available") for item in (reserve1, reserve2))
        case_available = bool(case.get("available")) or any(item.get("available") for item in (reserve1, reserve2))
        halted = not (common_available and case_available)
        operation = {
            "halted": halted,
            "message": "영업중지-토큰이 다 떨어졌어요. 낼 00시에 뵈어요~" if halted else "",
            "retry_after": min([value for value in [common.get("reset_at"), case.get("reset_at"), reserve1.get("reset_at"), reserve2.get("reset_at")] if value] or [self._next_kst_midnight_iso()]) if halted else "",
            "reason": "all_llm_providers_exhausted" if halted else "",
        }
        return {"common": common, "case": case, "reserve1": reserve1, "reserve2": reserve2, "embedding": self.ollama_embedding_status(), "operation": operation}

    def analysis_case(self, case: dict) -> tuple[dict, dict | None]:
        organization = self.store.get_organization(str(case.get("organization_id"))) if case.get("organization_id") else None
        values = [str((organization or {}).get("name") or "")]
        for key in ("abbreviations", "former_names", "people"):
            values.extend(str(value) for value in (organization or {}).get(key, []) if str(value).strip())
        enriched = dict(case)
        enriched["organization_terms"] = list(dict.fromkeys(value.strip() for value in values if value.strip()))
        return enriched, organization

    def recipients_with_connection_status(self) -> list[dict]:
        recipients = self.store.list_recipients()
        for recipient in recipients:
            checked = self.kakao.connection_status(recipient["id"])
            recipient["connection_status"] = "connected" if checked["connected"] else "failed"
            recipient["connection_label"] = checked["label"]
            recipient["connection_error"] = checked["error"]
        return recipients


    def analysis_report(self, article_id: str, case_id: str) -> dict:
        report = self.store.analysis_report(article_id, case_id)
        article, case = self.store.get_article(article_id), self.store.get_case(case_id)
        if not article or not case:
            return report
        evaluation_case, _organization = self.analysis_case(case)
        current = dict(report.get("current") or {})
        system_prompt, user_prompt, input_content = self.scoring.ollama.build_analysis_prompts(evaluation_case, article)
        if not current.get("user_prompt"):
            current.update({
                "system_prompt": system_prompt, "user_prompt": user_prompt, "prompt": user_prompt,
                "input_content": input_content, "reconstructed": True,
            })
        else:
            current.setdefault("input_content", input_content)
        report["current"] = current
        return report

    def process_next_reanalysis(self) -> dict | None:
        if not REMOTE_CASE_SEMAPHORE.acquire(blocking=False):
            return None
        try:
            job = self.store.next_reanalysis_job()
            if not job:
                return None
            article, case = self.store.get_article(job["article_id"]), self.store.get_case(job["case_id"])
            analysis = self.store.get_current_article_analysis(job["article_id"])
            if not article or not case or not analysis:
                self.store.finish_reanalysis(job["id"], None, 0, "article_case_or_common_analysis_missing")
                return {"id": job["id"], "status": "failed"}
            started = time.monotonic()
            self.store.start_reanalysis(job["id"])
            try:
                evaluation_case, organization = self.analysis_case(case)
                current_evaluation = self.store.get_current_case_evaluation(article["id"], case["id"])
                if current_evaluation:
                    evaluation_case["_semantic_raw"] = float(current_evaluation.get("semantic_raw") or 0)
                    evaluation_case["_semantic_score"] = float(current_evaluation.get("semantic_score") or 0)
                result = self.scoring.evaluate_case_with_common(evaluation_case, article, analysis, job["model"])
                result["organization_tag"] = str((organization or {}).get("name") or "")
                self.store.finish_reanalysis(job["id"], result, round((time.monotonic() - started) * 1000))
                return {"id": job["id"], "status": "completed", "decision": result.get("decision")}
            except Exception as error:
                self.store.finish_reanalysis(job["id"], None, round((time.monotonic() - started) * 1000), str(error))
                return {"id": job["id"], "status": "failed", "error": str(error)}
        finally:
            REMOTE_CASE_SEMAPHORE.release()

    @staticmethod
    def _quantile(values: list[float], ratio: float) -> float:
        ordered = sorted(float(value) for value in values)
        if not ordered:
            return 0.0
        position = max(0.0, min(1.0, ratio)) * (len(ordered) - 1)
        lower, upper = int(position), min(len(ordered) - 1, int(position) + 1)
        fraction = position - lower
        return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction

    def _case_embedding(self, case: dict) -> dict | None:
        model = self.selected_embedding_model()
        cached = self.store.get_case_embedding(case["id"], int(case.get("version", 1)), model)
        if cached and cached.get("status") == "completed":
            return cached
        retrieval_text = case_retrieval_text(case)
        if not retrieval_text:
            return None
        started = time.monotonic()
        recorded = False
        try:
            vectors = self.scoring.ollama.embeddings([f"search_query: {retrieval_text}"])
            vector = vectors[0] if vectors else []
            if not vector:
                raise ValueError("case_embedding_empty")
            population = self.store.list_article_embedding_vectors(model)
            similarities = [cosine_similarity(vector, item) for item in population if len(item) == len(vector)]
            calibration = {
                "sample_count": len(similarities),
                "q10": self._quantile(similarities, 0.10) if len(similarities) >= 10 else None,
                "q50": self._quantile(similarities, 0.50) if len(similarities) >= 10 else None,
                "q90": self._quantile(similarities, 0.90) if len(similarities) >= 10 else None,
            }
            self.store.record_llm_api_call("ollama", "embedding", model, "completed", round((time.monotonic() - started) * 1000))
            recorded = True
            return self.store.save_case_embedding(case, model, retrieval_text, vector, calibration)
        except Exception as error:
            if not recorded:
                self.store.record_llm_api_call("ollama", "embedding", model, "failed", round((time.monotonic() - started) * 1000), error=type(error).__name__)
            return self.store.save_case_embedding(case, model, retrieval_text, [], {}, type(error).__name__)

    def _route_article_analysis(self, analysis: dict, article: dict, organization_id: str | None) -> dict:
        """Create independent case rows after the shared article analysis is complete."""
        cases = self.store.list_cases_for_organization(organization_id, active_only=True) if organization_id else []
        counts = {"case_candidates": 0, "case_excluded": 0, "case_queued": 0, "case_before_start": 0}
        article_embedding = self.store.get_article_embedding(analysis["id"])
        article_vector = (article_embedding or {}).get("vector", [])
        semantic_threshold = float(self.store.get_setting("semantic_candidate_threshold", "65"))
        ready_at = (datetime.now(KST) + timedelta(seconds=2)).isoformat(timespec="seconds")
        for case in cases:
            monitor_from = str(case.get("monitor_from") or case.get("created_at") or "")
            first_seen_at = str(article.get("first_seen_at") or "")
            if monitor_from and first_seen_at and first_seen_at < monitor_from:
                counts["case_before_start"] += 1
                continue
            evaluation_case, _organization = self.analysis_case(case)
            case_embedding = self._case_embedding(evaluation_case)
            raw_similarity = 0.0
            if article_vector and case_embedding and case_embedding.get("vector") and len(article_vector) == len(case_embedding["vector"]):
                raw_similarity = cosine_similarity(article_vector, case_embedding["vector"])
            semantic_score = calibrated_semantic_score(raw_similarity, (case_embedding or {}).get("calibration", {})) if raw_similarity else 0.0
            candidate, gate_reason = case_candidate_gate(evaluation_case, article, analysis, semantic_score, semantic_threshold)
            evaluation, created = self.store.create_case_evaluation(
                analysis["id"], article["id"], case, candidate, raw_similarity, semantic_score, gate_reason)
            if candidate:
                counts["case_candidates"] += int(created)
                needs_queue = created or evaluation.get("status") in {"pending", "failed"}
                if needs_queue and self.store.queue_case_evaluation(evaluation["id"], ready_at=ready_at):
                    counts["case_queued"] += 1
            else:
                counts["case_excluded"] += int(created)
        return counts

    def requeue_article_case_evaluations(self, article_id: str) -> dict:
        """Send all current case judgments for one article back through the normal case pipeline."""
        article = self.store.get_article(article_id)
        analysis = self.store.get_current_article_analysis(article_id)
        if not article or not analysis:
            raise ValueError("기사 분석 기록을 찾지 못했습니다.")
        if analysis.get("status") != "completed":
            raise ValueError("공통 기사 분석이 완료된 뒤 케이스 재분석을 실행할 수 있습니다.")
        organization_id = analysis.get("organization_id")
        cases = self.store.list_cases_for_organization(organization_id, active_only=True) if organization_id else self.store.list_cases(active_only=True)
        article_embedding = self.store.get_article_embedding(analysis["id"])
        if not article_embedding or article_embedding.get("status") != "completed":
            self._embed_article_analysis(analysis, article)
            article_embedding = self.store.get_article_embedding(analysis["id"])
        article_vector = (article_embedding or {}).get("vector", [])
        semantic_threshold = float(self.store.get_setting("semantic_candidate_threshold", "65"))
        ready_at = now_iso()
        counts = {"cases": 0, "queued": 0, "candidate_excluded": 0, "before_start": 0}
        for case in cases:
            monitor_from = str(case.get("monitor_from") or case.get("created_at") or "")
            first_seen_at = str(article.get("first_seen_at") or "")
            if monitor_from and first_seen_at and first_seen_at < monitor_from:
                counts["before_start"] += 1
                continue
            evaluation_case, _organization = self.analysis_case(case)
            case_embedding = self._case_embedding(evaluation_case)
            raw_similarity = 0.0
            if article_vector and case_embedding and case_embedding.get("vector") and len(article_vector) == len(case_embedding["vector"]):
                raw_similarity = cosine_similarity(article_vector, case_embedding["vector"])
            semantic_score = calibrated_semantic_score(raw_similarity, (case_embedding or {}).get("calibration", {})) if raw_similarity else 0.0
            candidate, gate_reason = case_candidate_gate(evaluation_case, article, analysis, semantic_score, semantic_threshold)
            evaluation, _created = self.store.reset_case_evaluation_for_requeue(
                analysis["id"], article["id"], case, candidate, raw_similarity, semantic_score, gate_reason
            )
            counts["cases"] += 1
            if candidate:
                if self.store.queue_case_evaluation(evaluation["id"], ready_at=ready_at):
                    counts["queued"] += 1
            else:
                counts["candidate_excluded"] += 1
        return {"article_id": article_id, "analysis_id": analysis["id"], "counts": counts}

    def _embed_article_analysis(self, analysis: dict, article: dict) -> bool:
        embedding_model = self.selected_embedding_model()
        if not embedding_model or not getattr(getattr(self, "scoring", None), "ollama", None):
            return False
        text = " ".join([
            str(article.get("title") or ""), str(analysis.get("summary") or ""),
            " ".join(str(value) for value in analysis.get("classification_tags", [])),
            str(article.get("body") or "")[:5000],
        ]).strip()
        if not text:
            self.store.save_article_embedding(analysis["id"], embedding_model, [], "article_text_missing")
            return False
        started = time.monotonic()
        recorded = False
        try:
            vectors = self.scoring.ollama.embeddings([f"search_document: {text}"])
            vector = vectors[0] if vectors else []
            if not vector:
                raise ValueError("embedding_empty")
            self.store.record_llm_api_call("ollama", "embedding", embedding_model, "completed", round((time.monotonic() - started) * 1000))
            recorded = True
            self.store.save_article_embedding(analysis["id"], embedding_model, vector)
            self.press_releases.queue_for_article(analysis["id"])
            self._route_article_analysis(analysis, article, analysis.get("organization_id"))
            return True
        except Exception as error:
            if not recorded:
                self.store.record_llm_api_call("ollama", "embedding", embedding_model, "failed", round((time.monotonic() - started) * 1000), error=type(error).__name__)
            self.store.save_article_embedding(analysis["id"], embedding_model, [], type(error).__name__)
            return False

    def process_next_embedding(self) -> dict | None:
        """Backfill one historical article only when no LLM analysis work is waiting."""
        if not LOCAL_EMBEDDING_LOCK.acquire(blocking=False):
            return None
        try:
            analysis = self.store.next_embedding_analysis()
            if not analysis:
                return None
            article = self.store.get_article(analysis["article_id"])
            if not article:
                return None
            return {"analysis_id": analysis["id"], "embedded": self._embed_article_analysis(analysis, article)}
        finally:
            LOCAL_EMBEDDING_LOCK.release()

    def process_next_article_analysis(self) -> dict | None:
        if not COMMON_LLM_LOCK.acquire(blocking=False):
            return None
        try:
            job = self.store.next_article_analysis_job()
            if not job or not self.store.start_article_analysis_job(job["id"]):
                return None
            analysis = self.store.get_article_analysis(job["article_analysis_id"])
            article = self.store.get_article(analysis["article_id"]) if analysis else None
            if not analysis or not article:
                self.store.finish_article_analysis_job(job["id"], False, 0, "article_or_analysis_missing")
                return {"id": job["id"], "status": "failed"}
            started = time.monotonic()
            provider = "groq"
            common_model = self.selected_common_llm_model()
            fallback = False
            try:
                try:
                    result = self.scoring.analyze_article_common(article, common_model)
                except json.JSONDecodeError as error:
                    if int(job.get("attempts") or 0) < 1:
                        duration = round((time.monotonic() - started) * 1000)
                        self.store.finish_article_analysis_job(job["id"], False, duration, str(error), retryable=True)
                        return {"id": job["id"], "status": "pending", "stage": "article", "provider": provider, "error": "invalid_json_retry"}
                    result = self.scoring.fallback_article_common(article, common_model, str(error))
                    fallback = True
                    provider = "local_fallback"
                except GroqError as error:
                    if not self._is_common_daily_limit(error):
                        raise
                    self._remember_provider_failure("groq", error)
                    provider, common_model, result = self._try_common_reserve(article)
                    fallback = True
                saved = self.store.save_article_analysis(analysis["id"], result, common_model)
                self.store.finish_article_analysis_job(job["id"], True, round((time.monotonic() - started) * 1000))
                routed = {"case_candidates": 0, "case_excluded": 0, "case_queued": 0, "embedded": 0, "fallback": int(fallback), "provider": provider}
                return {"id": job["id"], "status": "completed", "stage": "article", "provider": provider, "counts": routed}
            except (GroqError, OpenRouterError) as error:
                duration = round((time.monotonic() - started) * 1000)
                if isinstance(error, OpenRouterError):
                    self._remember_provider_failure(provider, error)
                retry_after = getattr(error, "retry_after", "") or self._provider_reset_at(provider if provider in {"groq", "openrouter", "cloudflare", "gemini"} else "groq")
                if getattr(error, "deferred", False) or (getattr(error, "retryable", False) and int(job.get("attempts") or 0) < 2):
                    self.store.finish_article_analysis_job(job["id"], False, duration, str(error), retryable=True, retry_after=retry_after, keep_pending=getattr(error, "deferred", False))
                    return {"id": job["id"], "status": "pending", "stage": "article", "provider": provider, "http_status": getattr(error, "status", 0), "error": str(error), "retry_after": retry_after}
                result = self.scoring.fallback_article_common(article, common_model, str(error))
                self.store.save_article_analysis(analysis["id"], result, common_model)
                self.store.finish_article_analysis_job(job["id"], True, duration)
                routed = {"case_candidates": 0, "case_excluded": 0, "case_queued": 0, "embedded": 0, "fallback": 1, "provider": "local_fallback"}
                return {"id": job["id"], "status": "completed", "stage": "article", "provider": "local_fallback", "counts": routed}
            except Exception as error:
                self.store.finish_article_analysis_job(job["id"], False, round((time.monotonic() - started) * 1000), str(error))
                return {"id": job["id"], "status": "failed", "stage": "article", "error": str(error)}
        finally:
            COMMON_LLM_LOCK.release()

    def process_next_case_evaluation(self) -> dict | None:
        if not REMOTE_CASE_SEMAPHORE.acquire(blocking=False):
            return None
        try:
            jobs = self.store.next_case_evaluation_batch(self.selected_case_batch_size(), "openrouter")
            if not jobs:
                return None
            batch_id = str(jobs[0].get("batch_id") or "")
            counts = {"scored": 0, "queued": 0, "sent": 0, "delivery_failed": 0, "batch_size": len(jobs), "missing": 0}
            prepared: list[tuple[dict, dict, dict]] = []
            article = None
            analysis = None
            default_case_model = self.selected_case_llm_model()
            for job in jobs:
                evaluation = self.store.get_case_evaluation(job["case_evaluation_id"])
                item_article = self.store.get_article(evaluation["article_id"]) if evaluation else None
                case = self.store.get_case(evaluation["case_id"]) if evaluation else None
                item_analysis = self.store.get_article_analysis(evaluation["article_analysis_id"]) if evaluation else None
                if not evaluation or not item_article or not case or not item_analysis:
                    self.store.finish_case_evaluation_job(job["id"], False, 0, "article_case_or_common_analysis_missing", retryable=True)
                    counts["missing"] += 1
                    continue
                article, analysis = item_article, item_analysis
                if not case.get("is_active"):
                    result = self.scoring.fallback_case_evaluation(case, article, analysis, "case_inactive", default_case_model)
                    self.store.save_case_evaluation(evaluation["id"], result, default_case_model)
                    self.store.finish_case_evaluation_job(job["id"], True, 0)
                    counts["scored"] += 1
                    continue
                if analysis.get("status") != "completed":
                    retry_at = (datetime.now(KST) + timedelta(seconds=30)).isoformat(timespec="seconds")
                    self.store.finish_case_evaluation_job(job["id"], False, 0, "common_analysis_pending", retryable=True, retry_after=retry_at, keep_pending=True)
                    counts["missing"] += 1
                    continue
                evaluation_case, _organization = self.analysis_case(case)
                evaluation_case["_semantic_raw"] = float(evaluation.get("semantic_raw") or 0)
                evaluation_case["_semantic_score"] = float(evaluation.get("semantic_score") or 0)
                prepared.append((job, evaluation, evaluation_case))
            if not prepared or not article or not analysis:
                return {"id": batch_id, "status": "partial", "stage": "case_batch", "counts": counts}

            started = time.monotonic()
            provider = "openrouter"
            case_model = default_case_model
            try:
                cases = [item[2] for item in prepared]
                provider, case_model, results = self._evaluate_cases_with_provider_chain(cases, article, analysis)
                should_send = False
                for job, evaluation, case in prepared:
                    result = results.get(str(case["id"]))
                    if not result:
                        try:
                            if hasattr(self.scoring, "evaluate_case_with_common_provider"):
                                result = self.scoring.evaluate_case_with_common_provider(provider, case, article, analysis, case_model)
                            else:
                                result = self.scoring.evaluate_case_with_common(case, article, analysis, case_model)
                            result.setdefault("analysis_report", {})["batch_fallback_reason"] = "batch_result_missing"
                        except OpenRouterError:
                            self.store.finish_case_evaluation_job(job["id"], False, round((time.monotonic() - started) * 1000), "batch_result_missing", retryable=True)
                            counts["missing"] += 1
                            continue
                        except Exception as error:
                            self.store.finish_case_evaluation_job(job["id"], False, round((time.monotonic() - started) * 1000), f"batch_fallback_failed:{type(error).__name__}", retryable=True)
                            counts["missing"] += 1
                            continue
                    self.store.save_case_evaluation(evaluation["id"], result, case_model)
                    self.store.finish_case_evaluation_job(job["id"], True, round((time.monotonic() - started) * 1000))
                    counts["scored"] += 1
                    if result.get("decision") != "send":
                        continue
                    scheduled = delivery_at(case, result.get("urgent", False))
                    recipient_ids = self.store.case_recipient_ids(case["id"])
                    for recipient_id in recipient_ids:
                        self.store.queue_delivery(article["id"], case["id"], recipient_id, scheduled)
                        counts["queued"] += 1
                    should_send = should_send or bool(recipient_ids and (result.get("urgent", False) or case.get("send_relevant_immediately", True) or case.get("delivery_mode") == "immediate"))
                if should_send:
                    sent = self.send_due(max(20, counts["queued"]))
                    counts["sent"], counts["delivery_failed"] = sent["sent"], sent["failed"]
                status = "completed" if not counts["missing"] else "partial"
                return {"id": batch_id, "status": status, "stage": "case_batch", "provider": provider, "model": case_model, "counts": counts}
            except (OpenRouterError, json.JSONDecodeError) as error:
                duration = round((time.monotonic() - started) * 1000)
                retry_after = getattr(error, "retry_after", "") or self._provider_reset_at(provider)
                defer = bool(getattr(error, "deferred", False) or self._is_provider_quota_error(error))
                pending = 0
                for job, evaluation, case in prepared:
                    if defer or (getattr(error, "retryable", False) and int(job.get("attempts") or 0) < 3):
                        self.store.finish_case_evaluation_job(job["id"], False, duration, str(error), retryable=True, retry_after=retry_after, keep_pending=defer)
                        pending += 1
                    else:
                        result = self.scoring.fallback_case_evaluation(case, article, analysis, str(error), case_model)
                        self.store.save_case_evaluation(evaluation["id"], result, case_model)
                        self.store.finish_case_evaluation_job(job["id"], True, duration)
                        counts["scored"] += 1
                return {"id": batch_id, "status": "pending" if pending else "completed", "stage": "case_batch", "provider": provider, "http_status": getattr(error, "status", 0), "error": str(error), "retry_after": retry_after, "counts": counts}
            except Exception as error:
                duration = round((time.monotonic() - started) * 1000)
                for job, _evaluation, _case in prepared:
                    self.store.finish_case_evaluation_job(job["id"], False, duration, str(error), retryable=True)
                return {"id": batch_id, "status": "pending", "stage": "case_batch", "provider": provider, "error": str(error), "counts": counts}
        finally:
            REMOTE_CASE_SEMAPHORE.release()

    def _process_next_case_evaluation_legacy(self) -> dict | None:
        if not REMOTE_CASE_SEMAPHORE.acquire(blocking=False):
            return None
        try:
            job = self.store.next_case_evaluation_job()
            if not job or not self.store.start_case_evaluation_job(job["id"], "openrouter"):
                return None
            evaluation = self.store.get_case_evaluation(job["case_evaluation_id"])
            article = self.store.get_article(evaluation["article_id"]) if evaluation else None
            case = self.store.get_case(evaluation["case_id"]) if evaluation else None
            analysis = self.store.get_article_analysis(evaluation["article_analysis_id"]) if evaluation else None
            if not evaluation or not article or not case:
                self.store.finish_case_evaluation_job(job["id"], False, 0, "article_case_or_common_analysis_missing")
                return {"id": job["id"], "status": "failed", "stage": "case"}
            if not case.get("is_active"):
                case_model = self.selected_case_llm_model()
                result = self.scoring.fallback_case_evaluation(case, article, analysis or {}, "case_inactive", case_model)
                self.store.save_case_evaluation(evaluation["id"], result, case_model)
                self.store.finish_case_evaluation_job(job["id"], True, 0)
                return {"id": job["id"], "status": "completed", "stage": "case", "skipped": "case_inactive"}
            if not analysis or analysis.get("status") != "completed":
                retry_after = (datetime.now(KST) + timedelta(seconds=30)).isoformat(timespec="seconds")
                self.store.finish_case_evaluation_job(
                    job["id"], False, 0, "common_analysis_pending",
                    retryable=True, retry_after=retry_after, keep_pending=True,
                )
                return {"id": job["id"], "status": "pending", "stage": "case", "error": "common_analysis_pending"}
            started = time.monotonic()
            try:
                evaluation_case, _organization = self.analysis_case(case)
                case_model = self.selected_case_llm_model()
                result = self.scoring.evaluate_case_with_common(evaluation_case, article, analysis, case_model)
                saved = self.store.save_case_evaluation(evaluation["id"], result, case_model)
                self.store.finish_case_evaluation_job(job["id"], True, round((time.monotonic() - started) * 1000))
                counts = {"scored": 1, "queued": 0, "sent": 0, "delivery_failed": 0}
                if saved.get("decision") == "send":
                    scheduled = delivery_at(case, result.get("urgent", False))
                    recipient_ids = self.store.case_recipient_ids(case["id"])
                    for recipient_id in recipient_ids:
                        self.store.queue_delivery(article["id"], case["id"], recipient_id, scheduled)
                        counts["queued"] += 1
                    immediate = result.get("urgent", False) or case.get("send_relevant_immediately", True) or case.get("delivery_mode") == "immediate"
                    if recipient_ids and immediate:
                        sent = self.send_due(max(20, len(recipient_ids)))
                        counts["sent"], counts["delivery_failed"] = sent["sent"], sent["failed"]
                return {"id": job["id"], "status": "completed", "stage": "case", "counts": counts}
            except OpenRouterError as error:
                duration = round((time.monotonic() - started) * 1000)
                if error.deferred or (error.retryable and int(job.get("attempts") or 0) < 3):
                    self.store.finish_case_evaluation_job(
                        job["id"], False, duration, str(error), retryable=True,
                        retry_after=error.retry_after, keep_pending=error.deferred,
                    )
                    return {"id": job["id"], "status": "pending", "stage": "case", "provider": "openrouter", "http_status": error.status, "error": str(error)}
                result = self.scoring.fallback_case_evaluation(evaluation_case, article, analysis, str(error), case_model)
                self.store.save_case_evaluation(evaluation["id"], result, case_model)
                self.store.finish_case_evaluation_job(job["id"], True, duration)
                return {"id": job["id"], "status": "completed", "stage": "case", "fallback": 1, "counts": {"scored": 1, "queued": 0, "sent": 0, "delivery_failed": 0}}
            except Exception as error:
                self.store.finish_case_evaluation_job(job["id"], False, round((time.monotonic() - started) * 1000), str(error))
                return {"id": job["id"], "status": "failed", "stage": "case", "provider": "openrouter", "error": str(error)}
        finally:
            REMOTE_CASE_SEMAPHORE.release()

    def _evaluate_queued(self, job_id: str, case: dict, article: dict, counts: dict) -> bool:
        started = time.monotonic()
        if not self.store.start_llm_job(job_id):
            return False
        try:
            evaluation_case, organization = self.analysis_case(case)
            common = self.store.get_current_article_analysis(article["id"])
            if not common or common.get("status") != "completed":
                raise RuntimeError("common_analysis_missing")
            result = self.scoring.evaluate_case_with_common(
                evaluation_case, article, common, self.selected_case_llm_model()
            )
            result["organization_tag"] = str((organization or {}).get("name") or "")
            duration_ms = round((time.monotonic() - started) * 1000)
            llm_error = str(result.get("llm_error") or "")
            self.store.finish_llm_job(job_id, not llm_error, duration_ms, llm_error)
            saved_score = self.store.save_score(article["id"], case["id"], int(case.get("version", 1)), result)
            self.mirror.article_score(article, saved_score)
            counts["scored"] += 1
            if result["decision"] != "send":
                return True
            scheduled = delivery_at(case, result.get("urgent", False))
            recipient_ids = self.store.case_recipient_ids(case["id"])
            for recipient_id in recipient_ids:
                self.store.queue_delivery(article["id"], case["id"], recipient_id, scheduled)
                counts["queued"] += 1
            immediate = result.get("urgent", False) or case.get("send_relevant_immediately", True) or case.get("delivery_mode") == "immediate"
            if recipient_ids and immediate:
                delivery_result = self.send_due(max(20, len(recipient_ids)))
                counts["sent"] += delivery_result["sent"]
                counts["delivery_failed"] += delivery_result["failed"]
            return True
        except Exception as error:
            self.store.finish_llm_job(job_id, False, round((time.monotonic() - started) * 1000), str(error))
            raise


    def process_next_llm_job(self) -> dict | None:
        """Process one persistent analysis job so collection never blocks the full LLM queue."""
        if not REMOTE_CASE_SEMAPHORE.acquire(blocking=False):
            return None
        try:
            job = self.store.next_llm_job()
            if not job:
                return None
            article, case = self.store.get_article(job["article_id"]), self.store.get_case(job["case_id"])
            if not article or not case or not case.get("is_active"):
                self.store.finish_llm_job(job["id"], False, 0, "article_or_active_case_missing")
                return {"id": job["id"], "status": "failed"}
            counts = {"scored": 0, "queued": 0, "sent": 0, "delivery_failed": 0}
            try:
                processed = self._evaluate_queued(job["id"], case, article, counts)
                return {"id": job["id"], "status": "completed" if processed else "skipped", "counts": counts}
            except Exception as error:
                return {"id": job["id"], "status": "failed", "error": str(error), "counts": counts}
        finally:
            REMOTE_CASE_SEMAPHORE.release()


    def run_case(self, case_id: str) -> dict:
        case = self.store.get_case(case_id)
        if not case:
            raise ValueError("케이스를 찾지 못했습니다.")
        if case.get("organization_id"):
            return self.run_organization(str(case["organization_id"]))
        if not COLLECTION_LOCK.acquire(blocking=False):
            raise RuntimeError("다른 AI 언론동향 비서 수집 작업이 진행 중입니다.")
        run_id = self.store.start_run(case_id)
        counts = {"collected": 0, "new": 0, "analysis_queued": 0, "scored": 0, "queued": 0, "sent": 0, "delivery_failed": 0, "skipped": 0}
        errors: list[str] = []
        try:
            candidates = self.collector.collect(case)
            counts["collected"] = len(candidates)
            selected = []
            for candidate in candidates:
                if not publisher_allowed(case, candidate.get("publisher", "")):
                    counts["skipped"] += 1
                    continue
                if not quick_candidate_match(case, candidate):
                    counts["skipped"] += 1
                    continue
                selected.append(candidate)
                if len(selected) >= self.settings.per_run_article_limit:
                    break

            for candidate in selected:
                try:
                    article, created = self.store.upsert_article(candidate)
                    counts["new"] += int(created)
                    case_version = int(case.get("version", 1))
                    if self.store.score_exists(article["id"], case_id):
                        counts["skipped"] += 1
                        continue
                    fetched = self.collector.fetch_body(article["original_url"])
                    candidate.update(fetched)
                    article, _created = self.store.upsert_article(candidate)
                    self.store.queue_llm_job(article["id"], case_id, case_version, case.get("organization_id"))
                    counts["analysis_queued"] += 1
                except Exception as error:
                    errors.append(f"{candidate.get('title', '기사')[:80]}: {error}")
            self.store.set_case_schedule(case_id, next_collection_at(case), collected=True)
            self.mirror.case(self.store.get_case(case_id) or case)
            self.store.finish_run(run_id, "completed_with_errors" if errors else "completed", counts, "\n".join(errors))
            return {"run_id": run_id, "case_id": case_id, "counts": counts, "errors": errors}
        except Exception as error:
            self.store.set_case_schedule(case_id, next_collection_at(case), collected=False)
            self.store.finish_run(run_id, "failed", counts, str(error))
            raise
        finally:
            COLLECTION_LOCK.release()

    def run_organization(self, organization_id: str) -> dict:
        organization = self.store.get_organization(organization_id)
        if not organization:
            raise ValueError("기관을 찾지 못했습니다.")
        cases = self.store.list_cases_for_organization(organization_id, active_only=True)
        if not COLLECTION_LOCK.acquire(blocking=False):
            raise RuntimeError("다른 AI 언론동향 비서 수집 작업이 진행 중입니다.")
        run_id = self.store.start_run(organization_id=organization_id)
        counts = {"collected": 0, "new": 0, "analysis_queued": 0, "scored": 0, "queued": 0, "sent": 0, "delivery_failed": 0, "skipped": 0}
        errors: list[str] = []
        try:
            if not cases:
                self.store.set_organization_schedule(organization_id, next_collection_at(organization), collected=True)
                self.mirror.organization(self.store.get_organization(organization_id) or organization)
                self.store.finish_run(run_id, "completed", counts)
                return {"run_id": run_id, "organization_id": organization_id, "counts": counts, "errors": []}
            candidates = self.collector.collect_organization(organization)
            counts["collected"] = len(candidates)
            prepared: list[dict] = []
            for candidate in candidates:
                if not organization_candidate_match(organization, candidate):
                    counts["skipped"] += 1
                    continue
                try:
                    article, created = self.store.upsert_article(candidate)
                    counts["new"] += int(created)
                    if not article.get("body"):
                        candidate.update(self.collector.fetch_body(article["original_url"]))
                        article, _created = self.store.upsert_article(candidate)
                    if not organization_candidate_match(organization, article):
                        counts["skipped"] += 1
                        continue
                    prepared.append(article)
                    if len(prepared) >= int(organization.get("max_articles_per_run", 50)):
                        break
                except Exception as error:
                    errors.append(f"{candidate.get('title', '기사')[:80]}: {error}")

            for article in prepared:
                analysis, created_analysis = self.store.ensure_article_analysis(article, organization_id)
                if analysis.get("status") == "completed":
                    routed = self._route_article_analysis(analysis, article, organization_id) if self.store.get_article_embedding(analysis["id"]) else {"case_queued": 0}
                    counts["analysis_queued"] += routed["case_queued"]
                elif self.store.queue_article_analysis(analysis["id"], organization_id):
                    counts["analysis_queued"] += int(created_analysis)
            self.store.set_organization_schedule(organization_id, next_collection_at(organization), collected=True)
            self.mirror.organization(self.store.get_organization(organization_id) or organization)
            self.store.finish_run(run_id, "completed_with_errors" if errors else "completed", counts, "\n".join(errors))
            return {"run_id": run_id, "organization_id": organization_id, "counts": counts, "errors": errors}
        except Exception as error:
            self.store.set_organization_schedule(organization_id, next_collection_at(organization), collected=False)
            self.mirror.organization(self.store.get_organization(organization_id) or organization)
            self.store.finish_run(run_id, "failed", counts, str(error))
            raise
        finally:
            COLLECTION_LOCK.release()


    @staticmethod
    def message_text(delivery: dict) -> str:
        case_name = str(delivery.get("case_name") or "AI 언론동향 비서")[:20]
        raw_tags = delivery.get("classification_tags") or []
        if isinstance(raw_tags, str):
            try:
                raw_tags = json.loads(raw_tags)
            except (json.JSONDecodeError, TypeError):
                raw_tags = []
        tags = [str(delivery.get("organization_tag") or "").strip()[:20]]
        tags.extend(str(value).strip()[:20] for value in raw_tags if str(value).strip())
        tags = list(dict.fromkeys(tag for tag in tags if tag))[:3]
        tags = tags or [str(delivery.get("article_type") or "기타")[:20]]
        tag_line = " ".join(f"[{tag}]" for tag in tags)
        title = str(delivery.get("title") or "")[:58]
        summary = str(delivery.get("summary") or "")[:62]
        similarity = delivery.get("similarity_score", delivery.get("final_score", delivery.get("llm_score", 0)))
        text = f"{tag_line}\n[{case_name}] 유사도 {float(similarity or 0):.1f}%\n{title}\n\n{summary}"
        return text[:200]

    def article_link(self, article_id: str, fallback: str) -> str:
        redirect = urllib.parse.urlsplit(self.settings.kakao_redirect_uri)
        if redirect.scheme in {"http", "https"} and redirect.netloc:
            article_id = urllib.parse.quote(str(article_id), safe="")
            return f"{redirect.scheme}://{redirect.netloc}/poc/master-press/article/{article_id}"
        return fallback

    def send_due(self, limit: int = 20) -> dict:
        if not DELIVERY_LOCK.acquire(blocking=False):
            return {"sent": 0, "failed": 0, "errors": []}
        try:
            return self._send_due(limit)
        finally:
            DELIVERY_LOCK.release()

    def _send_due(self, limit: int = 20) -> dict:
        sent = failed = 0
        errors = []
        for delivery in self.store.due_deliveries(limit):
            try:
                status, _response = self.kakao.send_to_me(
                    delivery["recipient_id"],
                    self.message_text(delivery),
                    self.article_link(delivery["article_id"], delivery["original_url"]),
                )
                self.store.finish_delivery(delivery["id"], True, status)
                sent += 1
            except Exception as error:
                code = int(getattr(error, "status", 502))
                message = str(error)
                if code == 403 and "insufficient" in message.casefold() and "scope" in message.casefold():
                    notice = "카카오 메시지 발송 권한이 없어 재동의가 필요합니다."
                    self.store.mark_recipient_reauthorize(delivery["recipient_id"], notice)
                    self.store.fail_delivery_permanently(delivery["id"], code, notice)
                    errors.append(notice)
                else:
                    self.store.finish_delivery(delivery["id"], False, code, message)
                    errors.append(message)
                failed += 1
        return {"sent": sent, "failed": failed, "errors": errors}

    def orchestration_tick(self) -> dict:
        results = {"organizations": [], "cases": [], "delivery": {}, "press_releases": {}, "cleanup": {}}
        results["delivery"] = self.send_due()
        results["press_releases"] = self.press_releases.sync()
        for organization in self.store.list_due_organizations():
            try:
                results["organizations"].append(self.run_organization(organization["id"]))
            except RuntimeError as error:
                results["organizations"].append({"organization_id": organization["id"], "error": str(error)})
                break
            except Exception as error:
                results["organizations"].append({"organization_id": organization["id"], "error": str(error)})
        for case in self.store.list_due_cases():
            try:
                results["cases"].append(self.run_case(case["id"]))
            except RuntimeError as error:
                results["cases"].append({"case_id": case["id"], "error": str(error)})
                break
            except Exception as error:
                results["cases"].append({"case_id": case["id"], "error": str(error)})
        now = datetime.now(KST)
        if now.hour == 3 and now.minute < 2:
            results["cleanup"] = self.store.cleanup(self.settings.raw_retention_days, self.settings.metadata_retention_days)
        return results

    def common_worker_tick(self) -> dict | None:
        article = self.process_next_article_analysis()
        return {"stage": "article", "result": article} if article else None

    def embedding_worker_tick(self) -> dict | None:
        embedding = self.process_next_embedding()
        if embedding:
            return {"stage": "embedding", "result": embedding}
        if not LOCAL_EMBEDDING_LOCK.acquire(blocking=False):
            return None
        try:
            press = self.press_releases.process_next()
            return {"stage": "press_release", "result": press} if press else None
        finally:
            LOCAL_EMBEDDING_LOCK.release()

    def case_worker_tick(self, burst: bool = False) -> dict | None:
        if burst and self.store.pending_case_evaluation_jobs() < 10:
            return None
        if not burst:
            reanalysis = self.process_next_reanalysis()
            if reanalysis:
                return {"stage": "reanalysis", "result": reanalysis}
        result = self.process_next_case_evaluation()
        return {"stage": "case", "result": result} if result else None

    def tick(self) -> dict:
        return self.orchestration_tick()


_SERVICE: MasterPressService | None = None
_SERVICE_KEY: tuple | None = None
_SERVICE_LOCK = threading.Lock()


def _service_key(settings: Settings) -> tuple:
    return (
        str(settings.database_path), settings.naver_client_id, settings.kakao_redirect_uri,
        bool(settings.groq_api_key), settings.groq_base_url, settings.groq_common_model,
        settings.groq_daily_request_soft_limit, settings.groq_daily_token_soft_limit,
        settings.embedding_model, bool(settings.openrouter_api_key), settings.openrouter_base_url,
        settings.openrouter_case_model, settings.openrouter_daily_soft_limit,
        bool(getattr(settings, "worker_ai_key", "")), getattr(settings, "worker_ai_account_id", ""),
        getattr(settings, "worker_ai_base_url", ""), getattr(settings, "worker_ai_model", ""),
        getattr(settings, "worker_ai_daily_request_soft_limit", 0), getattr(settings, "worker_ai_daily_neuron_soft_limit", 0),
        bool(getattr(settings, "gemini_api_key", "")), getattr(settings, "gemini_base_url", ""),
        getattr(settings, "gemini_model", ""), getattr(settings, "gemini_daily_request_soft_limit", 0),
        getattr(settings, "gemini_daily_token_soft_limit", 0),
    )


def get_service() -> MasterPressService:
    global _SERVICE, _SERVICE_KEY
    settings = Settings.from_env()
    settings.ensure_directories()
    key = _service_key(settings)
    if _SERVICE is not None and _SERVICE_KEY == key:
        return _SERVICE
    with _SERVICE_LOCK:
        if _SERVICE is None or _SERVICE_KEY != key:
            _SERVICE = MasterPressService(settings, Store(settings.database_path))
            _SERVICE_KEY = key
        return _SERVICE


def worker_tick() -> dict:
    return get_service().orchestration_tick()


def common_worker_tick() -> dict | None:
    return get_service().common_worker_tick()


def embedding_worker_tick() -> dict | None:
    return get_service().embedding_worker_tick()


def case_worker_tick(burst: bool = False) -> dict | None:
    return get_service().case_worker_tick(burst=burst)
