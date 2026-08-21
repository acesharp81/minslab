from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .adapters.national_assembly.catalog import public_catalog
from .config import PROJECT_DIR, get_settings
from .db.bill_repository import BillRepository
from .db.committee_repository import CommitteeRepository
from .db.connection import connect
from .db.live_repository import LiveRepository
from .db.review_repository import ReviewRepository
from .db.schedule_repository import ScheduleRepository
from .domain import AuthorityStatus, LifecycleStatus, ReconciliationStatus
from .domain.scope import TARGET_COMMITTEES
from .services.live_magazine import ALLOWED_INSTITUTIONS, load_live_magazine
from .services.cross_institution_flow import build_cross_institution_flow
from .services.executive_briefing_query import filter_executive_briefings


app = FastAPI(
    title="지금 우리 국회에선 API",
    version="0.1.0",
    description="공식 국회 자료의 수집·정규화·검색을 위한 POC-07 API",
)


@app.get("/api/health", tags=["system"])
def health() -> dict[str, object]:
    settings = get_settings()
    return {
        "status": "ok",
        "project": "POC-07",
        "phase": "live-e2e-demo",
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


@app.get("/api/schedule/today", tags=["schedule"])
@app.get("/api/meetings/today", tags=["meetings"], deprecated=True)
def today_schedule() -> dict[str, object]:
    settings = get_settings()
    if not settings.database_url:
        return {
            "items": [],
            "source_status": "NOT_CONFIGURED",
            "message": "DATABASE_URL이 설정되지 않았습니다.",
        }
    today = datetime.now(ZoneInfo(settings.national_assembly_timezone)).date()
    try:
        with connect(settings.database_url) as connection:
            items = ScheduleRepository(connection).list_schedule_for_date(today)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="정규화 데이터베이스를 사용할 수 없습니다.") from exc
    return {
        "items": items,
        "count": len(items),
        "target_committee_count": sum(bool(item["is_target_committee"]) for item in items),
        "date": today,
        "source_status": "OFFICIAL",
    }




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
    path = PROJECT_DIR / "web" / "data" / "live_magazine.json"
    try:
        fallback = load_live_magazine(
            path, institution=institution, scope=scope, limit=min(max(limit * 2, 5), 20)
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="saved live magazine is not available") from exc
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="saved live magazine is invalid") from exc
    actual: list[dict[str, object]] = []
    review_source_status = "AVAILABLE"
    try:
        with connect(get_settings().database_url) as connection:
            actual = ReviewRepository(connection).list_magazine(
                institution=institution, scope=scope, limit=max(limit * 2, 20),
            )
    except Exception:
        review_source_status = "DB_UNAVAILABLE"
    if institution:
        items = actual[:limit] if actual else fallback["items"][:limit]
    else:
        items = []
        for target in ("EXECUTIVE", "LEGISLATURE"):
            actual_target = [item for item in actual if item["institution"] == target]
            fallback_target = [
                item for item in fallback["items"] if item["institution"] == target
            ]
            items.extend((actual_target or fallback_target)[:limit])
    return {
        "items": items,
        "count": len(items),
        "available_count": len(items),
        "rotation_ms": 5000,
        "simulation": all(bool(item.get("simulation")) for item in items),
        "authority_status": "PROVISIONAL",
        "review_source_status": review_source_status,
        "source": {"type": "LIVE_REVIEW_WITH_SIMULATION_FALLBACK"},
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
    try:
        with connect(get_settings().database_url) as connection:
            active = LiveRepository(connection).active_transcript_snapshot()
        demos = [item for item in active["broadcasts"] if item.get("simulation")]
        for demo in demos:
            payload["assembly"]["items"].append({
                "institution": "LEGISLATURE", "committee_name": demo["committee_name"],
                "short_name": "DEMO", "meeting_external_id": demo["external_id"],
                "title": demo["title"], "status_text": "데모 생중계",
                "is_live": True, "has_caption_service": True,
                "quick_vod_available": False, "quick_vod_url": None,
                "thumbnail_url": "assets/magazine/sim-committee-hearing.png",
                "broadcast_id": demo["broadcast_id"],
                "stream_url": None,
                "simulation": True,
            })
        payload["assembly"]["live_count"] += len(demos)
        payload["assembly"]["demo_live_count"] = len(demos)
    except Exception:
        payload["assembly"]["demo_live_count"] = 0
    return payload


def _validate_live_committee(committee: str | None) -> str | None:
    if committee and committee not in TARGET_COMMITTEES:
        raise HTTPException(status_code=422, detail="committee is outside the target scope")
    return committee


@app.get("/api/live/transcript/snapshot", tags=["live"])
def live_transcript_snapshot(committee: str | None = None) -> dict[str, object]:
    committee = _validate_live_committee(committee)
    settings = get_settings()
    try:
        with connect(settings.database_url) as connection:
            snapshot = LiveRepository(connection).active_transcript_snapshot(committee)
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
    except Exception as exc:
        raise HTTPException(status_code=503, detail="최근 LIVE 기록을 사용할 수 없습니다.") from exc
    return {
        **snapshot,
        "authority_status": "PROVISIONAL",
        "view_mode": "RECENT_REVIEW",
    }


@app.get("/api/live/broadcasts", tags=["live"])
def ended_live_broadcasts(
    committee: str | None = None, limit: int = 5,
) -> dict[str, object]:
    committee = _validate_live_committee(committee)
    if not 1 <= limit <= 20:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 20")
    try:
        with connect(get_settings().database_url) as connection:
            items = LiveRepository(connection).list_ended_broadcasts(
                committee, limit=limit,
            )
    except Exception as exc:
        raise HTTPException(status_code=503, detail="종료 방송 이력을 사용할 수 없습니다.") from exc
    return {
        "items": items,
        "count": len(items),
        "authority_status": "PROVISIONAL",
        "view_mode": "BROADCAST_HISTORY",
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
                after, committee_name=committee, limit=limit,
            )
    except Exception as exc:
        raise HTTPException(status_code=503, detail="LIVE 자막 데이터베이스를 사용할 수 없습니다.") from exc
    return {
        "items": items,
        "count": len(items),
        "after": after,
        "next_cursor": items[-1]["cursor"] if items else after,
        "has_more": len(items) == limit,
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
