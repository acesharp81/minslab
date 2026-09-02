from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import date, datetime, timezone
from typing import Any

from psycopg.types.json import Jsonb

from ..services.official_brief_integration import semantic_tokens


PROMPT_VERSION = "topic-report/1.5"


def _normalized(value: object) -> str:
    return " ".join(str(value or "").casefold().split())


def _has_topic_relevance(
    query_tokens: set[str], haystack_tokens: set[str], exact_topic: bool,
) -> bool:
    """Ministry is a filter; only the requested topic can establish relevance."""
    return bool(exact_topic or (query_tokens & haystack_tokens))


def _evidence_hash(items: list[dict[str, Any]]) -> str:
    payload = json.dumps(items, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _query_hash(
    ministry: str, topic: str, period_start: date, period_end: date,
    institution: str | None,
) -> str:
    payload = "\f".join((
        _normalized(ministry), _normalized(topic), period_start.isoformat(),
        period_end.isoformat(), institution or "",
    ))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _topic_mention_count(
    topic: dict[str, Any], linked_tasks: list[dict[str, Any]],
) -> int:
    """Count unique persisted utterance groups supporting one topic."""
    evidence_ids = {
        str(value) for value in topic.get("evidence_ids") or [] if value
    }
    for point in topic.get("speaker_points") or []:
        if not isinstance(point, dict):
            continue
        evidence_ids.update(
            str(value) for value in point.get("evidence_ids") or [] if value
        )
    for task in linked_tasks:
        evidence_ids.update(
            str(value) for value in task.get("evidence_ids") or [] if value
        )
    return max(1, len(evidence_ids))


def _official_executive_evidence(
    items: list[dict[str, Any]], *, broadcast_ids: dict[str, str],
    ministry: str, topic: str, period_start: date, period_end: date,
) -> list[dict[str, Any]]:
    """Convert official State Council material into topic-report evidence."""
    query_tokens = semantic_tokens(topic)
    ministry_tokens = semantic_tokens(ministry)
    normalized_topic = _normalized(topic)
    normalized_ministry = _normalized(ministry)
    evidence: list[dict[str, Any]] = []
    for meeting in items:
        raw_date = str(meeting.get("published_date") or "").replace(".", "-")
        try:
            meeting_date = date.fromisoformat(raw_date)
        except ValueError:
            continue
        if not period_start <= meeting_date <= period_end:
            continue
        news_id = str(meeting.get("news_id") or meeting.get("meeting_number") or "")
        meeting_title = str(meeting.get("title") or "국무회의 공식 결과")
        meeting_at = datetime.combine(
            meeting_date, datetime.min.time(), tzinfo=timezone.utc,
        ).isoformat()
        broadcast_id = broadcast_ids.get(news_id) or f"executive-{news_id}"
        for index, agenda in enumerate(meeting.get("agendas") or []):
            if not isinstance(agenda, dict):
                continue
            title = " ".join(str(agenda.get("topic") or "").split())
            summary_parts = [
                agenda.get("discussion_summary") or agenda.get("summary") or "",
            ]
            guidance = [
                row for row in agenda.get("presidential_guidance") or []
                if isinstance(row, dict)
            ]
            briefings = [
                row for row in agenda.get("related_ministry_briefings") or []
                if isinstance(row, dict)
            ]
            summary_parts.extend(row.get("text") or "" for row in guidance)
            summary_parts.extend(
                f"{row.get('title') or ''} {row.get('summary') or ''}"
                for row in briefings
            )
            summary = " ".join(
                " ".join(str(value).split()) for value in summary_parts if value
            )
            ministries = list(dict.fromkeys(
                str(value).strip()
                for value in (
                    list(agenda.get("ministries") or [])
                    + [
                        target for row in guidance
                        for target in row.get("target_ministries") or []
                    ]
                    + [row.get("ministry") for row in briefings]
                )
                if str(value or "").strip()
            ))
            haystack = " ".join((meeting_title, title, summary, " ".join(ministries)))
            haystack_normalized = _normalized(haystack)
            haystack_tokens = semantic_tokens(haystack)
            topic_overlap = len(query_tokens & haystack_tokens) / max(1, len(query_tokens))
            ministry_overlap = len(ministry_tokens & haystack_tokens) / max(1, len(ministry_tokens))
            exact_topic = bool(normalized_topic and normalized_topic in haystack_normalized)
            exact_ministry = bool(
                normalized_ministry and normalized_ministry in haystack_normalized
            )
            if normalized_topic and not _has_topic_relevance(
                query_tokens, haystack_tokens, exact_topic,
            ):
                continue
            score = round(
                topic_overlap * 0.55 + ministry_overlap * 0.25
                + (0.15 if exact_topic else 0.0)
                + (0.05 if exact_ministry else 0.0),
                4,
            )
            if score <= 0 or (
                normalized_ministry and not (ministry_overlap or exact_ministry)
            ):
                continue
            source_span_id = str(agenda.get("source_span_id") or f"agenda-{index + 1}")
            evidence.append({
                "id": f"executive-official:{news_id}:{source_span_id}",
                "broadcast_id": broadcast_id,
                "meeting_title": meeting_title,
                "meeting_at": meeting_at,
                "institution": "EXECUTIVE",
                "committee_name": "국무회의",
                "authority_status": "OFFICIAL_SOURCE",
                "topic_title": title,
                "summary": summary,
                "ministries": ministries,
                "tasks": [{
                    "title": " ".join(str(row.get("text") or "").split()),
                    "status": "OFFICIAL",
                    "ministries": list(row.get("target_ministries") or ministries),
                } for row in guidance[:8]],
                "mention_count": 1,
                "mention_basis": "OFFICIAL_ITEM",
                "score": score,
                "source_url": meeting.get("source_url"),
            })
    return evidence


class TopicReportRepository:
    def __init__(self, connection: Any):
        self.connection = connection

    def search(
        self, *, ministry: str, topic: str, period_start: date,
        period_end: date, institution: str | None = None, limit: int = 40,
        official_executive_items: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        rows = self.connection.execute(
            """
            SELECT broadcast.id, COALESCE(broadcast.title, '회의 제목 미확인'),
                   broadcast.institution, broadcast.committee_name,
                   COALESCE(broadcast.ended_at, broadcast.detected_at),
                   brief.brief,
                   COALESCE(integration.integrated_brief, '{}'::jsonb),
                   integration.status
            FROM live_broadcasts broadcast
            JOIN LATERAL (
                SELECT meeting_brief.brief
                FROM meeting_briefs meeting_brief
                WHERE meeting_brief.broadcast_id = broadcast.id
                ORDER BY (meeting_brief.provider = 'mistral') DESC,
                         meeting_brief.generated_at DESC, meeting_brief.id DESC
                LIMIT 1
            ) brief ON true
            LEFT JOIN LATERAL (
                SELECT item.integrated_brief, item.status
                FROM meeting_official_integrations item
                WHERE item.broadcast_id = broadcast.id AND item.status = 'READY'
                ORDER BY item.generated_at DESC, item.id DESC LIMIT 1
            ) integration ON true
            WHERE COALESCE(broadcast.ended_at, broadcast.detected_at)::date
                  BETWEEN %s AND %s
              AND broadcast.source_system NOT IN ('poc07.demo', 'poc07.test')
              AND (%s::text IS NULL OR broadcast.institution = %s)
            ORDER BY COALESCE(broadcast.ended_at, broadcast.detected_at) DESC
            """,
            (period_start, period_end, institution, institution),
        ).fetchall()
        query_tokens = semantic_tokens(topic)
        ministry_tokens = semantic_tokens(ministry)
        normalized_topic = _normalized(topic)
        normalized_ministry = _normalized(ministry)
        evidence: list[dict[str, Any]] = []
        meeting_count = 0
        for row in rows:
            (
                broadcast_id, meeting_title, source_institution, committee_name,
                meeting_at, provisional_brief, integrated_brief, integration_status,
            ) = row
            selected = (
                dict(integrated_brief)
                if integration_status == "READY" and integrated_brief
                else dict(provisional_brief or {})
            )
            authority = "OFFICIAL_INTEGRATED" if integration_status == "READY" else "PROVISIONAL"
            tasks = [item for item in selected.get("tasks", []) if isinstance(item, dict)]
            topics = [item for item in selected.get("topics", []) if isinstance(item, dict)]
            matched_meeting = False
            for index, item in enumerate(topics):
                topic_id = str(item.get("id") or f"topic-{index + 1}")
                linked_tasks = [
                    task for task in tasks
                    if str(task.get("topic_id") or "") == topic_id
                ]
                ministries = list(dict.fromkeys(
                    str(value).strip()
                    for value in (
                        list(item.get("ministries") or [])
                        + [owner for task in linked_tasks for owner in task.get("ministries") or []]
                    )
                    if str(value).strip()
                ))
                title = " ".join(str(item.get("title") or "").split())
                summary = " ".join(str(item.get("summary") or "").split())
                task_text = " ".join(
                    " ".join(str(task.get("title") or "").split())
                    for task in linked_tasks
                )
                haystack = " ".join((
                    meeting_title, committee_name or "", title, summary,
                    task_text, " ".join(ministries),
                ))
                haystack_normalized = _normalized(haystack)
                haystack_tokens = semantic_tokens(haystack)
                topic_overlap = len(query_tokens & haystack_tokens) / max(1, len(query_tokens))
                ministry_overlap = len(ministry_tokens & haystack_tokens) / max(1, len(ministry_tokens))
                exact_topic = bool(normalized_topic and normalized_topic in haystack_normalized)
                exact_ministry = bool(
                    normalized_ministry and normalized_ministry in haystack_normalized
                )
                if normalized_topic and not _has_topic_relevance(
                    query_tokens, haystack_tokens, exact_topic
                ):
                    continue
                score = round(
                    topic_overlap * 0.55 + ministry_overlap * 0.25
                    + (0.15 if exact_topic else 0.0)
                    + (0.05 if exact_ministry else 0.0),
                    4,
                )
                if score <= 0 or (
                    normalized_ministry and not (ministry_overlap or exact_ministry)
                ):
                    continue
                matched_meeting = True
                evidence.append({
                    "id": f"{broadcast_id}:{topic_id}",
                    "broadcast_id": str(broadcast_id),
                    "meeting_title": str(meeting_title),
                    "meeting_at": meeting_at.isoformat(),
                    "institution": source_institution,
                    "committee_name": committee_name,
                    "authority_status": authority,
                    "topic_title": title,
                    "summary": summary,
                    "ministries": ministries,
                    "tasks": [{
                        "title": " ".join(str(task.get("title") or "").split()),
                        "status": str(task.get("status") or "CANDIDATE"),
                        "ministries": list(task.get("ministries") or []),
                    } for task in linked_tasks[:8]],
                    "mention_count": _topic_mention_count(item, linked_tasks),
                    "mention_basis": "UNIQUE_UTTERANCE_EVIDENCE",
                    "score": score,
                })
            meeting_count += int(matched_meeting)
        if institution in (None, "EXECUTIVE") and official_executive_items:
            match_rows = self.connection.execute(
                """
                SELECT official_briefing_id, broadcast_id
                FROM executive_official_matches
                WHERE meeting_date BETWEEN %s AND %s
                """,
                (period_start, period_end),
            ).fetchall()
            broadcast_ids = {
                str(official_id): str(broadcast_id)
                for official_id, broadcast_id in match_rows
            }
            evidence.extend(_official_executive_evidence(
                official_executive_items, broadcast_ids=broadcast_ids,
                ministry=ministry, topic=topic,
                period_start=period_start, period_end=period_end,
            ))
        evidence.sort(key=lambda item: (item["score"], item["meeting_at"]), reverse=True)
        evidence = evidence[: max(1, min(limit, 80))]
        meeting_count = len({item["broadcast_id"] for item in evidence})
        return {
            "items": evidence,
            "count": len(evidence),
            "meeting_count": meeting_count,
            "evidence_set_hash": _evidence_hash(evidence),
            "search_method": "STRUCTURED_OFFICIAL_EXECUTIVE_SEMANTIC_TOKEN_RANKING_V4",
            "llm_calls": 0,
        }

    def create_or_cached(
        self, *, subscriber_id: uuid.UUID, ministry: str, topic: str,
        period_start: date, period_end: date, institution: str | None,
        evidence: list[dict[str, Any]], provider: str, model: str,
    ) -> dict[str, Any]:
        query_hash = _query_hash(ministry, topic, period_start, period_end, institution)
        evidence_set_hash = _evidence_hash(evidence)
        row = self.connection.execute(
            """
            INSERT INTO topic_reports (
                id, subscriber_id, ministry, topic, period_start, period_end,
                institution, query_hash, evidence_set_hash, evidence,
                provider, model, prompt_version
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (
                subscriber_id, query_hash, evidence_set_hash,
                provider, model, prompt_version
            ) DO UPDATE SET
                status = CASE
                    WHEN topic_reports.status IN ('FAILED', 'LIMIT_REACHED')
                    THEN 'PENDING' ELSE topic_reports.status
                END,
                last_error = CASE
                    WHEN topic_reports.status IN ('FAILED', 'LIMIT_REACHED')
                    THEN NULL ELSE topic_reports.last_error
                END,
                updated_at = CASE
                    WHEN topic_reports.status IN ('FAILED', 'LIMIT_REACHED')
                    THEN now() ELSE topic_reports.updated_at
                END
            RETURNING id, subscriber_id, ministry, topic, period_start, period_end,
                      institution, status, provider, model, prompt_version, report,
                      evidence, usage_metadata, last_error, generated_at,
                      created_at, updated_at
            """,
            (
                uuid.uuid4(), subscriber_id, ministry, topic, period_start,
                period_end, institution, query_hash, evidence_set_hash,
                Jsonb(evidence), provider, model, PROMPT_VERSION,
            ),
        ).fetchone()
        return self._row(row)

    def reserve_user_daily(
        self, report_id: uuid.UUID, subscriber_id: uuid.UUID, limit: int,
    ) -> int | None:
        report = self.connection.execute(
            """
            SELECT quota_reserved_at
            FROM topic_reports
            WHERE id = %s AND subscriber_id = %s
            FOR UPDATE
            """,
            (report_id, subscriber_id),
        ).fetchone()
        if report is None:
            return None
        if report[0] is not None:
            return 0
        row = self.connection.execute(
            """
            INSERT INTO topic_report_daily_usage (
                subscriber_id, usage_date, request_count
            ) VALUES (%s, timezone('UTC', now())::date, 1)
            ON CONFLICT (subscriber_id, usage_date) DO UPDATE
            SET request_count = topic_report_daily_usage.request_count + 1,
                updated_at = now()
            WHERE topic_report_daily_usage.request_count < %s
            RETURNING request_count
            """,
            (subscriber_id, limit),
        ).fetchone()
        if row is None:
            return None
        self.connection.execute(
            """
            UPDATE topic_reports
            SET quota_reserved_at = now(), updated_at = now()
            WHERE id = %s AND quota_reserved_at IS NULL
            """,
            (report_id,),
        )
        return int(row[0])

    def reserve_global_daily(self, limit: int) -> int | None:
        row = self.connection.execute(
            """
            INSERT INTO topic_report_global_daily_usage (usage_date, request_count)
            VALUES (timezone('UTC', now())::date, 1)
            ON CONFLICT (usage_date) DO UPDATE
            SET request_count = topic_report_global_daily_usage.request_count + 1,
                updated_at = now()
            WHERE topic_report_global_daily_usage.request_count < %s
            RETURNING request_count
            """,
            (limit,),
        ).fetchone()
        return int(row[0]) if row else None

    def claim(self, worker_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            WITH candidate AS (
                SELECT id FROM topic_reports
                WHERE status IN ('PENDING', 'PROCESSING')
                  AND (lease_expires_at IS NULL OR lease_expires_at < now())
                ORDER BY created_at
                FOR UPDATE SKIP LOCKED LIMIT 1
            )
            UPDATE topic_reports report
            SET status = 'PROCESSING', lease_owner = %s,
                lease_expires_at = now() + interval '3 minutes', updated_at = now()
            FROM candidate WHERE report.id = candidate.id
            RETURNING report.id, report.subscriber_id, report.ministry,
                      report.topic, report.period_start, report.period_end,
                      report.institution, report.status, report.provider,
                      report.model, report.prompt_version, report.report,
                      report.evidence, report.usage_metadata, report.last_error,
                      report.generated_at, report.created_at, report.updated_at
            """,
            (worker_id,),
        ).fetchone()
        return self._row(row) if row else None

    def complete(
        self, report_id: uuid.UUID, *, report: dict[str, Any],
        usage_metadata: dict[str, Any],
    ) -> None:
        self.connection.execute(
            """
            UPDATE topic_reports
            SET status = 'READY', report = %s, usage_metadata = %s,
                generated_at = now(), lease_owner = NULL,
                lease_expires_at = NULL, last_error = NULL, updated_at = now()
            WHERE id = %s
            """,
            (Jsonb(report), Jsonb(usage_metadata), report_id),
        )

    def fail(self, report_id: uuid.UUID, error: str, *, limited: bool = False) -> None:
        self.connection.execute(
            """
            UPDATE topic_reports
            SET status = %s, last_error = %s, lease_owner = NULL,
                lease_expires_at = NULL, updated_at = now()
            WHERE id = %s
            """,
            ("LIMIT_REACHED" if limited else "FAILED", error[:240], report_id),
        )

    def get(self, subscriber_id: uuid.UUID, report_id: uuid.UUID) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            SELECT id, subscriber_id, ministry, topic, period_start, period_end,
                   institution, status, provider, model, prompt_version, report,
                   evidence, usage_metadata, last_error, generated_at,
                   created_at, updated_at
            FROM topic_reports WHERE id = %s AND subscriber_id = %s
            """,
            (report_id, subscriber_id),
        ).fetchone()
        return self._row(row) if row else None

    def list(self, subscriber_id: uuid.UUID, limit: int = 20) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT id, subscriber_id, ministry, topic, period_start, period_end,
                   institution, status, provider, model, prompt_version, report,
                   evidence, usage_metadata, last_error, generated_at,
                   created_at, updated_at
            FROM topic_reports WHERE subscriber_id = %s
            ORDER BY created_at DESC LIMIT %s
            """,
            (subscriber_id, max(1, min(limit, 50))),
        ).fetchall()
        return [self._row(row) for row in rows]

    @staticmethod
    def markdown(item: dict[str, Any]) -> str:
        report = item.get("report") or {}
        scope = item.get("topic") or item.get("ministry") or "정책"
        lines = [f"# {report.get('title') or scope + ' 보고서'}", ""]
        if item.get("ministry"):
            lines.append(f"- 소관 부처: {item['ministry']}")
        if item.get("topic"):
            lines.append(f"- 주제: {item['topic']}")
        lines += [
            f"- 기간: {item['period_start']} ~ {item['period_end']}",
            f"- 작성 모델: {item['provider']} / {item['model']}", "",
            "## 핵심 요약", "", str(report.get("executive_summary") or ""), "",
        ]
        implications = report.get("policy_implications") or []
        if implications:
            lines += ["## 정책적 시사점", ""]
            for index, implication in enumerate(implications, 1):
                lines += [
                    f"### {index}. {implication.get('title') or '정책적 시사점'}", "",
                    str(implication.get("body") or ""), "",
                ]
        evidence_by_id = {
            str(source.get("id")): source
            for source in item.get("evidence") or [] if source.get("id")
        }
        for section in report.get("sections") or []:
            section_ids = {str(value) for value in section.get("evidence_ids") or []}
            ministries = list(section.get("ministries") or [])
            for evidence_id in section_ids:
                source = evidence_by_id.get(evidence_id) or {}
                ministries.extend(source.get("ministries") or [])
            for task in report.get("tasks") or []:
                if section_ids & {str(value) for value in task.get("evidence_ids") or []}:
                    ministries.extend(task.get("ministries") or [])
            ministries = list(dict.fromkeys(str(value).strip() for value in ministries if str(value).strip()))[:4]
            owners = " ".join(f"[{value}]" for value in ministries)
            heading = section.get("heading") or "주요 내용"
            lines += [f"## {owners + ' ' if owners else ''}{heading}", "", str(section.get("body") or ""), ""]
        tasks = report.get("tasks") or []
        if tasks:
            lines += ["## 도출 과제", ""]
            for task in tasks:
                owners = ", ".join(task.get("ministries") or [])
                lines.append(f"- {task.get('title')}" + (f" ({owners})" if owners else ""))
            lines.append("")
        lines += ["## 근거 회의", ""]
        for evidence in item.get("evidence") or []:
            lines.append(
                f"- {str(evidence.get('meeting_at') or '')[:10]} · "
                f"{evidence.get('meeting_title')} · {evidence.get('topic_title')}"
            )
        return "\n".join(lines).strip() + "\n"

    @staticmethod
    def _row(row: Any) -> dict[str, Any]:
        columns = (
            "report_id", "subscriber_id", "ministry", "topic",
            "period_start", "period_end", "institution", "status",
            "provider", "model", "prompt_version", "report", "evidence",
            "usage_metadata", "last_error", "generated_at", "created_at",
            "updated_at",
        )
        return dict(zip(columns, row, strict=True))
