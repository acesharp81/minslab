from __future__ import annotations

import hmac
import json
import re
import requests
from datetime import date, datetime, timedelta
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.gzip import GZipMiddleware

from .adapters.national_assembly.catalog import public_catalog
from .config import PROJECT_DIR, get_settings
from .db.bill_repository import BillRepository
from .db.committee_repository import CommitteeRepository
from .db.connection import connect
from .db.executive_briefing_repository import ExecutiveBriefingRepository
from .db.live_repository import LiveRepository
from .db.meeting_brief_repository import MeetingBriefRepository
from .db.official_change_report_repository import OfficialChangeReportRepository
from .db.official_evidence_query import official_evidence_items
from .db.official_integration_repository import OfficialIntegrationRepository
from .db.policy_issue_repository import PolicyIssueRepository
from .db.review_repository import ReviewRepository
from .db.schedule_repository import ScheduleRepository
from .db.speaker_repository import SpeakerRepository
from .db.summary_repository import SummaryRepository
from .db.watch_delivery_repository import WatchDeliveryRepository
from .db.watch_operations_repository import WatchOperationsRepository
from .db.watch_repository import WatchRepository
from .db.watch_test_repository import WatchTestRepository
from .domain import AuthorityStatus, LifecycleStatus, ReconciliationStatus
from .domain.scope import TARGET_COMMITTEES, is_live_transcript_scope
from .ingestion.schedule_worker import (
    ASSEMBLY_REFERENCE_SCHEMA,
    UPCOMING_SCHEDULE_SCHEMA,
)
from .services.cross_institution_flow import build_specific_cross_institution_flow
from .services.executive_briefing_query import filter_executive_briefings
from .services.integrated_brief_evidence import (
    attach_official_evidence_from_changes,
    official_evidence_ids,
)
from .services.meeting_brief import (
    PROMPT_VERSION as MEETING_BRIEF_PROMPT_VERSION,
)
from .services.meeting_brief import link_tasks_to_topics
from .services.meeting_topic_groups import (
    attach_meeting_topic_groups,
    build_meeting_topic_ontology,
)
from .services.meeting_sessions import build_meeting_sessions
from .services.mistral_budget import mistral_usage_cost_usd
from .services.official_brief_integration import build_official_brief_integration
from .services.official_evidence_presentation import (
    build_official_evidence_presentations,
)
from .services.official_speaker_presentation import apply_official_speakers
from .services.summary_client import summary_identity
from .services.transcript_presentation import (
    apply_speaker_overrides,
    default_speaker_name,
    executive_meeting_content_segments,
    group_transcript_segments,
)
from .services.watch_kakao import KakaoNotificationProvider, KakaoProviderError
from .services.watch_replay_script import (
    REPLAY_ESTIMATED_DURATION_SECONDS,
    REPLAY_MODE,
    build_hasi_ai_replay_script,
)
from .services.watch_summary import (
    COMPATIBLE_PROMPT_VERSIONS as WATCH_REPORT_COMPATIBLE_PROMPT_VERSIONS,
)
from .services.web_security import (
    clear_watch_cookie,
    install_security_middleware,
    set_watch_cookie,
)
from .topic_report_api import router as topic_report_router

ALLOWED_INSTITUTIONS = {"EXECUTIVE", "LEGISLATURE"}


app = FastAPI(
    title="국정ON API",
    version="0.1.0",
    description="공식 국회 자료의 수집·정규화·검색을 위한 POC-07 API",
)
app.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=5)
install_security_middleware(app)


app.include_router(topic_report_router)
class SpeakerOverridePayload(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)


class WatchRulePayload(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    include_terms: list[str] = Field(min_length=1, max_length=10)
    exclude_terms: list[str] = Field(default_factory=list, max_length=10)
    institution: str | None = None
    committee_name: str | None = Field(default=None, max_length=80)
    notification_policy: str = "FIRST_PER_MEETING"
    digest_enabled: bool = False
    kakao_enabled: bool = False


class WatchRuleUpdatePayload(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    include_terms: list[str] | None = Field(default=None, min_length=1, max_length=10)
    exclude_terms: list[str] | None = Field(default=None, max_length=10)
    institution: str | None = None
    committee_name: str | None = Field(default=None, max_length=80)
    notification_policy: str | None = None
    digest_enabled: bool | None = None
    kakao_enabled: bool | None = None
    enabled: bool | None = None


class WatchTestBroadcastPayload(BaseModel):
    replay_mode: str = REPLAY_MODE
    kakao_delivery_enabled: bool = False


class WatchReviewDecisionPayload(BaseModel):
    decision: str
    note: str = Field(default="", max_length=500)
    reviewed_by: str = Field(default="operator", min_length=1, max_length=80)



WATCH_NOTIFICATION_POLICIES = {
    "FIRST_PER_MEETING",
    "FIRST_PER_SPEAKER",
    "ONCE_PER_10_MINUTES",
    "INTERVAL_15_MINUTES",
    "INTERVAL_30_MINUTES",
    "INTERVAL_60_MINUTES",
    "EVERY_MATCH",
}


def _watch_cooldown_minutes(policy: str) -> int:
    return {
        "INTERVAL_15_MINUTES": 15,
        "INTERVAL_30_MINUTES": 30,
        "INTERVAL_60_MINUTES": 60,
    }.get(policy, 10)


def _clean_watch_terms(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        term = " ".join(str(value).split()).strip()
        if not term or len(term) > 60:
            raise HTTPException(
                status_code=422, detail="관심 문구는 1~60자로 입력해 주세요."
            )
        if term not in result:
            result.append(term)
    if not result:
        raise HTTPException(status_code=422, detail="관심 문구가 필요합니다.")
    return result


def _watch_subscriber(connection: object, token: str | None) -> UUID:
    if not get_settings().watch_alerts_enabled:
        raise HTTPException(
            status_code=503, detail="관심주제 알림 기능이 비활성화되어 있습니다."
        )
    subscriber_id = WatchRepository(connection).subscriber_for_token(token)
    if subscriber_id is None:
        raise HTTPException(
            status_code=401, detail="관심주제 세션을 다시 시작해 주세요."
        )
    return subscriber_id


def _watch_admin(token: str | None) -> None:
    settings = get_settings()
    expected = settings.watch_admin_token
    if not expected:
        raise HTTPException(
            status_code=503, detail="운영자 인증이 설정되지 않았습니다."
        )
    if not token or not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=401, detail="운영자 인증이 필요합니다.")


def _public_meeting_brief(
    item: dict[str, object] | None,
    progress_item: dict[str, object] | None = None,
    *,
    include_content: bool = True,
) -> dict[str, object] | None:
    if not item:
        return None
    raw_brief = dict(item.get("brief") or {})
    normalized_brief = (
        attach_meeting_topic_groups(link_tasks_to_topics(raw_brief))
        if include_content
        else {"utterance_count": int(raw_brief.get("utterance_count") or 0)}
    )
    progress = dict(progress_item or {})
    current_cursor = int(progress.get("current_source_last_event_cursor") or 0)
    saved_cursor = int(item.get("source_last_event_cursor") or 0)
    newer_input_pending = bool(
        progress
        and (
            current_cursor > saved_cursor
            if current_cursor and saved_cursor
            else progress.get("transcript_hash")
            and progress.get("transcript_hash") != item["transcript_hash"]
        )
    )
    is_ai_result = item["provider"] in {"mistral", "openrouter"}
    analysis_outdated = bool(
        is_ai_result
        and item.get("prompt_version") != MEETING_BRIEF_PROMPT_VERSION
    )
    # A prompt-version upgrade must not hide an already completed report.
    # Only new transcript input invalidates the visible result. Legacy reports
    # remain readable while their background upgrade runs.
    result_pending = newer_input_pending
    if not progress:
        total = int((item.get("brief") or {}).get("utterance_count") or 0)
        progress = {
            "status": "COMPLETED" if is_ai_result else "PROCESSING",
            "phase": "COMPLETED" if is_ai_result else "QUEUED",
            "total_utterances": total,
            "processed_utterances": total if is_ai_result else 0,
            "total_chunks": 0,
            "completed_chunks": 0,
        }
    ready = is_ai_result and not result_pending
    return {
        "brief_id": item["brief_id"],
        "broadcast_id": item["broadcast_id"],
        "transcript_hash": item["transcript_hash"],
        "provider": item["provider"],
        "model": item["model"],
        "prompt_version": item["prompt_version"],
        "authority_status": item["authority_status"],
        "review_status": item["review_status"],
        "generated_at": item["generated_at"],
        "brief": normalized_brief,
        "brief_content_loaded": include_content,
        "brief_status": "READY" if ready else "PROCESSING",
        "brief_progress": progress,
        "brief_is_stale": result_pending,
        "brief_upgrade_pending": analysis_outdated,
        "brief_upgrade_status": progress.get("status") if analysis_outdated else None,
        "brief_outdated_reason": "NEW_TRANSCRIPT" if newer_input_pending else None,
        "previous_utterance_count": int(
            (item.get("brief") or {}).get("utterance_count") or 0
        )
        if newer_input_pending
        else None,
    }


def _present_transcript(
    connection: object,
    snapshot: dict[str, object],
    *,
    official_speakers: bool = True,
) -> dict[str, object]:
    broadcast_ids = [item["broadcast_id"] for item in snapshot.get("broadcasts", [])]
    speaker_repository = SpeakerRepository(connection)
    overrides = speaker_repository.override_map(broadcast_ids)
    raw_segments = list(snapshot.get("segments", []))
    institution_rows = connection.execute(
        "SELECT id, institution FROM live_broadcasts WHERE id = ANY(%s)",
        (broadcast_ids,),
    ).fetchall() if broadcast_ids else []
    executive_ids = {
        broadcast_id for broadcast_id, institution in institution_rows
        if institution == "EXECUTIVE"
    }
    excluded_pre_meeting = 0
    for broadcast_id in executive_ids:
        source = [item for item in raw_segments if item.get("broadcast_id") == broadcast_id]
        meeting_content = executive_meeting_content_segments(source)
        if len(meeting_content) < len(source):
            included = {item.get("segment_id") for item in meeting_content}
            excluded = {
                item.get("segment_id") for item in source
                if item.get("segment_id") not in included
            }
            raw_segments = [
                item for item in raw_segments
                if item.get("segment_id") not in excluded
            ]
            excluded_pre_meeting += len(excluded)
    segments = apply_speaker_overrides(raw_segments, overrides)
    if official_speakers:
        segments = apply_official_speakers(segments)
    snapshot["segments"] = segments
    snapshot["speaker_options"] = {
        str(broadcast_id): [
            {
                **item,
                "effective_display_name": item["display_name"]
                or default_speaker_name(item["source_speaker_label"]),
                "overridden": bool(item["display_name"]),
            }
            for item in speaker_repository.options(broadcast_id)
        ]
        for broadcast_id in broadcast_ids
    }
    utterances = group_transcript_segments(segments)
    settings = get_settings()
    summary_provider, summary_model, prompt_version = summary_identity(settings)
    cached_summaries = SummaryRepository(connection).summary_map(
        broadcast_ids,
        provider=summary_provider,
        model=summary_model,
        prompt_version=prompt_version,
    )
    cached_count = 0
    for utterance in utterances:
        cached = cached_summaries.get(
            (
                utterance["broadcast_id"],
                utterance["content_hash"],
            )
        )
        if not cached:
            continue
        utterance["summary"] = cached["summary"]
        utterance["summary_kind"] = "AI_CACHED"
        utterance["summary_provider"] = cached["provider"]
        utterance["summary_model"] = cached["model"]
        utterance["summary_generated_at"] = cached["created_at"]
        utterance["live_insight"] = cached.get("live_insight") or None
        cached_count += 1
    lifecycle_by_broadcast = {
        item["broadcast_id"]: str(item.get("lifecycle_status") or "")
        for item in snapshot.get("broadcasts", [])
    }
    sessions = build_meeting_sessions(
        utterances,
        lifecycle_by_broadcast=lifecycle_by_broadcast,
    )
    snapshot["utterances"] = utterances
    snapshot["meeting_sessions"] = sessions
    snapshot["meeting_session_summary"] = {
        "count": len(sessions),
        "active_count": sum(1 for item in sessions if item["status"] == "ACTIVE"),
        "checkpointed_count": sum(
            1 for item in sessions if item["status"] == "CHECKPOINTED"
        ),
    }

    snapshot["presentation_summary"] = {
        "excluded_pre_meeting_segment_count": excluded_pre_meeting,
        "segment_count": len(segments),
        "utterance_count": len(utterances),
        "ai_summary_count": cached_count,
        "gemini_summary_count": sum(
            1 for item in utterances if item.get("summary_provider") == "gemini"
        ),
        "extractive_fallback_count": len(utterances) - cached_count,
        "mistral_summary_count": sum(
            1 for item in utterances if item.get("summary_provider") == "mistral"
        ),
    }
    return snapshot


@app.get("/api/health", tags=["system"])
def health() -> dict[str, object]:
    settings = get_settings()
    return {
        "status": "ok",
        "project": "POC-07",
        "phase": "open-beta",
        "environment": settings.national_assembly_env,
        "data_sources_verified": True,
        "ai_enrichment_enabled": settings.ai_enrichment_enabled,
    }


@app.get("/api/meta", tags=["system"])
def metadata() -> dict[str, object]:
    return {
        "project": {
            "id": "POC-07",
            "name": "국정ON",
            "english_name": "GukjeongON",
        },
        "statuses": {
            "lifecycle": [item.value for item in LifecycleStatus],
            "authority": [item.value for item in AuthorityStatus],
            "reconciliation": [item.value for item in ReconciliationStatus],
        },
        "official_and_ai_separated": True,
        "target_committees": list(TARGET_COMMITTEES),
    }


def _usage_reset_at(period: str, timezone_name: str) -> str:
    now_utc = datetime.now(ZoneInfo("UTC"))
    if period == "DAILY":
        reset_utc = (now_utc + timedelta(days=1)).replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
    else:
        if now_utc.month == 12:
            reset_utc = now_utc.replace(
                year=now_utc.year + 1,
                month=1,
                day=1,
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            )
        else:
            reset_utc = now_utc.replace(
                month=now_utc.month + 1,
                day=1,
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            )
    return reset_utc.astimezone(ZoneInfo(timezone_name)).isoformat()


@app.get("/api/ai/usage", tags=["system"])
def ai_usage() -> dict[str, object]:
    settings = get_settings()
    mistral_usage = {
        "request_count": 0, "input_tokens": 0, "output_tokens": 0,
        "total_tokens": 0, "audio_request_count": 0,
        "audio_seconds": 0.0, "audio_cost_usd": 0.0,
    }
    local_openrouter = 0
    status = "AVAILABLE"
    if settings.database_url:
        try:
            with connect(settings.database_url) as connection:
                repository = SummaryRepository(connection)
                mistral_usage.update(repository.monthly_provider_usage("mistral"))
                local_openrouter = repository.daily_usage("openrouter")
        except Exception:
            status = "UNAVAILABLE"
    gateway: dict[str, object] = {}
    if settings.openrouter_gateway_status_url:
        try:
            response = requests.get(settings.openrouter_gateway_status_url, timeout=2.0)
            response.raise_for_status()
            gateway = response.json()
        except Exception:
            status = "UNAVAILABLE"
    openrouter_used = int(gateway.get("reserved", local_openrouter))
    openrouter_limit = int(gateway.get("operational_limit") or settings.openrouter_daily_limit)
    mistral_cost = mistral_usage_cost_usd(
        mistral_usage,
        input_usd_per_million=settings.mistral_input_usd_per_million,
        output_usd_per_million=settings.mistral_output_usd_per_million,
    )
    return {
        "provider": "combined",
        "provider_label": "OpenRouter 공용 + Mistral STT",
        "model": f"{settings.llm_model or '-'} · {settings.executive_transcription_model}",
        "used": openrouter_used, "limit": openrouter_limit,
        "unit": "requests", "period": "DAILY",
        "request_count": openrouter_used,
        "usage_percent": round((openrouter_used / openrouter_limit) * 100, 2) if openrouter_limit else 0,
        "resets_at": _usage_reset_at("DAILY", settings.national_assembly_timezone),
        "status": status,
        "providers": [
            {
                "provider": "openrouter", "period": "DAILY",
                "used": openrouter_used, "limit": openrouter_limit,
                "usage_percent": round(
                    (openrouter_used / openrouter_limit) * 100, 2
                ) if openrouter_limit else 0,
                "resets_at": _usage_reset_at(
                    "DAILY", settings.national_assembly_timezone
                ),
                "official_limit": int(gateway.get("official_limit") or 1000),
                "completed": int(gateway.get("completed") or 0),
                "failed": int(gateway.get("failed") or 0),
                "remaining": max(0, openrouter_limit - openrouter_used),
                "combined_projects": True,
                "breakdown": gateway.get("breakdown") or [],
            },
            {
                "provider": "mistral", "period": "MONTHLY",
                **mistral_usage, "cost_usd": round(mistral_cost, 6),
                "credit_usd": float(settings.mistral_monthly_credit_usd),
                "usage_percent": round(
                    (mistral_cost / float(settings.mistral_monthly_credit_usd)) * 100,
                    2,
                ) if settings.mistral_monthly_credit_usd else 0,
                "resets_at": _usage_reset_at(
                    "MONTHLY", settings.national_assembly_timezone
                ),
                "transcription_model": settings.executive_transcription_model,
            },
        ],
    }
    provider, model, _ = summary_identity(settings)
    provider_labels = {
        "mistral": "Mistral Studio",
        "openrouter": "OpenRouter",
        "gemini": "Google AI Studio",
        "disabled": "AI 요약 미사용",
    }
    period = "DAILY" if provider == "openrouter" else "MONTHLY"
    unit = "requests" if provider == "openrouter" else "tokens"
    limit = int(settings.openrouter_daily_limit) if provider == "openrouter" else 0
    credit_usd = (
        float(settings.mistral_monthly_credit_usd) if provider == "mistral" else 0.0
    )
    usage = {
        "request_count": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "audio_request_count": 0,
        "audio_seconds": 0.0,
        "audio_cost_usd": 0.0,
    }
    status = "NOT_CONFIGURED" if not settings.database_url else "AVAILABLE"
    if settings.database_url and provider in {"mistral", "openrouter"}:
        try:
            with connect(settings.database_url) as connection:
                repository = SummaryRepository(connection)
                if provider == "openrouter":
                    usage["request_count"] = repository.daily_usage(provider)
                else:
                    usage.update(repository.monthly_token_usage(provider, model))
        except Exception:
            status = "UNAVAILABLE"
    used = usage["request_count"] if unit == "requests" else usage["total_tokens"]
    cost_usd = (
        mistral_usage_cost_usd(
            usage,
            input_usd_per_million=settings.mistral_input_usd_per_million,
            output_usd_per_million=settings.mistral_output_usd_per_million,
        )
        if provider == "mistral"
        else 0.0
    )
    usage_percent = (
        (cost_usd / credit_usd) * 100
        if provider == "mistral" and credit_usd
        else (used / limit) * 100
        if limit
        else 0
    )
    return {
        "provider": provider,
        "provider_label": provider_labels.get(provider, provider or "AI 요약 미사용"),
        "model": model or "-",
        "used": used,
        "limit": limit,
        "unit": unit,
        "period": period,
        "request_count": usage["request_count"],
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
        "audio_request_count": usage.get("audio_request_count", 0),
        "audio_seconds": usage.get("audio_seconds", 0.0),
        "audio_cost_usd": round(float(usage.get("audio_cost_usd", 0.0)), 6),
        "transcription_model": settings.executive_transcription_model,
        "cost_usd": round(cost_usd, 6),
        "credit_usd": credit_usd,
        "remaining_usd": round(max(0.0, credit_usd - cost_usd), 6),
        "input_usd_per_million": settings.mistral_input_usd_per_million,
        "output_usd_per_million": settings.mistral_output_usd_per_million,
        "usage_percent": round(usage_percent, 2),
        "resets_at": _usage_reset_at(period, settings.national_assembly_timezone),
        "status": status,
    }


def _schedule_range(days: int) -> dict[str, object]:
    settings = get_settings()
    today = datetime.now(ZoneInfo(settings.national_assembly_timezone)).date()
    end_date = today + timedelta(days=days - 1)
    snapshot_path = settings.processed_data_dir / "upcoming_schedule.json"
    try:
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        if snapshot.get("schema_version") != UPCOMING_SCHEDULE_SCHEMA:
            raise ValueError("upcoming schedule contract mismatch")
        items = [
            item
            for item in snapshot.get("items", [])
            if today.isoformat()
            <= str(item.get("scheduled_date", ""))
            <= end_date.isoformat()
        ]
        source_status = "OFFICIAL"
        generated_at = snapshot.get("generated_at")
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        if not settings.database_url:
            return {
                "items": [],
                "count": 0,
                "target_committee_count": 0,
                "start_date": today,
                "end_date": end_date,
                "days": days,
                "source_status": "SYNC_PENDING",
            }
        try:
            with connect(settings.database_url) as connection:
                items = []
                for offset in range(days):
                    items.extend(
                        ScheduleRepository(connection).list_schedule_for_date(
                            today + timedelta(days=offset)
                        )
                    )
        except Exception as exc:
            raise HTTPException(
                status_code=503, detail="정규화 데이터베이스를 사용할 수 없습니다."
            ) from exc
        source_status = "OFFICIAL_DB_FALLBACK"
        generated_at = None
    return {
        "items": items,
        "count": len(items),
        "target_committee_count": sum(
            bool(item.get("is_target_committee")) for item in items
        ),
        "start_date": today,
        "end_date": end_date,
        "date": today,
        "days": days,
        "generated_at": generated_at,
        "source_status": source_status,
    }


def mark_confirmed_broadcast_schedules(
    items: list[dict[str, object]],
    live_status: dict[str, object],
    *,
    today: date,
    completed_broadcasts: list[dict[str, object]] | None = None,
) -> list[dict[str, object]]:
    result = [dict(item) for item in items]
    ended = [dict(item) for item in (completed_broadcasts or [])]
    used_ended_ids: set[str] = set()
    assembly_status = (
        (live_status.get("assembly") or {}).get("items") or []
        if isinstance(live_status.get("assembly"), dict) else []
    )
    executive_status = (
        live_status.get("executive")
        if isinstance(live_status.get("executive"), dict) else {}
    )

    def completed_candidate(item: dict[str, object]) -> dict[str, object] | None:
        scheduled_date = str(item.get("scheduled_date") or "")
        committee_name = str(item.get("committee_name") or "")
        candidates = [
            candidate for candidate in ended
            if str(candidate.get("broadcast_id") or "") not in used_ended_ids
            and str(candidate.get("broadcast_date") or "") == scheduled_date
            and str(candidate.get("committee_name") or "") == committee_name
        ]
        if not candidates:
            return None
        meeting_id = str(item.get("meeting_id") or "")
        if meeting_id:
            exact = [
                candidate for candidate in candidates
                if str(candidate.get("meeting_id") or "") == meeting_id
            ]
            if exact:
                return exact[0]
        if len(candidates) == 1:
            return candidates[0]
        item_time = str(item.get("start_time") or item.get("time_text") or "")[:5]
        time_match = re.fullmatch(r"(\d{1,2}):(\d{2})", item_time)
        if not time_match:
            return None
        item_minutes = int(time_match.group(1)) * 60 + int(time_match.group(2))
        timed: list[tuple[int, dict[str, object]]] = []
        for candidate in candidates:
            candidate_match = re.match(
                r"(\d{1,2}):(\d{2})", str(candidate.get("broadcast_time") or ""),
            )
            if candidate_match:
                candidate_minutes = (
                    int(candidate_match.group(1)) * 60 + int(candidate_match.group(2))
                )
                timed.append((abs(candidate_minutes - item_minutes), candidate))
        if not timed:
            return None
        distance, candidate = min(timed, key=lambda value: value[0])
        return candidate if distance <= 240 else None

    for item in result:
        scheduled_date = str(item.get("scheduled_date") or "")
        if item.get("broadcast_scheduled"):
            item["broadcast_status"] = (
                "LIVE"
                if scheduled_date == today.isoformat()
                and bool(executive_status.get("is_live"))
                else (
                    "COMPLETED"
                    if scheduled_date < today.isoformat()
                    else "SCHEDULED"
                )
            )
            continue
        if str(item.get("schedule_kind") or "") != "위원회":
            continue
        completed = completed_candidate(item)
        if completed:
            completed_id = str(completed.get("broadcast_id") or "")
            if completed_id:
                used_ended_ids.add(completed_id)
            item["broadcast_scheduled"] = True
            item["broadcast_status"] = "COMPLETED"
            item["broadcast_source_url"] = "https://assembly.webcast.go.kr/"
            item["meeting_external_id"] = completed.get("external_id")
            continue
        if scheduled_date != today.isoformat():
            continue
        item_time = str(item.get("start_time") or item.get("time_text") or "")[:5]
        for candidate in assembly_status:
            if not isinstance(candidate, dict):
                continue
            if str(candidate.get("committee_name") or "") != str(
                item.get("committee_name") or ""
            ):
                continue
            status_text = str(candidate.get("status_text") or "")
            if not candidate.get("is_live") and "예정" not in status_text:
                continue
            time_match = re.search(r"\d{1,2}:\d{2}", status_text)
            candidate_time = time_match.group(0) if time_match else ""
            if item_time and candidate_time and item_time != candidate_time.zfill(5):
                continue
            item["broadcast_scheduled"] = True
            item["broadcast_status"] = (
                "LIVE" if candidate.get("is_live") else "SCHEDULED"
            )
            item["broadcast_source_url"] = "https://assembly.webcast.go.kr/"
            item["meeting_external_id"] = candidate.get("meeting_external_id")
            break
    return result


@app.get("/api/schedule/upcoming", tags=["schedule"])
def upcoming_schedule(days: int = 2) -> dict[str, object]:
    if not 1 <= days <= 7:
        raise HTTPException(status_code=422, detail="days must be between 1 and 7")
    return _schedule_range(days)


@app.get("/api/schedule/today", tags=["schedule"])
@app.get("/api/meetings/today", tags=["meetings"], deprecated=True)
def today_schedule() -> dict[str, object]:
    return _schedule_range(1)


@app.get("/api/schedule/calendar", tags=["schedule"])
def calendar_schedule(start: date, end: date) -> dict[str, object]:
    if end < start:
        raise HTTPException(status_code=422, detail="end must not precede start")
    if (end - start).days > 41:
        raise HTTPException(status_code=422, detail="calendar range is limited to 42 days")
    settings = get_settings()
    if not settings.database_url:
        return {
            "items": [], "count": 0, "start_date": start,
            "end_date": end, "source_status": "NOT_CONFIGURED",
        }
    try:
        with connect(settings.database_url) as connection:
            items = ScheduleRepository(connection).list_schedule_range(start, end)
            completed_broadcasts = LiveRepository(
                connection,
            ).list_ended_broadcasts_for_schedule_range(start, end)
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="공식 일정 저장소를 사용할 수 없습니다.",
        ) from exc
    live_status = {}
    try:
        live_status = json.loads(
            (settings.processed_data_dir / "live_status.json").read_text(
                encoding="utf-8",
            )
        )
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    items = mark_confirmed_broadcast_schedules(
        items, live_status,
        today=datetime.now(
            ZoneInfo(settings.national_assembly_timezone),
        ).date(),
        completed_broadcasts=completed_broadcasts,
    )
    return {
        "items": items,
        "count": len(items),
        "start_date": start,
        "end_date": end,
        "source_status": "OFFICIAL_DB",
    }


@app.get("/api/assembly/reference", tags=["assembly"])
def assembly_reference(response: Response) -> dict[str, object]:
    path = get_settings().processed_data_dir / "assembly_reference.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != ASSEMBLY_REFERENCE_SCHEMA:
            raise ValueError("assembly reference contract mismatch")
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        return {
            "schema_version": ASSEMBLY_REFERENCE_SCHEMA,
            "source_status": "SYNC_PENDING",
            "seat_count": 0,
            "party_seats": [],
            "election_type_seats": [],
            "gender_seats": [],
        }
    response.headers["Cache-Control"] = "public, max-age=300"
    return payload


@app.get("/api/committees/meetings", tags=["committees"])
def target_committee_meetings(limit: int = 50) -> dict[str, object]:
    if not 1 <= limit <= 200:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 200")
    settings = get_settings()
    if not settings.database_url:
        return {"items": [], "count": 0, "source_status": "NOT_CONFIGURED"}
    try:
        with connect(settings.database_url) as connection:
            items = CommitteeRepository(connection).list_target_meetings(limit=limit)
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="정규화 데이터베이스를 사용할 수 없습니다."
        ) from exc
    return {"items": items, "count": len(items), "source_status": "OFFICIAL"}


@app.get("/api/executive/briefings", tags=["executive"])
def executive_briefings(
    limit: int = 10,
    ministry: str | None = None,
    q: str | None = None,
) -> dict[str, object]:
    if not 1 <= limit <= 20:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 20")
    for value in (ministry, q):
        if value is not None and (not value.strip() or len(value) > 80):
            raise HTTPException(
                status_code=422, detail="invalid executive briefing filter"
            )
    path = get_settings().processed_data_dir / "executive_briefings.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail="official executive briefings have not been collected",
        ) from exc
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=503, detail="official executive briefing snapshot is invalid"
        ) from exc
    if payload.get("schema_version") != "executive-briefings.v1":
        raise HTTPException(
            status_code=503, detail="official executive briefing contract mismatch"
        )
    source_items = payload.get("items", [])[:limit]
    live_briefs = {}
    settings = get_settings()
    if settings.database_url:
        try:
            with connect(settings.database_url) as connection:
                live_briefs = ExecutiveBriefingRepository(
                    connection,
                ).live_briefs_by_official_ids(
                    item.get("news_id") for item in source_items
                )
        except Exception:  # noqa: BLE001 - optional enrichment must not hide official data
            # Official results remain available when the optional LIVE
            # enrichment store is temporarily unavailable.
            live_briefs = {}
    result = filter_executive_briefings(
        source_items, ministry=ministry, query=q,
        live_briefs_by_official_id=live_briefs,
    )
    return {
        **payload,
        **result,
        "count": result["meeting_count"],
        "unfiltered_meeting_count": len(source_items),
    }


@app.get("/api/committees/meetings/{conference_id}/transcript", tags=["committees"])
def committee_official_transcript(
    conference_id: str,
    offset: int = 0,
    limit: int = 100,
    topic: str | None = None,
    ministry: str | None = None,
) -> dict[str, object]:
    if not (
        conference_id.startswith("N")
        and conference_id[1:].isdigit()
        and len(conference_id) <= 20
    ):
        raise HTTPException(status_code=422, detail="invalid conference id")
    if offset < 0 or not 1 <= limit <= 200:
        raise HTTPException(status_code=422, detail="invalid transcript page")
    for value in (topic, ministry):
        if value is not None and (not value.strip() or len(value) > 50):
            raise HTTPException(status_code=422, detail="invalid transcript filter")
    try:
        with connect(get_settings().database_url) as connection:
            transcript = CommitteeRepository(connection).list_official_transcript(
                conference_id,
                offset=offset,
                limit=limit,
                topic=topic.strip() if topic else None,
                ministry=ministry.strip() if ministry else None,
            )
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="공식 회의록을 조회할 수 없습니다."
        ) from exc
    if transcript is None:
        raise HTTPException(
            status_code=404, detail="수집된 공식 회의록 본문이 없습니다."
        )
    return {
        **transcript,
        "count": len(transcript["items"]),
        "source_status": "OFFICIAL_SOURCE",
    }


@app.get("/api/committees/policy-flow", tags=["committees"])
def committee_policy_flow(committee: str | None = None) -> dict[str, object]:
    if committee and committee not in TARGET_COMMITTEES:
        raise HTTPException(
            status_code=422, detail="committee is outside the target scope"
        )
    try:
        with connect(get_settings().database_url) as connection:
            result = CommitteeRepository(connection).policy_flow(committee)
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="정책 흐름을 조회할 수 없습니다."
        ) from exc
    return {**result, "source_status": "OFFICIAL_TEXT_WITH_DRAFT_CLASSIFICATION"}


@app.get("/api/policy/cross-institution-flow", tags=["policy"])
def cross_institution_policy_flow(committee: str | None = None) -> dict[str, object]:
    if committee and committee not in TARGET_COMMITTEES:
        raise HTTPException(
            status_code=422, detail="committee is outside the target scope"
        )
    path = get_settings().processed_data_dir / "executive_briefings.json"
    try:
        executive = json.loads(path.read_text(encoding="utf-8"))
        with connect(get_settings().database_url) as connection:
            issues = PolicyIssueRepository(connection).specific_issue_flow()
        if committee:
            issues = {
                **issues,
                "items": [
                    item for item in issues.get("items", [])
                    if (
                        item.get("latest_legislative_meeting") or {}
                    ).get("committee_name") == committee
                ],
            }
        result = build_specific_cross_institution_flow(
            executive.get("items", []), issues
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail="official executive briefings have not been collected",
        ) from exc
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=503, detail="official executive briefing snapshot is invalid"
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="기관 간 정책 흐름을 조회할 수 없습니다."
        ) from exc
    return {
        **result,
        "committee_filter": committee,
        "source_status": "OFFICIAL_EXECUTIVE_WITH_SPECIFIC_REPORT_TOPIC_LINK",
    }


@app.get("/api/policy/specific-issues", tags=["policy"])
def specific_policy_issues(limit: int | None = None) -> dict[str, object]:
    """Return concrete report topics, their recurrence, and transition evidence."""
    if limit is not None and not 1 <= limit <= 500:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 500")
    try:
        with connect(get_settings().database_url) as connection:
            result = PolicyIssueRepository(connection).specific_issue_flow()
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="구체 정책 쟁점을 조회할 수 없습니다."
        ) from exc
    if limit is None:
        return result
    items = list(result.get("items") or [])[:limit]
    return {
        **result,
        "items": items,
        "count": len(items),
        "total_count": int(result.get("count") or len(items)),
    }


@app.get("/api/policy/ontology", tags=["policy"])
def policy_ontology() -> dict[str, object]:
    """Return the topic ontology plus usage and integrity metrics."""
    try:
        with connect(get_settings().database_url) as connection:
            briefs = [
                item.get("brief") or {}
                for item in MeetingBriefRepository(connection).latest_all()
            ]
        return {
            **build_meeting_topic_ontology(briefs),
            "source_status": "STORED_MEETING_REPORTS",
            "additional_llm_calls": 0,
        }
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="온톨로지 구성을 조회할 수 없습니다."
        ) from exc


@app.get("/api/bills", tags=["bills"])
def search_bills(
    q: str | None = None,
    committee: str | None = None,
    stage: str | None = None,
    limit: int = 50,
) -> dict[str, object]:
    if not 1 <= limit <= 200:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 200")
    if committee and committee not in TARGET_COMMITTEES:
        raise HTTPException(
            status_code=422, detail="committee is outside the target scope"
        )
    q = q.strip() if q else None
    stage = stage.strip() if stage else None
    if q and len(q) > 100:
        raise HTTPException(status_code=422, detail="q must be at most 100 characters")
    settings = get_settings()
    if not settings.database_url:
        return {"items": [], "count": 0, "source_status": "NOT_CONFIGURED"}
    try:
        with connect(settings.database_url) as connection:
            items = BillRepository(connection).search_target_bills(
                query=q,
                committee_name=committee,
                process_stage=stage,
                limit=limit,
            )
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="의안 데이터베이스를 사용할 수 없습니다."
        ) from exc
    return {"items": items, "count": len(items), "source_status": "OFFICIAL"}


@app.get("/api/live/magazine", tags=["live"])
def live_magazine(
    institution: str | None = None,
    scope: str | None = None,
    limit: int = 5,
) -> dict[str, object]:
    if institution and institution not in ALLOWED_INSTITUTIONS:
        raise HTTPException(status_code=422, detail="unsupported institution")
    if scope and len(scope) > 50:
        raise HTTPException(
            status_code=422, detail="scope must be at most 50 characters"
        )
    if not 1 <= limit <= 20:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 20")
    actual: list[dict[str, object]] = []
    review_source_status = "AVAILABLE"
    try:
        with connect(get_settings().database_url) as connection:
            actual = ReviewRepository(connection).list_magazine(
                institution=institution,
                scope=scope,
                limit=max(limit * 2, 20),
            )
    except Exception:  # noqa: BLE001 - keep the public read model available
        review_source_status = "DB_UNAVAILABLE"
    if institution:
        items = actual[:limit]
    else:
        items = []
        for target in ("EXECUTIVE", "LEGISLATURE"):
            actual_target = [item for item in actual if item["institution"] == target]
            items.extend(actual_target[:limit])
    for item in items:
        item["speaker_label"] = default_speaker_name(item.get("speaker_label"))
    return {
        "items": items,
        "count": len(items),
        "available_count": len(items),
        "rotation_ms": 5000,
        "authority_status": "PROVISIONAL",
        "review_source_status": review_source_status,
        "source": {"type": "LIVE_REVIEW"},
    }


@app.get("/api/live/status", tags=["live"])
def live_status() -> dict[str, object]:
    path = get_settings().processed_data_dir / "live_status.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail="LIVE source probe has not run"
        ) from exc
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=503, detail="LIVE source snapshot is invalid"
        ) from exc
    if payload.get("schema_version") != "live-source-status.v1":
        raise HTTPException(
            status_code=503, detail="LIVE source snapshot contract mismatch"
        )
    play_by_meeting = {
        str(contract.get("meeting_external_id")): contract
        for contract in payload.get("assembly", {}).get("play_contracts", [])
        if contract.get("meeting_external_id")
    }
    for item in payload.get("assembly", {}).get("items", []):
        contract = play_by_meeting.get(str(item.get("meeting_external_id")))
        item["stream_url"] = contract.get("stream_url") if contract else None
    return payload


def _validate_live_committee(committee: str | None) -> str | None:
    if committee and not is_live_transcript_scope(committee):
        raise HTTPException(
            status_code=422, detail="committee is outside the target scope"
        )
    return committee


@app.get("/api/live/transcript/snapshot", tags=["live"])
def live_transcript_snapshot(
    committee: str | None = None,
    broadcast_id: UUID | None = None,
) -> dict[str, object]:
    committee = _validate_live_committee(committee)
    settings = get_settings()
    try:
        with connect(settings.database_url) as connection:
            snapshot = LiveRepository(connection).active_transcript_snapshot(
                committee,
                broadcast_id=broadcast_id,
            )
            snapshot = _present_transcript(connection, snapshot)
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="LIVE 자막 데이터베이스를 사용할 수 없습니다."
        ) from exc
    return {
        **snapshot,
        "authority_status": "LIVE",
        "transport": "CURSOR_POLL",
        "poll_interval_ms": 2000,
    }


@app.get("/api/live/transcript/recent", tags=["live"])
def recent_live_transcript(committee: str | None = None) -> dict[str, object]:
    committee = _validate_live_committee(committee)
    settings = get_settings()
    try:
        with connect(settings.database_url) as connection:
            snapshot = LiveRepository(connection).recent_transcript_snapshot(committee)
            snapshot = _present_transcript(connection, snapshot)
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="최근 LIVE 기록을 사용할 수 없습니다."
        ) from exc
    return {
        **snapshot,
        "authority_status": "PROVISIONAL",
        "view_mode": "RECENT_REVIEW",
    }


@app.get("/api/live/broadcasts", tags=["live"])
def ended_live_broadcasts(
    committee: str | None = None,
    limit: int = 5,
    offset: int = 0,
) -> dict[str, object]:
    committee = _validate_live_committee(committee)
    if not 1 <= limit <= 20:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 20")
    if not 0 <= offset <= 1000:
        raise HTTPException(status_code=422, detail="offset must be between 0 and 1000")
    try:
        with connect(get_settings().database_url) as connection:
            items = LiveRepository(connection).list_ended_broadcasts(
                committee,
                limit=limit + 1,
                offset=offset,
            )
            has_more = len(items) > limit
            items = items[:limit]
            briefs = MeetingBriefRepository(connection).latest_summary_map(
                item["broadcast_id"] for item in items
            )
            progresses = MeetingBriefRepository(connection).progress_map(
                item["broadcast_id"] for item in items
            )
            for item in items:
                item["meeting_brief"] = _public_meeting_brief(
                    briefs.get(item["broadcast_id"]),
                    progresses.get(item["broadcast_id"]),
                    include_content=False,
                )
                item["brief_status"] = (
                    item["meeting_brief"].get("brief_status")
                    if item["meeting_brief"]
                    else "PENDING"
                )
                item["brief_progress"] = (
                    item["meeting_brief"].get("brief_progress")
                    if item["meeting_brief"]
                    else None
                )
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="종료 방송 이력을 사용할 수 없습니다."
        ) from exc
    return {
        "items": items,
        "count": len(items),
        "offset": offset,
        "next_offset": offset + len(items),
        "has_more": has_more,
        "authority_status": "PROVISIONAL",
        "view_mode": "BROADCAST_HISTORY",
    }


@app.get("/api/live/overview", tags=["live"])
def live_collection_overview(days: int = 7) -> dict[str, object]:
    if not 1 <= days <= 30:
        raise HTTPException(status_code=422, detail="days must be between 1 and 30")
    try:
        with connect(get_settings().database_url) as connection:
            summary = SpeakerRepository(connection).collection_overview(days=days)
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="LIVE 수집 현황을 사용할 수 없습니다."
        ) from exc
    return {**summary, "days": days, "authority_status": "LIVE_SOURCE_STATS"}


@app.get("/api/live/broadcasts/{broadcast_id}/speakers", tags=["live"])
def broadcast_speakers(broadcast_id: UUID) -> dict[str, object]:
    try:
        with connect(get_settings().database_url) as connection:
            items = SpeakerRepository(connection).options(broadcast_id)
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="화자 정보를 사용할 수 없습니다."
        ) from exc
    if not items:
        raise HTTPException(
            status_code=404, detail="방송 또는 화자 정보를 찾을 수 없습니다."
        )
    return {"items": items, "count": len(items)}


@app.put("/api/live/broadcasts/{broadcast_id}/speakers/{source_label}", tags=["live"])
def update_broadcast_speaker(
    broadcast_id: UUID,
    source_label: str,
    payload: SpeakerOverridePayload,
) -> dict[str, object]:
    source_label = source_label.strip()
    display_name = payload.display_name.strip()
    if not source_label or len(source_label) > 80 or not display_name:
        raise HTTPException(status_code=422, detail="invalid speaker label")
    try:
        with connect(get_settings().database_url) as connection:
            item = SpeakerRepository(connection).set_override(
                broadcast_id,
                source_label,
                display_name,
            )
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="화자 이름을 저장할 수 없습니다."
        ) from exc
    if item is None:
        raise HTTPException(
            status_code=404, detail="해당 방송의 화자 코드를 찾을 수 없습니다."
        )
    return {**item, "effective_display_name": display_name, "overridden": True}


@app.delete(
    "/api/live/broadcasts/{broadcast_id}/speakers/{source_label}", tags=["live"]
)
def reset_broadcast_speaker(broadcast_id: UUID, source_label: str) -> dict[str, object]:
    source_label = source_label.strip()
    if not source_label or len(source_label) > 80:
        raise HTTPException(status_code=422, detail="invalid speaker label")
    try:
        with connect(get_settings().database_url) as connection:
            deleted = SpeakerRepository(connection).delete_override(
                broadcast_id,
                source_label,
            )
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="화자 이름을 초기화할 수 없습니다."
        ) from exc
    return {
        "source_speaker_label": source_label,
        "effective_display_name": default_speaker_name(source_label),
        "overridden": False,
        "deleted": deleted,
    }


@app.get("/api/live/broadcasts/{broadcast_id}/transcript", tags=["live"])
def ended_live_broadcast_transcript(broadcast_id: UUID) -> dict[str, object]:
    try:
        with connect(get_settings().database_url) as connection:
            repository = LiveRepository(connection)
            snapshot = repository.ended_transcript_snapshot(broadcast_id)
            official_context = repository.broadcast_official_context(broadcast_id)
            reconciliations = repository.broadcast_reconciliation_details(broadcast_id)
            for segment in snapshot["segments"]:
                segment["official_reconciliation"] = reconciliations.get(
                    segment["revision_id"]
                )
            snapshot = _present_transcript(connection, snapshot)
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="종료 방송 기록을 사용할 수 없습니다."
        ) from exc
    if not snapshot["broadcasts"]:
        raise HTTPException(
            status_code=404, detail="종료 방송 기록을 찾을 수 없습니다."
        )
    return {
        **snapshot,
        "official_context": official_context,
        "authority_status": "PROVISIONAL",
        "view_mode": "ENDED_REVIEW",
    }


@app.get("/api/live/broadcasts/{broadcast_id}/brief", tags=["live"])
def ended_live_broadcast_brief(broadcast_id: UUID) -> dict[str, object]:
    try:
        with connect(get_settings().database_url) as connection:
            repository = MeetingBriefRepository(connection)
            item = repository.latest(broadcast_id)
            progress = repository.progress(broadcast_id)
            integration = (
                OfficialIntegrationRepository(connection).latest_for_brief(
                    item["brief_id"]
                )
                if item
                else None
            )
            official_context = LiveRepository(connection).broadcast_official_context(
                broadcast_id
            )
            integration_deferred = bool(
                integration
                and (integration.get("usage_metadata") or {}).get("reuse_reason")
                    == "TEMPORARY_UPDATE_DEFERRED"
            )
            official_change_report = (
                OfficialChangeReportRepository(connection).latest(integration["integration_id"])
                if integration and integration.get("integration_id")
                and not integration_deferred
                else None
            )
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="회의 결과 브리프를 사용할 수 없습니다."
        ) from exc
    public = _public_meeting_brief(item, progress)
    if not public:
        raise HTTPException(
            status_code=404, detail="생성된 회의 결과 브리프가 없습니다."
        )
    if (
        integration
        and integration.get("status") == "READY"
        and (integration.get("usage_metadata") or {}).get("reuse_reason")
            != "TEMPORARY_UPDATE_DEFERRED"
        and integration.get("meeting_brief_id") == public.get("brief_id")
        and (
            not (official_context or {}).get("official_document_id")
            or integration.get("official_document_id")
                == (official_context or {}).get("official_document_id")
        )
    ):
        provisional_brief = public["brief"]
        integrated_brief = attach_official_evidence_from_changes(
            integration.get("integrated_brief") or provisional_brief,
            integration.get("changes") or [],
        )
        for field in (
            "meeting_session_version",
            "meeting_session_count",
            "meeting_sessions",
            "live_topic_assignment",
        ):
            if field in provisional_brief:
                integrated_brief[field] = provisional_brief[field]
        lineage = provisional_brief.get("live_topic_lineage")
        if lineage:
            integrated_brief["live_topic_lineage"] = lineage
            lineage_ids = {
                str(topic.get("id") or ""): topic.get("live_topic_cluster_ids") or []
                for topic in provisional_brief.get("topics") or []
            }
            for topic in integrated_brief.get("topics") or []:
                topic_id = str(topic.get("id") or "")
                if topic_id in lineage_ids:
                    topic["live_topic_cluster_ids"] = lineage_ids[topic_id]
        public["provisional_brief"] = provisional_brief
        public["brief"] = attach_meeting_topic_groups(
            link_tasks_to_topics(integrated_brief)
        )
        public["official_integration"] = {
            "status": integration["status"],
            "integration_version": integration["integration_version"],
            "official_document_id": integration["official_document_id"],
            "change_count": len(integration.get("changes") or []),
            "changes": integration.get("changes") or [],
            "speaker_stats": integration.get("speaker_stats") or {},
            "generated_at": integration["generated_at"],
        }
    else:
        public["official_integration"] = {
            "status": (
                "WAITING"
                if not integration or integration_deferred
                else integration.get("status")
            ),
            "change_count": 0,
            "changes": [],
        }
    if official_change_report:
        public["official_change_report"] = {
            "status": official_change_report.get("status"),
            "provider": official_change_report.get("provider"),
            "model": official_change_report.get("model"),
            "report": official_change_report.get("report") or {},
            "generated_at": official_change_report.get("generated_at"),
            "updated_at": official_change_report.get("updated_at"),
        }
    else:
        public["official_change_report"] = {
            "status": (
                "PENDING" if public["official_integration"].get("status") == "READY"
                else "NOT_APPLICABLE"
            ),
            "report": {},
        }
    public["official_context"] = official_context
    return public


def _meeting_brief_markdown(record: dict[str, object]) -> str:
    brief = attach_meeting_topic_groups(
        link_tasks_to_topics(dict(record.get("brief") or {}))
    )
    integration = dict(record.get("official_integration") or {})
    lines = [
        f"# {brief.get('headline') or '회의 결과'}",
        "",
        f"> 자료 상태: {record.get('authority_status') or 'PROVISIONAL'} · "
        f"생성 시각: {record.get('generated_at') or '-'}",
        "",
        str(brief.get("summary") or "저장된 요약이 없습니다."),
        "",
        "## 주요 논의 주제",
        "",
    ]
    detailed_topics = brief.get("topics") or []
    topic_by_id = {
        str(topic.get("id")): topic for topic in detailed_topics if topic.get("id")
    }
    topic_groups = brief.get("topic_groups") or [
        {
            "title": topic.get("title") or "주제",
            "summary": topic.get("summary") or "",
            "topic_ids": [str(topic.get("id"))],
        }
        for topic in detailed_topics
    ]
    for group in topic_groups:
        lines.extend(
            (
                f"### {group.get('title') or '대상 주제'}",
                "",
                str(group.get("summary") or ""),
                "",
            )
        )
        for topic_id in group.get("topic_ids") or []:
            topic = topic_by_id.get(str(topic_id))
            if not topic:
                continue
            lines.extend(
                (
                    f"#### {topic.get('title') or '세부 쟁점'}",
                    "",
                    str(topic.get("summary") or ""),
                    "",
                )
            )
            for point in topic.get("speaker_points") or []:
                lines.append(
                    f"- {point.get('speaker_label') or '화자 확인 중'}: "
                    f"{point.get('summary') or ''}"
                )
            if topic.get("speaker_points"):
                lines.append("")
    lineage = brief.get("live_topic_lineage") or {}
    if lineage.get("cluster_count"):
        lines.extend(
            (
                "## 실시간 주제 계보",
                "",
                f"- 전체 {lineage.get('cluster_count') or 0}묶음 · "
                f"연결 {lineage.get('mapped_cluster_count') or 0} · "
                f"교차 {lineage.get('ambiguous_cluster_count') or 0} · "
                f"미연결 {lineage.get('unmapped_cluster_count') or 0}",
                "",
            )
        )
        unmapped = [
            cluster
            for cluster in lineage.get("clusters") or []
            if cluster.get("mapping_status") == "UNMAPPED"
        ]
        if unmapped:
            lines.append("### 최종 상위 주제에 포함되지 않은 실시간 논의")
            lines.append("")
            lines.extend(
                f"- {cluster.get('title') or '제목 확인 필요'}" for cluster in unmapped
            )
            lines.append("")
    lines.extend(("## 도출 과제", ""))
    tasks = [
        task for task in brief.get("tasks") or [] if task.get("status") != "RESOLVED"
    ]
    if not tasks:
        lines.append("- 확인된 미해결 과제가 없습니다.")
    for task in tasks:
        ministries = ", ".join(task.get("ministries") or []) or "담당 부처 미확정"
        lines.append(f"- {task.get('title') or '과제'} ({ministries})")
    lines.extend(("", "## 공식자료 반영", ""))
    if integration.get("status") == "READY":
        lines.append(
            f"- 공식자료 통합 완료 · 의미 있는 변경 {integration.get('change_count') or 0}건"
        )
    else:
        lines.append("- 공식자료 대기 또는 통합 진행 중")
    lines.extend(
        (
            "",
            "---",
            "이 문서는 저장된 회의 결과와 근거로 생성했으며 추가 LLM 호출을 사용하지 않았습니다.",
            "",
        )
    )
    return "\n".join(lines)


@app.get("/api/live/broadcasts/{broadcast_id}/brief.md", tags=["live"])
def ended_live_broadcast_brief_markdown(broadcast_id: UUID) -> Response:
    record = ended_live_broadcast_brief(broadcast_id)
    return Response(
        content=_meeting_brief_markdown(record),
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="meeting-{broadcast_id}.md"',
            "X-LLM-Calls": "0",
        },
    )


@app.get("/api/live/broadcasts/{broadcast_id}/brief/official", tags=["live"])
def ended_live_broadcast_brief_official(broadcast_id: UUID) -> dict[str, object]:
    """Return official material and conservative links to the LIVE brief."""
    try:
        with connect(get_settings().database_url) as connection:
            live_repository = LiveRepository(connection)
            context = live_repository.broadcast_official_context(broadcast_id)
            material = live_repository.broadcast_official_material(broadcast_id)
            live_brief = MeetingBriefRepository(connection).latest(broadcast_id)
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="공식 자료 매칭 상태를 사용할 수 없습니다."
        ) from exc
    if context is None:
        raise HTTPException(
            status_code=404, detail="종료 방송 기록을 찾을 수 없습니다."
        )
    published = context.get("official_status") == "PUBLISHED"
    matched = int(context.get("matched_segment_count") or 0)
    final = int(context.get("final_segment_count") or 0)
    document = material.get("document")
    if live_brief:
        live_brief = {
            **live_brief,
            "brief": link_tasks_to_topics(live_brief.get("brief") or {}),
        }
    integration = (
        build_official_brief_integration(
            live_brief,
            material.get("utterances") or [],
        )
        if document
        else None
    )
    indexed = bool(integration and integration["summary"]["official_policy_utterances"])
    status = (
        "INTEGRATED"
        if published and indexed
        else "PUBLISHED"
        if published
        else "WAITING"
    )
    return {
        "broadcast_id": broadcast_id,
        "status": status,
        "message": (
            "LIVE 분석과 공식 회의록의 관련 근거를 연결했습니다."
            if status == "INTEGRATED"
            else "공식 자료는 발행되었으며 발언 분류를 준비하고 있습니다."
            if published
            else "공식 회의록이 발행되면 LIVE 저장본과 자동으로 연결합니다."
        ),
        "match_rate": round(matched / final * 100, 1) if final else 0.0,
        "exact_match": {
            "matched_segments": matched,
            "final_segments": final,
            "method": "EXACT_NORMALIZED_SUBSTRING",
        },
        "context": context,
        "document": document,
        "integration": integration,
        "authority_status": (
            (document or {}).get("authority_status")
            or context.get("official_authority_status")
            or ("OFFICIAL" if published else "PROVISIONAL")
        ),
    }


@app.get("/api/live/broadcasts/{broadcast_id}/brief/evidence", tags=["live"])
def ended_live_broadcast_brief_evidence(
    broadcast_id: UUID,
    entity_type: str,
    entity_id: str,
) -> dict[str, object]:
    if entity_type not in {
        "topic", "topic_group", "task", "speaker", "live_topic_cluster",
    }:
        raise HTTPException(status_code=422, detail="unsupported evidence entity type")
    if not entity_id or len(entity_id) > 80:
        raise HTTPException(status_code=422, detail="invalid evidence entity id")
    try:
        with connect(get_settings().database_url) as connection:
            repository = MeetingBriefRepository(connection)
            brief = repository.latest(broadcast_id)
            if not brief:
                raise HTTPException(
                    status_code=404, detail="회의 결과 브리프가 없습니다."
                )
            integration = OfficialIntegrationRepository(connection).latest_for_brief(
                brief["brief_id"]
            )
            evidence_brief = (
                integration.get("integrated_brief")
                if integration and integration.get("status") == "READY"
                else brief.get("brief") or {}
            )
            if integration and integration.get("status") == "READY":
                evidence_brief = attach_official_evidence_from_changes(
                    evidence_brief,
                    integration.get("changes") or [],
                )
            evidence_brief = attach_meeting_topic_groups(
                link_tasks_to_topics(evidence_brief)
            )
            group_topic_ids: list[str] = []
            if entity_type == "topic_group":
                group = next(
                    (
                        value for value in evidence_brief.get("topic_groups") or []
                        if str(value.get("id")) == entity_id
                    ),
                    None,
                )
                if not group:
                    raise HTTPException(
                        status_code=404, detail="대상 주제를 찾을 수 없습니다."
                    )
                group_topic_ids = [str(value) for value in group.get("topic_ids") or []]
                evidence_ids = [str(value) for value in group.get("evidence_ids") or []]
                official_ids = []
                for topic_id in group_topic_ids:
                    for value in official_evidence_ids(
                        evidence_brief, "topic", topic_id
                    ):
                        if value not in official_ids:
                            official_ids.append(value)
            else:
                evidence_ids = repository.evidence_ids(
                    {"brief": evidence_brief}, entity_type, entity_id
                )
                official_ids = official_evidence_ids(
                    evidence_brief, entity_type, entity_id
                )
            if not evidence_ids and not official_ids:
                raise HTTPException(
                    status_code=404, detail="연결된 근거 발언이 없습니다."
                )
            live_utterances = []
            live_repository = LiveRepository(connection)
            if evidence_ids:
                snapshot = live_repository.ended_transcript_snapshot(broadcast_id)
                reconciliations = live_repository.broadcast_reconciliation_details(
                    broadcast_id
                )
                for segment in snapshot["segments"]:
                    segment["official_reconciliation"] = reconciliations.get(
                        segment["revision_id"]
                    )
                snapshot = _present_transcript(
                    connection,
                    snapshot,
                    official_speakers=False,
                )
                evidence_set = set(evidence_ids)
                live_utterances = [
                    item
                    for item in snapshot["utterances"]
                    if evidence_set.intersection(
                        {
                            str(item.get("utterance_id") or ""),
                            *(str(value) for value in item.get("segment_ids") or []),
                        }
                    )
                ]
            official_utterances = (
                official_evidence_items(connection, official_ids)
                if official_ids
                else []
            )
            material = live_repository.broadcast_official_material(broadcast_id)
            document = material.get("document") or {}
            current_official_rows = list(material.get("utterances") or [])
            current_official_ids = [
                value
                for value in official_ids
                if any(
                    str(row.get("utterance_id")) == str(value)
                    for row in current_official_rows
                )
            ]
            # Persisted official IDs are the reviewed source of truth.  Only
            # run the broader deterministic matcher as a fallback; otherwise
            # generic legal terms can pull unrelated nearby speeches into a
            # newly-added official topic.
            if (
                entity_type in {"topic", "topic_group", "task"}
                and current_official_rows
                and not current_official_ids
            ):
                related = build_official_brief_integration(
                    {"brief": evidence_brief},
                    current_official_rows,
                )
                collection = (
                    related.get("topics", [])
                    if entity_type in {"topic", "topic_group"}
                    else related.get("tasks", [])
                )
                target_ids = (
                    set(group_topic_ids)
                    if entity_type == "topic_group"
                    else {entity_id}
                )
                entities = [
                    value for value in collection
                    if str(value.get("id")) in target_ids
                ]
                for entity in entities:
                    for record in entity.get("official_evidence", []):
                        value = str(record.get("utterance_id") or "")
                        if value and value not in current_official_ids:
                            current_official_ids.append(value)
            official_presentations = (
                build_official_evidence_presentations(
                    live_utterances,
                    current_official_rows,
                    current_official_ids,
                    publication_stage=str(
                        document.get("publication_stage") or "UNKNOWN"
                    ),
                    authority_status=str(
                        document.get("authority_status") or "PROVISIONAL"
                    ),
                )
                if current_official_rows
                else []
            )
            utterances = (
                official_presentations or live_utterances or official_utterances
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="근거 발언을 사용할 수 없습니다."
        ) from exc
    return {
        "broadcast_id": broadcast_id,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "items": utterances,
        "count": len(utterances),
        "authority_status": (
            str(document.get("authority_status"))
            if official_presentations
            else "PROVISIONAL"
        ),
        "source": (
            "OFFICIAL_TRANSCRIPT_PRESENTATION"
            if official_presentations
            else "LIVE_CAPTION_TURN"
            if live_utterances
            else "OFFICIAL_TRANSCRIPT_UTTERANCE"
        ),
        "official_reference_count": len(official_presentations),
        "publication_stage": (
            document.get("publication_stage") if official_presentations else None
        ),
        "live_baseline_count": len(live_utterances),
    }


@app.get("/api/live/tasks", tags=["live"])
def live_follow_up_tasks(
    committee: str | None = None,
    ministry: str | None = None,
    limit: int = 20,
) -> dict[str, object]:
    committee = _validate_live_committee(committee)
    if ministry is not None:
        ministry = ministry.strip()
        if not ministry or len(ministry) > 50:
            raise HTTPException(status_code=422, detail="invalid ministry filter")
    if not 1 <= limit <= 100:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 100")
    try:
        with connect(get_settings().database_url) as connection:
            items = LiveRepository(connection).list_open_follow_up_tasks(
                committee,
                ministry=ministry,
                limit=limit,
            )
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="후속 과제 기록을 사용할 수 없습니다."
        ) from exc
    ministries = sorted(
        {value for item in items for value in item.get("ministries", [])}
    )
    return {
        "items": items,
        "count": len(items),
        "ministries": ministries,
        "authority_status": "PROVISIONAL",
        "source": "FINAL_CAPTION_REVISION_WITH_EXPLICIT_OPEN_TASK",
    }


@app.get("/api/live/transcript/delta", tags=["live"])
def live_transcript_delta(
    after: int = 0,
    committee: str | None = None,
    broadcast_id: UUID | None = None,
    limit: int = 200,
) -> dict[str, object]:
    if after < 0:
        raise HTTPException(status_code=422, detail="after must be zero or greater")
    if not 1 <= limit <= 500:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 500")
    committee = _validate_live_committee(committee)
    settings = get_settings()
    try:
        with connect(settings.database_url) as connection:
            items = LiveRepository(connection).transcript_events_after(
                after,
                committee_name=committee,
                broadcast_id=broadcast_id,
                limit=limit,
            )
            broadcast_ids = sorted({item["broadcast_id"] for item in items})
            source_event_count = len(items)
            next_cursor = items[-1]["cursor"] if items else after
            overrides = SpeakerRepository(connection).override_map(broadcast_ids)
            items = apply_speaker_overrides(items, overrides)
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="LIVE 자막 데이터베이스를 사용할 수 없습니다."
        ) from exc
    return {
        "items": items,
        "count": len(items),
        "after": after,
        "next_cursor": next_cursor,
        "has_more": source_event_count == limit,
        "authority_status": "LIVE",
    }


@app.get("/api/data-sources", tags=["system"])
def data_sources() -> dict[str, object]:
    sources = public_catalog()
    return {
        "items": sources,
        "summary": {
            "total": len(sources),
            "application_required": sum(
                item["status"] == "APPLICATION_REQUIRED" for item in sources
            ),
            "callable": sum(bool(item["callable"]) for item in sources),
        },
    }


@app.post("/api/watch/session", tags=["watch"])
def create_watch_session(
    request: Request,
    response: Response,
    x_watch_token: str | None = Header(default=None),
) -> dict[str, object]:
    if not get_settings().watch_alerts_enabled:
        raise HTTPException(
            status_code=503, detail="관심주제 알림 기능이 비활성화되어 있습니다."
        )
    try:
        with connect(get_settings().database_url) as connection:
            repository = WatchRepository(connection)
            existing = repository.subscriber_for_token(x_watch_token)
            if existing is not None:
                return {
                    "subscriber_id": existing,
                    "token": "",
                    "token_type": "Secure-Cookie",
                    "session_mode": "COOKIE",
                }
            subscriber_id, token = WatchRepository(connection).create_subscriber()
            web_token = WatchDeliveryRepository(connection).create_web_session(
                subscriber_id, user_agent=request.headers.get("user-agent", ""),
            )
            set_watch_cookie(response, web_token)
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="관심주제 세션을 시작할 수 없습니다."
        ) from exc
    return {
        "subscriber_id": subscriber_id,
        "token": token,
        "token_type": "X-Watch-Token",
        "session_mode": "COOKIE_WITH_LEGACY_FALLBACK",
    }


@app.post("/api/watch/session/upgrade", tags=["watch"])
def upgrade_watch_session(
    request: Request,
    response: Response,
    x_watch_token: str | None = Header(default=None),
) -> dict[str, object]:
    try:
        with connect(get_settings().database_url) as connection:
            subscriber_id = _watch_subscriber(connection, x_watch_token)
            token = WatchDeliveryRepository(connection).create_web_session(
                subscriber_id, user_agent=request.headers.get("user-agent", ""),
            )
            set_watch_cookie(response, token)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="보안 세션으로 전환할 수 없습니다."
        ) from exc
    return {"upgraded": True, "session_mode": "COOKIE"}


@app.delete("/api/watch/session/current", tags=["watch"])
def revoke_current_watch_session(
    request: Request,
    response: Response,
    x_watch_token: str | None = Header(default=None),
) -> dict[str, object]:
    settings = get_settings()
    token = request.cookies.get(settings.watch_session_cookie_name)
    try:
        with connect(settings.database_url) as connection:
            _watch_subscriber(connection, x_watch_token)
            revoked = bool(token) and WatchDeliveryRepository(
                connection
            ).revoke_web_session(token)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="현재 기기 세션을 종료할 수 없습니다."
        ) from exc
    clear_watch_cookie(response)
    return {"revoked": bool(revoked)}


@app.delete("/api/watch/session/all", tags=["watch"])
def revoke_all_watch_sessions(
    response: Response,
    x_watch_token: str | None = Header(default=None),
) -> dict[str, object]:
    try:
        with connect(get_settings().database_url) as connection:
            subscriber_id = _watch_subscriber(connection, x_watch_token)
            revoked = WatchDeliveryRepository(connection).revoke_all_web_sessions(
                subscriber_id
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="전체 기기 세션을 종료할 수 없습니다."
        ) from exc
    clear_watch_cookie(response)
    return {"revoked": revoked}


@app.get("/api/watch/rules", tags=["watch"])
def watch_rules(x_watch_token: str | None = Header(default=None)) -> dict[str, object]:
    try:
        with connect(get_settings().database_url) as connection:
            subscriber_id = _watch_subscriber(connection, x_watch_token)
            items = WatchRepository(connection).list_rules(subscriber_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="관심주제 설정을 불러올 수 없습니다."
        ) from exc
    return {"items": items, "count": len(items)}


@app.post("/api/watch/rules", tags=["watch"])
def create_watch_rule(
    payload: WatchRulePayload,
    x_watch_token: str | None = Header(default=None),
) -> dict[str, object]:
    if payload.institution and payload.institution not in ALLOWED_INSTITUTIONS:
        raise HTTPException(status_code=422, detail="지원하지 않는 기관 범위입니다.")
    if payload.notification_policy not in WATCH_NOTIFICATION_POLICIES:
        raise HTTPException(status_code=422, detail="지원하지 않는 알림 빈도입니다.")
    includes = _clean_watch_terms(payload.include_terms)
    excludes = (
        _clean_watch_terms(payload.exclude_terms) if payload.exclude_terms else []
    )
    try:
        with connect(get_settings().database_url) as connection:
            subscriber_id = _watch_subscriber(connection, x_watch_token)
            item = WatchRepository(connection).create_rule(
                subscriber_id,
                name=" ".join(payload.name.split()),
                include_terms=includes,
                exclude_terms=excludes,
                institution=payload.institution,
                committee_name=(payload.committee_name or "").strip() or None,
                notification_policy=payload.notification_policy,
                cooldown_minutes=_watch_cooldown_minutes(payload.notification_policy),
                digest_enabled=payload.digest_enabled,
                kakao_enabled=payload.kakao_enabled,
            )
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="관심주제를 저장할 수 없습니다."
        ) from exc
    return item


@app.put("/api/watch/rules/{rule_id}", tags=["watch"])
def update_watch_rule(
    rule_id: UUID,
    payload: WatchRuleUpdatePayload,
    x_watch_token: str | None = Header(default=None),
) -> dict[str, object]:
    values = payload.model_dump(exclude_unset=True)
    if values.get("institution") and values["institution"] not in ALLOWED_INSTITUTIONS:
        raise HTTPException(status_code=422, detail="지원하지 않는 기관 범위입니다.")
    if (
        values.get("notification_policy")
        and values["notification_policy"] not in WATCH_NOTIFICATION_POLICIES
    ):
        raise HTTPException(status_code=422, detail="지원하지 않는 알림 빈도입니다.")
    if "include_terms" in values:
        values["include_terms"] = _clean_watch_terms(values["include_terms"])
    if "exclude_terms" in values:
        values["exclude_terms"] = (
            _clean_watch_terms(values["exclude_terms"])
            if values["exclude_terms"]
            else []
        )
    if "name" in values:
        values["name"] = " ".join(values["name"].split())
    if "notification_policy" in values:
        values["cooldown_minutes"] = _watch_cooldown_minutes(
            values["notification_policy"]
        )
    try:
        with connect(get_settings().database_url) as connection:
            subscriber_id = _watch_subscriber(connection, x_watch_token)
            item = WatchRepository(connection).update_rule(
                subscriber_id, rule_id, **values
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="관심주제를 수정할 수 없습니다."
        ) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="관심주제를 찾을 수 없습니다.")
    return item


@app.delete("/api/watch/rules/{rule_id}", tags=["watch"])
def delete_watch_rule(
    rule_id: UUID,
    x_watch_token: str | None = Header(default=None),
) -> dict[str, object]:
    try:
        with connect(get_settings().database_url) as connection:
            subscriber_id = _watch_subscriber(connection, x_watch_token)
            deleted = WatchRepository(connection).delete_rule(subscriber_id, rule_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="관심주제를 삭제할 수 없습니다."
        ) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="삭제할 알림 주제를 찾을 수 없습니다.")
    return {"deleted": deleted}


@app.get("/api/watch/rules/{rule_id}/report", tags=["watch"])
def watch_rule_report(
    rule_id: UUID,
    x_watch_token: str | None = Header(default=None),
) -> dict[str, object]:
    try:
        settings = get_settings()
        with connect(settings.database_url) as connection:
            subscriber_id = _watch_subscriber(connection, x_watch_token)
            repository = WatchRepository(connection)
            item = repository.latest_rule_report(subscriber_id, rule_id)
            if item is not None and settings.watch_llm_enabled:
                current_ids = {str(match["match_id"]) for match in item.get("matches") or []}
                integrated = item.get("integrated_summary") or {}
                saved_ids = {
                    str(match_id)
                    for match_id in integrated.get("evidence_match_ids", [])
                }
                if integrated.get("prompt_version") not in WATCH_REPORT_COMPATIBLE_PROMPT_VERSIONS:
                    saved_ids = set()
                new_evidence_count = len(current_ids - saved_ids)
                if new_evidence_count >= settings.watch_llm_min_new_matches:
                    item["summary_requested"] = repository.request_rule_report_summary(
                        subscriber_id, item["session_id"],
                    )
                    item["summary_status"] = (
                        "UPDATING" if item.get("integrated_summary") else "GENERATING"
                    )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="알림 주제 보고서를 불러올 수 없습니다."
        ) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="알림 주제를 찾을 수 없습니다.")
    return item


@app.get("/api/watch/notifications", tags=["watch"])
def watch_notifications(
    limit: int = 50,
    x_watch_token: str | None = Header(default=None),
) -> dict[str, object]:
    if not 1 <= limit <= 100:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 100")
    try:
        with connect(get_settings().database_url) as connection:
            subscriber_id = _watch_subscriber(connection, x_watch_token)
            return WatchRepository(connection).list_notifications(
                subscriber_id, limit=limit
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="알림 내역을 불러올 수 없습니다."
        ) from exc


@app.post("/api/watch/notifications/{notification_id}/read", tags=["watch"])
def read_watch_notification(
    notification_id: UUID,
    x_watch_token: str | None = Header(default=None),
) -> dict[str, object]:
    try:
        with connect(get_settings().database_url) as connection:
            subscriber_id = _watch_subscriber(connection, x_watch_token)
            updated = WatchRepository(connection).mark_notification_read(
                subscriber_id,
                notification_id,
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="알림 상태를 저장할 수 없습니다."
        ) from exc
    return {"updated": updated}


@app.delete("/api/watch/notifications/{notification_id}", tags=["watch"])
def delete_watch_notification(
    notification_id: UUID,
    x_watch_token: str | None = Header(default=None),
) -> dict[str, object]:
    try:
        with connect(get_settings().database_url) as connection:
            subscriber_id = _watch_subscriber(connection, x_watch_token)
            deleted = WatchRepository(connection).delete_notification(
                subscriber_id,
                notification_id,
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="감지 기록을 삭제할 수 없습니다."
        ) from exc
    return {"deleted": deleted}


@app.delete("/api/watch/notifications", tags=["watch"])
def clear_read_watch_notifications(
    x_watch_token: str | None = Header(default=None),
) -> dict[str, object]:
    try:
        with connect(get_settings().database_url) as connection:
            subscriber_id = _watch_subscriber(connection, x_watch_token)
            deleted_count = WatchRepository(connection).clear_read_notifications(
                subscriber_id
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="읽은 감지 기록을 정리할 수 없습니다."
        ) from exc
    return {"deleted_count": deleted_count}


@app.get("/api/watch/metrics", tags=["watch"])
def watch_metrics(
    x_watch_token: str | None = Header(default=None),
) -> dict[str, object]:
    try:
        with connect(get_settings().database_url) as connection:
            subscriber_id = _watch_subscriber(connection, x_watch_token)
            metrics = WatchRepository(connection).metrics(subscriber_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="알림 운영 지표를 불러올 수 없습니다."
        ) from exc
    return {
        **metrics,
        "retention_limit": 50,
        "authority_status": "OPERATIONAL_METRIC",
    }


@app.get("/api/watch/kakao/status", tags=["watch"])
def watch_kakao_status(
    x_watch_token: str | None = Header(default=None),
) -> dict[str, object]:
    settings = get_settings()
    provider = KakaoNotificationProvider(settings)
    try:
        with connect(settings.database_url) as connection:
            subscriber_id = _watch_subscriber(connection, x_watch_token)
            account = WatchDeliveryRepository(connection).status(subscriber_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="Kakao 연결 상태를 불러올 수 없습니다."
        ) from exc
    return {**provider.configuration(), **account, "provider": "KAKAO"}


@app.post("/api/watch/kakao/authorize", tags=["watch"])
def watch_kakao_authorize(
    x_watch_token: str | None = Header(default=None),
) -> dict[str, object]:
    settings = get_settings()
    provider = KakaoNotificationProvider(settings)
    if not provider.configured():
        raise HTTPException(
            status_code=503, detail="Kakao 연결 설정이 완료되지 않았습니다."
        )
    try:
        with connect(settings.database_url) as connection:
            subscriber_id = _watch_subscriber(connection, x_watch_token)
            state = WatchDeliveryRepository(connection).begin_oauth(subscriber_id)
            url = provider.authorization_url(state)
    except HTTPException:
        raise
    except KakaoProviderError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="Kakao 연결을 시작할 수 없습니다."
        ) from exc
    return {"authorization_url": url, "expires_in_seconds": 600}


@app.get("/api/watch/kakao/callback", tags=["watch"], include_in_schema=False)
def watch_kakao_callback(
    request: Request,
    code: str = "",
    state: str = "",
    error: str = "",
) -> RedirectResponse:
    settings = get_settings()
    destination = settings.watch_public_base_url or "/"
    if error or not code or not state:
        return RedirectResponse(f"{destination}?watch_kakao=denied", status_code=303)
    try:
        with connect(settings.database_url) as connection:
            repository = WatchDeliveryRepository(connection)
            subscriber_id = repository.consume_oauth(state)
            if subscriber_id is None:
                raise KakaoProviderError(
                    "만료되거나 사용된 Kakao 연결 요청입니다.", 400
                )
            account = KakaoNotificationProvider(settings).exchange_code(code)
            if "talk_message" not in account["scopes"]:
                raise KakaoProviderError("Kakao 메시지 전송 동의가 필요합니다.", 400)
            repository.lock_kakao_identity(account["kakao_user_id"])
            canonical_id = (
                repository.subscriber_for_kakao_user(account["kakao_user_id"])
                or subscriber_id
            )
            # When a Kakao identity already has a canonical account, its cloud
            # rules remain authoritative. Login must not silently import rules
            # from a transient browser subscriber and accumulate duplicates.
            repository.save_account(canonical_id, account)
            web_token = repository.create_web_session(
                canonical_id, user_agent=request.headers.get("user-agent", ""),
            )
    except KakaoProviderError as exc:
        result = "consent_required" if "동의" in str(exc) else "failed"
        return RedirectResponse(f"{destination}?watch_kakao={result}", status_code=303)
    except Exception:
        return RedirectResponse(f"{destination}?watch_kakao=failed", status_code=303)
    response = RedirectResponse(f"{destination}?watch_kakao=connected", status_code=303)
    set_watch_cookie(response, web_token)
    return response


@app.delete("/api/watch/kakao", tags=["watch"])
def watch_kakao_disconnect(
    x_watch_token: str | None = Header(default=None),
) -> dict[str, object]:
    settings = get_settings()
    try:
        with connect(settings.database_url) as connection:
            subscriber_id = _watch_subscriber(connection, x_watch_token)
            repository = WatchDeliveryRepository(connection)
            # Remote unlink revokes every token for the same Kakao user/app,
            # including tokens owned by another service. Disconnect only this
            # PoC's account and outbox; app-level revocation is an operator task.
            repository.disconnect(subscriber_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="Kakao 연결을 해제할 수 없습니다."
        ) from exc
    return {"disconnected": True, "remote_unlinked": False, "warning": ""}


@app.get("/api/watch/admin/reviews", tags=["watch-admin"])
def watch_admin_reviews(
    limit: int = 50,
    x_watch_admin_token: str | None = Header(default=None),
) -> dict[str, object]:
    _watch_admin(x_watch_admin_token)
    if not 1 <= limit <= 100:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 100")
    try:
        with connect(get_settings().database_url) as connection:
            items = WatchOperationsRepository(connection).review_queue(limit=limit)
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="운영 검토 목록을 불러올 수 없습니다."
        ) from exc
    return {"items": items, "count": len(items), "automatic_judgment_preserved": True}


@app.get("/api/watch/admin/session", tags=["watch-admin"])
def watch_admin_session(
    x_watch_admin_token: str | None = Header(default=None),
) -> dict[str, bool]:
    """Validate the tab-scoped operator session without loading operational data."""
    _watch_admin(x_watch_admin_token)
    return {"authenticated": True}


@app.post("/api/watch/admin/reviews/{verification_id}", tags=["watch-admin"])
def decide_watch_admin_review(
    verification_id: UUID,
    payload: WatchReviewDecisionPayload,
    x_watch_admin_token: str | None = Header(default=None),
) -> dict[str, object]:
    _watch_admin(x_watch_admin_token)
    if payload.decision not in {"APPROVE", "CORRECT", "DEFER"}:
        raise HTTPException(status_code=422, detail="지원하지 않는 검토 결정입니다.")
    try:
        with connect(get_settings().database_url) as connection:
            item = WatchOperationsRepository(connection).decide(
                verification_id,
                decision=payload.decision,
                note=" ".join(payload.note.split()),
                reviewed_by=" ".join(payload.reviewed_by.split()),
            )
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="운영 검토 결정을 저장할 수 없습니다."
        ) from exc
    if item is None:
        raise HTTPException(
            status_code=404, detail="자동 판정 항목을 찾을 수 없습니다."
        )
    return item


@app.post("/api/watch/admin/live-regression/run", tags=["watch-admin"])
def run_watch_live_regression(
    limit: int = 20,
    x_watch_admin_token: str | None = Header(default=None),
) -> dict[str, object]:
    _watch_admin(x_watch_admin_token)
    if not 1 <= limit <= 100:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 100")
    try:
        with connect(get_settings().database_url) as connection:
            items = WatchOperationsRepository(connection).audit_recent(limit=limit)
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="실방송 회귀 점검을 실행할 수 없습니다."
        ) from exc
    return {"items": items, "count": len(items)}


@app.get("/api/watch/admin/live-regression", tags=["watch-admin"])
def watch_live_regression_status(
    limit: int = 50,
    x_watch_admin_token: str | None = Header(default=None),
) -> dict[str, object]:
    _watch_admin(x_watch_admin_token)
    try:
        with connect(get_settings().database_url) as connection:
            items = WatchOperationsRepository(connection).latest_audits(limit=limit)
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="실방송 회귀 이력을 불러올 수 없습니다."
        ) from exc
    return {"items": items, "count": len(items)}


@app.get("/api/watch/sessions/{session_id}", tags=["watch"])
def watch_session_detail(
    session_id: UUID,
    x_watch_token: str | None = Header(default=None),
) -> dict[str, object]:
    try:
        with connect(get_settings().database_url) as connection:
            subscriber_id = _watch_subscriber(connection, x_watch_token)
            item = WatchRepository(connection).session(subscriber_id, session_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="관련 발언 흐름을 불러올 수 없습니다."
        ) from exc
    if item is None:
        raise HTTPException(
            status_code=404, detail="관련 발언 흐름을 찾을 수 없습니다."
        )
    return item


@app.post("/api/watch/test-broadcasts", tags=["watch"])
def start_watch_test_broadcast(
    payload: WatchTestBroadcastPayload | None = None,
    x_watch_token: str | None = Header(default=None),
    x_watch_admin_token: str | None = Header(default=None),
) -> dict[str, object]:
    _watch_admin(x_watch_admin_token)
    payload = payload or WatchTestBroadcastPayload()
    if not get_settings().watch_test_broadcasts_enabled:
        raise HTTPException(
            status_code=503, detail="테스트 방송 기능이 비활성화되어 있습니다."
        )
    try:
        with connect(get_settings().database_url) as connection:
            subscriber_id = _watch_subscriber(connection, x_watch_token)
            rules = [
                item
                for item in WatchRepository(connection).list_rules(subscriber_id)
                if item["enabled"]
            ]
            if not rules:
                raise HTTPException(
                    status_code=409, detail="먼저 관심주제를 하나 이상 등록해 주세요."
                )
            if payload.replay_mode not in {"SYNTHETIC", REPLAY_MODE}:
                raise HTTPException(status_code=422, detail="지원하지 않는 테스트 방송입니다.")
            replay_text = " ".join(
                str(step["text"]) for step in build_hasi_ai_replay_script()
            ).casefold()
            matching_rules = [
                rule for rule in rules
                if rule.get("institution") in {None, "", "LEGISLATURE"}
                and any(
                    str(term).strip().casefold() in replay_text
                    for term in rule.get("include_terms") or []
                    if str(term).strip()
                )
            ] if payload.replay_mode == REPLAY_MODE else rules
            if not matching_rules:
                raise HTTPException(
                    status_code=409,
                    detail="이 행안위 구간에서 감지할 AI·인공지능·행정안전부 알람을 먼저 등록해 주세요.",
                )
            if payload.kakao_delivery_enabled:
                if not WatchDeliveryRepository(connection).connected(subscriber_id):
                    raise HTTPException(
                        status_code=409,
                        detail="카카오 나에게 보내기를 먼저 연결해 주세요.",
                    )
                if not any(rule.get("kakao_enabled") for rule in matching_rules):
                    raise HTTPException(
                        status_code=409,
                        detail="감지 가능한 알람 주제에서 ‘카카오로도 받기’를 켜 주세요.",
                    )
            keyword = str(matching_rules[0]["include_terms"][0])
            item = WatchTestRepository(connection).start(
                subscriber_id,
                keyword,
                datetime.now(ZoneInfo("UTC")),
                replay_mode=payload.replay_mode,
                kakao_delivery_enabled=payload.kakao_delivery_enabled,
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="행안위 재현 테스트 방송을 시작할 수 없습니다."
        ) from exc
    return {
        **item,
        "keyword": keyword,
        "actual_timing": False,
        "timing_mode": "ACCELERATED" if payload.replay_mode == REPLAY_MODE else "SYNTHETIC",
        "estimated_duration_seconds": (
            REPLAY_ESTIMATED_DURATION_SECONDS
            if payload.replay_mode == REPLAY_MODE else 36
        ),
    }


@app.post("/api/watch/test-broadcasts/{test_id}/playback-ready", tags=["watch"])
def activate_watch_test_broadcast(
    test_id: UUID,
    x_watch_token: str | None = Header(default=None),
    x_watch_admin_token: str | None = Header(default=None),
) -> dict[str, object]:
    _watch_admin(x_watch_admin_token)
    try:
        with connect(get_settings().database_url) as connection:
            subscriber_id = _watch_subscriber(connection, x_watch_token)
            item = WatchTestRepository(connection).activate(
                subscriber_id, test_id, datetime.now(ZoneInfo("UTC")),
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="영상과 자막 재현을 동기화할 수 없습니다."
        ) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="테스트 방송을 찾을 수 없습니다.")
    return item


@app.get("/api/watch/test-broadcasts/latest", tags=["watch"])
def latest_watch_test_broadcast(
    x_watch_token: str | None = Header(default=None),
    x_watch_admin_token: str | None = Header(default=None),
) -> dict[str, object]:
    _watch_admin(x_watch_admin_token)
    try:
        with connect(get_settings().database_url) as connection:
            subscriber_id = _watch_subscriber(connection, x_watch_token)
            item = WatchTestRepository(connection).latest(subscriber_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="테스트 방송 상태를 불러올 수 없습니다."
        ) from exc
    return {"item": item}


@app.get("/api/watch/test-broadcasts/{test_id}", tags=["watch"])
def watch_test_broadcast(
    test_id: UUID,
    x_watch_token: str | None = Header(default=None),
    x_watch_admin_token: str | None = Header(default=None),
) -> dict[str, object]:
    _watch_admin(x_watch_admin_token)
    try:
        with connect(get_settings().database_url) as connection:
            subscriber_id = _watch_subscriber(connection, x_watch_token)
            item = WatchTestRepository(connection).get(subscriber_id, test_id)
            if item is None:
                raise HTTPException(
                    status_code=404, detail="테스트 방송을 찾을 수 없습니다."
                )
            snapshot = LiveRepository(connection).test_transcript_snapshot(
                item["broadcast_id"],
                lifecycle_status=item["lifecycle_status"],
            )
            snapshot = _present_transcript(
                connection, snapshot, official_speakers=False
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="테스트 방송 기록을 불러올 수 없습니다."
        ) from exc
    return {**item, "transcript": snapshot}


WEB_DIR = PROJECT_DIR / "web"
if WEB_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=WEB_DIR), name="assets")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(Path(WEB_DIR) / "index.html")
