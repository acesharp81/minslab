from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .adapters.national_assembly.catalog import public_catalog
from .config import PROJECT_DIR, get_settings
from .db.bill_repository import BillRepository
from .db.committee_repository import CommitteeRepository
from .db.connection import connect
from .db.live_repository import LiveRepository
from .db.meeting_brief_repository import MeetingBriefRepository
from .db.official_evidence_query import official_evidence_items
from .db.official_integration_repository import OfficialIntegrationRepository
from .db.review_repository import ReviewRepository
from .db.schedule_repository import ScheduleRepository
from .db.speaker_repository import SpeakerRepository
from .db.summary_repository import SummaryRepository
from .domain import AuthorityStatus, LifecycleStatus, ReconciliationStatus
from .domain.scope import TARGET_COMMITTEES
from .ingestion.schedule_worker import UPCOMING_SCHEDULE_SCHEMA
from .services.cross_institution_flow import build_cross_institution_flow
from .services.executive_briefing_query import filter_executive_briefings
from .services.integrated_brief_evidence import (
    attach_official_evidence_from_changes,
    official_evidence_ids,
)
from .services.meeting_brief import link_tasks_to_topics
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
    group_transcript_segments,
)

ALLOWED_INSTITUTIONS = {"EXECUTIVE", "LEGISLATURE"}


app = FastAPI(
    title="지금 우리 국회에선 API",
    version="0.1.0",
    description="공식 국회 자료의 수집·정규화·검색을 위한 POC-07 API",
)

class SpeakerOverridePayload(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)


def _public_meeting_brief(
    item: dict[str, object] | None,
    progress_item: dict[str, object] | None = None,
) -> dict[str, object] | None:
    if not item:
        return None
    normalized_brief = link_tasks_to_topics(dict(item.get("brief") or {}))
    progress = dict(progress_item or {})
    if progress and progress.get("transcript_hash") != item["transcript_hash"]:
        progress = {}
    if not progress:
        total = int((item.get("brief") or {}).get("utterance_count") or 0)
        progress = {
            "status": "COMPLETED" if item["provider"] == "mistral" else "PROCESSING",
            "phase": "COMPLETED" if item["provider"] == "mistral" else "QUEUED",
            "total_utterances": total,
            "processed_utterances": total if item["provider"] == "mistral" else 0,
            "total_chunks": 0,
            "completed_chunks": 0,
        }
    ready = item["provider"] == "mistral"
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
        "brief_status": "READY" if ready else "PROCESSING",
        "brief_progress": progress,
    }


def _present_transcript(
    connection: object, snapshot: dict[str, object], *, official_speakers: bool = True,
) -> dict[str, object]:
    broadcast_ids = [item["broadcast_id"] for item in snapshot.get("broadcasts", [])]
    speaker_repository = SpeakerRepository(connection)
    overrides = speaker_repository.override_map(broadcast_ids)
    segments = apply_speaker_overrides(snapshot.get("segments", []), overrides)
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
        broadcast_ids, provider=summary_provider, model=summary_model,
        prompt_version=prompt_version,
    )
    cached_count = 0
    for utterance in utterances:
        cached = cached_summaries.get((
            utterance["broadcast_id"], utterance["content_hash"],
        ))
        if not cached:
            continue
        utterance["summary"] = cached["summary"]
        utterance["summary_kind"] = "AI_CACHED"
        utterance["summary_provider"] = cached["provider"]
        utterance["summary_model"] = cached["model"]
        utterance["summary_generated_at"] = cached["created_at"]
        utterance["live_insight"] = cached.get("live_insight") or None
        cached_count += 1
    snapshot["utterances"] = utterances
    snapshot["presentation_summary"] = {
        "segment_count": len(segments),
        "utterance_count": len(utterances),
        "ai_summary_count": cached_count,
        "gemini_summary_count": sum(1 for item in utterances if item.get("summary_provider") == "gemini"),
        "extractive_fallback_count": len(utterances) - cached_count,
        "mistral_summary_count": sum(1 for item in utterances if item.get("summary_provider") == "mistral"),
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
            "name": "지금 우리 국회에선",
            "english_name": "NationalAssembly",
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
            hour=0, minute=0, second=0, microsecond=0,
        )
    else:
        if now_utc.month == 12:
            reset_utc = now_utc.replace(
                year=now_utc.year + 1, month=1, day=1,
                hour=0, minute=0, second=0, microsecond=0,
            )
        else:
            reset_utc = now_utc.replace(
                month=now_utc.month + 1, day=1,
                hour=0, minute=0, second=0, microsecond=0,
            )
    return reset_utc.astimezone(ZoneInfo(timezone_name)).isoformat()


@app.get("/api/ai/usage", tags=["system"])
def ai_usage() -> dict[str, object]:
    settings = get_settings()
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
        float(settings.mistral_monthly_credit_usd)
        if provider == "mistral" else 0.0
    )
    usage = {
        "request_count": 0, "input_tokens": 0,
        "output_tokens": 0, "total_tokens": 0,
        "audio_request_count": 0, "audio_seconds": 0.0, "audio_cost_usd": 0.0,
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
    cost_usd = mistral_usage_cost_usd(
        usage,
        input_usd_per_million=settings.mistral_input_usd_per_million,
        output_usd_per_million=settings.mistral_output_usd_per_million,
    ) if provider == "mistral" else 0.0
    usage_percent = (
        (cost_usd / credit_usd) * 100
        if provider == "mistral" and credit_usd
        else (used / limit) * 100 if limit else 0
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
            item for item in snapshot.get("items", [])
            if today.isoformat() <= str(item.get("scheduled_date", "")) <= end_date.isoformat()
        ]
        source_status = "OFFICIAL"
        generated_at = snapshot.get("generated_at")
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        if not settings.database_url:
            return {
                "items": [], "count": 0, "target_committee_count": 0,
                "start_date": today, "end_date": end_date, "days": days,
                "source_status": "SYNC_PENDING",
            }
        try:
            with connect(settings.database_url) as connection:
                items = []
                for offset in range(days):
                    items.extend(ScheduleRepository(connection).list_schedule_for_date(
                        today + timedelta(days=offset)
                    ))
        except Exception as exc:
            raise HTTPException(status_code=503, detail="정규화 데이터베이스를 사용할 수 없습니다.") from exc
        source_status = "OFFICIAL_DB_FALLBACK"
        generated_at = None
    return {
        "items": items,
        "count": len(items),
        "target_committee_count": sum(bool(item.get("is_target_committee")) for item in items),
        "start_date": today,
        "end_date": end_date,
        "date": today,
        "days": days,
        "generated_at": generated_at,
        "source_status": source_status,
    }


@app.get("/api/schedule/upcoming", tags=["schedule"])
def upcoming_schedule(days: int = 2) -> dict[str, object]:
    if not 1 <= days <= 7:
        raise HTTPException(status_code=422, detail="days must be between 1 and 7")
    return _schedule_range(days)


@app.get("/api/schedule/today", tags=["schedule"])
@app.get("/api/meetings/today", tags=["meetings"], deprecated=True)
def today_schedule() -> dict[str, object]:
    return _schedule_range(1)




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
        raise HTTPException(status_code=503, detail="정규화 데이터베이스를 사용할 수 없습니다.") from exc
    return {"items": items, "count": len(items), "source_status": "OFFICIAL"}


@app.get("/api/executive/briefings", tags=["executive"])
def executive_briefings(
    limit: int = 10, ministry: str | None = None, q: str | None = None,
) -> dict[str, object]:
    if not 1 <= limit <= 20:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 20")
    for value in (ministry, q):
        if value is not None and (not value.strip() or len(value) > 80):
            raise HTTPException(status_code=422, detail="invalid executive briefing filter")
    path = get_settings().processed_data_dir / "executive_briefings.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="official executive briefings have not been collected") from exc
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=503, detail="official executive briefing snapshot is invalid") from exc
    if payload.get("schema_version") != "executive-briefings.v1":
        raise HTTPException(status_code=503, detail="official executive briefing contract mismatch")
    source_items = payload.get("items", [])[:limit]
    result = filter_executive_briefings(source_items, ministry=ministry, query=q)
    return {
        **payload,
        **result,
        "count": result["meeting_count"],
        "unfiltered_meeting_count": len(source_items),
    }


@app.get("/api/committees/meetings/{conference_id}/transcript", tags=["committees"])
def committee_official_transcript(
    conference_id: str, offset: int = 0, limit: int = 100,
    topic: str | None = None, ministry: str | None = None,
) -> dict[str, object]:
    if not (conference_id.startswith("N") and conference_id[1:].isdigit() and len(conference_id) <= 20):
        raise HTTPException(status_code=422, detail="invalid conference id")
    if offset < 0 or not 1 <= limit <= 200:
        raise HTTPException(status_code=422, detail="invalid transcript page")
    for value in (topic, ministry):
        if value is not None and (not value.strip() or len(value) > 50):
            raise HTTPException(status_code=422, detail="invalid transcript filter")
    try:
        with connect(get_settings().database_url) as connection:
            transcript = CommitteeRepository(connection).list_official_transcript(
                conference_id, offset=offset, limit=limit,
                topic=topic.strip() if topic else None,
                ministry=ministry.strip() if ministry else None,
            )
    except Exception as exc:
        raise HTTPException(status_code=503, detail="공식 회의록을 조회할 수 없습니다.") from exc
    if transcript is None:
        raise HTTPException(status_code=404, detail="수집된 공식 회의록 본문이 없습니다.")
    return {**transcript, "count": len(transcript["items"]), "source_status": "OFFICIAL_SOURCE"}


@app.get("/api/committees/policy-flow", tags=["committees"])
def committee_policy_flow(committee: str | None = None) -> dict[str, object]:
    if committee and committee not in TARGET_COMMITTEES:
        raise HTTPException(status_code=422, detail="committee is outside the target scope")
    try:
        with connect(get_settings().database_url) as connection:
            result = CommitteeRepository(connection).policy_flow(committee)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="정책 흐름을 조회할 수 없습니다.") from exc
    return {**result, "source_status": "OFFICIAL_TEXT_WITH_DRAFT_CLASSIFICATION"}


@app.get("/api/policy/cross-institution-flow", tags=["policy"])
def cross_institution_policy_flow(committee: str | None = None) -> dict[str, object]:
    if committee and committee not in TARGET_COMMITTEES:
        raise HTTPException(status_code=422, detail="committee is outside the target scope")
    path = get_settings().processed_data_dir / "executive_briefings.json"
    try:
        executive = json.loads(path.read_text(encoding="utf-8"))
        with connect(get_settings().database_url) as connection:
            legislative = CommitteeRepository(connection).policy_flow(committee)
        result = build_cross_institution_flow(executive.get("items", []), legislative)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="official executive briefings have not been collected") from exc
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=503, detail="official executive briefing snapshot is invalid") from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="기관 간 정책 흐름을 조회할 수 없습니다.") from exc
    return {
        **result,
        "committee_filter": committee,
        "source_status": "OFFICIAL_EVIDENCE_WITH_DRAFT_RULE_LINK",
    }


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
        raise HTTPException(status_code=422, detail="committee is outside the target scope")
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
                query=q, committee_name=committee, process_stage=stage, limit=limit,
            )
    except Exception as exc:
        raise HTTPException(status_code=503, detail="의안 데이터베이스를 사용할 수 없습니다.") from exc
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
        raise HTTPException(status_code=422, detail="scope must be at most 50 characters")
    if not 1 <= limit <= 20:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 20")
    actual: list[dict[str, object]] = []
    review_source_status = "AVAILABLE"
    try:
        with connect(get_settings().database_url) as connection:
            actual = ReviewRepository(connection).list_magazine(
                institution=institution, scope=scope, limit=max(limit * 2, 20),
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
        raise HTTPException(status_code=404, detail="LIVE source probe has not run") from exc
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=503, detail="LIVE source snapshot is invalid") from exc
    if payload.get("schema_version") != "live-source-status.v1":
        raise HTTPException(status_code=503, detail="LIVE source snapshot contract mismatch")
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
    if committee and committee not in TARGET_COMMITTEES:
        raise HTTPException(status_code=422, detail="committee is outside the target scope")
    return committee


@app.get("/api/live/transcript/snapshot", tags=["live"])
def live_transcript_snapshot(
    committee: str | None = None, broadcast_id: UUID | None = None,
) -> dict[str, object]:
    committee = _validate_live_committee(committee)
    settings = get_settings()
    try:
        with connect(settings.database_url) as connection:
            snapshot = LiveRepository(connection).active_transcript_snapshot(
                committee, broadcast_id=broadcast_id,
            )
            snapshot = _present_transcript(connection, snapshot)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="LIVE 자막 데이터베이스를 사용할 수 없습니다.") from exc
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
        raise HTTPException(status_code=503, detail="최근 LIVE 기록을 사용할 수 없습니다.") from exc
    return {
        **snapshot,
        "authority_status": "PROVISIONAL",
        "view_mode": "RECENT_REVIEW",
    }


@app.get("/api/live/broadcasts", tags=["live"])
def ended_live_broadcasts(
    committee: str | None = None, limit: int = 5, offset: int = 0,
) -> dict[str, object]:
    committee = _validate_live_committee(committee)
    if not 1 <= limit <= 20:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 20")
    if not 0 <= offset <= 1000:
        raise HTTPException(status_code=422, detail="offset must be between 0 and 1000")
    try:
        with connect(get_settings().database_url) as connection:
            items = LiveRepository(connection).list_ended_broadcasts(
                committee, limit=limit + 1, offset=offset,
            )
            has_more = len(items) > limit
            items = items[:limit]
            briefs = MeetingBriefRepository(connection).latest_map(
                item["broadcast_id"] for item in items
            )
            progresses = MeetingBriefRepository(connection).progress_map(
                item["broadcast_id"] for item in items
            )
            for item in items:
                item["meeting_brief"] = _public_meeting_brief(
                    briefs.get(item["broadcast_id"]),
                    progresses.get(item["broadcast_id"]),
                )
                item["brief_status"] = (
                    item["meeting_brief"].get("brief_status")
                    if item["meeting_brief"] else "PENDING"
                )
                item["brief_progress"] = (
                    item["meeting_brief"].get("brief_progress")
                    if item["meeting_brief"] else None
                )
    except Exception as exc:
        raise HTTPException(status_code=503, detail="종료 방송 이력을 사용할 수 없습니다.") from exc
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
        raise HTTPException(status_code=503, detail="LIVE 수집 현황을 사용할 수 없습니다.") from exc
    return {**summary, "days": days, "authority_status": "LIVE_SOURCE_STATS"}


@app.get("/api/live/broadcasts/{broadcast_id}/speakers", tags=["live"])
def broadcast_speakers(broadcast_id: UUID) -> dict[str, object]:
    try:
        with connect(get_settings().database_url) as connection:
            items = SpeakerRepository(connection).options(broadcast_id)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="화자 정보를 사용할 수 없습니다.") from exc
    if not items:
        raise HTTPException(status_code=404, detail="방송 또는 화자 정보를 찾을 수 없습니다.")
    return {"items": items, "count": len(items)}


@app.put("/api/live/broadcasts/{broadcast_id}/speakers/{source_label}", tags=["live"])
def update_broadcast_speaker(
    broadcast_id: UUID, source_label: str, payload: SpeakerOverridePayload,
) -> dict[str, object]:
    source_label = source_label.strip()
    display_name = payload.display_name.strip()
    if not source_label or len(source_label) > 80 or not display_name:
        raise HTTPException(status_code=422, detail="invalid speaker label")
    try:
        with connect(get_settings().database_url) as connection:
            item = SpeakerRepository(connection).set_override(
                broadcast_id, source_label, display_name,
            )
    except Exception as exc:
        raise HTTPException(status_code=503, detail="화자 이름을 저장할 수 없습니다.") from exc
    if item is None:
        raise HTTPException(status_code=404, detail="해당 방송의 화자 코드를 찾을 수 없습니다.")
    return {**item, "effective_display_name": display_name, "overridden": True}


@app.delete("/api/live/broadcasts/{broadcast_id}/speakers/{source_label}", tags=["live"])
def reset_broadcast_speaker(broadcast_id: UUID, source_label: str) -> dict[str, object]:
    source_label = source_label.strip()
    if not source_label or len(source_label) > 80:
        raise HTTPException(status_code=422, detail="invalid speaker label")
    try:
        with connect(get_settings().database_url) as connection:
            deleted = SpeakerRepository(connection).delete_override(
                broadcast_id, source_label,
            )
    except Exception as exc:
        raise HTTPException(status_code=503, detail="화자 이름을 초기화할 수 없습니다.") from exc
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
        raise HTTPException(status_code=503, detail="종료 방송 기록을 사용할 수 없습니다.") from exc
    if not snapshot["broadcasts"]:
        raise HTTPException(status_code=404, detail="종료 방송 기록을 찾을 수 없습니다.")
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
                OfficialIntegrationRepository(connection).latest_for_brief(item["brief_id"])
                if item else None)
            official_context = LiveRepository(connection).broadcast_official_context(
                broadcast_id
            )
    except Exception as exc:
        raise HTTPException(status_code=503, detail="회의 결과 브리프를 사용할 수 없습니다.") from exc
    public = _public_meeting_brief(item, progress)
    if not public:
        raise HTTPException(status_code=404, detail="생성된 회의 결과 브리프가 없습니다.")
    if (
        integration and integration.get("status") == "READY"
        and integration.get("meeting_brief_id") == public.get("brief_id")
    ):
        public["provisional_brief"] = public["brief"]
        public["brief"] = attach_official_evidence_from_changes(
            integration.get("integrated_brief") or public["brief"],
            integration.get("changes") or [],
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
            "status": "WAITING" if not integration else integration.get("status"),
            "change_count": 0,
            "changes": [],
        }
    public["official_context"] = official_context
    return public


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
        raise HTTPException(status_code=503, detail="공식 자료 매칭 상태를 사용할 수 없습니다.") from exc
    if context is None:
        raise HTTPException(status_code=404, detail="종료 방송 기록을 찾을 수 없습니다.")
    published = context.get("official_status") == "PUBLISHED"
    matched = int(context.get("matched_segment_count") or 0)
    final = int(context.get("final_segment_count") or 0)
    document = material.get("document")
    if live_brief:
        live_brief = {
            **live_brief, "brief": link_tasks_to_topics(live_brief.get("brief") or {}),
        }
    integration = build_official_brief_integration(
        live_brief, material.get("utterances") or [],
    ) if document else None
    indexed = bool(integration and integration["summary"]["official_policy_utterances"])
    status = (
        "INTEGRATED" if published and indexed
        else "PUBLISHED" if published
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
    broadcast_id: UUID, entity_type: str, entity_id: str,
) -> dict[str, object]:
    if entity_type not in {"topic", "task", "speaker"}:
        raise HTTPException(status_code=422, detail="unsupported evidence entity type")
    if not entity_id or len(entity_id) > 80:
        raise HTTPException(status_code=422, detail="invalid evidence entity id")
    try:
        with connect(get_settings().database_url) as connection:
            repository = MeetingBriefRepository(connection)
            brief = repository.latest(broadcast_id)
            if not brief:
                raise HTTPException(status_code=404, detail="회의 결과 브리프가 없습니다.")
            integration = OfficialIntegrationRepository(connection).latest_for_brief(brief["brief_id"])
            evidence_brief = (
                integration.get("integrated_brief")
                if integration and integration.get("status") == "READY"
                else brief.get("brief") or {}
            )
            if integration and integration.get("status") == "READY":
                evidence_brief = attach_official_evidence_from_changes(
                    evidence_brief, integration.get("changes") or [],
                )
            evidence_ids = repository.evidence_ids(
                {"brief": evidence_brief}, entity_type, entity_id)
            official_ids = official_evidence_ids(evidence_brief, entity_type, entity_id)
            if not evidence_ids and not official_ids:
                raise HTTPException(status_code=404, detail="연결된 근거 발언이 없습니다.")
            live_utterances = []
            live_repository = LiveRepository(connection)
            if evidence_ids:
                snapshot = live_repository.ended_transcript_snapshot(broadcast_id)
                reconciliations = (
                    live_repository.broadcast_reconciliation_details(broadcast_id)
                )
                for segment in snapshot["segments"]:
                    segment["official_reconciliation"] = reconciliations.get(
                        segment["revision_id"]
                    )
                snapshot = _present_transcript(
                    connection, snapshot, official_speakers=False,
                )
                evidence_set = set(evidence_ids)
                live_utterances = [
                    item for item in snapshot["utterances"]
                    if evidence_set.intersection({
                        str(item.get("utterance_id") or ""),
                        *(str(value) for value in item.get("segment_ids") or []),
                    })
                ]
            official_utterances = (
                official_evidence_items(connection, official_ids)
                if official_ids else []
            )
            material = live_repository.broadcast_official_material(broadcast_id)
            document = material.get("document") or {}
            current_official_rows = list(material.get("utterances") or [])
            current_official_ids = [
                value for value in official_ids
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
                entity_type in {"topic", "task"}
                and current_official_rows
                and not current_official_ids
            ):
                related = build_official_brief_integration(
                    {"brief": evidence_brief}, current_official_rows,
                )
                collection = (
                    related.get("topics", [])
                    if entity_type == "topic" else related.get("tasks", [])
                )
                entity = next(
                    (
                        value for value in collection
                        if str(value.get("id")) == entity_id
                    ),
                    None,
                )
                for record in (entity or {}).get("official_evidence", []):
                    value = str(record.get("utterance_id") or "")
                    if value and value not in current_official_ids:
                        current_official_ids.append(value)
            official_presentations = build_official_evidence_presentations(
                live_utterances,
                current_official_rows,
                current_official_ids,
                publication_stage=str(
                    document.get("publication_stage") or "UNKNOWN"
                ),
                authority_status=str(
                    document.get("authority_status") or "PROVISIONAL"
                ),
            ) if current_official_rows else []
            utterances = (
                official_presentations or live_utterances or official_utterances
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="근거 발언을 사용할 수 없습니다.") from exc
    return {
        "broadcast_id": broadcast_id,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "items": utterances,
        "count": len(utterances),
        "authority_status": (
            str(document.get("authority_status"))
            if official_presentations else "PROVISIONAL"
        ),
        "source": (
            "OFFICIAL_TRANSCRIPT_PRESENTATION"
            if official_presentations else "LIVE_CAPTION_TURN"
            if live_utterances else "OFFICIAL_TRANSCRIPT_UTTERANCE"
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
                committee, ministry=ministry, limit=limit,
            )
    except Exception as exc:
        raise HTTPException(status_code=503, detail="후속 과제 기록을 사용할 수 없습니다.") from exc
    ministries = sorted({
        value for item in items for value in item.get("ministries", [])
    })
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
                after, committee_name=committee, broadcast_id=broadcast_id, limit=limit,
            )
            broadcast_ids = sorted({item["broadcast_id"] for item in items})
            source_event_count = len(items)
            next_cursor = items[-1]["cursor"] if items else after
            overrides = SpeakerRepository(connection).override_map(broadcast_ids)
            items = apply_speaker_overrides(items, overrides)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="LIVE 자막 데이터베이스를 사용할 수 없습니다.") from exc
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

WEB_DIR = PROJECT_DIR / "web"
if WEB_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=WEB_DIR), name="assets")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(Path(WEB_DIR) / "index.html")
