from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from psycopg.types.json import Jsonb

from ..services.transcript_presentation import (
    apply_speaker_overrides,
    group_transcript_segments,
)
from ..services.watch_lifecycle import (
    completion_ready,
    declaration_kind,
    rank_topics,
    topic_projection,
)
from .summary_repository import SummaryRepository


class WatchLifecycleRepository:
    def __init__(self, connection: Any):
        self.connection = connection

    def record_boundary(
        self,
        broadcast_id: Any,
        kind: str,
        occurred_at: datetime,
        evidence: dict[str, Any],
    ) -> None:
        cursor = self.connection.execute(
            """SELECT COALESCE(MAX(r.event_cursor), 0) FROM transcript_segment_revisions r
               JOIN transcript_segments s ON s.id = r.segment_id
               WHERE s.broadcast_id = %s AND r.received_at <= %s""",
            (broadcast_id, occurred_at),
        ).fetchone()[0]
        row = self.connection.execute(
            """INSERT INTO watch_meeting_boundaries(id, broadcast_id, kind, occurred_at, cutoff_cursor, evidence)
               VALUES (%s,%s,%s,%s,%s,%s)
               ON CONFLICT (broadcast_id, kind, cutoff_cursor) DO NOTHING RETURNING id""",
            (uuid.uuid4(), broadcast_id, kind, occurred_at, cursor, Jsonb(evidence)),
        ).fetchone()
        if row:
            self.connection.execute(
                """UPDATE watch_topic_episodes e SET status = 'WAITING', boundary_id = %s
                   FROM watch_sessions s WHERE e.session_id = s.id AND s.broadcast_id = %s
                   AND e.status = 'OPEN' AND e.started_cursor <= %s""",
                (row[0], broadcast_id, cursor),
            )

    def observe_revision(self, revision: dict[str, Any]) -> None:
        if not revision.get("is_final"):
            return
        parts = (revision.get("source_payload") or {}).get("speaker_segments") or []
        kind = next(
            (
                value
                for part in parts
                if (
                    value := declaration_kind(
                        str(part.get("text") or ""), str(part.get("speaker") or "")
                    )
                )
            ),
            None,
        )
        kind = kind or declaration_kind(
            str(revision.get("text") or ""), str(revision.get("speaker_label") or "")
        )
        if kind:
            self.record_boundary(
                revision["broadcast_id"],
                kind,
                revision["received_at"],
                {
                    "revision_id": str(revision["revision_id"]),
                    "method": "PRESIDING_DECLARATION",
                },
            )
            self.connection.execute(
                """INSERT INTO watch_broadcast_signals VALUES (%s,%s,%s)
                   ON CONFLICT (broadcast_id) DO UPDATE SET state=EXCLUDED.state, observed_at=EXCLUDED.observed_at""",
                (revision["broadcast_id"], kind, revision["received_at"]),
            )

    def observe_official(
        self, items: list[dict[str, Any]], observed_at: datetime, source_version_id: Any
    ) -> None:
        for item in items:
            external_id = item.get("meeting_external_id")
            if not external_id:
                continue
            row = self.connection.execute(
                "SELECT id FROM live_broadcasts WHERE source_system='assembly.webcast.go.kr' AND external_id=%s",
                (external_id,),
            ).fetchone()
            if not row:
                continue
            broadcast_id = row[0]
            text = str(item.get("status_text") or "").replace(" ", "")
            state = (
                "RECESS"
                if ("계속예정" in text or text.startswith("정회"))
                else "LIVE"
                if item.get("is_live")
                else None
            )
            if state is None:
                continue
            old = self.connection.execute(
                "SELECT state,observed_at FROM watch_broadcast_signals WHERE broadcast_id=%s",
                (broadcast_id,),
            ).fetchone()
            if state == "LIVE" and old and old[0] == "RECESS":
                resumed = self.connection.execute(
                    "SELECT 1 FROM live_broadcasts WHERE id=%s AND last_caption_received_at>%s",
                    (broadcast_id, old[1]),
                ).fetchone()
                if not resumed:
                    continue
            if state == "RECESS" and (not old or old[0] != state):
                self.record_boundary(
                    broadcast_id,
                    state,
                    observed_at,
                    {
                        "source_document_version_id": str(source_version_id),
                        "status_text": item["status_text"],
                        "method": "OFFICIAL_STATUS",
                    },
                )
            self.connection.execute(
                """INSERT INTO watch_broadcast_signals VALUES (%s,%s,%s)
                   ON CONFLICT (broadcast_id) DO UPDATE SET state=EXCLUDED.state, observed_at=EXCLUDED.observed_at""",
                (broadcast_id, state, observed_at),
            )

    def on_detection(
        self,
        session_id: Any,
        rule: dict[str, Any],
        revision: dict[str, Any],
        event_id: Any,
        *,
        matched_term: str,
    ) -> Any | None:
        from ..services.watch_matcher import normalize_watch_text

        term_key = normalize_watch_text(matched_term).replace(" ", "")
        # Worker cursor lock serializes this transaction with reconciliation.
        self.connection.execute(
            """UPDATE watch_topic_episodes SET status='CANCELED', closed_at=now()
               WHERE session_id=%s AND status='OPEN' AND rule_revision<>%s""",
            (session_id, rule["current_revision"]),
        )
        row = self.connection.execute(
            """SELECT e.id FROM watch_topic_episodes e LEFT JOIN watch_meeting_boundaries b ON b.id=e.boundary_id
               WHERE e.session_id=%s AND e.rule_revision=%s AND e.matched_term=%s AND (e.status='OPEN' OR
               (e.status='WAITING' AND e.started_cursor<=%s AND b.cutoff_cursor>=%s))
               ORDER BY e.started_cursor DESC LIMIT 1""",
            (
                session_id,
                rule["current_revision"],
                term_key,
                revision["cursor"],
                revision["cursor"],
            ),
        ).fetchone()
        created = row is None
        episode_id = row[0] if row else uuid.uuid4()
        if created:
            self.connection.execute(
                """INSERT INTO watch_topic_episodes(id,session_id,rule_revision,started_cursor,started_at,matched_term)
                   VALUES (%s,%s,%s,%s,%s,%s)""",
                (
                    episode_id,
                    session_id,
                    rule["current_revision"],
                    revision["cursor"],
                    revision["received_at"],
                    term_key,
                ),
            )
        self.connection.execute(
            "INSERT INTO watch_episode_detections VALUES (%s,%s) ON CONFLICT DO NOTHING",
            (episode_id, event_id),
        )
        self.connection.execute(
            "UPDATE watch_detection_events SET episode_id=%s WHERE id=%s",
            (episode_id, event_id),
        )
        # A boundary may have arrived before the detection worker caught up.
        boundary = self.connection.execute(
            """SELECT id FROM watch_meeting_boundaries WHERE broadcast_id=%s AND cutoff_cursor >= %s
               ORDER BY occurred_at LIMIT 1""",
            (revision["broadcast_id"], revision["cursor"]),
        ).fetchone()
        if boundary:
            self.connection.execute(
                "UPDATE watch_topic_episodes SET status='WAITING',boundary_id=%s WHERE id=%s",
                (boundary[0], episode_id),
            )
        return episode_id if created else None

    def dispatch(
        self,
        *,
        subscriber_id: Any,
        session_id: Any,
        key: str,
        stage: int,
        title: str,
        body: str,
        details: dict[str, Any],
        source_system: str,
        occurred_at: datetime,
        kakao: bool,
        event_id: Any = None,
    ) -> bool:
        from .watch_repository import (
            WatchRepository,
            _allows_kakao_delivery,
            _is_test_source,
        )

        dispatch_id = uuid.uuid4()
        details = {**details, "title": title, "stage": stage}
        row = self.connection.execute(
            """INSERT INTO watch_dispatches(id,subscriber_id,session_id,dedupe_key,stage,details)
               VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (dedupe_key) DO NOTHING RETURNING id""",
            (dispatch_id, subscriber_id, session_id, key, stage, Jsonb(details)),
        ).fetchone()
        if not row:
            return False
        notification_id = uuid.uuid4()
        self.connection.execute(
            """INSERT INTO watch_notifications(id,subscriber_id,session_id,detection_event_id,title,body,
                   is_test,notification_type,dedupe_key,dispatch_id)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                notification_id,
                subscriber_id,
                session_id,
                event_id,
                title,
                body,
                _is_test_source(source_system),
                {1: "MATCH", 2: "TOPIC_COMPLETE", 3: "DIGEST"}[stage],
                key,
                dispatch_id,
            ),
        )
        WatchRepository(self.connection)._enqueue_outbox(
            subscriber_id,
            notification_id,
            kakao_enabled=kakao and _allows_kakao_delivery(source_system, occurred_at),
        )
        return True

    def utterances(
        self, broadcast_id: Any, lifecycle: str, *, cutoff: int | None = None
    ) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """SELECT DISTINCT ON(s.id) s.id,r.id,s.broadcast_id,r.event_cursor,r.text,r.speaker_label,
                      r.is_final,r.received_at,r.source_payload
               FROM transcript_segments s JOIN transcript_segment_revisions r ON r.segment_id=s.id
               WHERE s.broadcast_id=%s AND (%s::bigint IS NULL OR r.event_cursor<=%s)
               ORDER BY s.id,r.event_cursor DESC""",
            (broadcast_id, cutoff, cutoff),
        ).fetchall()
        columns = (
            "segment_id",
            "revision_id",
            "broadcast_id",
            "cursor",
            "text",
            "speaker_label",
            "is_final",
            "received_at",
            "source_payload",
        )
        segments = [dict(zip(columns, row, strict=True)) for row in rows]
        for item in segments:
            payload = item.pop("source_payload") or {}
            item["source_speaker_segments"] = payload.get("speaker_segments") or []
            item["insight_hint"] = payload.get("insight")
        utterances = group_transcript_segments(apply_speaker_overrides(segments, {}))
        source = self.connection.execute(
            "SELECT source_system FROM live_broadcasts WHERE id=%s", (broadcast_id,)
        ).fetchone()[0]
        cached = SummaryRepository(self.connection).summary_map(
            [broadcast_id], provider="", model="", prompt_version="", utterances=utterances
        )
        for u in utterances:
            summary = cached.get((broadcast_id, u["content_hash"]))
            if summary:
                u.update(
                    summary=summary["summary"], live_insight=summary["live_insight"]
                )
            if source in {
                "poc07.test",
                "poc07.replay.local",
                "poc07.replay.kakao",
            } and u.get("insight_hints"):
                u["live_insight"] = u["insight_hints"][-1]
                summary = True  # Fixture-authored hints, no external LLM call.
            u["ready"] = bool(
                summary
                and (u.get("live_insight") or {}).get("topic")
            )
        # LIVE's final turn is not closed yet, even if its latest caption is final.
        if cutoff is None and lifecycle == "LIVE" and utterances:
            utterances = utterances[:-1]
        return utterances

    def reconcile(self, *, now: datetime | None = None) -> dict[str, int]:
        from .watch_repository import WatchRepository

        now = now or datetime.now(UTC)
        ended = self.connection.execute(
            """SELECT DISTINCT b.id,b.ended_at FROM live_broadcasts b
               JOIN watch_sessions s ON s.broadcast_id=b.id
               JOIN watch_topic_episodes e ON e.session_id=s.id
               LEFT JOIN watch_broadcast_signals signal ON signal.broadcast_id=b.id
               WHERE b.lifecycle_status='ENDED' AND b.ended_at IS NOT NULL
               AND COALESCE(signal.state,'') <> 'RECESS'
               AND b.ended_at >= (SELECT starts_at FROM watch_lifecycle_rollout)
               AND (b.source_system <> 'assembly.webcast.go.kr'
                    OR b.ended_at <= %s - interval '5 minutes')""", (now,),
        ).fetchall()
        for broadcast_id, at in ended:
            self.record_boundary(
                broadcast_id, "ENDED", at, {"method": "BROADCAST_LIFECYCLE"}
            )
        rows = self.connection.execute(
            """SELECT e.id,e.session_id,e.started_cursor,e.status,e.boundary_id,
                      s.subscriber_id,s.broadcast_id,r.enabled,r.kakao_enabled,r.current_revision,e.rule_revision,
                      b.lifecycle_status,b.source_system,r.name,b.title, boundary.cutoff_cursor,boundary.occurred_at
               FROM watch_topic_episodes e JOIN watch_sessions s ON s.id=e.session_id
               JOIN watch_rules r ON r.id=s.rule_id JOIN live_broadcasts b ON b.id=s.broadcast_id
               LEFT JOIN watch_meeting_boundaries boundary ON boundary.id=e.boundary_id
               WHERE e.status IN ('OPEN','WAITING') ORDER BY e.started_cursor""",
        ).fetchall()
        completed = 0
        snapshots: dict[tuple[Any, Any], list[dict[str, Any]]] = {}
        subscribers = set()
        for (
            episode_id,
            session_id,
            start_cursor,
            status,
            boundary_id,
            subscriber_id,
            broadcast_id,
            enabled,
            kakao,
            current_revision,
            rule_revision,
            lifecycle,
            source,
            rule_name,
            meeting_title,
            cutoff,
            boundary_at,
        ) in rows:
            if not enabled or current_revision != rule_revision:
                self.connection.execute(
                    "UPDATE watch_topic_episodes SET status='CANCELED',closed_at=%s WHERE id=%s",
                    (now, episode_id),
                )
                continue
            snapshot_key = (broadcast_id, cutoff)
            if snapshot_key not in snapshots:
                snapshots[snapshot_key] = self.utterances(
                    broadcast_id, lifecycle, cutoff=cutoff
                )
            utterances = snapshots[snapshot_key]
            # Include the full first matched speaker turn, not preceding unrelated turns.
            relevant = [u for u in utterances if int(u["last_cursor"]) >= start_cursor]
            segments = {
                str(row[0])
                for row in self.connection.execute(
                    "SELECT event.segment_id FROM watch_detection_events event JOIN watch_episode_detections link ON link.event_id=event.id WHERE link.episode_id=%s",
                    (episode_id,),
                ).fetchall()
            }
            visible = {str(s).split(":")[0] for u in relevant for s in u["segment_ids"]}
            if not segments.issubset(visible):
                continue
            topics = topic_projection(relevant, segments)
            all_complete = bool(topics)
            for topic in topics:
                topic_segments = {
                    value.split(":")[0]
                    for point in topic["points"]
                    for value in point["segment_ids"]
                }
                ready = completion_ready(
                    relevant, topic_segments, now=now, boundary=bool(boundary_id)
                )
                all_complete = all_complete and ready
                if not ready:
                    continue
                details = {
                    "topics": [topic],
                    "meeting_title": meeting_title,
                    "authority": "LIVE",
                    "grace_seconds": 300,
                }
                # A keyword can span several different topics before its open
                # detection period ends. Complete each topic independently.
                first_evidence = topic["points"][0]["utterance_id"]
                completed += self.dispatch(
                    subscriber_id=subscriber_id,
                    session_id=session_id,
                    key=f"topic:{episode_id}:{first_evidence}",
                    stage=2,
                    title=f"주제 완료 · {rule_name}",
                    body=self.topic_body([topic]),
                    details=details,
                    source_system=source,
                    occurred_at=boundary_at or now,
                    kakao=kakao,
                )
                subscribers.add(subscriber_id)
            if all_complete:
                self.connection.execute(
                    "UPDATE watch_topic_episodes SET status='CLOSED',closed_at=%s,details=%s WHERE id=%s",
                    (
                        now,
                        Jsonb(
                            {
                                "topics": topics,
                                "meeting_title": meeting_title,
                                "authority": "LIVE",
                            }
                        ),
                        episode_id,
                    ),
                )
        digests = self.finalize_boundaries(now)
        for subscriber_id in subscribers:
            WatchRepository(self.connection).prune_notification_history(subscriber_id)
        return {"topics_completed": completed, "digests_created": digests}

    @staticmethod
    def topic_body(topics: list[dict[str, Any]]) -> str:
        return "\n".join(
            f"{i}. {t['title']} — {t['points'][0]['summary']}"
            for i, t in enumerate(topics, 1)
            if t["points"]
        )

    def finalize_boundaries(self, now: datetime) -> int:
        from .watch_repository import WatchRepository

        rows = self.connection.execute(
            """SELECT DISTINCT boundary.id,boundary.broadcast_id,boundary.kind,boundary.occurred_at,boundary.cutoff_cursor,
                      s.subscriber_id,b.source_system,b.title
               FROM watch_meeting_boundaries boundary JOIN live_broadcasts b ON b.id=boundary.broadcast_id
               JOIN watch_sessions s ON s.broadcast_id=b.id JOIN watch_topic_episodes e ON e.session_id=s.id
               JOIN watch_rules r ON r.id=s.rule_id
               WHERE r.enabled AND e.started_cursor <= boundary.cutoff_cursor
                 AND NOT (boundary.kind='ENDED' AND boundary.evidence->>'method'='BROADCAST_LIFECYCLE'
                   AND EXISTS (SELECT 1 FROM watch_meeting_boundaries corrected
                     WHERE corrected.broadcast_id=boundary.broadcast_id AND corrected.kind='RECESS'
                     AND corrected.cutoff_cursor=boundary.cutoff_cursor
                     AND corrected.occurred_at>=boundary.occurred_at))
                 AND NOT EXISTS (SELECT 1 FROM watch_dispatches d
                   WHERE d.dedupe_key='boundary:' || boundary.id::text || ':' || s.subscriber_id::text)""",
        ).fetchall()
        count = 0
        subscribers = set()
        for (
            boundary_id,
            broadcast_id,
            kind,
            occurred_at,
            cutoff,
            subscriber_id,
            source,
            title,
        ) in rows:
            episodes = self.connection.execute(
                """SELECT e.status,e.details,e.session_id,r.kakao_enabled,e.rule_revision,r.current_revision
                   FROM watch_topic_episodes e JOIN watch_sessions s ON s.id=e.session_id JOIN watch_rules r ON r.id=s.rule_id
                   WHERE s.broadcast_id=%s AND s.subscriber_id=%s AND e.started_cursor<=%s AND r.enabled""",
                (broadcast_id, subscriber_id, cutoff),
            ).fetchall()
            active = [e for e in episodes if e[0] != "CANCELED" and e[4] == e[5]]
            if not active or any(e[0] != "CLOSED" for e in active):
                continue
            # Re-project all eligible detections up to this boundary so the same
            # topic discussed again later is merged with its earlier statements.
            utterances = self.utterances(broadcast_id, "ENDED", cutoff=cutoff)
            detected = {
                str(r[0])
                for r in self.connection.execute(
                    """SELECT event.segment_id FROM watch_detection_events event
                   JOIN watch_rules rule ON rule.id=event.rule_id
                   JOIN transcript_segment_revisions revision ON revision.id=event.revision_id
                   WHERE event.subscriber_id=%s AND event.broadcast_id=%s AND revision.event_cursor<=%s
                     AND rule.enabled AND event.detected_at>=rule.starts_at AND event.episode_id IS NOT NULL""",
                    (subscriber_id, broadcast_id, cutoff),
                ).fetchall()
            }
            matched = [
                u
                for u in utterances
                if detected.intersection(str(s).split(":")[0] for s in u["segment_ids"])
            ]
            if not matched:
                continue
            start = min(int(u["first_cursor"]) for u in matched)
            scope = [u for u in utterances if int(u["last_cursor"]) >= start]
            if any(not u.get("ready") for u in scope):
                continue
            topics = rank_topics(topic_projection(utterances, detected))
            if not topics:
                continue
            kakao_detected = {
                str(r[0])
                for r in self.connection.execute(
                    """SELECT event.segment_id FROM watch_detection_events event
                   JOIN watch_rules rule ON rule.id=event.rule_id
                   JOIN transcript_segment_revisions revision ON revision.id=event.revision_id
                   WHERE event.subscriber_id=%s AND event.broadcast_id=%s AND revision.event_cursor<=%s
                     AND rule.enabled AND rule.kakao_enabled AND event.detected_at>=rule.starts_at
                     AND event.episode_id IS NOT NULL""",
                    (subscriber_id, broadcast_id, cutoff),
                ).fetchall()
            }
            kakao_topics = rank_topics(topic_projection(utterances, kakao_detected))
            label = "정회" if kind == "RECESS" else "회의 종료"
            count += self.dispatch(
                subscriber_id=subscriber_id,
                session_id=active[0][2],
                key=f"boundary:{boundary_id}:{subscriber_id}",
                stage=3,
                title=f"{label} · 관심 주제 모아보기",
                body=self.topic_body(topics),
                details={
                    "topics": topics,
                    "meeting_title": title,
                    "boundary_kind": kind,
                    "authority": "LIVE",
                    "as_of": occurred_at.isoformat(),
                    "kakao_body": self.topic_body(kakao_topics),
                },
                source_system=source,
                occurred_at=occurred_at,
                kakao=bool(kakao_topics),
            )
            subscribers.add(subscriber_id)
        for subscriber_id in subscribers:
            WatchRepository(self.connection).prune_notification_history(subscriber_id)
        return count

    def detail(self, subscriber_id: Any, dispatch_id: Any) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT session_id,details,created_at FROM watch_dispatches WHERE id=%s AND subscriber_id=%s",
            (dispatch_id, subscriber_id),
        ).fetchone()
        return (
            {
                "session_id": row[0],
                **row[1],
                "created_at": row[2],
                "dispatch_id": dispatch_id,
            }
            if row
            else None
        )
