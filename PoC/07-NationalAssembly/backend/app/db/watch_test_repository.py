from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from psycopg.types.json import Jsonb

from .live_repository import CaptionRevision, LiveBroadcastObservation, LiveRepository
from .schedule_repository import SourceVersionInput
from ..services.watch_replay_script import (
    REPLAY_MODE,
    REPLAY_SOURCE_LABEL,
    REPLAY_TITLE,
    REPLAY_VIDEO_URL,
    build_hasi_ai_replay_script,
)
from ..services.watch_test_script import build_watch_test_script


class WatchTestRepository:
    def __init__(self, connection: Any):
        self.connection = connection

    def start(
        self,
        subscriber_id: uuid.UUID,
        keyword: str,
        now: datetime,
        *,
        replay_mode: str = "SYNTHETIC",
        kakao_delivery_enabled: bool = False,
    ) -> dict[str, Any]:
        active = self.connection.execute(
            """
            SELECT test.id FROM watch_test_broadcasts test
            WHERE test.subscriber_id = %s AND test.status IN ('QUEUED', 'LIVE')
            ORDER BY test.created_at DESC LIMIT 1
            """,
            (subscriber_id,),
        ).fetchone()
        if active:
            return self.get(subscriber_id, active[0])
        test_id = uuid.uuid4()
        external_id = f"watch-test-{test_id}"
        is_replay = replay_mode == REPLAY_MODE
        script = build_hasi_ai_replay_script() if is_replay else build_watch_test_script(keyword)
        source_system = (
            "poc07.replay.kakao" if is_replay and kakao_delivery_enabled
            else "poc07.replay.local" if is_replay
            else "poc07.test"
        )
        source = self._source(
            external_id,
            {
                "test_id": str(test_id),
                "replay_mode": replay_mode,
                "source_label": REPLAY_SOURCE_LABEL if is_replay else "synthetic",
                "kakao_delivery_enabled": bool(kakao_delivery_enabled),
            },
            now,
        )
        broadcast_id = LiveRepository(self.connection).observe_broadcast(
            LiveBroadcastObservation(
                institution="LEGISLATURE" if is_replay else "EXECUTIVE",
                external_id=external_id,
                committee_name="행정안전위원회" if is_replay else "관심주제 알림 테스트",
                title=REPLAY_TITLE if is_replay else f"관심주제 알림 가상방송 · {keyword}",
                caption_source_status="TEST_CAPTION",
                caption_websocket_url=None,
                thumbnail_url=None,
                observed_at=now,
                source=source,
                source_system=source_system,
            )
        )
        self.connection.execute(
            """
            INSERT INTO watch_test_broadcasts (
                id, subscriber_id, broadcast_id, status, current_step,
                total_steps, next_emit_at, script, started_at, replay_mode,
                video_embed_url, kakao_delivery_enabled
            ) VALUES (%s, %s, %s, %s, 0, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                test_id, subscriber_id, broadcast_id,
                "QUEUED" if is_replay else "LIVE", len(script),
                now + timedelta(seconds=15) if is_replay else now,
                Jsonb(script), None if is_replay else now, replay_mode,
                REPLAY_VIDEO_URL if is_replay else None,
                bool(kakao_delivery_enabled),
            ),
        )
        return self.get(subscriber_id, test_id)

    def activate(self, subscriber_id: uuid.UUID, test_id: uuid.UUID, now: datetime) -> dict[str, Any] | None:
        self.connection.execute(
            """
            UPDATE watch_test_broadcasts
            SET status = 'LIVE', next_emit_at = %s,
                started_at = COALESCE(started_at, %s), updated_at = now()
            WHERE id = %s AND subscriber_id = %s AND status = 'QUEUED'
            """,
            (now, now, test_id, subscriber_id),
        )
        return self.get(subscriber_id, test_id)

    def get(self, subscriber_id: uuid.UUID, test_id: uuid.UUID) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            SELECT test.id, test.broadcast_id, test.status, test.current_step,
                   test.total_steps, test.started_at, test.ended_at, test.created_at,
                   broadcast.title, broadcast.lifecycle_status,
                   broadcast.last_caption_received_at, test.replay_mode,
                   test.video_embed_url, test.kakao_delivery_enabled,
                   broadcast.source_system, broadcast.institution,
                   broadcast.committee_name
            FROM watch_test_broadcasts test
            JOIN live_broadcasts broadcast ON broadcast.id = test.broadcast_id
            WHERE test.id = %s AND test.subscriber_id = %s
            """,
            (test_id, subscriber_id),
        ).fetchone()
        if not row:
            return None
        return dict(zip(
            (
                "test_id", "broadcast_id", "status", "current_step", "total_steps",
                "started_at", "ended_at", "created_at", "title", "lifecycle_status",
                "last_caption_received_at", "replay_mode", "video_embed_url",
                "kakao_delivery_enabled", "source_system", "institution",
                "committee_name",
            ),
            row,
            strict=True,
        ))

    def latest(self, subscriber_id: uuid.UUID) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            SELECT id FROM watch_test_broadcasts WHERE subscriber_id = %s
            ORDER BY created_at DESC LIMIT 1
            """,
            (subscriber_id,),
        ).fetchone()
        return self.get(subscriber_id, row[0]) if row else None

    def emit_due(self, now: datetime, interval_seconds: int = 3) -> bool:
        row = self.connection.execute(
            """
            SELECT id, broadcast_id, current_step, total_steps, script
            FROM watch_test_broadcasts
            WHERE status IN ('QUEUED', 'LIVE') AND next_emit_at <= %s
            ORDER BY next_emit_at FOR UPDATE SKIP LOCKED LIMIT 1
            """,
            (now,),
        ).fetchone()
        if not row:
            return False
        test_id, broadcast_id, current_step, total_steps, script = row
        step = script[current_step]
        segment_id = str(step.get("source_segment_id") or f"test-{current_step + 1:03d}")
        elapsed_seconds = int(step.get("elapsed_seconds") or current_step * interval_seconds)
        next_delay_seconds = max(1, min(90, int(step.get("delay_seconds") or interval_seconds)))
        source = self._source(
            f"{test_id}/{segment_id}",
            {"test_id": str(test_id), "step": current_step + 1},
            now,
        )
        LiveRepository(self.connection).append_caption_revision(
            broadcast_id,
            CaptionRevision(
                source_segment_id=segment_id,
                text=str(step["text"]),
                speaker_label=str(step["speaker"]),
                is_final=True,
                received_at=now,
                source_payload={
                    "test_broadcast": True,
                    "step": current_step + 1,
                    "insight": step.get("insight"),
                },
                source=source,
                start_offset_ms=elapsed_seconds * 1000,
                end_offset_ms=(elapsed_seconds + next_delay_seconds) * 1000,
            ),
        )
        next_step = current_step + 1
        if next_step >= total_steps:
            LiveRepository(self.connection).finish_broadcast(broadcast_id, now)
            self.connection.execute(
                """
                UPDATE watch_test_broadcasts SET status = 'COMPLETED', current_step = %s,
                       ended_at = %s, updated_at = now() WHERE id = %s
                """,
                (next_step, now, test_id),
            )
            self.connection.execute(
                """
                UPDATE watch_sessions SET status = 'ENDED', updated_at = now()
                WHERE broadcast_id = %s
                """,
                (broadcast_id,),
            )
        else:
            self.connection.execute(
                """
                UPDATE watch_test_broadcasts SET status = 'LIVE', current_step = %s,
                       next_emit_at = %s, started_at = COALESCE(started_at, %s),
                       updated_at = now() WHERE id = %s
                """,
                (next_step, now + timedelta(seconds=next_delay_seconds), now, test_id),
            )
        return True

    @staticmethod
    def _source(external_id: str, metadata: dict[str, Any], now: datetime) -> SourceVersionInput:
        payload = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
        return SourceVersionInput(
            source_type="WATCH_TEST_BROADCAST",
            source_url=f"https://local.invalid/poc07/watch-test/{external_id}",
            content_hash=hashlib.sha256(payload.encode("utf-8")).hexdigest(),
            raw_path=Path("watch-test") / f"{external_id.replace('/', '-')}.json",
            retrieved_at=now,
            parser_version="watch-test.v1",
            content_type="application/json",
            metadata=metadata,
        )
