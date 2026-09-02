from __future__ import annotations

import json
import logging
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Response
from pydantic import BaseModel, Field

from .config import get_settings
from .db.connection import connect
from .db.topic_report_repository import TopicReportRepository
from .db.watch_delivery_repository import WatchDeliveryRepository
from .db.watch_repository import WatchRepository
from .domain.ministry import canonical_ministry_name
from .services.openrouter_summary import DEFAULT_MODEL


router = APIRouter(prefix="/api/topic-reports", tags=["topic-reports"])
LOGGER = logging.getLogger(__name__)


def _official_executive_items() -> list[dict[str, object]]:
    path = get_settings().processed_data_dir / "executive_briefings.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []
    if payload.get("schema_version") != "executive-briefings.v1":
        return []
    return [item for item in payload.get("items") or [] if isinstance(item, dict)]


class TopicReportQueryPayload(BaseModel):
    ministry: str = Field(default="", max_length=80)
    topic: str = Field(default="", max_length=160)
    period_start: date
    period_end: date
    institution: str | None = None


def _subscriber(connection: object, token: str | None) -> UUID:
    subscriber_id = WatchRepository(connection).subscriber_for_token(token)
    if subscriber_id is None:
        raise HTTPException(status_code=401, detail="사용자 세션을 다시 시작해 주세요.")
    return subscriber_id


def _clean(payload: TopicReportQueryPayload) -> tuple[str, str, str | None]:
    settings = get_settings()
    ministry = canonical_ministry_name(payload.ministry)
    topic = " ".join(payload.topic.split())
    if not ministry and not topic:
        raise HTTPException(status_code=422, detail="소관 부처나 주제 중 하나는 입력해 주세요.")
    if topic and len(topic) < 2:
        raise HTTPException(status_code=422, detail="주제는 두 글자 이상 입력해 주세요.")
    institution = payload.institution or None
    if institution and institution not in {"EXECUTIVE", "LEGISLATURE"}:
        raise HTTPException(status_code=422, detail="지원하지 않는 기관 범위입니다.")
    if payload.period_end < payload.period_start:
        raise HTTPException(status_code=422, detail="종료일은 시작일보다 빠를 수 없습니다.")
    if (payload.period_end - payload.period_start).days > settings.topic_report_max_period_days:
        raise HTTPException(
            status_code=422,
            detail=f"한 번에 최대 {settings.topic_report_max_period_days}일까지 조회할 수 있습니다.",
        )
    return ministry, topic, institution


@router.post("/search")
def search_topic_report(
    payload: TopicReportQueryPayload,
    response: Response,
    x_watch_token: str | None = Header(default=None),
) -> dict[str, object]:
    ministry, topic, institution = _clean(payload)
    try:
        with connect(get_settings().database_url) as connection:
            _subscriber(connection, x_watch_token)
            result = TopicReportRepository(connection).search(
                ministry=ministry, topic=topic,
                period_start=payload.period_start, period_end=payload.period_end,
                institution=institution,
                official_executive_items=_official_executive_items(),
            )
    except HTTPException:
        raise
    except Exception as exc:
        LOGGER.warning("topic report search failed: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="주제 관련 자료를 검색할 수 없습니다.") from exc
    response.headers["X-LLM-Calls"] = "0"
    return result


@router.post("")
def create_topic_report(
    payload: TopicReportQueryPayload,
    response: Response,
    x_watch_token: str | None = Header(default=None),
) -> dict[str, object]:
    settings = get_settings()
    if not settings.topic_reports_enabled:
        raise HTTPException(status_code=503, detail="주제별 보고서 기능이 비활성화되어 있습니다.")
    ministry, topic, institution = _clean(payload)
    model = settings.topic_report_model.strip() or settings.watch_llm_model.strip() or DEFAULT_MODEL
    try:
        with connect(settings.database_url) as connection:
            subscriber_id = _subscriber(connection, x_watch_token)
            delivery = WatchDeliveryRepository(connection)
            if not delivery.connected(subscriber_id):
                raise HTTPException(
                    status_code=403,
                    detail="주제별 보고서 작성은 카카오 연결 후 사용할 수 있습니다.",
                )
            repository = TopicReportRepository(connection)
            search = repository.search(
                ministry=ministry, topic=topic,
                period_start=payload.period_start, period_end=payload.period_end,
                institution=institution,
                official_executive_items=_official_executive_items(),
            )
            if not search["items"]:
                raise HTTPException(
                    status_code=404, detail="조건에 맞는 회의 근거를 찾지 못했습니다."
                )
            item = repository.create_or_cached(
                subscriber_id=subscriber_id, ministry=ministry, topic=topic,
                period_start=payload.period_start, period_end=payload.period_end,
                institution=institution, evidence=search["items"],
                provider="openrouter", model=model,
            )
    except HTTPException:
        raise
    except Exception as exc:
        LOGGER.warning("topic report creation failed: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="주제별 보고서 작성을 시작할 수 없습니다.") from exc
    response.headers["X-LLM-Calls"] = "0" if item["status"] == "READY" else "PENDING"
    return {**item, "search_summary": {
        "evidence_count": search["count"], "meeting_count": search["meeting_count"],
    }}


@router.get("")
def list_topic_reports(
    limit: int = 20,
    x_watch_token: str | None = Header(default=None),
) -> dict[str, object]:
    try:
        with connect(get_settings().database_url) as connection:
            subscriber_id = _subscriber(connection, x_watch_token)
            items = TopicReportRepository(connection).list(subscriber_id, limit=limit)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="주제별 보고서 목록을 불러올 수 없습니다.") from exc
    return {"items": items, "count": len(items)}


@router.get("/{report_id}")
def topic_report_detail(
    report_id: UUID,
    x_watch_token: str | None = Header(default=None),
) -> dict[str, object]:
    try:
        with connect(get_settings().database_url) as connection:
            subscriber_id = _subscriber(connection, x_watch_token)
            item = TopicReportRepository(connection).get(subscriber_id, report_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="주제별 보고서를 불러올 수 없습니다.") from exc
    if item is None:
        raise HTTPException(status_code=404, detail="주제별 보고서를 찾을 수 없습니다.")
    return item


@router.get("/{report_id}/report.md")
def topic_report_markdown(
    report_id: UUID,
    x_watch_token: str | None = Header(default=None),
) -> Response:
    try:
        with connect(get_settings().database_url) as connection:
            subscriber_id = _subscriber(connection, x_watch_token)
            repository = TopicReportRepository(connection)
            item = repository.get(subscriber_id, report_id)
            if item is None:
                raise HTTPException(status_code=404, detail="주제별 보고서를 찾을 수 없습니다.")
            if item["status"] != "READY":
                raise HTTPException(status_code=409, detail="보고서 작성이 아직 완료되지 않았습니다.")
            content = repository.markdown(item)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="보고서를 내려받을 수 없습니다.") from exc
    return Response(
        content=content, media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="topic-report-{report_id}.md"',
            "X-LLM-Calls": "0",
        },
    )
