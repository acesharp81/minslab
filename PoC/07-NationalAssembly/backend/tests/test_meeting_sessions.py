from __future__ import annotations

import json
import unittest
import uuid
from datetime import datetime, timedelta, timezone

from app.services.meeting_sessions import (
    SESSION_GAP_SECONDS,
    attach_meeting_sessions,
    build_meeting_sessions,
)


class MeetingSessionTests(unittest.TestCase):
    def utterance(
        self, index: int, minutes: int, topic: str,
        broadcast_id: uuid.UUID,
    ) -> dict[str, object]:
        moment = datetime(2026, 8, 31, tzinfo=timezone.utc) + timedelta(minutes=minutes)
        return {
            "utterance_id": f"u-{index}",
            "broadcast_id": broadcast_id,
            "speaker_label": "위원",
            "text": f"{topic} 관련 발언 {index}",
            "start_at": moment,
            "end_at": moment + timedelta(seconds=20),
            "first_cursor": index,
            "last_cursor": index,
            "live_insight": {
                "topic": topic,
                "topic_key": topic,
                "owners": ["행정안전부"],
                "task": None,
            },
        }

    def test_one_to_n_sessions_are_inferred_from_thirty_minute_caption_gaps(self):
        broadcast_id = uuid.uuid4()
        utterances = [
            self.utterance(1, 0, "오전 예산 심사", broadcast_id),
            self.utterance(2, 10, "오전 예산 심사", broadcast_id),
            self.utterance(3, 120, "오후 재정 심사", broadcast_id),
            self.utterance(4, 130, "오후 재정 심사", broadcast_id),
            self.utterance(5, 240, "저녁 결산 심사", broadcast_id),
        ]
        sessions = build_meeting_sessions(
            utterances, lifecycle_by_broadcast={broadcast_id: "LIVE"},
        )
        self.assertEqual(30 * 60, SESSION_GAP_SECONDS)
        self.assertEqual(3, len(sessions))
        self.assertEqual(
            ["CHECKPOINTED", "CHECKPOINTED", "ACTIVE"],
            [item["status"] for item in sessions],
        )
        self.assertEqual(
            ["session-1", "session-1", "session-2", "session-2", "session-3"],
            [item["meeting_session_id"] for item in utterances],
        )
        json.dumps(sessions)

    def test_single_continuous_meeting_remains_one_session(self):
        broadcast_id = uuid.uuid4()
        utterances = [
            self.utterance(1, 0, "법률 심사", broadcast_id),
            self.utterance(2, 20, "법률 심사", broadcast_id),
        ]
        sessions = build_meeting_sessions(
            utterances, lifecycle_by_broadcast={broadcast_id: "ENDED"},
        )
        self.assertEqual(1, len(sessions))
        self.assertEqual("CHECKPOINTED", sessions[0]["status"])

    def test_sessions_are_attached_to_saved_provisional_brief_without_llm(self):
        broadcast_id = uuid.uuid4()
        utterances = [
            self.utterance(1, 0, "행정안전 점검", broadcast_id),
            self.utterance(2, 60, "재난 대응 점검", broadcast_id),
        ]
        result = attach_meeting_sessions(
            {"headline": "회의 결과", "topics": [], "tasks": []},
            utterances,
            lifecycle_by_broadcast={broadcast_id: "ENDED"},
        )
        self.assertEqual(2, result["meeting_session_count"])
        self.assertEqual("meeting-sessions/1.0", result["meeting_session_version"])
        self.assertTrue(all(item["topics"] for item in result["meeting_sessions"]))


if __name__ == "__main__":
    unittest.main()
