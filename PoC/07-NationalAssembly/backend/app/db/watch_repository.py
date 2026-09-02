from __future__ import annotations

import hashlib
import re
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Any

from psycopg.types.json import Jsonb

from ..services.watch_matcher import match_watch_rule, normalize_watch_text
from ..services.transcript_presentation import (
    group_transcript_segments,
    summarize_utterance,
)

NOTIFICATION_RETENTION_LIMIT = 50


def normalize_watch_briefing_presentation(
    summary: str | None, claims: object,
) -> tuple[str, list[dict[str, Any]]]:
    """Apply deterministic display-only corrections without changing evidence."""
    def normalize(value: object) -> str:
        text = re.sub(r"(?<=[가-힣])各", " 각", str(value or ""))
        text = re.sub(r"各\s*기관", "각 기관", text)
        return text.replace("各", "각")

    normalized_summary = normalize(summary)
    normalized_claims: list[dict[str, Any]] = []
    for raw_claim in claims if isinstance(claims, list) else []:
        if not isinstance(raw_claim, dict):
            continue
        claim = dict(raw_claim)
        claim["title"] = normalize(claim.get("title"))
        claim["text"] = normalize(claim.get("text"))
        normalized_claims.append(claim)
    return normalized_summary, normalized_claims


def watch_key_sentence(excerpt: str, matched_term: str, *, max_chars: int = 220) -> str:
    """Return one readable evidence phrase without pretending it is an AI summary."""
    text = " ".join(str(excerpt or "").split())
    if len(text) <= max_chars:
        return text
    term = " ".join(str(matched_term or "").split())
    index = text.casefold().find(term.casefold()) if term else -1
    if index < 0:
        return summarize_utterance(text, max_chars=max_chars)
    left = max(0, index - max_chars // 2)
    right = min(len(text), left + max_chars)
    left = max(0, right - max_chars)
    phrase = text[left:right].strip()
    return ("…" if left else "") + phrase + ("…" if right < len(text) else "")


def build_watch_fallback_summary(
    matches: list[dict[str, Any]], *, limit: int = 5,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for match in matches:
        phrase = watch_key_sentence(match.get("excerpt") or "", match.get("matched_term") or "")
        normalized = normalize_watch_text(phrase)
        if not phrase or normalized in seen:
            continue
        seen.add(normalized)
        items.append({
            "speaker_label": str(match.get("speaker_label") or "화자 확인 중"),
            "summary": phrase,
            "summary_kind": "KEY_SENTENCE_FALLBACK",
            "match_id": match.get("match_id"),
        })
        if len(items) >= limit:
            break
    return items


class WatchRepository:
    def __init__(self, connection: Any):
        self.connection = connection

    @staticmethod
    def token_hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def create_subscriber(self) -> tuple[uuid.UUID, str]:
        token = secrets.token_urlsafe(32)
        subscriber_id = uuid.uuid4()
        self.connection.execute(
            "INSERT INTO watch_subscribers (id, token_hash) VALUES (%s, %s)",
            (subscriber_id, self.token_hash(token)),
        )
        return subscriber_id, token

    def subscriber_for_token(self, token: str | None) -> uuid.UUID | None:
        if not token or len(token) > 200:
            return None
        token_hash = self.token_hash(token)
        session = self.connection.execute(
            """
            UPDATE watch_web_sessions SET last_seen_at = now()
            WHERE token_hash = %s AND revoked_at IS NULL AND expires_at > now()
            RETURNING subscriber_id
            """,
            (token_hash,),
        ).fetchone()
        if session:
            return session[0]
        row = self.connection.execute(
            """
            UPDATE watch_subscribers SET last_seen_at = now()
            WHERE token_hash = %s RETURNING id
            """,
            (token_hash,),
        ).fetchone()
        return row[0] if row else None

    def list_rules(self, subscriber_id: uuid.UUID) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT id, name, include_terms, exclude_terms, institution,
                   committee_name, notification_policy, cooldown_minutes,
                   digest_enabled, kakao_enabled, enabled, starts_at, current_revision,
                   created_at, updated_at
            FROM watch_rules WHERE subscriber_id = %s AND archived_at IS NULL
            ORDER BY enabled DESC, created_at DESC
            """,
            (subscriber_id,),
        ).fetchall()
        columns = (
            "rule_id", "name", "include_terms", "exclude_terms", "institution",
            "committee_name", "notification_policy", "cooldown_minutes",
            "digest_enabled", "kakao_enabled", "enabled", "starts_at", "current_revision",
            "created_at", "updated_at",
        )
        return [dict(zip(columns, row, strict=True)) for row in rows]

    def create_rule(
        self,
        subscriber_id: uuid.UUID,
        *,
        name: str,
        include_terms: list[str],
        exclude_terms: list[str],
        institution: str | None,
        committee_name: str | None,
        notification_policy: str,
        cooldown_minutes: int = 10,
        digest_enabled: bool = False,
        kakao_enabled: bool = False,
    ) -> dict[str, Any]:
        active_count = self.connection.execute(
            "SELECT COUNT(*) FROM watch_rules WHERE subscriber_id = %s AND archived_at IS NULL",
            (subscriber_id,),
        ).fetchone()[0]
        if active_count >= 20:
            raise ValueError("알림 주제는 브라우저당 최대 20개까지 저장할 수 있습니다.")
        row = self.connection.execute(
            """
            INSERT INTO watch_rules (
                id, subscriber_id, name, include_terms, exclude_terms,
                institution, committee_name, notification_policy,
                cooldown_minutes, digest_enabled, kakao_enabled
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, name, include_terms, exclude_terms, institution,
                      committee_name, notification_policy, cooldown_minutes,
                      digest_enabled, kakao_enabled, enabled, starts_at, current_revision,
                      created_at, updated_at
            """,
            (
                uuid.uuid4(), subscriber_id, name, include_terms, exclude_terms,
                institution, committee_name, notification_policy,
                cooldown_minutes, digest_enabled, kakao_enabled,
            ),
        ).fetchone()
        item = dict(zip(
            (
                "rule_id", "name", "include_terms", "exclude_terms", "institution",
                "committee_name", "notification_policy", "cooldown_minutes",
                "digest_enabled", "kakao_enabled", "enabled", "starts_at", "current_revision",
                "created_at", "updated_at",
            ),
            row,
            strict=True,
        ))
        self._save_rule_revision(item)
        return item

    def update_rule(
        self, subscriber_id: uuid.UUID, rule_id: uuid.UUID, **values: Any,
    ) -> dict[str, Any] | None:
        allowed = {
            "name", "include_terms", "exclude_terms", "institution",
            "committee_name", "notification_policy", "cooldown_minutes",
            "digest_enabled", "kakao_enabled", "enabled",
        }
        assignments: list[str] = []
        parameters: list[Any] = []
        for key, value in values.items():
            if key in allowed:
                assignments.append(f"{key} = %s")
                parameters.append(value)
        if not assignments:
            rows = self.list_rules(subscriber_id)
            return next((item for item in rows if item["rule_id"] == rule_id), None)
        assignments.extend((
            "current_revision = current_revision + 1",
            "starts_at = now()",
            "updated_at = now()",
        ))
        parameters.extend((rule_id, subscriber_id))
        row = self.connection.execute(
            f"""
            UPDATE watch_rules SET {', '.join(assignments)}
            WHERE id = %s AND subscriber_id = %s
            RETURNING id, name, include_terms, exclude_terms, institution,
                      committee_name, notification_policy, cooldown_minutes,
                      digest_enabled, kakao_enabled, enabled, starts_at, current_revision,
                      created_at, updated_at
            """,
            parameters,
        ).fetchone()
        if not row:
            return None
        item = dict(zip(
            (
                "rule_id", "name", "include_terms", "exclude_terms", "institution",
                "committee_name", "notification_policy", "cooldown_minutes",
                "digest_enabled", "kakao_enabled", "enabled", "starts_at", "current_revision",
                "created_at", "updated_at",
            ),
            row,
            strict=True,
        ))
        self._save_rule_revision(item)
        return item

    def _save_rule_revision(self, rule: dict[str, Any]) -> None:
        configuration = {
            key: rule.get(key) for key in (
                "name", "include_terms", "exclude_terms", "institution",
                "committee_name", "notification_policy", "cooldown_minutes",
                "digest_enabled", "kakao_enabled", "enabled",
            )
        }
        self.connection.execute(
            """
            INSERT INTO watch_rule_revisions (
                id, rule_id, revision, effective_at, configuration
            ) VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (rule_id, revision) DO NOTHING
            """,
            (
                uuid.uuid4(), rule["rule_id"], rule["current_revision"],
                rule["starts_at"], Jsonb(configuration),
            ),
        )

    def delete_rule(self, subscriber_id: uuid.UUID, rule_id: uuid.UUID) -> bool:
        archived = self.connection.execute(
            """
            UPDATE watch_rules SET enabled = false, archived_at = now(), updated_at = now()
            WHERE id = %s AND subscriber_id = %s AND archived_at IS NULL RETURNING id
            """,
            (rule_id, subscriber_id),
        ).fetchone()
        if not archived:
            return False
        self.connection.execute(
            "DELETE FROM watch_sessions WHERE rule_id = %s AND subscriber_id = %s",
            (rule_id, subscriber_id),
        )
        self.connection.execute(
            "DELETE FROM watch_detection_events WHERE rule_id = %s AND subscriber_id = %s",
            (rule_id, subscriber_id),
        )
        return True

    def list_notifications(
        self, subscriber_id: uuid.UUID, *, limit: int = 50,
    ) -> dict[str, Any]:
        rows = self.connection.execute(
            """
            SELECT notification.id, notification.title, notification.body,
                   notification.is_test, notification.read_at,
                   notification.created_at, notification.session_id,
                   event.matched_term, event.excerpt, event.speaker_label,
                   notification.notification_type,
                   broadcast.title, broadcast.institution, broadcast.lifecycle_status
            FROM watch_notifications notification
            LEFT JOIN watch_detection_events event ON event.id = notification.detection_event_id
            JOIN watch_sessions session ON session.id = notification.session_id
            JOIN live_broadcasts broadcast ON broadcast.id = session.broadcast_id
            WHERE notification.subscriber_id = %s
            ORDER BY notification.created_at DESC LIMIT %s
            """,
            (subscriber_id, limit),
        ).fetchall()
        columns = (
            "notification_id", "title", "body", "is_test", "read_at", "created_at",
            "session_id", "matched_term", "excerpt", "speaker_label",
            "notification_type", "meeting_title", "institution", "lifecycle_status",
        )
        items = [dict(zip(columns, row, strict=True)) for row in rows]
        unread = self.connection.execute(
            "SELECT COUNT(*) FROM watch_notifications WHERE subscriber_id = %s AND read_at IS NULL",
            (subscriber_id,),
        ).fetchone()[0]
        return {"items": items, "count": len(items), "unread_count": unread}

    def mark_notification_read(
        self, subscriber_id: uuid.UUID, notification_id: uuid.UUID,
    ) -> bool:
        return self.connection.execute(
            """
            UPDATE watch_notifications SET read_at = COALESCE(read_at, now())
            WHERE id = %s AND subscriber_id = %s RETURNING id
            """,
            (notification_id, subscriber_id),
        ).fetchone() is not None

    def delete_notification(
        self, subscriber_id: uuid.UUID, notification_id: uuid.UUID,
    ) -> bool:
        row = self.connection.execute(
            """
            DELETE FROM watch_notifications
            WHERE id = %s AND subscriber_id = %s
            RETURNING session_id
            """,
            (notification_id, subscriber_id),
        ).fetchone()
        if not row:
            return False
        self._remove_empty_notification_sessions(subscriber_id, [row[0]])
        return True

    def clear_read_notifications(self, subscriber_id: uuid.UUID) -> int:
        rows = self.connection.execute(
            """
            DELETE FROM watch_notifications
            WHERE subscriber_id = %s AND read_at IS NOT NULL
            RETURNING session_id
            """,
            (subscriber_id,),
        ).fetchall()
        self._remove_empty_notification_sessions(
            subscriber_id, [row[0] for row in rows],
        )
        return len(rows)

    def prune_notification_history(
        self,
        subscriber_id: uuid.UUID,
        *,
        keep: int = NOTIFICATION_RETENTION_LIMIT,
    ) -> int:
        rows = self.connection.execute(
            """
            DELETE FROM watch_notifications notification
            WHERE notification.subscriber_id = %s
              AND notification.id IN (
                SELECT stale.id
                FROM watch_notifications stale
                WHERE stale.subscriber_id = %s
                ORDER BY stale.created_at DESC, stale.id DESC
                OFFSET %s
              )
            RETURNING notification.session_id
            """,
            (subscriber_id, subscriber_id, max(keep, 1)),
        ).fetchall()
        self._remove_empty_notification_sessions(
            subscriber_id, [row[0] for row in rows],
        )
        return len(rows)

    def _remove_empty_notification_sessions(
        self, subscriber_id: uuid.UUID, session_ids: list[uuid.UUID],
    ) -> None:
        for session_id in set(session_ids):
            self.connection.execute(
                """
                DELETE FROM watch_sessions session
                WHERE session.id = %s AND session.subscriber_id = %s
                  AND NOT EXISTS (
                    SELECT 1 FROM watch_notifications notification
                    WHERE notification.session_id = session.id
                  )
                """,
                (session_id, subscriber_id),
            )
        self.connection.execute(
            """
            DELETE FROM watch_detection_events event
            WHERE event.subscriber_id = %s
              AND NOT EXISTS (
                SELECT 1 FROM watch_notifications notification
                WHERE notification.detection_event_id = event.id
              )
              AND NOT EXISTS (
                SELECT 1 FROM watch_matches match
                WHERE match.detection_event_id = event.id
              )
            """,
            (subscriber_id,),
        )

    def session(self, subscriber_id: uuid.UUID, session_id: uuid.UUID) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            SELECT session.id, session.title, session.status, session.first_matched_at,
                   session.last_matched_at, session.match_count, session.broadcast_id,
                   rule.id, rule.name, rule.include_terms, broadcast.institution,
                   broadcast.committee_name, broadcast.lifecycle_status,
                   broadcast.source_system
            FROM watch_sessions session
            JOIN watch_rules rule ON rule.id = session.rule_id
            JOIN live_broadcasts broadcast ON broadcast.id = session.broadcast_id
            WHERE session.id = %s AND session.subscriber_id = %s
            """,
            (session_id, subscriber_id),
        ).fetchone()
        if not row:
            return None
        item = dict(zip(
            (
                "session_id", "title", "status", "first_matched_at", "last_matched_at",
                "match_count", "broadcast_id", "rule_id", "rule_name", "include_terms",
                "institution", "committee_name", "lifecycle_status", "source_system",
            ),
            row,
            strict=True,
        ))
        matches = self.connection.execute(
            """
            SELECT id, speaker_label, excerpt, matched_term, matched_at, segment_id
            FROM watch_matches WHERE session_id = %s ORDER BY matched_at, id
            """,
            (session_id,),
        ).fetchall()
        item["matches"] = [dict(zip(
            ("match_id", "speaker_label", "excerpt", "matched_term", "matched_at", "segment_id"),
            match,
            strict=True,
        )) for match in matches]
        speaker_flows: list[dict[str, Any]] = []
        by_speaker: dict[str, dict[str, Any]] = {}
        for match in item["matches"]:
            speaker = str(match.get("speaker_label") or "화자 확인 중")
            flow = by_speaker.get(speaker)
            if flow is None:
                flow = {"speaker_label": speaker, "match_count": 0, "summaries": []}
                by_speaker[speaker] = flow
                speaker_flows.append(flow)
            flow["match_count"] += 1
            flow["summaries"].append(summarize_utterance(match["excerpt"], max_chars=150))
        item["distinct_speaker_count"] = len(speaker_flows)
        item["speaker_flows"] = speaker_flows
        item["current_summary"] = build_watch_fallback_summary(item["matches"])
        item["current_summary_total"] = len(item["matches"])
        item["current_summary_truncated"] = (
            len(item["current_summary"]) < len(item["matches"])
        )
        item["summary_status"] = "READY_WITHOUT_LLM"
        version_rows = self.connection.execute(
            """
            SELECT status, summary, claims, evidence_match_ids, provider, model,
                   cost_usd, created_at, prompt_version
            FROM watch_summary_versions WHERE session_id = %s
            ORDER BY created_at DESC
            """,
            (session_id,),
        ).fetchall()
        if version_rows:
            latest = version_rows[0]
            latest_ready = next((row for row in version_rows if row[0] == "READY"), None)
            state_labels = {
                "PENDING": "GENERATING",
                "FAILED": "FAILED_RETAINING_FREE_SUMMARY",
                "LIMIT_REACHED": "LIMIT_REACHED_FREE_SUMMARY",
                "READY": "READY_WITH_LLM",
            }
            item["summary_status"] = state_labels.get(latest[0], "READY_WITHOUT_LLM")
            if latest_ready:
                display_summary, display_claims = normalize_watch_briefing_presentation(
                    latest_ready[1], latest_ready[2],
                )
                item["integrated_summary"] = {
                    "summary": display_summary, "claims": display_claims,
                    "evidence_match_ids": latest_ready[3],
                    "provider": latest_ready[4], "model": latest_ready[5],
                    "cost_usd": float(latest_ready[6]), "created_at": latest_ready[7],
                    "prompt_version": latest_ready[8],
                }
        verification_rows = self.connection.execute(
            """
            SELECT verification.status, COUNT(*)
            FROM watch_match_official_verifications verification
            JOIN watch_matches match ON match.id = verification.match_id
            WHERE match.session_id = %s
            GROUP BY verification.status
            """,
            (session_id,),
        ).fetchall()
        item["official_verification"] = {
            "status": self._session_verification_status(verification_rows),
            "counts": {status: count for status, count in verification_rows},
        }
        return item

    def request_rule_report_summary(
        self, subscriber_id: uuid.UUID, session_id: uuid.UUID,
    ) -> bool:
        row = self.connection.execute(
            """
            UPDATE watch_sessions SET report_summary_requested_at = now(),
                   updated_at = updated_at
            WHERE id = %s AND subscriber_id = %s AND match_count >= 3
            RETURNING id
            """,
            (session_id, subscriber_id),
        ).fetchone()
        return row is not None

    def latest_rule_report(
        self, subscriber_id: uuid.UUID, rule_id: uuid.UUID,
    ) -> dict[str, Any] | None:
        rule = next(
            (
                item for item in self.list_rules(subscriber_id)
                if item["rule_id"] == rule_id
            ),
            None,
        )
        if rule is None:
            return None
        row = self.connection.execute(
            """
            SELECT session.id
            FROM watch_sessions session
            JOIN live_broadcasts broadcast ON broadcast.id = session.broadcast_id
            WHERE session.subscriber_id = %s AND session.rule_id = %s
            ORDER BY (broadcast.lifecycle_status = 'LIVE') DESC,
                     session.last_matched_at DESC, session.id DESC
            LIMIT 1
            """,
            (subscriber_id, rule_id),
        ).fetchone()
        if row:
            report = self.session(subscriber_id, row[0])
            if report is not None:
                report["report_scope"] = "CURRENT_OR_LATEST_MEETING"
                report["llm_calls_on_view"] = 0
                return report
        return {
            "rule_id": rule["rule_id"],
            "rule_name": rule["name"],
            "include_terms": rule["include_terms"],
            "institution": rule["institution"],
            "status": "NO_MATCHES",
            "matches": [],
            "current_summary": [],
            "speaker_flows": [],
            "match_count": 0,
            "distinct_speaker_count": 0,
            "report_scope": "CURRENT_OR_LATEST_MEETING",
            "llm_calls_on_view": 0,
        }

    @staticmethod
    def _session_verification_status(rows: list[Any]) -> str:
        counts = {status: int(count) for status, count in rows}
        if counts.get("REVIEW_REQUIRED"):
            return "REVIEW_REQUIRED"
        if counts.get("OFFICIAL_CORRECTED"):
            return "OFFICIAL_CORRECTED"
        if counts.get("OFFICIAL_NOT_CONFIRMED"):
            return "OFFICIAL_NOT_CONFIRMED"
        if counts.get("OFFICIAL_CONFIRMED"):
            return "OFFICIAL_CONFIRMED"
        return "PENDING_OFFICIAL"

    def rebuild_bundle_matches(self, broadcast_id: uuid.UUID) -> int:
        """Project fast detections into consecutive-speaker utterance evidence."""
        segment_rows = self.connection.execute(
            """
            SELECT DISTINCT ON (segment.id)
                   segment.id, revision.id, segment.broadcast_id,
                   revision.event_cursor, revision.text, revision.speaker_label,
                   revision.is_final, revision.received_at
            FROM transcript_segments segment
            JOIN transcript_segment_revisions revision ON revision.segment_id = segment.id
            WHERE segment.broadcast_id = %s
            ORDER BY segment.id, revision.event_cursor DESC
            """,
            (broadcast_id,),
        ).fetchall()
        segments = [dict(zip(
            (
                "segment_id", "revision_id", "broadcast_id", "cursor", "text",
                "speaker_label", "is_final", "received_at",
            ),
            row,
            strict=True,
        )) for row in segment_rows]
        for segment in segments:
            segment["source_speaker_label"] = segment["speaker_label"]
        utterances = group_transcript_segments(segments)
        session_rows = self.connection.execute(
            "SELECT id, rule_id FROM watch_sessions WHERE broadcast_id = %s",
            (broadcast_id,),
        ).fetchall()
        total = 0
        for session_id, rule_id in session_rows:
            detections = self.connection.execute(
                """
                SELECT event.id, event.segment_id, event.revision_id,
                       event.matched_term, event.detected_at
                FROM watch_detection_events event
                WHERE event.rule_id = %s AND event.broadcast_id = %s
                ORDER BY event.detected_at, event.id
                """,
                (rule_id, broadcast_id),
            ).fetchall()
            by_segment = {
                str(row[1]): {
                    "event_id": row[0], "segment_id": row[1], "revision_id": row[2],
                    "matched_term": row[3], "matched_at": row[4],
                }
                for row in detections
            }
            self.connection.execute("DELETE FROM watch_matches WHERE session_id = %s", (session_id,))
            session_count = 0
            for utterance in utterances:
                detected = next((
                    by_segment.get(str(segment_id))
                    for segment_id in utterance.get("segment_ids") or []
                    if by_segment.get(str(segment_id))
                ), None)
                if detected is None:
                    continue
                self.connection.execute(
                    """
                    INSERT INTO watch_matches (
                        id, session_id, detection_event_id, segment_id, revision_id,
                        speaker_label, excerpt, matched_term, matched_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        uuid.uuid4(), session_id, detected["event_id"],
                        detected["segment_id"], detected["revision_id"],
                        utterance.get("speaker_label"), utterance["text"],
                        detected["matched_term"], detected["matched_at"],
                    ),
                )
                session_count += 1
            self.connection.execute(
                """
                UPDATE watch_sessions SET match_count = %s, updated_at = now()
                WHERE id = %s
                """,
                (session_count, session_id),
            )
            total += session_count
        return total

    def process_revision(self, revision: dict[str, Any]) -> int:
        if not revision.get("is_final"):
            return 0
        rules = self._candidate_rules(revision)
        created = 0
        for rule in rules:
            match = match_watch_rule(str(revision.get("text") or ""), rule)
            if not match:
                continue
            event_id = uuid.uuid4()
            event = self.connection.execute(
                """
                INSERT INTO watch_detection_events (
                    id, subscriber_id, rule_id, broadcast_id, segment_id, revision_id,
                    matched_term, excerpt, speaker_label, detected_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (rule_id, revision_id) DO NOTHING RETURNING id
                """,
                (
                    event_id, rule["subscriber_id"], rule["rule_id"],
                    revision["broadcast_id"], revision["segment_id"], revision["revision_id"],
                    match.term, match.excerpt, revision.get("speaker_label"),
                    revision["received_at"],
                ),
            ).fetchone()
            if not event:
                continue
            session_id = self._upsert_session(rule, revision)
            inserted = self.connection.execute(
                """
                INSERT INTO watch_matches (
                    id, session_id, detection_event_id, segment_id, revision_id,
                    speaker_label, excerpt, matched_term, matched_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (session_id, revision_id) DO NOTHING RETURNING id
                """,
                (
                    uuid.uuid4(), session_id, event_id, revision["segment_id"],
                    revision["revision_id"], revision.get("speaker_label"), match.excerpt,
                    match.term, revision["received_at"],
                ),
            ).fetchone()
            if inserted:
                self.connection.execute(
                    """
                    UPDATE watch_sessions SET match_count = match_count + 1,
                           last_matched_at = %s, updated_at = now()
                    WHERE id = %s
                    """,
                    (revision["received_at"], session_id),
                )
            if self._should_notify(rule, revision):
                notification_id = uuid.uuid4()
                dedupe_key = self._notification_dedupe_key(rule, revision, event_id)
                notification = self.connection.execute(
                    """
                    INSERT INTO watch_notifications (
                        id, subscriber_id, detection_event_id, session_id, title, body,
                        is_test, notification_type, dedupe_key
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'MATCH', %s)
                    ON CONFLICT DO NOTHING RETURNING id
                    """,
                    (
                        notification_id, rule["subscriber_id"], event_id, session_id,
                        f"{rule['name']} 언급 감지",
                        f"{revision['title']} · {match.excerpt}",
                        revision.get("source_system") == "poc07.test",
                        dedupe_key,
                    ),
                ).fetchone()
                if notification:
                    self._enqueue_outbox(
                        rule["subscriber_id"], notification_id,
                        kakao_enabled=(
                            bool(rule.get("kakao_enabled"))
                            and revision.get("source_system") != "poc07.test"
                        ),
                    )
                    self.prune_notification_history(rule["subscriber_id"])
            created += 1
        return created

    def finalize_ended_sessions(self, *, digest_enabled: bool = True) -> dict[str, int]:
        rows = self.connection.execute(
            """
            SELECT session.id, session.subscriber_id, session.rule_id,
                   session.broadcast_id, session.title, session.match_count,
                   rule.name, rule.digest_enabled, rule.kakao_enabled,
                   broadcast.source_system,
                   COUNT(DISTINCT COALESCE(match.speaker_label, ''))
            FROM watch_sessions session
            JOIN watch_rules rule ON rule.id = session.rule_id
            JOIN live_broadcasts broadcast ON broadcast.id = session.broadcast_id
            LEFT JOIN watch_matches match ON match.session_id = session.id
            WHERE broadcast.lifecycle_status = 'ENDED'
              AND (
                session.status = 'LIVE'
                OR (
                  rule.digest_enabled
                  AND NOT EXISTS (
                    SELECT 1 FROM watch_notifications notification
                    WHERE notification.session_id = session.id
                      AND notification.notification_type = 'DIGEST'
                  )
                )
              )
            GROUP BY session.id, rule.id, broadcast.id
            """
        ).fetchall()
        digests = 0
        for row in rows:
            (
                session_id, subscriber_id, rule_id, broadcast_id, title,
                match_count, rule_name, wants_digest, wants_kakao,
                source_system, speaker_count,
            ) = row
            self.connection.execute(
                "UPDATE watch_sessions SET status = 'ENDED', updated_at = now() WHERE id = %s",
                (session_id,),
            )
            if not digest_enabled or not wants_digest:
                continue
            notification_id = uuid.uuid4()
            notification = self.connection.execute(
                """
                INSERT INTO watch_notifications (
                    id, subscriber_id, detection_event_id, session_id, title, body,
                    is_test, notification_type, dedupe_key
                ) VALUES (%s, %s, NULL, %s, %s, %s, %s, 'DIGEST', %s)
                ON CONFLICT (dedupe_key) DO NOTHING RETURNING id
                """,
                (
                    notification_id, subscriber_id, session_id,
                    f"{rule_name} 회의 종료 요약",
                    f"{title} · 관련 발언 {match_count}묶음 · 화자 {speaker_count}명",
                    source_system == "poc07.test",
                    f"digest:{rule_id}:{broadcast_id}",
                ),
            ).fetchone()
            if notification:
                self._enqueue_outbox(
                    subscriber_id, notification_id,
                    kakao_enabled=(bool(wants_kakao) and source_system != "poc07.test"),
                )
                self.prune_notification_history(subscriber_id)
                digests += 1
        return {"sessions_ended": len(rows), "digests_created": digests}

    def _enqueue_outbox(
        self, subscriber_id: uuid.UUID, notification_id: uuid.UUID, *,
        kakao_enabled: bool,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO notification_outbox (
                id, subscriber_id, notification_id, channel, status, sent_at
            ) VALUES (%s, %s, %s, 'IN_APP', 'SENT', now())
            ON CONFLICT (notification_id, channel) DO NOTHING
            """,
            (uuid.uuid4(), subscriber_id, notification_id),
        )
        if not kakao_enabled:
            return
        self.connection.execute(
            """
            INSERT INTO notification_outbox (
                id, subscriber_id, notification_id, channel, status
            )
            SELECT %s, %s, %s, 'KAKAO', 'PENDING'
            WHERE EXISTS (
                SELECT 1 FROM watch_kakao_accounts
                WHERE subscriber_id = %s AND status = 'ACTIVE'
            )
            ON CONFLICT (notification_id, channel) DO NOTHING
            """,
            (uuid.uuid4(), subscriber_id, notification_id, subscriber_id),
        )

    def refresh_official_verifications(self) -> int:
        rows = self.connection.execute(
            """
            SELECT match.id, document.id, reconciliation.official_utterance_id,
                   reconciliation.reconciliation_status, match.excerpt,
                   utterance.text
            FROM watch_matches match
            JOIN watch_sessions session ON session.id = match.session_id
            JOIN meeting_official_integrations integration
              ON integration.broadcast_id = session.broadcast_id
             AND integration.status = 'READY'
            JOIN official_transcript_documents document
              ON document.id = integration.official_document_id
             AND document.publication_stage = 'FINAL'
             AND document.authority_status = 'OFFICIAL'
            LEFT JOIN LATERAL (
                SELECT item.official_utterance_id, item.reconciliation_status,
                       item.created_at
                FROM transcript_official_reconciliations item
                JOIN official_transcript_utterances candidate
                  ON candidate.id = item.official_utterance_id
                 AND candidate.document_id = document.id
                WHERE item.transcript_revision_id = match.revision_id
                ORDER BY item.created_at DESC LIMIT 1
            ) reconciliation ON true
            LEFT JOIN official_transcript_utterances utterance
              ON utterance.id = reconciliation.official_utterance_id
            LEFT JOIN watch_match_official_verifications existing
              ON existing.match_id = match.id
             AND existing.official_document_id = document.id
            WHERE existing.id IS NULL
               OR existing.verified_at < integration.generated_at
               OR existing.verified_at < reconciliation.created_at
            """
        ).fetchall()
        updated = 0
        for match_id, document_id, utterance_id, reconciliation, excerpt, official_text in rows:
            if reconciliation == "CONFLICT":
                status, method = "REVIEW_REQUIRED", "OFFICIAL_CONFLICT"
            elif reconciliation == "MATCHED" and official_text:
                # The existing reconciler only emits MATCHED for one unique
                # official sentence. Stylistic expansion alone is not a
                # correction and must not be presented as a meaningful diff.
                status = "OFFICIAL_CONFIRMED"
                method = (
                    "EXACT_NORMALIZED"
                    if normalize_watch_text(excerpt) == normalize_watch_text(official_text)
                    else "UNIQUE_OFFICIAL_SENTENCE"
                )
            else:
                status, method = "OFFICIAL_NOT_CONFIRMED", "FINAL_DOCUMENT_NO_MATCH"
            self.connection.execute(
                """
                INSERT INTO watch_match_official_verifications (
                    id, match_id, official_document_id, official_utterance_id,
                    status, verification_method
                ) VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (match_id, official_document_id)
                DO UPDATE SET official_utterance_id = EXCLUDED.official_utterance_id,
                              status = EXCLUDED.status,
                              verification_method = EXCLUDED.verification_method,
                              verified_at = now()
                """,
                (uuid.uuid4(), match_id, document_id, utterance_id, status, method),
            )
            updated += 1
        return updated

    def metrics(self, subscriber_id: uuid.UUID) -> dict[str, Any]:
        row = self.connection.execute(
            """
            WITH event_metric AS (
              SELECT COUNT(*) AS detections,
                     AVG(EXTRACT(EPOCH FROM (created_at - detected_at)) * 1000)
                       AS detection_latency_ms
              FROM watch_detection_events WHERE subscriber_id = %s
            ), notification_metric AS (
              SELECT COUNT(*) AS notifications,
                     COUNT(*) FILTER (WHERE notification_type = 'MATCH') AS match_notifications,
                     COUNT(*) FILTER (WHERE notification_type = 'DIGEST') AS digests,
                     AVG(EXTRACT(EPOCH FROM (notification.created_at - event.detected_at)) * 1000)
                       FILTER (WHERE notification.notification_type = 'MATCH')
                       AS notification_latency_ms
              FROM watch_notifications notification
              LEFT JOIN watch_detection_events event
                ON event.id = notification.detection_event_id
              WHERE notification.subscriber_id = %s
            ), verification_metric AS (
              SELECT COUNT(DISTINCT verification.match_id) AS eligible,
                     COUNT(DISTINCT verification.match_id) FILTER (
                       WHERE verification.status IN ('OFFICIAL_CONFIRMED', 'OFFICIAL_CORRECTED')
                     ) AS checked,
                     COUNT(DISTINCT verification.match_id) FILTER (
                       WHERE verification.status = 'REVIEW_REQUIRED'
                     ) AS review_required
              FROM watch_match_official_verifications verification
              JOIN watch_matches match ON match.id = verification.match_id
              JOIN watch_sessions session ON session.id = match.session_id
              WHERE session.subscriber_id = %s
            )
            SELECT
              (SELECT COUNT(*) FROM watch_rules
               WHERE subscriber_id = %s AND archived_at IS NULL),
              event_metric.detections,
              (SELECT COUNT(*) FROM watch_matches match
               JOIN watch_sessions session ON session.id = match.session_id
               WHERE session.subscriber_id = %s),
              notification_metric.notifications,
              notification_metric.digests,
              verification_metric.checked,
              verification_metric.review_required,
              GREATEST(event_metric.detections - notification_metric.match_notifications, 0),
              COALESCE(event_metric.detection_latency_ms, 0),
              COALESCE(notification_metric.notification_latency_ms, 0),
              CASE WHEN verification_metric.eligible > 0
                THEN ROUND(verification_metric.checked * 100.0 / verification_metric.eligible, 1)
                ELSE 0 END
            FROM event_metric, notification_metric, verification_metric
            """,
            (subscriber_id, subscriber_id, subscriber_id, subscriber_id, subscriber_id),
        ).fetchone()
        keys = (
            "active_rules", "detections", "matches", "notifications", "digests",
            "officially_checked", "review_required", "suppressed",
            "detection_latency_ms", "notification_latency_ms",
            "official_confirmation_rate",
        )
        metrics = dict(zip(keys, row, strict=True))
        for key in keys[:8]:
            metrics[key] = int(metrics[key] or 0)
        for key in keys[8:]:
            metrics[key] = float(metrics[key] or 0)
        summary = self.connection.execute(
            """
            SELECT COUNT(*) FILTER (WHERE version.status = 'READY'),
                   COALESCE(SUM(version.cost_usd) FILTER (WHERE version.status = 'READY'), 0)
            FROM watch_summary_versions version
            JOIN watch_sessions session ON session.id = version.session_id
            WHERE session.subscriber_id = %s
              AND version.created_at >= date_trunc('month', now())
            """,
            (subscriber_id,),
        ).fetchone()
        delivery = self.connection.execute(
            """
            SELECT COUNT(*) FILTER (WHERE channel = 'KAKAO' AND status = 'SENT'),
                   COUNT(*) FILTER (WHERE channel = 'KAKAO' AND status = 'FAILED')
            FROM notification_outbox WHERE subscriber_id = %s
            """,
            (subscriber_id,),
        ).fetchone()
        metrics.update({
            "llm_calls": int(summary[0] or 0),
            "cost_usd": float(summary[1] or 0),
            "kakao_sent": int(delivery[0] or 0),
            "kakao_failed": int(delivery[1] or 0),
        })
        return metrics

    def _candidate_rules(self, revision: dict[str, Any]) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT rule.id, rule.subscriber_id, rule.name, rule.include_terms,
                   rule.exclude_terms, rule.institution, rule.committee_name,
                   rule.notification_policy, rule.cooldown_minutes,
                   rule.digest_enabled, rule.kakao_enabled, rule.current_revision
            FROM watch_rules rule
            WHERE rule.enabled AND rule.archived_at IS NULL AND rule.starts_at <= %s
              AND (rule.institution IS NULL OR rule.institution = %s)
              AND (rule.committee_name IS NULL OR rule.committee_name = %s)
            """,
            (
                revision["received_at"], revision.get("institution"),
                revision.get("committee_name"),
            ),
        ).fetchall()
        columns = (
            "rule_id", "subscriber_id", "name", "include_terms", "exclude_terms",
            "institution", "committee_name", "notification_policy",
            "cooldown_minutes", "digest_enabled", "kakao_enabled", "current_revision",
        )
        return [dict(zip(columns, row, strict=True)) for row in rows]

    def _upsert_session(self, rule: dict[str, Any], revision: dict[str, Any]) -> uuid.UUID:
        row = self.connection.execute(
            """
            INSERT INTO watch_sessions (
                id, subscriber_id, rule_id, broadcast_id, title,
                first_matched_at, last_matched_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (rule_id, broadcast_id) DO UPDATE SET
                last_matched_at = GREATEST(watch_sessions.last_matched_at, EXCLUDED.last_matched_at),
                status = EXCLUDED.status, updated_at = now()
            RETURNING id
            """,
            (
                uuid.uuid4(), rule["subscriber_id"], rule["rule_id"],
                revision["broadcast_id"], revision.get("title") or "회의 생방송",
                revision["received_at"], revision["received_at"],
            ),
        ).fetchone()
        return row[0]

    def _should_notify(self, rule: dict[str, Any], revision: dict[str, Any]) -> bool:
        policy = rule["notification_policy"]
        if policy == "EVERY_MATCH":
            return True
        if policy == "FIRST_PER_SPEAKER":
            row = self.connection.execute(
                """
                SELECT 1
                FROM watch_notifications notification
                JOIN watch_detection_events event ON event.id = notification.detection_event_id
                WHERE event.rule_id = %s AND event.broadcast_id = %s
                  AND COALESCE(event.speaker_label, '') = COALESCE(%s, '')
                  AND notification.notification_type = 'MATCH'
                LIMIT 1
                """,
                (
                    rule["rule_id"], revision["broadcast_id"],
                    revision.get("speaker_label"),
                ),
            ).fetchone()
            return row is None
        row = self.connection.execute(
            """
            SELECT MAX(notification.created_at)
            FROM watch_notifications notification
            JOIN watch_detection_events event ON event.id = notification.detection_event_id
            WHERE event.rule_id = %s AND event.broadcast_id = %s
            """,
            (rule["rule_id"], revision["broadcast_id"]),
        ).fetchone()
        last = row[0]
        if last is None:
            return True
        interval_minutes = {
            "ONCE_PER_10_MINUTES": 10,
            "INTERVAL_15_MINUTES": 15,
            "INTERVAL_30_MINUTES": 30,
            "INTERVAL_60_MINUTES": 60,
        }.get(policy)
        if interval_minutes:
            return last <= datetime.now(last.tzinfo) - timedelta(minutes=interval_minutes)
        return False

    @staticmethod
    def _notification_dedupe_key(
        rule: dict[str, Any], revision: dict[str, Any], event_id: uuid.UUID,
    ) -> str:
        policy = rule["notification_policy"]
        prefix = f"{rule['rule_id']}:{revision['broadcast_id']}"
        if policy == "FIRST_PER_MEETING":
            return f"first:{prefix}"
        if policy == "FIRST_PER_SPEAKER":
            speaker = str(revision.get("speaker_label") or "unknown")
            return f"speaker:{prefix}:{hashlib.sha256(speaker.encode()).hexdigest()[:16]}"
        return f"match:{event_id}"
