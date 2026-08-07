from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import urllib.parse
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .collectors import NewsCollector, case_excluded_match, organization_candidate_match, quick_candidate_match
from .config import Settings
from .kakao import KakaoClient
from .magazine import MagazinePublisher, edition_title
from .matching import article_topic_fields, expanded_case_terms, term_in_text
from .press_releases import PressReleaseManager
from .provider_quota import QuotaLockDecision, confirmed_free_quota_exhaustion, quota_lock_decision
from .shadow import ShadowCaseStore
from .scoring import GroqError, OpenRouterError, RelevanceEngine, calibrated_semantic_score, case_retrieval_text, cosine_similarity, parse_llm_json
from .storage import KST, Store, now_iso
from .supabase_mirror import SupabaseMirror


COLLECTION_LOCK = threading.Lock()
COMMON_LLM_LOCK = threading.Lock()
LOCAL_EMBEDDING_LOCK = threading.Lock()
CASE_MODEL1_PRIORITY_SECONDS = 5
SHADOW_CASE_SEMAPHORE = threading.BoundedSemaphore(1)
REMOTE_CASE_SEMAPHORE = threading.BoundedSemaphore(2)
DELIVERY_LOCK = threading.Lock()

# Permanent failover is reserved for measured near-exhaustion. Ordinary API
# instability uses this short, self-clearing reserve window.
PROVIDER_TEMPORARY_RETRY_MINUTES = 10
PROVIDER_TRANSIENT_FAILURE_THRESHOLD = 3
CASE_PROPOSAL_HARMFUL_EXPRESSIONS = (
    "씨발", "시발", "ㅆㅂ", "개새끼", "병신", "ㅂㅅ", "좆", "지랄",
    "미친놈", "미친년", "멍청이", "등신", "닥쳐", "꺼져", "죽어버려",
)


def verified_case_proposal_moderation(text: str, result: dict) -> tuple[bool, str, list[str]]:
    """Accept a blocked verdict only when its quoted evidence exists in the submitted text."""
    raw_unsafe = result.get("unsafe") is True or str(result.get("unsafe", "")).strip().lower() in {"true", "1", "yes"}
    evidence = result.get("evidence") or result.get("matched_text") or []
    if isinstance(evidence, str):
        evidence = [evidence]
    normalized_text = " ".join(str(text or "").casefold().split())
    harmful_matches = [value for value in CASE_PROPOSAL_HARMFUL_EXPRESSIONS if value in normalized_text]
    verified = []
    for value in evidence if isinstance(evidence, list) else []:
        excerpt = " ".join(str(value or "").strip().casefold().split())
        harmful_evidence = any(value in excerpt for value in CASE_PROPOSAL_HARMFUL_EXPRESSIONS)
        if len(excerpt) >= 2 and excerpt in normalized_text and harmful_evidence and excerpt not in verified:
            verified.append(excerpt)
    unsafe = bool(raw_unsafe and verified and harmful_matches)
    if unsafe:
        reason = str(result.get("reason") or "원문에서 문제 표현 감지")[:500]
    elif raw_unsafe:
        reason = "모델이 문제를 제기했으나 원문에서 일치하는 위반 표현을 확인하지 못했습니다."
    else:
        reason = str(result.get("reason") or "문제 표현 없음")[:500]
    return unsafe, reason, verified



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
        self.store.ensure_pipeline_lease_schema()
        self.worker_id = f"{os.getpid()}:{uuid.uuid4()}"
        self.collector = NewsCollector(settings)
        self.scoring = RelevanceEngine(settings, store)
        self._migrate_common_reserve_defaults()
        self._migrate_reserve2_default()
        self._migrate_stage_model_defaults()
        self.scoring.ollama.embedding_model = self.selected_embedding_model()
        # Request paths only enqueue mirror work; a separate worker performs remote I/O.
        self.mirror = SupabaseMirror(settings, store)
        self.press_releases = PressReleaseManager(settings, store, self.scoring.ollama, self.mirror)
        self.store.ensure_shadow_case_schema()
        self.shadow_cases = ShadowCaseStore(store)
        self.kakao = KakaoClient(settings, store)
        # Multiple stage workers intentionally share the database. A process-id
        # session reset would requeue another live worker's jobs, so recovery is
        # exclusively lease-expiry based for this pipeline.
        self.recovered_llm_jobs = 0
        self.recovered_pipeline_jobs = self.store.recover_incomplete_pipeline_jobs()
        self.recovered_llm_jobs += sum(self.recovered_pipeline_jobs.values())
        self._next_case_stall_recovery_at = 0.0
        self._next_common_stall_recovery_at = 0.0

    def _lease_owner(self) -> str:
        """Return a stable owner even for lightweight test/service constructions."""
        owner = str(getattr(self, "worker_id", "") or "")
        if not owner:
            owner = f"{os.getpid()}:{uuid.uuid4()}"
            self.worker_id = owner
        return owner

    def _migrate_stage_model_defaults(self) -> None:
        """Install the verified fixed provider topology once."""
        if self.store.get_setting("stage_model_topology_v2", ""):
            return
        common_primary = str(getattr(self.settings, "groq_common_model", "llama-3.1-8b-instant") or "llama-3.1-8b-instant")
        common_fallback = "@cf/meta/llama-3.1-8b-instruct-fast"
        case_primary = str(getattr(self.settings, "openrouter_case_model", "google/gemma-4-26b-a4b-it:free") or "google/gemma-4-26b-a4b-it:free")
        case_fallback = "gemini-3.1-flash-lite"
        burst = str(getattr(self.settings, "openai_shadow_model", "gpt-5.4-mini") or "gpt-5.4-mini")
        for key, value in (
            ("common_llm_model", common_primary),
            ("common_fallback_llm_model", common_fallback),
            ("case_llm_model", case_primary),
            ("case_fallback_llm_model", case_fallback),
            ("burst_llm_model", burst),
        ):
            self.store.set_setting(key, value)
        self.store.set_setting("case_fallback_enabled", "1")
        self.store.set_setting("stage_model_topology_v2", now_iso())

    def _migrate_common_reserve_defaults(self) -> None:
        """Swap the old Groq-primary/Cloudflare-reserve defaults once, preserving custom choices."""
        old_common = str(getattr(getattr(self, "settings", None), "groq_common_model", "llama-3.1-8b-instant") or "llama-3.1-8b-instant")
        old_reserve = str(getattr(getattr(self, "settings", None), "worker_ai_model", "@cf/google/gemma-4-26b-a4b-it") or "@cf/google/gemma-4-26b-a4b-it")
        current_common = self.store.get_setting("common_llm_model", "")
        current_reserve = self.store.get_setting("reserve1_llm_model", "")
        if current_common in {"", old_common} and current_reserve in {"", old_reserve}:
            self.store.set_setting("common_llm_model", old_reserve)
            self.store.set_setting("reserve1_llm_model", old_common)

    def _migrate_reserve2_default(self) -> None:
        """Move the previous Gemini reserve2 default to GPT-5.4 mini once."""
        old_default = str(getattr(getattr(self, "settings", None), "gemini_model", "gemini-3.5-flash-lite") or "gemini-3.5-flash-lite")
        new_default = str(getattr(getattr(self, "settings", None), "openai_shadow_model", "gpt-5.4-mini") or "gpt-5.4-mini")
        current = self.store.get_setting("reserve2_llm_model", "")
        if current in {"", old_default}:
            self.store.set_setting("reserve2_llm_model", new_default)

    def selected_common_llm_model(self) -> str:
        default = getattr(getattr(self, "settings", None), "groq_common_model", "llama-3.1-8b-instant")
        return self.store.get_setting("common_llm_model", default)

    def selected_llm_model(self) -> str:
        """Backward-compatible name for the shared analysis model."""
        return self.selected_common_llm_model()

    def selected_case_llm_model(self) -> str:
        default = getattr(getattr(self, "settings", None), "openrouter_case_model", "google/gemma-4-26b-a4b-it:free")
        return self.store.get_setting("case_llm_model", default)

    def selected_case_model1(self) -> str:
        """RPM-limited NVIDIA primary worker: provider-affine chunks of five."""
        return str(getattr(getattr(self, "settings", None), "nvidia_case_model", "openai/gpt-oss-120b") or "openai/gpt-oss-120b")

    def selected_case_model2(self) -> str:
        """Token-budgeted OpenAI secondary worker: up to ten cases per request."""
        return str(getattr(getattr(self, "settings", None), "openai_shadow_model", "gpt-5.4-mini") or "gpt-5.4-mini")

    def selected_case_single_model(self) -> str:
        return str(getattr(getattr(self, "settings", None), "openrouter_case_model", "google/gemma-4-26b-a4b-it:free") or "google/gemma-4-26b-a4b-it:free")

    def selected_common_turbo_model(self) -> str:
        return self.selected_case_single_model()

    def case_batch_size_for_provider(self, provider: str) -> int:
        return {"openai": 10, "nvidia": 5, "openrouter": 1}.get(str(provider or "").lower(), self.selected_case_batch_size())

    def selected_common_fallback_model(self) -> str:
        return self.store.get_setting("common_fallback_llm_model", "@cf/meta/llama-3.1-8b-instruct-fast")

    def selected_case_fallback_model(self) -> str:
        return self.store.get_setting("case_fallback_llm_model", "gemini-3.1-flash-lite")

    def case_fallback_enabled(self) -> bool:
        return self.store.get_setting("case_fallback_enabled", "1").casefold() in {"1", "true", "yes", "on"}

    def selected_burst_model(self) -> str:
        default = getattr(getattr(self, "settings", None), "openai_shadow_model", "gpt-5.4-mini")
        return self.store.get_setting("burst_llm_model", default)

    def selected_burst_threshold(self) -> int:
        try:
            return max(5, min(100, int(self.store.get_setting("burst_threshold", "5"))))
        except (TypeError, ValueError):
            return 5

    def selected_burst_stop_threshold(self) -> int:
        return max(1, min(3, self.selected_burst_threshold() - 2))

    def selected_reserve1_model(self) -> str:
        default = getattr(getattr(self, "settings", None), "groq_common_model", "llama-3.1-8b-instant")
        return self.store.get_setting("reserve1_llm_model", default)

    def selected_reserve2_model(self) -> str:
        default = getattr(getattr(self, "settings", None), "openai_shadow_model", "gpt-5.4-mini")
        return self.store.get_setting("reserve2_llm_model", default)

    def selected_case_batch_size(self) -> int:
        try:
            return max(1, min(10, int(self.store.get_setting("case_batch_size", "10"))))
        except ValueError:
            return 10
    def shadow_enabled(self) -> bool:
        return self.store.get_setting("openai_shadow_enabled", "1").casefold() not in {"0", "false", "off", "no"}

    def shadow_daily_limit(self) -> int:
        configured = int(getattr(self.settings, "openai_shadow_daily_limit", 150) or 150)
        try:
            return max(1, min(1000, int(self.store.get_setting("openai_shadow_daily_limit", str(configured)))))
        except ValueError:
            return configured

    def shadow_status(self) -> dict:
        status = self.shadow_cases.status(self.shadow_daily_limit())
        provider_status = self.openai_status(False)
        status["enabled"] = self.shadow_enabled()
        status["available"] = bool(
            getattr(self.settings, "openai_api_key", "")
            and getattr(self.settings, "openai_shadow_model", "")
            and provider_status.get("available")
        )
        status["model"] = str(getattr(self.settings, "openai_shadow_model", "gpt-5.4-mini"))
        status["token_soft_limit"] = int(provider_status.get("token_soft_limit") or 0)
        status["token_remaining"] = int(provider_status.get("token_remaining") or 0)
        status["token_budget_exhausted"] = bool(provider_status.get("token_budget_exhausted"))
        status["token_budget_reset_at"] = str(provider_status.get("token_budget_reset_at") or "")
        status["state"] = "running" if status["enabled"] and status["available"] else ("disabled" if not status["enabled"] else "key_missing")
        if status["enabled"] and status["token_budget_exhausted"]:
            status["state"] = "token_budget_wait"
        return status



    def selected_embedding_model(self) -> str:
        default = getattr(getattr(self, "settings", None), "embedding_model", "nomic-embed-text:latest")
        return self.store.get_setting("embedding_model", default)

    def configured_common_reserve_models(self, selected: str = "") -> list[str]:
        return ["llama-3.1-8b-instant"]

    def _switchable_common_reserve_models(self, selected: str = "") -> list[str]:
        return self.configured_common_reserve_models(selected)

    def available_common_llm_models(self) -> list[str]:
        return self._switchable_common_reserve_models(self.selected_common_llm_model())

    def available_llm_models(self) -> list[str]:
        return self.available_common_llm_models()

    def available_case_llm_models(self) -> list[str]:
        return [self.selected_case_model1(), self.selected_case_model2(), self.selected_case_single_model()]

    def available_reserve1_models(self) -> list[str]:
        return ["llama-3.1-8b-instant"]

    def available_reserve2_models(self) -> list[str]:
        return ["gpt-5.4-mini"]

    def available_common_fallback_models(self) -> list[str]:
        return ["@cf/meta/llama-3.1-8b-instruct-fast"]

    def available_case_fallback_models(self) -> list[str]:
        return ["gemini-3.1-flash-lite"]

    def available_burst_models(self) -> list[str]:
        return [self.selected_common_turbo_model()]

    def available_embedding_models(self) -> list[str]:
        model = self.selected_embedding_model()
        return [model] if model else []

    def _provider_for_switchable_llm_model(self, model: str) -> str:
        model = str(model or "").strip()
        if not model:
            return ""
        if model == getattr(getattr(self, "settings", None), "worker_ai_model", "@cf/google/gemma-4-26b-a4b-it") or model.startswith("@cf/"):
            return "cloudflare"
        if model == getattr(getattr(self, "settings", None), "nvidia_case_model", "openai/gpt-oss-120b") or "gpt-oss-120b" in model:
            return "nvidia"
        if model == getattr(getattr(self, "settings", None), "openrouter_case_model", "google/gemma-4-26b-a4b-it:free") or model.endswith(":free"):
            return "openrouter"
        if model == getattr(getattr(self, "settings", None), "groq_common_model", "llama-3.1-8b-instant") or model in {"llama-3.1-8b-instant"}:
            return "groq"
        if model.startswith("gemini-"):
            return "gemini"
        if model.startswith("gpt-"):
            return "openai"
        return "groq"

    def _status_for_switchable_llm_model(self, model: str, probe: bool = False) -> dict:
        provider = self._provider_for_switchable_llm_model(model)
        if provider == "cloudflare":
            status = self.cloudflare_status(probe)
        elif provider == "openrouter":
            status = self.openrouter_status(probe)
        elif provider == "nvidia":
            status = self.nvidia_status(probe)
        elif provider == "groq":
            status = self.groq_status(probe)
        elif provider == "gemini":
            status = self.gemini_status(probe)
        elif provider == "openai":
            status = self.openai_status(probe)
        else:
            status = {"connected": False, "available": False, "error": "모델 제공자를 확인할 수 없습니다.", "attempts": 0, "soft_limit": 0}
        status["model"] = model
        status["provider"] = provider
        return status

    def model_role_status(self, model: str, stages: str | list[str], probe: bool = False) -> dict:
        """Return role usage in the provider's documented reset window."""
        status = self._status_for_switchable_llm_model(model, probe)
        stage_names = [str(stages)] if isinstance(stages, str) else [str(value) for value in stages]
        provider = str(status.get("provider") or "")
        day_start, reset_at, reset_basis, reset_label = self._provider_usage_window(provider)
        usage_rows = [self.store.provider_usage_since(status.get("provider", ""), day_start, stage=stage) for stage in stage_names]
        completed = sum(int(row.get("completed") or 0) for row in usage_rows)
        attempts = sum(int(row.get("attempts") or 0) for row in usage_rows)
        failed = sum(int(row.get("failed") or 0) for row in usage_rows)
        input_tokens = sum(int(row.get("input_tokens") or 0) for row in usage_rows)
        output_tokens = sum(int(row.get("output_tokens") or 0) for row in usage_rows)
        usage_units = sum(int(row.get("usage_units") or 0) for row in usage_rows)
        weighted_seconds = sum(float(row.get("average_seconds") or 0) * int(row.get("completed") or 0) for row in usage_rows)
        status.update({
            "attempts": attempts,
            "completed": completed,
            "failed": failed,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "tokens": input_tokens + output_tokens,
            "usage_units": usage_units,
            "average_seconds": round(weighted_seconds / completed, 2) if completed else 0,
            "period": reset_basis,
            "usage_period": reset_basis,
            "usage_day_start": day_start,
            "usage_stages": stage_names,
            "reset_at": reset_at,
            "reset_basis": reset_basis,
            "reset_label": reset_label,
        })
        return status

    def _active_provider_chain(self, chain: list[tuple[str, str]]) -> list[tuple[str, str]]:
        """Return available providers in configured primary/reserve order."""
        active = []
        seen = set()
        current = now_iso()
        for provider, model in chain:
            provider = str(provider or "").strip().lower()
            model = str(model or "").strip()
            if not provider or not model:
                continue
            key = (provider, model)
            if key in seen:
                continue
            disabled_until = self._provider_disabled_until(provider)
            if disabled_until and disabled_until > current:
                continue
            if self._provider_temporarily_paused(provider):
                continue
            if not hasattr(self, "settings"):
                seen.add(key)
                active.append(key)
                continue
            status = self._provider_status(provider, model)
            if not status.get("available"):
                continue
            seen.add(key)
            active.append(key)
        return active

    def stage_primary_available(self, stage: str) -> bool:
        if stage == "common":
            return bool(self._common_provider_chain())
        if stage == "case":
            return any(self._provider_status(provider, model).get("available") for provider, model in (
                ("nvidia", self.selected_case_model1()),
                ("openai", self.selected_case_model2()),
                ("openrouter", self.selected_case_single_model()),
            ))
        return False

    def burst_provider_available(self) -> bool:
        return self.common_turbo_available()

    def common_turbo_available(self) -> bool:
        model = self.selected_common_turbo_model()
        if not self._active_provider_chain([("openrouter", model)]):
            return False
        limit = int(getattr(self.settings, "openrouter_daily_soft_limit", 1000) or 1000)
        reserve = min(limit - 1, int(getattr(self.settings, "openrouter_case_reserve_calls", 100) or 100))
        usage = self.store.openrouter_usage_today(limit)
        return int(usage.get("attempts") or 0) < max(0, limit - reserve)

    def _provider_status(self, provider: str, model: str = "") -> dict:
        """Read local provider availability without issuing a remote probe."""
        if provider == "openrouter":
            status = self.openrouter_status(False)
        elif provider == "nvidia":
            status = self.nvidia_status(False)
        elif provider == "cloudflare":
            status = self.cloudflare_status(False)
        elif provider == "groq":
            status = self.groq_status(False)
        elif provider == "gemini":
            status = self.gemini_status(False)
        elif provider == "openai":
            status = self.openai_status(False)
        else:
            return {"provider": provider, "model": model, "available": False, "connected": False}
        if model:
            status["model"] = model
        return status

    def _next_provider_reset(self, providers: list[str]) -> str:
        """Return the earliest confirmed quota lock expiry among providers."""
        current = now_iso()
        reset_points = []
        for provider in dict.fromkeys(str(item or "").strip().lower() for item in providers):
            if not provider:
                continue
            reset_at = self._provider_disabled_until(provider)
            if reset_at and reset_at > current:
                reset_points.append(reset_at)
        return min(reset_points) if reset_points else (datetime.now(KST) + timedelta(hours=1)).isoformat(timespec="seconds")

    def _next_provider_retry(self, providers: list[str]) -> str:
        """Use a short retry window for transient failures; resets for hard stops."""
        current = now_iso()
        retry_points = []
        for provider in dict.fromkeys(str(item or "").strip().lower() for item in providers):
            if not provider:
                continue
            for candidate in (
                self._provider_temporary_until(provider),
                self._provider_disabled_until(provider),
                self._provider_probe_until(provider),
            ):
                if candidate and candidate > current:
                    retry_points.append(candidate)
        return min(retry_points) if retry_points else (datetime.now(KST) + timedelta(minutes=PROVIDER_TEMPORARY_RETRY_MINUTES)).isoformat(timespec="seconds")

    def _groq_usage_window(self) -> tuple[str, str, str]:
        since = (datetime.now(KST) - timedelta(hours=24)).isoformat(timespec="seconds")
        rate_reset = self.store.get_setting("llm_provider_rate_reset_at:groq", "")
        try:
            reset_at = rate_reset if rate_reset and rate_reset > now_iso() else ""
            reset_label = datetime.fromisoformat(reset_at).astimezone(KST).strftime("%H:%M:%S") if reset_at else ""
        except Exception:
            reset_label, reset_at = "", ""
        label = "Groq 응답 헤더" + (f" · 다음 초기화 {reset_label}" if reset_label else "")
        return since, reset_at, label

    def groq_status(self, probe: bool = False) -> dict:
        since, reset_at, reset_label = self._groq_usage_window()
        usage = self.store.provider_usage_since("groq", since)
        status = self.scoring.common_llm.key_status() if probe else {"connected": bool(self.settings.groq_api_key)}
        result = {**status, **usage, "model": self.selected_reserve1_model(), "provider": "groq",
                  "period": "Groq window", "day_start": since, "reset_basis": "Groq rate-limit header",
                  "reset_at": reset_at, "reset_label": reset_label}
        return self._attach_provider_guard(result)

    def openrouter_status(self, probe: bool = False) -> dict:
        since, reset_at = self._utc_day_window_kst()
        usage = self.store.provider_usage_since("openrouter", since)
        status = self.scoring.case_llm.key_status() if probe else {"connected": bool(self.settings.openrouter_api_key)}
        result = {**status, **usage, "model": self.selected_case_single_model(), "provider": "openrouter", "period": "UTC day", "reset_basis": "UTC 00:00", "reset_at": reset_at, "reset_label": "한국시간 09:00"}
        return self._attach_provider_guard(result)

    def nvidia_status(self, probe: bool = False) -> dict:
        since, reset_at = self._utc_day_window_kst()
        usage = self.store.provider_usage_since("nvidia", since)
        status = self.scoring.nvidia_llm.key_status() if probe else {
            "connected": bool(getattr(self.settings, "nvidia_api_key", ""))
        }
        result = {**status, **usage, "model": self.selected_case_model1(), "provider": "nvidia",
                  "period": "UTC day", "reset_basis": "UTC 00:00",
                  "reset_at": reset_at, "reset_label": "한국시간 09:00"}
        return self._attach_provider_guard(result)

    def cloudflare_status(self, probe: bool = False) -> dict:
        since, reset_at = self._utc_day_window_kst()
        usage = self.store.provider_usage_since("cloudflare", since)
        has_key = bool(getattr(self.settings, "worker_ai_key", ""))
        has_account = bool(getattr(self.settings, "worker_ai_account_id", ""))
        connected = bool(has_key and has_account)
        if probe:
            status = self.scoring.reserve1_llm.key_status()
        else:
            status = {"connected": connected, "error": "" if connected else ("Cloudflare API 키 미설정" if not has_key else "Cloudflare Account ID 미설정")}
        result = {**status, **usage, "model": self.selected_common_fallback_model(), "provider": "cloudflare",
                  "period": "UTC day", "reset_basis": "UTC 00:00", "reset_at": reset_at, "reset_label": "한국시간 09:00"}
        return self._attach_provider_guard(result)

    def gemini_status(self, probe: bool = False) -> dict:
        since, reset_at = self._pacific_day_window_kst()
        usage = self.store.provider_usage_since("gemini", since)
        status = self.scoring.reserve2_llm.key_status() if probe else {"connected": bool(getattr(self.settings, "gemini_api_key", ""))}
        result = {**status, **usage, "model": self.selected_case_fallback_model(), "provider": "gemini",
                  "period": "Pacific day", "reset_basis": "Pacific 00:00", "reset_at": reset_at,
                  "reset_label": f"한국시간 {datetime.fromisoformat(reset_at).astimezone(KST).strftime('%H:%M')}"}
        return self._attach_provider_guard(result)

    def openai_status(self, probe: bool = False) -> dict:
        since, reset_at = self._utc_day_window_kst()
        token_limit = int(getattr(self.settings, "openai_daily_token_soft_limit", 2450000) or 2450000)
        usage = self.store.provider_usage_since("openai", since, token_limit=token_limit)
        status = self.scoring.shadow_llm.key_status() if probe else {"connected": bool(getattr(self.settings, "openai_api_key", ""))}
        result = {**status, **usage, "model": getattr(self.settings, "openai_shadow_model", "gpt-5.4-mini"),
                  "provider": "openai", "period": "UTC day", "reset_basis": "UTC 00:00", "reset_at": reset_at, "reset_label": "한국시간 09:00"}
        result = self._attach_provider_guard(result)
        result["token_budget_exhausted"] = bool(token_limit and int(result.get("tokens") or 0) >= token_limit)
        result["token_budget_reset_at"] = reset_at
        if result["token_budget_exhausted"]:
            result["available"] = False
            result["state_label"] = "Mini 일일 토큰 예산 소진 · OSS 처리 중"
        return result

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
            "models": models, "probed": bool(probe), "period": "KST day",
            "reset_basis": "KST 00:00", "reset_at": self._next_kst_midnight_iso(),
            "reset_label": "한국시간 00:00", **usage,
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

    def _provider_usage_window(self, provider: str) -> tuple[str, str, str, str]:
        provider = str(provider or "").strip().lower()
        if provider in {"cloudflare", "openrouter", "openai", "nvidia"}:
            start, reset = self._utc_day_window_kst()
            return start, reset, "UTC day", "한국시간 09:00"
        if provider == "gemini":
            start, reset = self._pacific_day_window_kst()
            label = f"한국시간 {datetime.fromisoformat(reset).astimezone(KST).strftime('%H:%M')}"
            return start, reset, "Pacific day", label
        if provider == "groq":
            since, reset, label = self._groq_usage_window()
            return since, reset, "Groq rate-limit window", label
        start = datetime.now(KST).replace(hour=0, minute=0, second=0, microsecond=0)
        reset = start + timedelta(days=1)
        return start.isoformat(timespec="seconds"), reset.isoformat(timespec="seconds"), "KST day", "한국시간 00:00"

    def _provider_disabled_until(self, provider: str) -> str:
        return self.store.get_setting(f"llm_provider_disabled_until:{provider}", "")

    def _provider_probe_until(self, provider: str) -> str:
        return self.store.get_setting(f"llm_provider_probe_until:{provider}", "")

    def _provider_attempt_allowed(self, provider: str) -> bool:
        """Honor a live lock and serialize the first check after it expires."""
        disabled_until = self._provider_disabled_until(provider)
        if not disabled_until:
            return True
        if disabled_until > now_iso():
            return False
        return self.store.claim_provider_quota_probe(provider)

    def _provider_temporary_until(self, provider: str) -> str:
        key = f"llm_provider_temporary_until:{provider}"
        paused_until = self.store.get_setting(key, "")
        if paused_until and paused_until <= now_iso():
            self.store.set_setting(key, "")
            self.store.set_setting(f"llm_provider_temporary_reason:{provider}", "")
            return ""
        return paused_until

    def _provider_temporarily_paused(self, provider: str) -> bool:
        paused_until = self._provider_temporary_until(provider)
        return bool(paused_until and paused_until > now_iso())

    def _mark_provider_temporary(self, provider: str, reason: str = "") -> str:
        retry_after = (datetime.now(KST) + timedelta(minutes=PROVIDER_TEMPORARY_RETRY_MINUTES)).isoformat(timespec="seconds")
        self.store.set_setting(f"llm_provider_temporary_until:{provider}", retry_after)
        self.store.set_setting(f"llm_provider_temporary_reason:{provider}", str(reason)[:300])
        return retry_after

    def _clear_provider_transient_failures(self, provider: str) -> None:
        self.store.set_setting(f"llm_provider_transient_failures:{provider}", "0")

    def _clear_provider_quota_lock(self, provider: str) -> None:
        self.store.set_settings({
            f"llm_provider_disabled_until:{provider}": "",
            f"llm_provider_disabled_reason:{provider}": "",
            f"llm_provider_lock_mode:{provider}": "",
            f"llm_provider_lock_confidence:{provider}": "",
            f"llm_provider_lock_reset_source:{provider}": "",
            f"llm_provider_lock_detected_at:{provider}": "",
            f"llm_provider_probe_until:{provider}": "",
        })

    def _remember_provider_success(self, provider: str) -> None:
        self._clear_provider_transient_failures(provider)
        self._clear_provider_quota_lock(provider)

    def _mark_provider_exhausted(self, provider: str, decision: QuotaLockDecision) -> str:
        self.store.set_settings({
            f"llm_provider_disabled_until:{provider}": decision.lock_until,
            f"llm_provider_disabled_reason:{provider}": decision.reason[:500],
            f"llm_provider_lock_mode:{provider}": decision.lock_mode,
            f"llm_provider_lock_confidence:{provider}": decision.confidence,
            f"llm_provider_lock_reset_source:{provider}": decision.reset_source,
            f"llm_provider_lock_detected_at:{provider}": now_iso(),
            f"llm_provider_probe_until:{provider}": "",
            f"llm_provider_transient_failures:{provider}": "0",
        })
        return decision.lock_until

    def _attach_provider_guard(self, status: dict) -> dict:
        provider = str(status.get("provider") or "")
        disabled_until = self._provider_disabled_until(provider) if provider else ""
        temporary_until = self._provider_temporary_until(provider) if provider else ""
        probe_until = self._provider_probe_until(provider) if provider else ""
        status["disabled_until"] = disabled_until
        status["disabled_reason"] = self.store.get_setting(f"llm_provider_disabled_reason:{provider}", "") if provider else ""
        status["lock_mode"] = self.store.get_setting(f"llm_provider_lock_mode:{provider}", "") if provider else ""
        status["lock_confidence"] = self.store.get_setting(f"llm_provider_lock_confidence:{provider}", "") if provider else ""
        status["lock_reset_source"] = self.store.get_setting(f"llm_provider_lock_reset_source:{provider}", "") if provider else ""
        status["lock_detected_at"] = self.store.get_setting(f"llm_provider_lock_detected_at:{provider}", "") if provider else ""
        status["probe_until"] = probe_until
        status["temporary_until"] = temporary_until
        status["temporary_reason"] = self.store.get_setting(f"llm_provider_temporary_reason:{provider}", "") if provider else ""
        status["exhausted"] = bool(disabled_until and disabled_until > now_iso())
        status["quota_recheck_due"] = bool(disabled_until and disabled_until <= now_iso())
        status["quota_probe_in_flight"] = bool(status["quota_recheck_due"] and probe_until and probe_until > now_iso())
        status["temporarily_paused"] = bool(temporary_until and temporary_until > now_iso())
        status["available"] = bool(status.get("connected") and not status["exhausted"] and not status["temporarily_paused"] and not status["quota_probe_in_flight"])
        return status

    @staticmethod
    def _is_provider_quota_error(error: Exception) -> bool:
        return confirmed_free_quota_exhaustion(str(error or ""), int(getattr(error, "status", 0) or 0))

    @staticmethod
    def _is_common_daily_limit(error: Exception) -> bool:
        return MasterPressService._is_provider_quota_error(error)

    def _remote_provider_chain(self, include_openrouter: bool = False) -> list[tuple[str, str]]:
        chain = []
        if include_openrouter:
            chain.append(("openrouter", self.selected_case_llm_model()))
        if self.case_fallback_enabled():
            fallback = self.selected_case_fallback_model()
            chain.append((self._provider_for_switchable_llm_model(fallback), fallback))
        return self._active_provider_chain(chain)

    def _common_provider_chain(self) -> list[tuple[str, str]]:
        common_model = self.selected_common_llm_model()
        fallback_model = self.selected_common_fallback_model()
        chain = [
            (self._provider_for_switchable_llm_model(common_model), common_model),
            (self._provider_for_switchable_llm_model(fallback_model), fallback_model),
        ]
        return self._active_provider_chain(chain)

    def _remember_provider_failure(self, provider: str, error: Exception) -> str:
        if str(error) in {"reserve_llm_unavailable", "case_llm_providers_unavailable"}:
            return ""
        if not isinstance(error, OpenRouterError):
            return ""
        reason = str(error)
        decision = quota_lock_decision(error)
        if decision.confirmed_exhaustion:
            existing = self._provider_disabled_until(provider)
            if existing and existing > now_iso():
                return existing
            return self._mark_provider_exhausted(provider, decision)
        if self._provider_disabled_until(provider):
            self._clear_provider_quota_lock(provider)
        else:
            self.store.release_provider_quota_probe(provider)
        if error.retryable or error.status in {408, 429, 500, 502, 503, 504}:
            count_key = f"llm_provider_transient_failures:{provider}"
            try:
                failure_count = max(0, int(self.store.get_setting(count_key, "0"))) + 1
            except ValueError:
                failure_count = 1
            self.store.set_setting(count_key, str(failure_count))
            if failure_count >= PROVIDER_TRANSIENT_FAILURE_THRESHOLD:
                self._mark_provider_temporary(provider, reason)
        return ""

    def _try_common_reserve(self, article: dict) -> tuple[str, str, dict]:
        last_error: Exception | None = None
        chain = self._common_provider_chain()
        primary = (
            self._provider_for_switchable_llm_model(self.selected_common_llm_model()),
            self.selected_common_llm_model(),
        )
        for provider, model in chain:
            if not self._provider_attempt_allowed(provider):
                continue
            try:
                if hasattr(self.scoring, "analyze_article_common_with_provider"):
                    result = self.scoring.analyze_article_common_with_provider(provider, article, model)
                else:
                    result = self.scoring.analyze_article_common(article, model)
                self._remember_provider_success(provider)
                report = result.setdefault("analysis_report", {})
                if (provider, model) == primary:
                    report.pop("fallback", None)
                    report.pop("fallback_reason", None)
                else:
                    report["fallback"] = True
                    report["fallback_reason"] = "common_primary_unavailable"
                return provider, model, result
            except json.JSONDecodeError as error:
                last_error = error
                self._clear_provider_quota_lock(provider)
                # Workers AI can occasionally return an incomplete JSON body despite
                # a successful HTTP response. Retry its primary common-analysis call
                # once before consuming a reserve provider.
                if provider == "cloudflare":
                    try:
                        if hasattr(self.scoring, "analyze_article_common_with_provider"):
                            result = self.scoring.analyze_article_common_with_provider(provider, article, model)
                        else:
                            result = self.scoring.analyze_article_common(article, model)
                        self._remember_provider_success(provider)
                        report = result.setdefault("analysis_report", {})
                        if (provider, model) == primary:
                            report.pop("fallback", None)
                            report.pop("fallback_reason", None)
                        else:
                            report["fallback"] = True
                            report["fallback_reason"] = "common_primary_unavailable"
                        return provider, model, result
                    except json.JSONDecodeError as retry_error:
                        last_error = retry_error
                    except OpenRouterError as retry_error:
                        last_error = retry_error
                        setattr(retry_error, "provider", provider)
                        self._remember_provider_failure(provider, retry_error)
                continue
            except OpenRouterError as error:
                last_error = error
                setattr(error, "provider", provider)
                self._remember_provider_failure(provider, error)
                continue
        if last_error and self._active_provider_chain(chain):
            raise last_error
        raise OpenRouterError("reserve_llm_unavailable", status=503, retryable=True,
                              retry_after=self._next_provider_retry([
                                  self._provider_for_switchable_llm_model(self.selected_common_llm_model()),
                                  self._provider_for_switchable_llm_model(self.selected_common_fallback_model()),
                              ]), deferred=True)

    def _evaluate_cases_with_provider_chain(self, cases: list[dict], article: dict, analysis: dict) -> tuple[str, str, dict[str, dict]]:
        last_error: Exception | None = None
        chain = self._remote_provider_chain(include_openrouter=True)
        for provider, model in chain:
            if not self._provider_attempt_allowed(provider):
                continue
            try:
                if hasattr(self.scoring, "evaluate_cases_with_common_provider"):
                    results = self.scoring.evaluate_cases_with_common_provider(provider, cases, article, analysis, model)
                elif provider == "openrouter" and hasattr(self.scoring, "evaluate_cases_with_common"):
                    results = self.scoring.evaluate_cases_with_common(cases, article, analysis, model)
                else:
                    raise OpenRouterError(f"{provider}_client_unavailable", status=503, retryable=True)
                self._remember_provider_success(provider)
                return provider, model, results
            except OpenRouterError as error:
                last_error = error
                setattr(error, "provider", provider)
                self._remember_provider_failure(provider, error)
                if self._is_provider_quota_error(error) or error.status in {408, 429, 500, 502, 503, 504}:
                    continue
                raise
            except json.JSONDecodeError as error:
                last_error = error
                self._clear_provider_quota_lock(provider)
                continue
        if last_error and self._active_provider_chain(chain):
            raise last_error
        raise OpenRouterError("case_llm_providers_unavailable", status=503, retryable=True,
                              retry_after=self._next_provider_retry([
                                  "openrouter",
                                  self._provider_for_switchable_llm_model(self.selected_case_fallback_model()),
                              ]), deferred=True)

    def pipeline_provider_status(self) -> dict:
        burst_start_threshold = self.selected_burst_threshold()
        burst_stop_threshold = self.selected_burst_stop_threshold()
        common = {**self._status_for_switchable_llm_model(self.selected_common_llm_model(), False), "concurrency": 1, "slot": "model1"}
        common_fallback = {**self._status_for_switchable_llm_model(self.selected_common_fallback_model(), False), "concurrency": 1, "slot": "model2"}
        case = {**self.nvidia_status(False), "concurrency": 1, "batch_size": 5, "slot": "model1", "worker_slot": "oss"}
        case_fallback = {**self.openai_status(False), "concurrency": 1, "batch_size": 10, "slot": "model2", "worker_slot": "mini", "enabled": True}
        case_single = {**self.openrouter_status(False), "concurrency": 1, "batch_size": 1, "slot": "single"}
        burst = {**self.openrouter_status(False), "model": self.selected_common_turbo_model(),
                 "available": self.common_turbo_available(), "stage": "common",
                 "burst_threshold": burst_start_threshold}
        primary_unavailable = not bool(common.get("available"))
        if primary_unavailable:
            fallback = next((item for item in (common_fallback,) if item.get("available")), {})
            common["fallback_provider"] = fallback.get("provider", "")
            common["fallback_active"] = bool(fallback)
            common["fallback_model"] = fallback.get("model", "")
            if common.get("temporarily_paused"):
                common["state_label"] = f"기본 모델 10분 재시도 · {fallback.get('provider','예비')} 임시 사용 중" if fallback else "기본 모델 10분 재시도 대기"
            else:
                common["state_label"] = f"{fallback.get('provider','예비')} 예비 사용 중" if fallback else "공통분석 초기화 대기"
        chain_item = lambda item: {key: value for key, value in item.items() if key != "chain"}
        common["chain"] = [chain_item(common), chain_item(common_fallback)]
        temporary_waiting = any(item.get("temporarily_paused") for item in (common, case, common_fallback, case_fallback, case_single, burst))
        case["chain"] = [chain_item(case), chain_item(case_fallback), chain_item(case_single)]
        common_available = bool(common.get("available")) or bool(common_fallback.get("available"))
        case_available = bool(case.get("available")) or bool(case_fallback.get("available")) or bool(case_single.get("available"))
        burst_available = bool(burst.get("available"))
        common_operational = common_available or burst_available
        case_operational = case_available
        providers_waiting = not (common_operational and case_operational)
        # A ten-minute retry is a live, recoverable state, never an end-of-day shutdown.
        halted = bool(providers_waiting and not temporary_waiting)
        operation = {
            "halted": halted,
            "waiting": bool(providers_waiting),
            "message": ("일시 중단된 모델을 10분 뒤 다시 확인합니다." if temporary_waiting else "사용 가능한 병렬 분석 모델이 없습니다. 가장 이른 공급자 초기화 후 재개합니다.") if providers_waiting else "",
            "retry_after": min([value for value in [common.get("temporary_until"), common.get("reset_at"), case.get("temporary_until"), case.get("reset_at"), common_fallback.get("temporary_until"), common_fallback.get("reset_at"), case_fallback.get("temporary_until"), case_fallback.get("reset_at"), burst.get("temporary_until"), burst.get("reset_at")] if value] or [self._next_kst_midnight_iso()]) if providers_waiting else "",
            "reason": ("temporary_provider_retry" if temporary_waiting else "all_llm_providers_exhausted") if providers_waiting else "",
        }
        common_pending = self.store.pending_article_analysis_jobs(include_deferred=True)
        common_ready = self.store.pending_article_analysis_jobs()
        case_pending_jobs = self.store.pending_case_evaluation_jobs(include_deferred=True)
        case_ready_jobs = self.store.pending_case_evaluation_jobs()
        case_pending_bundles = self.store.pending_case_evaluation_bundles(include_deferred=True)
        case_ready_bundles = self.store.pending_case_evaluation_bundles()
        recent_burst_start = (datetime.now(KST) - timedelta(minutes=2)).isoformat(timespec="seconds")
        with self.store.connect() as connection:
            recent_common_burst = connection.execute(
                "SELECT 1 FROM article_analysis_jobs WHERE provider_lane='turbo' "
                "AND COALESCE(finished_at,started_at,queued_at)>=? LIMIT 1", (recent_burst_start,),
            ).fetchone()
        common_turbo = burst_available and common_pending >= burst_start_threshold
        case_turbo = False
        return {
            "common": common, "case": case,
            "common_fallback": common_fallback, "case_fallback": case_fallback, "case_single": case_single,
            "burst": burst,
            "queues": {
                "common_pending": common_pending,
                "common_ready": common_ready,
                "common_turbo": common_turbo,
                "case_pending_jobs": case_pending_jobs,
                "case_ready_jobs": case_ready_jobs,
                "case_pending_bundles": case_pending_bundles,
                "case_ready_bundles": case_ready_bundles,
                "case_turbo": case_turbo,
                "burst_start_threshold": burst_start_threshold,
                "burst_stop_threshold": burst_stop_threshold,
            },
            # Backward-compatible aliases for older dashboard clients.
            "reserve1": common_fallback, "reserve2": case_fallback,
            "embedding": self.ollama_embedding_status(), "operation": operation,
        }

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
        if report is None:
            report = {}
        report["feedback"] = self.store.analysis_feedback_summary(article_id, case_id)
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
        self.store.mark_article_cases_routed(analysis["id"])
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
        try:
            vectors = self.scoring.ollama.embeddings([f"search_document: {text}"])
            vector = vectors[0] if vectors else []
            if not vector:
                raise ValueError("embedding_empty")
            self.store.save_article_embedding(analysis["id"], embedding_model, vector)
            if hasattr(self.mirror, "article_embedding"): self.mirror.article_embedding(analysis, article, vector, embedding_model)
            queued_matches = self.press_releases.queue_for_article(analysis["id"])
            if queued_matches and hasattr(self.press_releases, "process_article_matches"):
                self.press_releases.process_article_matches(article["id"], limit=256)
            self._route_article_analysis(analysis, article, analysis.get("organization_id"))
            return True
        except Exception as error:
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

    def process_next_article_analysis(self, forced_provider: str = "", forced_model: str = "",
                                      provider_lane: str = "primary") -> dict | None:
        if not COMMON_LLM_LOCK.acquire(blocking=False):
            return None
        try:
            lease_owner = self._lease_owner()
            job = self.store.claim_next_article_analysis_job(lease_owner, provider_lane)
            if not job:
                return None
            analysis = self.store.get_article_analysis(job["article_analysis_id"])
            article = self.store.get_article(analysis["article_id"]) if analysis else None
            if not analysis or not article:
                self.store.finish_article_analysis_job(job["id"], False, 0, "article_or_analysis_missing", lease_owner=lease_owner)
                return {"id": job["id"], "status": "failed"}
            started = time.monotonic()
            provider = forced_provider or self._provider_for_switchable_llm_model(self.selected_common_llm_model())
            common_model = forced_model or self.selected_common_llm_model()
            fallback = False
            try:
                try:
                    if forced_provider and forced_model:
                        if not self._provider_attempt_allowed(forced_provider):
                            retry_after = self._next_provider_retry([forced_provider])
                            self.store.finish_article_analysis_job(
                                job["id"], False, 0, "provider_quota_locked", retryable=True,
                                retry_after=retry_after, keep_pending=True, lease_owner=lease_owner,
                            )
                            return {"id": job["id"], "status": "pending", "stage": "article", "provider": forced_provider, "retry_after": retry_after}
                        result = self.scoring.analyze_article_common_with_provider(forced_provider, article, forced_model)
                        self._remember_provider_success(forced_provider)
                    else:
                        provider, common_model, result = self._try_common_reserve(article)
                    fallback = (provider, common_model) != (
                        self._provider_for_switchable_llm_model(self.selected_common_llm_model()),
                        self.selected_common_llm_model(),
                    )
                except json.JSONDecodeError as error:
                    if forced_provider:
                        retry_after = now_iso()
                        self.store.finish_article_analysis_job(
                            job["id"], False, round((time.monotonic() - started) * 1000),
                            str(error), retryable=True, retry_after=retry_after,
                            keep_pending=True, lease_owner=lease_owner,
                        )
                        return {"id": job["id"], "status": "pending", "stage": "article", "provider": provider, "retry_after": retry_after, "handoff": True}
                    if int(job.get("attempts") or 0) < 1:
                        duration = round((time.monotonic() - started) * 1000)
                        self.store.finish_article_analysis_job(job["id"], False, duration, str(error), retryable=True, lease_owner=lease_owner)
                        return {"id": job["id"], "status": "pending", "stage": "article", "provider": provider, "error": "invalid_json_retry"}
                    result = self.scoring.ollama.fallback_article_common(article, common_model, str(error))
                    fallback = True
                    provider = "local_fallback"
                except OpenRouterError as error:
                    raise
                saved = self.store.save_article_analysis(analysis["id"], result, common_model, job["id"], lease_owner)
                if not saved:
                    return {"id": job["id"], "status": "stale", "stage": "article", "provider": provider}
                self.store.finish_article_analysis_job(job["id"], True, round((time.monotonic() - started) * 1000), lease_owner=lease_owner)
                routed = {"case_candidates": 0, "case_excluded": 0, "case_queued": 0, "embedded": 0, "fallback": int(fallback), "provider": provider}
                return {"id": job["id"], "status": "completed", "stage": "article", "provider": provider, "counts": routed}
            except (GroqError, OpenRouterError) as error:
                duration = round((time.monotonic() - started) * 1000)
                provider = str(getattr(error, "provider", provider) or provider)
                lock_until = self._remember_provider_failure(provider, error)
                retry_after = now_iso() if forced_provider else (
                    lock_until or getattr(error, "retry_after", "") or self._next_provider_retry([provider])
                )
                defer = bool(getattr(error, "deferred", False) or self._is_provider_quota_error(error))
                if defer or (getattr(error, "retryable", False) and int(job.get("attempts") or 0) < 2):
                    self.store.finish_article_analysis_job(job["id"], False, duration, str(error), retryable=True, retry_after=retry_after, keep_pending=defer, lease_owner=lease_owner)
                    return {"id": job["id"], "status": "pending", "stage": "article", "provider": provider, "http_status": getattr(error, "status", 0), "error": str(error), "retry_after": retry_after}
                result = self.scoring.ollama.fallback_article_common(article, common_model, str(error))
                saved = self.store.save_article_analysis(analysis["id"], result, common_model, job["id"], lease_owner)
                if not saved:
                    return {"id": job["id"], "status": "stale", "stage": "article", "provider": provider}
                self.store.finish_article_analysis_job(job["id"], True, duration, lease_owner=lease_owner)
                routed = {"case_candidates": 0, "case_excluded": 0, "case_queued": 0, "embedded": 0, "fallback": 1, "provider": "local_fallback"}
                return {"id": job["id"], "status": "completed", "stage": "article", "provider": "local_fallback", "counts": routed}
            except Exception as error:
                self.store.finish_article_analysis_job(job["id"], False, round((time.monotonic() - started) * 1000), str(error), lease_owner=lease_owner)
                return {"id": job["id"], "status": "failed", "stage": "article", "error": str(error)}
        finally:
            COMMON_LLM_LOCK.release()

    def _queue_shadow_case_evaluation(self, evaluation: dict, case: dict, article: dict, analysis: dict, result: dict, model: str) -> bool:
        settings = getattr(self, "settings", None)
        if not hasattr(self, "shadow_cases") or not self.shadow_enabled() or not getattr(settings, "openai_api_key", ""):
            return False
        if result.get("llm_error") or str(model).startswith("gpt-5.4-mini"):
            return False
        score = float(result.get("final_score") or 0)
        threshold = float(case.get("relevance_threshold", 70) or 70)
        components = (result.get("analysis_report") or {}).get("components") or {}
        boundary = abs(score - threshold) <= 10
        evidence_gap = str(result.get("evidence_status") or "") != "verified"
        sensitive = _case_has_negative_intent(case) or _article_has_negative_signal(article, analysis)
        target_gap = components.get("target_verified") is False
        if not (boundary or evidence_gap or sensitive or target_gap):
            return False
        status = self.shadow_status()
        if status["requested"] >= status["daily_limit"] or status["queue_depth"] >= status["daily_limit"]:
            return False
        payload = {
            **evaluation, **result, "model": model,
            "id": evaluation["id"], "decision": result.get("decision", "low"),
        }
        return self.shadow_cases.queue(payload)

    def process_next_shadow_case_evaluation(self) -> dict | None:
        if not SHADOW_CASE_SEMAPHORE.acquire(blocking=False):
            return None
        try:
            status = self.shadow_status()
            if not status["enabled"] or not status["available"] or status["requested"] >= status["daily_limit"]:
                return None
            job = self.shadow_cases.next_job()
            if not job:
                return None
            started = time.monotonic()
            try:
                evaluation = self.store.get_case_evaluation(str(job["case_evaluation_id"]))
                article = self.store.get_article(str(job["article_id"]))
                case = self.store.get_case(str(job["case_id"]))
                analysis = self.store.get_article_analysis(str(job["article_analysis_id"]))
                if not all((evaluation, article, case, analysis)) or analysis.get("status") != "completed":
                    raise RuntimeError("shadow_source_missing")
                evaluation_case, _organization = self.analysis_case(case)
                evaluation_case["_semantic_raw"] = float(evaluation.get("semantic_raw") or 0)
                evaluation_case["_semantic_score"] = float(evaluation.get("semantic_score") or 0)
                model = str(getattr(self.settings, "openai_shadow_model", "gpt-5.4-mini"))
                judgments = self.scoring.shadow_llm.judge_cases([evaluation_case], article, analysis, model)
                judgment = judgments.get(str(evaluation_case["id"]))
                if not judgment:
                    raise RuntimeError("shadow_result_missing")
                result = self.scoring.evaluate_case_with_common(evaluation_case, article, analysis, model, judgment)
                self.shadow_cases.finish(str(job["id"]), result, duration_ms=round((time.monotonic() - started) * 1000))
                return {
                    "id": job["id"], "stage": "shadow_case", "status": "completed",
                    "decision_match": result.get("decision") == job.get("primary_decision"),
                    "tokens": int(((result.get("analysis_report") or {}).get("usage") or {}).get("total_tokens") or 0),
                }
            except Exception as error:
                self.shadow_cases.finish(str(job["id"]), error=type(error).__name__, duration_ms=round((time.monotonic() - started) * 1000))
                return {"id": job["id"], "stage": "shadow_case", "status": "failed", "error": type(error).__name__}
        finally:
            SHADOW_CASE_SEMAPHORE.release()

    def _recover_case_batch_json_with_single(
        self, cases: list[dict], article: dict, analysis: dict,
        failed_provider: str, batch_error: Exception,
    ) -> tuple[str, dict[str, dict]]:
        model = self.selected_case_single_model()
        if not self._provider_status("openrouter", model).get("available"):
            return model, {}
        results: dict[str, dict] = {}
        for case in cases:
            if not self._provider_attempt_allowed("openrouter"):
                break
            try:
                result = self.scoring.evaluate_case_with_common_provider(
                    "openrouter", case, article, analysis, model,
                )
            except OpenRouterError as error:
                self._remember_provider_failure("openrouter", error)
                break
            except (json.JSONDecodeError, ValueError, TypeError):
                break
            report = result.setdefault("analysis_report", {})
            report["batch_fallback_reason"] = "batch_json_invalid"
            report["batch_fallback_from_provider"] = failed_provider
            report["batch_fallback_error"] = str(batch_error)[:200]
            results[str(case["id"])] = result
            self._remember_provider_success("openrouter")
        return model, results

    def process_next_case_evaluation(self, forced_provider: str = "", forced_model: str = "",
                                     provider_lane: str = "primary", batch_size: int | None = None,
                                     single_unowned_only: bool = False,
                                     allow_unowned_single: bool = True) -> dict | None:
        if not REMOTE_CASE_SEMAPHORE.acquire(blocking=False):
            return None
        try:
            lease_owner = self._lease_owner()
            claim_provider = forced_provider or "openrouter"
            jobs = self.store.next_case_evaluation_batch(
                batch_size or self.case_batch_size_for_provider(claim_provider), claim_provider,
                lease_owner=lease_owner, provider_lane=provider_lane,
                single_unowned_only=single_unowned_only,
                allow_unowned_single=allow_unowned_single,
            )
            if not jobs:
                return None
            batch_id = str(jobs[0].get("batch_id") or "")
            counts = {"scored": 0, "queued": 0, "sent": 0, "delivery_failed": 0, "batch_size": len(jobs), "missing": 0}
            prepared: list[tuple[dict, dict, dict]] = []
            article = None
            analysis = None
            default_case_model = forced_model or self.selected_case_llm_model()
            for job in jobs:
                evaluation = self.store.get_case_evaluation(job["case_evaluation_id"])
                item_article = self.store.get_article(evaluation["article_id"]) if evaluation else None
                case = self.store.get_case(evaluation["case_id"]) if evaluation else None
                item_analysis = self.store.get_article_analysis(evaluation["article_analysis_id"]) if evaluation else None
                if not evaluation or not item_article or not case or not item_analysis:
                    self.store.finish_case_evaluation_job(job["id"], False, 0, "article_case_or_common_analysis_missing", retryable=True, lease_owner=lease_owner)
                    counts["missing"] += 1
                    continue
                article, analysis = item_article, item_analysis
                if not case.get("is_active"):
                    result = self.scoring.fallback_case_evaluation(case, article, analysis, "case_inactive", default_case_model)
                    self.store.save_case_evaluation(evaluation["id"], result, default_case_model, job["id"], lease_owner)
                    self.store.finish_case_evaluation_job(job["id"], True, 0, lease_owner=lease_owner)
                    counts["scored"] += 1
                    continue
                if analysis.get("status") != "completed":
                    retry_at = (datetime.now(KST) + timedelta(seconds=30)).isoformat(timespec="seconds")
                    self.store.finish_case_evaluation_job(job["id"], False, 0, "common_analysis_pending", retryable=True, retry_after=retry_at, keep_pending=True, lease_owner=lease_owner)
                    counts["missing"] += 1
                    continue
                evaluation_case, _organization = self.analysis_case(case)
                evaluation_case["_semantic_raw"] = float(evaluation.get("semantic_raw") or 0)
                evaluation_case["_semantic_score"] = float(evaluation.get("semantic_score") or 0)
                prepared.append((job, evaluation, evaluation_case))
            if not prepared or not article or not analysis:
                return {"id": batch_id, "status": "partial", "stage": "case_batch", "counts": counts}

            started = time.monotonic()
            provider = forced_provider or "openrouter"
            case_model = default_case_model
            try:
                cases = [item[2] for item in prepared]
                if forced_provider and forced_model:
                    if not self._provider_attempt_allowed(forced_provider):
                        retry_after = now_iso()
                        for job, _evaluation, _case in prepared:
                            self.store.finish_case_evaluation_job(
                                job["id"], False, 0, "provider_quota_locked", retryable=True,
                                retry_after=retry_after, keep_pending=True, lease_owner=lease_owner,
                            )
                        article_analysis_id = str(jobs[0].get("article_analysis_id") or "")
                        if article_analysis_id:
                            self.store.release_case_bundle_provider(article_analysis_id, forced_provider)
                        return {"id": batch_id, "status": "pending", "stage": "case_batch", "provider": forced_provider, "retry_after": retry_after, "counts": counts, "handoff": True}
                    try:
                        results = self.scoring.evaluate_cases_with_common_provider(
                            forced_provider, cases, article, analysis, forced_model,
                        )
                    except json.JSONDecodeError as batch_error:
                        if forced_provider == "openrouter":
                            raise
                        case_model, results = self._recover_case_batch_json_with_single(
                            cases, article, analysis, forced_provider, batch_error,
                        )
                        if not results:
                            raise
                        provider = "openrouter"
                    else:
                        self._remember_provider_success(forced_provider)
                else:
                    provider, case_model, results = self._evaluate_cases_with_provider_chain(cases, article, analysis)
                should_send = False
                for job, evaluation, case in prepared:
                    result = results.get(str(case["id"]))
                    result_model = case_model
                    if not result:
                        single_model = self.selected_case_single_model()
                        if not self._provider_attempt_allowed("openrouter"):
                            self.store.finish_case_evaluation_job(
                                job["id"], False, round((time.monotonic() - started) * 1000),
                                "batch_result_missing", retryable=True, lease_owner=lease_owner,
                            )
                            counts["missing"] += 1
                            continue
                        try:
                            if hasattr(self.scoring, "evaluate_case_with_common_provider"):
                                result = self.scoring.evaluate_case_with_common_provider(
                                    "openrouter", case, article, analysis, single_model,
                                )
                            else:
                                result = self.scoring.evaluate_case_with_common(
                                    case, article, analysis, single_model,
                                )
                            self._remember_provider_success("openrouter")
                            result_model = single_model
                            report = result.setdefault("analysis_report", {})
                            report["batch_fallback_reason"] = "batch_result_missing"
                            report["batch_fallback_from_provider"] = provider
                        except OpenRouterError as error:
                            self._remember_provider_failure("openrouter", error)
                            self.store.finish_case_evaluation_job(
                                job["id"], False, round((time.monotonic() - started) * 1000),
                                "batch_result_missing", retryable=True, lease_owner=lease_owner,
                            )
                            counts["missing"] += 1
                            continue
                        except Exception as error:
                            self.store.finish_case_evaluation_job(
                                job["id"], False, round((time.monotonic() - started) * 1000),
                                f"batch_fallback_failed:{type(error).__name__}", retryable=True,
                                lease_owner=lease_owner,
                            )
                            counts["missing"] += 1
                            continue
                    saved = self.store.save_case_evaluation(evaluation["id"], result, result_model, job["id"], lease_owner)
                    if not saved:
                        counts["missing"] += 1
                        continue
                    self._queue_shadow_case_evaluation(evaluation, case, article, analysis, result, result_model)
                    self.store.finish_case_evaluation_job(job["id"], True, round((time.monotonic() - started) * 1000), lease_owner=lease_owner)
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
                lock_until = ""
                if isinstance(error, OpenRouterError):
                    provider = str(getattr(error, "provider", provider) or provider)
                    lock_until = self._remember_provider_failure(provider, error)
                else:
                    self._clear_provider_quota_lock(provider)
                if forced_provider:
                    if isinstance(error, json.JSONDecodeError):
                        max_attempts = max(int(job.get("attempts") or 1) for job, _evaluation, _case in prepared)
                        cooldown_seconds = min(900, max(60, max_attempts * 30))
                        handoff_at = (datetime.now(KST) + timedelta(seconds=cooldown_seconds)).isoformat(timespec="seconds")
                    else:
                        handoff_at = now_iso()
                    for job, _evaluation, _case in prepared:
                        self.store.finish_case_evaluation_job(
                            job["id"], False, duration, str(error), retryable=True,
                            retry_after=handoff_at, keep_pending=True, lease_owner=lease_owner,
                        )
                    article_analysis_id = str(jobs[0].get("article_analysis_id") or "")
                    if article_analysis_id:
                        self.store.release_case_bundle_provider(article_analysis_id, forced_provider)
                    return {
                        "id": batch_id, "status": "pending", "stage": "case_batch",
                        "provider": provider, "http_status": getattr(error, "status", 0),
                        "error": str(error), "retry_after": handoff_at, "counts": counts,
                        "handoff": True,
                    }
                retry_after = lock_until or getattr(error, "retry_after", "") or self._next_provider_retry([provider])
                defer = bool(getattr(error, "deferred", False) or self._is_provider_quota_error(error))
                pending = 0
                for job, evaluation, case in prepared:
                    if defer or (getattr(error, "retryable", False) and int(job.get("attempts") or 0) < 3):
                        self.store.finish_case_evaluation_job(job["id"], False, duration, str(error), retryable=True, retry_after=retry_after, keep_pending=defer, lease_owner=lease_owner)
                        pending += 1
                    else:
                        result = self.scoring.fallback_case_evaluation(case, article, analysis, str(error), case_model)
                        self.store.save_case_evaluation(evaluation["id"], result, case_model, job["id"], lease_owner)
                        self.store.finish_case_evaluation_job(job["id"], True, duration, lease_owner=lease_owner)
                        counts["scored"] += 1
                return {"id": batch_id, "status": "pending" if pending else "completed", "stage": "case_batch", "provider": provider, "http_status": getattr(error, "status", 0), "error": str(error), "retry_after": retry_after, "counts": counts}
            except Exception as error:
                duration = round((time.monotonic() - started) * 1000)
                for job, _evaluation, _case in prepared:
                    self.store.finish_case_evaluation_job(job["id"], False, duration, str(error), retryable=True, lease_owner=lease_owner)
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
                provider, case_model, results = self._evaluate_cases_with_provider_chain([evaluation_case], article, analysis)
                result = results[str(evaluation_case["id"])]
                self._queue_shadow_case_evaluation(evaluation, evaluation_case, article, analysis, result, case_model)
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
                provider = str(getattr(error, "provider", "openrouter") or "openrouter")
                lock_until = self._remember_provider_failure(provider, error)
                if error.deferred or (error.retryable and int(job.get("attempts") or 0) < 3):
                    self.store.finish_case_evaluation_job(
                        job["id"], False, duration, str(error), retryable=True,
                        retry_after=lock_until or error.retry_after or self._next_provider_retry(["openrouter"]), keep_pending=error.deferred,
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
            _provider, _model, results = self._evaluate_cases_with_provider_chain([evaluation_case], article, common)
            result = results[str(evaluation_case["id"])]
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

    def magazine_link(self, edition_id: str) -> str:
        redirect = urllib.parse.urlsplit(self.settings.kakao_redirect_uri)
        edition_id = urllib.parse.quote(str(edition_id), safe="")
        if redirect.scheme in {"http", "https"} and redirect.netloc:
            return f"{redirect.scheme}://{redirect.netloc}/poc/master-press/?view=magazine&edition={edition_id}"
        return f"/poc/master-press/?view=magazine&edition={edition_id}"

    @staticmethod
    def magazine_kakao_title(edition: dict) -> str:
        raw = str(edition.get("title") or "매거진")
        return " ".join(raw.replace("CaseON", "").split()) or "매거진"

    @staticmethod
    def magazine_message_text(edition: dict, selected_case_ids: list[str]) -> str:
        selected, issue_keys, headlines = set(selected_case_ids), set(), []
        for member in edition.get("members") or []:
            matches = {str(item.get("id") or "") for item in member.get("case_matches") or []}
            if not (selected & matches) or member.get("issue_key") in issue_keys:
                continue
            issue_keys.add(member.get("issue_key"))
            headlines.append(str(member.get("title") or "주요 뉴스")[:24])
            if len(headlines) == 5:
                break
        title = MasterPressService.magazine_kakao_title({
            **edition,
            "title": edition.get("title") or edition_title(edition.get("organization_name") or "기관", edition.get("edition_slot") or "morning"),
        })
        lines = [f"{title} 발간되었습니다.", "", "주요뉴스"]
        lines.extend(f"- {headline}" for headline in headlines)
        return "\n".join(lines)[:200]

    def send_due(self, limit: int = 20) -> dict:
        if not DELIVERY_LOCK.acquire(blocking=False):
            return {"sent": 0, "failed": 0, "errors": []}
        try:
            article = self._send_due(limit)
            magazine = self._send_due_magazines(limit)
            return {"sent": article["sent"] + magazine["sent"], "failed": article["failed"] + magazine["failed"], "errors": article["errors"] + magazine["errors"], "magazine": magazine}
        finally:
            DELIVERY_LOCK.release()

    def _send_due(self, limit: int = 20) -> dict:
        sent = failed = 0
        errors = []
        owner = self._lease_owner()
        for delivery in self.store.due_deliveries(limit, lease_owner=owner):
            try:
                status, _response = self.kakao.send_to_me(
                    delivery["recipient_id"],
                    self.message_text(delivery),
                    self.article_link(delivery["article_id"], delivery["original_url"]),
                    image_url=str(delivery.get("image_url") or ""),
                    title=str(delivery.get("title") or ""),
                    description=str(delivery.get("summary") or ""),
                )
                if self.store.finish_delivery(delivery["id"], True, status, lease_owner=owner):
                    sent += 1
                else:
                    errors.append(f"delivery_lease_lost:{delivery['id']}")
                    failed += 1
            except Exception as error:
                code = int(getattr(error, "status", 502))
                message = str(error)
                if code == 403 and "insufficient" in message.casefold() and "scope" in message.casefold():
                    notice = "카카오 메시지 발송 권한이 없어 재동의가 필요합니다."
                    self.store.mark_recipient_reauthorize(delivery["recipient_id"], notice)
                    self.store.fail_delivery_permanently(
                        delivery["id"], code, notice, lease_owner=owner,
                    )
                    errors.append(notice)
                else:
                    self.store.finish_delivery(
                        delivery["id"], False, code, message, lease_owner=owner,
                    )
                    errors.append(message)
                failed += 1
        return {"sent": sent, "failed": failed, "errors": errors}

    def publish_due_magazines(self) -> dict:
        publisher = MagazinePublisher(self.store)
        editions = publisher.publish_due()
        queued = sum(self.store.queue_magazine_deliveries(edition) for edition in editions)
        return {"published": len(editions), "queued": queued, "edition_ids": [edition.get("id") for edition in editions], "deferred": publisher.deferred}

    @staticmethod
    def magazine_edition_metrics(edition: dict | None) -> dict:
        """Summarize a snapshot so an admin can verify that republishing changed it."""
        members = list((edition or {}).get("members") or [])
        issue_sizes: dict[str, int] = {}
        for member in members:
            issue_key = str(member.get("issue_key") or "article:" + str(member.get("article_id") or ""))
            issue_sizes[issue_key] = issue_sizes.get(issue_key, 0) + 1
        return {
            "issue_count": len(issue_sizes), "article_count": len(members),
            "grouped_issue_count": sum(1 for size in issue_sizes.values() if size > 1),
            "grouped_article_count": sum(size for size in issue_sizes.values() if size > 1),
            "generated_at": str((edition or {}).get("generated_at") or ""),
        }

    def republish_magazine(self, edition_id: str) -> dict:
        publisher = MagazinePublisher(self.store)
        edition = publisher.edition(str(edition_id))
        if not edition:
            raise ValueError("재발행할 매거진을 찾지 못했습니다.")
        readiness = publisher.window_readiness(
            str(edition["organization_id"]), str(edition["window_start_at"]), str(edition["window_end_at"])
        )
        if not readiness["ready"]:
            pending = sum(int(readiness.get(key) or 0) for key in ("pending_common", "pending_embedding", "pending_case_articles", "pending_similarity"))
            raise ValueError(f"기사 묶음 처리가 아직 끝나지 않았습니다. 대기 {pending}건")
        refreshed = publisher.publish(
            str(edition["organization_id"]), str(edition["edition_date"]), str(edition["edition_slot"]),
            str(edition["window_start_at"]), str(edition["window_end_at"]), force=True,
        )
        try:
            similarity_threshold = float(self.store.get_setting("magazine_similarity_threshold", "90"))
        except (TypeError, ValueError):
            similarity_threshold = 90.0
        return {
            "republished": True, "edition": refreshed, "readiness": readiness,
            "similarity_threshold": similarity_threshold,
            "previous": self.magazine_edition_metrics(edition),
            "current": self.magazine_edition_metrics(refreshed),
        }

    def resend_magazine(self, edition_id: str) -> dict:
        publisher = MagazinePublisher(self.store)
        edition = publisher.edition(str(edition_id))
        if not edition:
            raise ValueError("재발송할 매거진을 찾지 못했습니다.")
        queued = self.store.requeue_magazine_deliveries(edition)
        delivery = self.send_due_magazines(max(20, queued))
        return {"edition_id": str(edition_id), "queued": queued, "delivery": delivery}

    def publish_magazine_slot(self, slot: str, reference: datetime | None = None, force: bool = False) -> dict:
        publisher = MagazinePublisher(self.store)
        editions = publisher.publish_for_slot(slot, reference=reference, force=force)
        queued = sum(self.store.queue_magazine_deliveries(edition) for edition in editions)
        delivery = self.send_due_magazines(max(20, queued))
        return {
            "slot": slot,
            "published": len(editions),
            "queued": queued,
            "edition_ids": [str(edition.get("id") or "") for edition in editions],
            "delivery": delivery,
            "deferred": publisher.deferred,
        }

    def send_due_magazines(self, limit: int = 20) -> dict:
        return self._send_due_magazines(limit)

    def _send_due_magazines(self, limit: int = 20) -> dict:
        sent = failed = 0
        errors: list[str] = []
        publisher = MagazinePublisher(self.store)
        for delivery in self.store.due_magazine_deliveries(limit):
            try:
                edition = publisher.edition(str(delivery["edition_id"])) or {}
                selected_case_ids = json.loads(str(delivery.get("selected_case_ids") or "[]"))
                text = self.magazine_message_text(edition, selected_case_ids)
                status, _response = self.kakao.send_to_me(
                    delivery["recipient_id"], text, self.magazine_link(delivery["edition_id"]),
                    title=self.magazine_kakao_title(edition), description=text,
                    button_title="매거진 바로가기",
                )
                self.store.finish_magazine_delivery(delivery["id"], True, status)
                sent += 1
            except Exception as error:
                code, message = int(getattr(error, "status", 502)), str(error)
                self.store.finish_magazine_delivery(delivery["id"], False, code, message)
                errors.append(message)
                failed += 1
        return {"sent": sent, "failed": failed, "errors": errors}

    def resend_recent_magazines(self, recipient_id: str, limit: int = 3) -> dict:
        recipient = self.store.get_recipient(str(recipient_id))
        if not recipient or recipient.get("status") != "active":
            raise ValueError("활성 카카오 수신자를 찾지 못했습니다.")
        recent = self.store.recent_magazines_for_recipient(str(recipient_id), limit)
        if not recent:
            raise ValueError("재발송할 매거진이 없거나 매거진 알림 구독이 설정되지 않았습니다.")
        publisher = MagazinePublisher(self.store)
        sent = []
        for item in reversed(recent):
            edition = publisher.edition(str(item["id"])) or {}
            selected_case_ids = item.get("selected_case_ids") or []
            text = self.magazine_message_text(edition, selected_case_ids)
            status, _response = self.kakao.send_to_me(
                str(recipient_id), text, self.magazine_link(str(item["id"])),
                title=self.magazine_kakao_title(edition), description=text,
                button_title="매거진 바로가기",
            )
            sent.append({
                "edition_id": str(item["id"]),
                "title": self.magazine_kakao_title(edition),
                "edition_date": item.get("edition_date"),
                "edition_slot": item.get("edition_slot"),
                "status": status,
            })
        return {"sent": len(sent), "items": sent}

    def process_next_case_proposal_moderation(self) -> dict | None:
        proposal = self.store.next_case_proposal_for_moderation()
        if not proposal:
            return None
        model = str(getattr(self.settings, "openai_moderation_model", "") or "gpt-5.4-mini")
        text = "\n".join([
            f"제목: {proposal.get('original_title') or proposal.get('title') or ''}",
            f"닉네임: {proposal.get('nickname') or ''}",
            f"프롬프트: {proposal.get('original_prompt') or proposal.get('prompt') or ''}",
            "키워드: " + ", ".join(proposal.get("original_include_terms") or proposal.get("include_terms") or []),
            "필수키워드: " + ", ".join(proposal.get("original_required_terms") or proposal.get("required_terms") or []),
        ])[:6000]
        started = time.monotonic()
        try:
            response = self.scoring.shadow_llm.request("/chat/completions", {
                "model": model, "stream": False, "format": "json",
                "record_stage": "moderation",
                "messages": [
                    {"role": "system", "content": "당신은 공개 게시판 클린 AI입니다. 욕설, 혐오·비하, 개인 공격, 명예훼손성 비방, 음란·폭력 조장, 개인정보 노출, 광고·스팸이 있으면 unsafe=true로 판단하세요. 공공기관 정책 비판이나 케이스 제안 자체는 허용하세요. unsafe=true이면 원문에 실제 존재하는 위반 표현을 evidence 배열에 정확히 인용하세요. 근거 표현을 정확히 인용할 수 없으면 unsafe=false입니다. JSON만 반환하세요."},
                    {"role": "user", "content": "다음 케이스 신청 게시글을 검사하세요. JSON 형식: {\"unsafe\":false,\"reason\":\"짧은 한국어 사유\",\"evidence\":[\"원문의 정확한 위반 표현\"]}\n\n" + text},
                ],
                "options": {"temperature": 0, "num_predict": 300},
                "response_schema": {
                    "name": "case_proposal_moderation",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "unsafe": {"type": "boolean"},
                            "reason": {"type": "string"},
                            "evidence": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["unsafe", "reason", "evidence"],
                        "additionalProperties": False,
                    },
                },
            })
            raw = response.get("message", {}).get("content", "")
            data = parse_llm_json(raw)
            unsafe, reason, evidence = verified_case_proposal_moderation(text, data)
            item = self.store.finish_case_proposal_moderation(proposal["id"], unsafe, reason, model)
            return {"proposal_id": proposal["id"], "flagged": unsafe, "reason": reason, "evidence": evidence, "item": item}
        except Exception as error:
            return {"proposal_id": proposal["id"], "flagged": False, "error": str(error), "item": proposal}

    def _body_backfill_config(self) -> tuple[int, int, int, int, int, int, int]:
        def setting(name: str, default: int, low: int, high: int) -> int:
            try: return max(low, min(high, int(self.store.get_setting(name, str(default)))))
            except (TypeError, ValueError): return default
        start_hour = setting("body_backfill_start_hour", 0, 0, 23)
        end_hour = setting("body_backfill_end_hour", 6, 1, 24)
        if start_hour >= end_hour:
            start_hour, end_hour = 0, 24
        return (
            setting("body_backfill_window_days", 7, 1, 7),
            setting("body_backfill_daily_limit", 180, 1, 1000),
            setting("body_backfill_interval_seconds", 600, 60, 3600),
            setting("body_backfill_domain_interval_seconds", 600, 60, 86400),
            setting("body_backfill_batch_size", 6, 1, 20),
            start_hour, end_hour,
        )

    def _body_backfill_enabled(self) -> bool:
        return str(self.store.get_setting("body_backfill_enabled", "0") or "").strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _body_retry_at(error: str, attempts: int, now: datetime) -> tuple[bool, str]:
        permanent = {"robots_disallowed", "http_401", "http_403", "http_404", "http_410", "http_451"}
        if error in permanent: return False, ""
        max_attempts = 2 if error == "body_unavailable" else 3
        if attempts >= max_attempts: return False, ""
        hours = (6, 24, 72)[min(max(0, attempts - 1), 2)]
        return True, (now + timedelta(hours=hours)).isoformat(timespec="seconds")

    def body_backfill_status(self) -> dict:
        window_days, daily_limit, interval_seconds, domain_interval_seconds, batch_size, start_hour, end_hour = self._body_backfill_config(); now = datetime.now(KST)
        status = self.store.missing_body_status(now.isoformat(timespec="seconds"), (now-timedelta(days=window_days)).isoformat(timespec="seconds"))
        key=f"body_backfill_processed:{now.strftime('%Y%m%d')}"
        try: processed=int(self.store.get_setting(key,"0") or 0)
        except ValueError: processed=0
        status.update({"window_days":window_days,"batch_size":batch_size,"processed_today":max(0,processed),"daily_limit":daily_limit,
            "daily_remaining":max(0,daily_limit-processed),"next_run_at":self.store.get_setting("body_backfill_next_run_at",""),
            "enabled":self._body_backfill_enabled(),"paused":not self._body_backfill_enabled(),"interval_seconds":interval_seconds,"domain_interval_seconds":domain_interval_seconds,
            "start_hour":start_hour,"end_hour":end_hour,"within_schedule":start_hour <= now.hour < end_hour})
        return status

    def backfill_missing_article_bodies(self) -> dict:
        window_days, daily_limit, interval_seconds, domain_interval_seconds, batch_size, start_hour, end_hour = self._body_backfill_config(); now=datetime.now(KST)
        result={"paused":False,"processed":0,"filled":0,"failed":0,"selected":0,"reason":""}
        if not self._body_backfill_enabled(): result.update(paused=True,reason="disabled"); return result
        if not (start_hour <= now.hour < end_hour): result.update(paused=True,reason="scheduled_window"); return result
        key=f"body_backfill_processed:{now.strftime('%Y%m%d')}"
        try: processed=int(self.store.get_setting(key,"0") or 0)
        except ValueError: processed=0
        next_run=self.store.get_setting("body_backfill_next_run_at","")
        if processed>=daily_limit: result["reason"]="daily_limit"; return result
        if next_run and next_run>now.isoformat(timespec="seconds"): result["reason"]="interval"; return result
        remaining=max(1,daily_limit-processed)
        # Look beyond one publisher's newest rows so the existing per-domain
        # cooldown can still yield a diverse batch without relaxing safety.
        candidate_limit=min(200,max(batch_size*20,min(batch_size*40,remaining*4)))
        rows=self.store.list_articles_missing_body(now.isoformat(timespec="seconds"),(now-timedelta(days=window_days)).isoformat(timespec="seconds"),candidate_limit)
        result["selected"]=len(rows)
        for row in rows:
            host=urllib.parse.urlsplit(str(row.get("original_url") or "")).netloc.lower()
            if not host: continue
            domain_key="body_backfill_domain_next_at:"+host
            if self.store.get_setting(domain_key,"")>now.isoformat(timespec="seconds"): continue
            fetched=self.collector.fetch_body(str(row["original_url"]))
            attempts=int(row.get("body_attempts") or 0)+1; body=str(fetched.get("body") or "")
            retryable,next_attempt=(False,"") if body else self._body_retry_at(str(fetched.get("error") or "body_unavailable"),attempts,now)
            self.store.save_body_backfill_result(row["id"],fetched,retryable,next_attempt)
            self.store.increment_setting_counter(key,1)
            self.store.set_setting(domain_key,(now+timedelta(seconds=domain_interval_seconds)).isoformat(timespec="seconds"))
            result["processed"]+=1
            result["filled"]+=1 if body else 0
            result["failed"]+=0 if body else 1
            if result["processed"]>=min(batch_size,remaining): break
        self.store.set_setting("body_backfill_next_run_at",(now+timedelta(seconds=interval_seconds)).isoformat(timespec="seconds"))
        if not result["processed"]: result["reason"]="no_eligible_candidate"
        return result

    def orchestration_tick(self) -> dict:
        results = {"organizations": [], "cases": [], "magazine": {}, "delivery": {}, "press_releases": {}, "body_backfill": {}, "cleanup": {}}
        try:
            results["magazine"] = self.publish_due_magazines()
        except Exception as error:
            results["magazine"] = {"error": str(error)}
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
        if getattr(self.settings, "web_body_backfill_enabled", False):
            try:
                results["body_backfill"] = self.backfill_missing_article_bodies()
            except Exception as error:
                results["body_backfill"] = {"error": str(error)}
        else:
            results["body_backfill"] = {"deferred": "systemd"}
        now = datetime.now(KST)
        if now.hour == 23 and now.minute >= 55:
            self.store.processing_summary(14)

        if now.hour == 3 and now.minute < 2:
            results["cleanup"] = self.store.cleanup(self.settings.raw_retention_days, self.settings.metadata_retention_days)
        return results

    def common_worker_tick(self, burst: bool = False, slot: str = "model1") -> dict | None:
        now = time.monotonic()
        if now >= self._next_common_stall_recovery_at:
            self._next_common_stall_recovery_at = now + 60.0
            self.store.recover_stalled_article_analysis_jobs()
        if burst:
            if self.store.pending_article_analysis_jobs(include_deferred=True) < self.selected_burst_threshold():
                return None
            if not self.common_turbo_available():
                return None
            provider, model, lane = "openrouter", self.selected_common_turbo_model(), "turbo"
        elif slot == "model2":
            model = self.selected_common_fallback_model()
            provider, lane = self._provider_for_switchable_llm_model(model), "common_model2"
        else:
            model = self.selected_common_llm_model()
            provider, lane = self._provider_for_switchable_llm_model(model), "common_model1"
        if not self._provider_status(provider, model).get("available"):
            return None
        article = self.process_next_article_analysis(provider, model, lane)
        return {"stage": "article", "slot": slot if not burst else "turbo", "result": article} if article else None

    def embedding_worker_tick(self) -> dict | None:
        # Press-release matching is part of the live article pipeline.  Keep
        # draining an existing batch even while article embeddings are arriving.
        embedding = self.process_next_embedding()
        if not LOCAL_EMBEDDING_LOCK.acquire(blocking=False):
            return {"stage": "embedding", "result": embedding} if embedding else None
        try:
            press = self.press_releases.process_next(match_limit=48)
            if embedding:
                return {"stage": "embedding", "result": embedding, "press_release": press}
            if press:
                return {"stage": "press_release", "result": press}
            moderation = self.process_next_case_proposal_moderation()
            return {"stage": "case_proposal_moderation", "result": moderation} if moderation else None
        finally:
            LOCAL_EMBEDDING_LOCK.release()

    def case_worker_tick(self, burst: bool = False, slot: str = "mini") -> dict | None:
        if burst:
            return None
        now = time.monotonic()
        if now >= self._next_case_stall_recovery_at:
            self._next_case_stall_recovery_at = now + 60.0
            self.store.recover_stalled_case_evaluation_jobs()
            self.store.release_invalid_openrouter_case_bundles()
        if slot == "mini":
            reanalysis = self.process_next_reanalysis()
            if reanalysis:
                return {"stage": "reanalysis", "result": reanalysis}
            provider, model, batch_size = "openai", self.selected_case_model2(), 10
        elif slot == "oss":
            provider, model, batch_size = "nvidia", self.selected_case_model1(), 5
        elif slot == "single":
            provider, model, batch_size = "openrouter", self.selected_case_single_model(), 1
        else:
            raise ValueError(f"unknown_case_worker_slot:{slot}")
        if not self._provider_status(provider, model).get("available"):
            self.store.release_pending_case_provider(provider)
            return None
        if slot == "mini" and self._provider_status("nvidia", self.selected_case_model1()).get("available"):
            if not self.store.ready_case_evaluation_jobs_older_than(
                CASE_MODEL1_PRIORITY_SECONDS, provider="openai",
            ):
                return None
        single_available = bool(self._provider_status("openrouter", self.selected_case_single_model()).get("available"))
        result = self.process_next_case_evaluation(
            provider, model, f"case_{slot}", batch_size=batch_size,
            single_unowned_only=(slot == "single"),
            allow_unowned_single=(slot == "single" or not single_available),
        )
        return {"stage": "case", "slot": slot, "result": result} if result else None

    def shadow_worker_tick(self) -> dict | None:
        result = self.process_next_shadow_case_evaluation()
        return {"stage": "shadow_case", "result": result} if result else None

    def shadow_worker_tick(self) -> dict | None:
        result = self.process_next_shadow_case_evaluation()
        return {"stage": "shadow_case", "result": result} if result else None

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
        getattr(settings, "openrouter_case_reserve_calls", 100),
        bool(getattr(settings, "nvidia_api_key", "")), getattr(settings, "nvidia_base_url", ""),
        getattr(settings, "nvidia_case_model", ""),
        getattr(settings, "openai_daily_token_soft_limit", 2450000),
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
            # Avoid DDL on a normal web request, which can wait behind a collector write.
            # Empty databases (test/fresh deployment) still receive their initial schema.
            store = Store(settings.database_path, initialize=False)
            try:
                with store.connect() as connection: connection.execute("SELECT 1 FROM app_settings LIMIT 1")
            except sqlite3.OperationalError:
                store = Store(settings.database_path)
            _SERVICE = MasterPressService(settings, store)
            _SERVICE_KEY = key
        return _SERVICE


def worker_tick() -> dict:
    return get_service().orchestration_tick()


def common_worker_tick(burst: bool = False, slot: str = "model1") -> dict | None:
    return get_service().common_worker_tick(burst=burst, slot=slot)


def embedding_worker_tick() -> dict | None:
    return get_service().embedding_worker_tick()


def case_worker_tick(burst: bool = False, slot: str = "mini") -> dict | None:
    return get_service().case_worker_tick(burst=burst, slot=slot)

def shadow_worker_tick() -> dict | None:
    return get_service().shadow_worker_tick()
