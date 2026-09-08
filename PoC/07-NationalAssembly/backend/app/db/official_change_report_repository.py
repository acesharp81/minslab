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
    def _input_hash(snapshot: dict[str, Any]) -> str:
        """Hash only fields sent to the explanatory LLM.

        display_after and official evidence ids are deterministic presentation
        metadata.  Changing them must not spend another report request.
        """
        prompt_snapshot = {
            "meeting_title": snapshot.get("meeting_title"),
            "provisional_headline": snapshot.get("provisional_headline"),
            "official_headline": snapshot.get("official_headline"),
            "speaker_stats": snapshot.get("speaker_stats") or {},
            "changes": [{
                key: source.get(key)
                for key in (
                    "id", "entity_type", "operation", "field", "title",
                    "before", "after", "presentation_status",
                )
            } for source in snapshot.get("changes") or []],
        }
        encoded = json.dumps(
            prompt_snapshot, ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), default=str,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _rebind_report_changes(
        report: dict[str, Any], snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        rebound = json.loads(json.dumps(report, ensure_ascii=False, default=str))
        changes = {
            str(source.get("id")): source
            for source in snapshot.get("changes") or [] if source.get("id")
        }
        for item in rebound.get("items") or []:
            item["changes"] = [
                changes[change_id]
                for change_id in item.get("change_ids") or []
                if change_id in changes
            ]
        return rebound

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
        return integration_id, snapshot, OfficialChangeReportRepository._input_hash(
            snapshot,
        )

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
            reusable = self.connection.execute(
                """
                SELECT id, report
                FROM meeting_official_change_reports
                WHERE integration_id <> %s AND input_hash = %s
                  AND provider = %s AND model = %s AND prompt_version = %s
                  AND status = 'READY'
                ORDER BY generated_at DESC NULLS LAST, updated_at DESC, id DESC
                LIMIT 1
                """,
                (integration_id, input_hash, provider, model, prompt_version),
            ).fetchone()
            if not reusable:
                legacy_candidates = self.connection.execute(
                    """
                    SELECT id, report, input_snapshot
                    FROM meeting_official_change_reports
                    WHERE integration_id <> %s AND provider = %s AND model = %s
                      AND prompt_version = %s AND status = 'READY'
                    ORDER BY generated_at DESC NULLS LAST, updated_at DESC, id DESC
                    LIMIT 100
                    """,
                    (integration_id, provider, model, prompt_version),
                ).fetchall()
                reusable = next((
                    (report_id, report)
                    for report_id, report, prior_snapshot in legacy_candidates
                    if self._input_hash(prior_snapshot or {}) == input_hash
                ), None)
            if reusable:
                source_report_id, report = reusable
                report = self._rebind_report_changes(report or {}, snapshot)
                result = self.connection.execute(
                    """
                    INSERT INTO meeting_official_change_reports (
                        id, integration_id, input_hash, input_snapshot,
                        status, provider, model, prompt_version, report,
                        usage_metadata, generated_at
                    ) VALUES (
                        %s, %s, %s, %s, 'READY', %s, %s, %s, %s, %s, now()
                    )
                    ON CONFLICT (integration_id, provider, model, prompt_version)
                    DO UPDATE SET input_hash = EXCLUDED.input_hash,
                                  input_snapshot = EXCLUDED.input_snapshot,
                                  status = 'READY', report = EXCLUDED.report,
                                  usage_metadata = EXCLUDED.usage_metadata,
                                  last_error = NULL, lease_owner = NULL,
                                  lease_expires_at = NULL,
                                  attempt_count = 0, next_attempt_at = NULL,
                                  generated_at = now(), updated_at = now()
                    WHERE meeting_official_change_reports.input_hash
                              IS DISTINCT FROM EXCLUDED.input_hash
                       OR meeting_official_change_reports.status <> 'READY'
                    RETURNING id
                    """,
                    (
                        uuid.uuid4(), integration_id, input_hash, Jsonb(snapshot),
                        provider, model, prompt_version, Jsonb(report),
                        Jsonb({
                            "api_requests": 0,
                            "reuse_reason": "CROSS_INTEGRATION_INPUT_HASH",
                            "source_report_id": str(source_report_id),
                        }),
                    ),
                ).fetchone()
                changed += int(result is not None)
                continue
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
                              attempt_count = 0, next_attempt_at = NULL,
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
                lease_expires_at = now() + interval '5 minutes',
                attempt_count = attempt_count + 1, updated_at = now()
            WHERE report.id = (
                SELECT candidate.id
                FROM meeting_official_change_reports candidate
                WHERE (candidate.status = 'PENDING'
                       AND (candidate.next_attempt_at IS NULL
                            OR candidate.next_attempt_at <= now()))
                   OR (candidate.status = 'PROCESSING' AND candidate.lease_expires_at < now())
                   OR (candidate.status = 'FAILED' AND candidate.attempt_count < 3
                       AND candidate.next_attempt_at <= now())
                ORDER BY candidate.next_attempt_at NULLS FIRST,
                         candidate.created_at, candidate.id
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
                next_attempt_at = NULL, generated_at = now(), updated_at = now()
            WHERE id = %s
            """,
            (Jsonb(report), Jsonb(usage_metadata), report_id),
        )

    def fail(self, report_id: Any, error: str, *, limited: bool = False) -> None:
        self.connection.execute(
            """
            UPDATE meeting_official_change_reports
            SET status = CASE
                    WHEN %s THEN 'LIMIT_REACHED'
                    WHEN attempt_count < 3 THEN 'PENDING'
                    ELSE 'FAILED'
                END,
                last_error = %s,
                next_attempt_at = CASE
                    WHEN %s OR attempt_count >= 3 THEN NULL
                    ELSE now() + make_interval(
                    secs => LEAST(300, 15 * (2 ^ LEAST(attempt_count, 4)))
                ) END,
                lease_owner = NULL, lease_expires_at = NULL, updated_at = now()
            WHERE id = %s
            """,
            (limited, error[:120], limited, report_id),
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
