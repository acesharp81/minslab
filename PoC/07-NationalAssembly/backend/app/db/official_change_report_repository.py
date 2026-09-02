from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from psycopg.types.json import Jsonb


class OfficialChangeReportRepository:
    def __init__(self, connection: Any):
        self.connection = connection

    @staticmethod
    def _snapshot(row: Any) -> tuple[Any, dict[str, Any], str]:
        integration_id, meeting_title, provisional, integrated, changes, speaker_stats = row
        normalized_changes = []
        for index, source in enumerate(changes or []):
            change = dict(source) if isinstance(source, dict) else {}
            normalized_changes.append({
                "id": f"change-{index + 1}",
                "entity_type": str(change.get("entity_type") or ""),
                "operation": str(change.get("operation") or ""),
                "field": str(change.get("field") or ""),
                "title": str(change.get("title") or ""),
                "before": change.get("before"),
                "after": change.get("after"),
                "display_after": change.get("display_after"),
                "presentation_status": str(change.get("presentation_status") or ""),
                "official_utterance_ids": [
                    str(value) for value in change.get("official_utterance_ids") or []
                    if value
                ],
            })
        snapshot = {
            "meeting_title": str(meeting_title or ""),
            "provisional_headline": str((provisional or {}).get("headline") or ""),
            "official_headline": str((integrated or {}).get("headline") or ""),
            "changes": normalized_changes,
            "speaker_stats": dict(speaker_stats or {}),
        }
        encoded = json.dumps(
            snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        return integration_id, snapshot, hashlib.sha256(encoded).hexdigest()

    def sync_pending(
        self, *, provider: str, model: str, prompt_version: str, limit: int = 20,
    ) -> int:
        rows = self.connection.execute(
            """
            WITH latest AS (
                SELECT DISTINCT ON (integration.broadcast_id)
                       integration.id, integration.broadcast_id,
                       integration.meeting_brief_id,
                       integration.integrated_brief, integration.changes,
                       integration.speaker_stats
                FROM meeting_official_integrations integration
                WHERE integration.status = 'READY'
                ORDER BY integration.broadcast_id,
                         integration.generated_at DESC, integration.id DESC
            )
            SELECT latest.id, broadcast.title, brief.brief,
                   latest.integrated_brief, latest.changes, latest.speaker_stats
            FROM latest
            JOIN live_broadcasts broadcast ON broadcast.id = latest.broadcast_id
            JOIN meeting_briefs brief ON brief.id = latest.meeting_brief_id
            ORDER BY brief.generated_at DESC, latest.id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        changed = 0
        for row in rows:
            integration_id, snapshot, input_hash = self._snapshot(row)
            result = self.connection.execute(
                """
                INSERT INTO meeting_official_change_reports (
                    id, integration_id, input_hash, input_snapshot,
                    status, provider, model, prompt_version
                ) VALUES (%s, %s, %s, %s, 'PENDING', %s, %s, %s)
                ON CONFLICT (integration_id, provider, model, prompt_version)
                DO UPDATE SET input_hash = EXCLUDED.input_hash,
                              input_snapshot = EXCLUDED.input_snapshot,
                              status = 'PENDING', report = '{}'::jsonb,
                              usage_metadata = '{}'::jsonb, last_error = NULL,
                              lease_owner = NULL, lease_expires_at = NULL,
                              generated_at = NULL, updated_at = now()
                WHERE meeting_official_change_reports.input_hash
                      IS DISTINCT FROM EXCLUDED.input_hash
                RETURNING id
                """,
                (
                    uuid.uuid4(), integration_id, input_hash, Jsonb(snapshot),
                    provider, model, prompt_version,
                ),
            ).fetchone()
            changed += int(result is not None)
        return changed

    def claim(self, worker_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            UPDATE meeting_official_change_reports report
            SET status = 'PROCESSING', lease_owner = %s,
                lease_expires_at = now() + interval '5 minutes', updated_at = now()
            WHERE report.id = (
                SELECT candidate.id
                FROM meeting_official_change_reports candidate
                WHERE candidate.status = 'PENDING'
                   OR (candidate.status = 'PROCESSING' AND candidate.lease_expires_at < now())
                ORDER BY candidate.created_at, candidate.id
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            )
            RETURNING report.id, report.integration_id, report.input_snapshot,
                      report.provider, report.model, report.prompt_version
            """,
            (worker_id,),
        ).fetchone()
        if not row:
            return None
        columns = (
            "report_id", "integration_id", "input_snapshot",
            "provider", "model", "prompt_version",
        )
        return dict(zip(columns, row, strict=True))

    def reserve_daily(self, limit: int) -> int | None:
        row = self.connection.execute(
            """
            INSERT INTO official_change_report_daily_usage (
                usage_date, request_count
            ) VALUES (CURRENT_DATE, 1)
            ON CONFLICT (usage_date)
            DO UPDATE SET request_count = official_change_report_daily_usage.request_count + 1,
                          updated_at = now()
            WHERE official_change_report_daily_usage.request_count < %s
            RETURNING request_count
            """,
            (limit,),
        ).fetchone()
        return int(row[0]) if row else None

    def complete(
        self, report_id: Any, *, report: dict[str, Any], usage_metadata: dict[str, Any],
    ) -> None:
        self.connection.execute(
            """
            UPDATE meeting_official_change_reports
            SET status = 'READY', report = %s, usage_metadata = %s,
                last_error = NULL, lease_owner = NULL, lease_expires_at = NULL,
                generated_at = now(), updated_at = now()
            WHERE id = %s
            """,
            (Jsonb(report), Jsonb(usage_metadata), report_id),
        )

    def fail(self, report_id: Any, error: str, *, limited: bool = False) -> None:
        self.connection.execute(
            """
            UPDATE meeting_official_change_reports
            SET status = %s, last_error = %s,
                lease_owner = NULL, lease_expires_at = NULL, updated_at = now()
            WHERE id = %s
            """,
            ("LIMIT_REACHED" if limited else "FAILED", error[:120], report_id),
        )

    def latest(self, integration_id: Any) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            SELECT id, integration_id, status, provider, model, prompt_version,
                   report, usage_metadata, last_error, generated_at, updated_at
            FROM meeting_official_change_reports
            WHERE integration_id = %s
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            (integration_id,),
        ).fetchone()
        if not row:
            return None
        columns = (
            "report_id", "integration_id", "status", "provider", "model",
            "prompt_version", "report", "usage_metadata", "last_error",
            "generated_at", "updated_at",
        )
        return dict(zip(columns, row, strict=True))
