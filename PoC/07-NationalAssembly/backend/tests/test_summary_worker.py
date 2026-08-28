from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.ingestion.summary_worker import closed_utterances


class SummaryWorkerTests(unittest.TestCase):
    def _segments(self):
        started = datetime(2026, 8, 22, tzinfo=timezone.utc)
        return [
            {
                "broadcast_id": "broadcast-1", "segment_id": f"s{index}",
                "revision_id": f"r{index}", "cursor": index,
                "received_at": started + timedelta(seconds=index),
                "speaker_label": speaker, "text": text, "is_final": True,
            }
            for index, (speaker, text) in enumerate([
                ("0", "첫 문장"), ("0", "둘째 문장"), ("1", "답변 시작"),
            ], start=1)
        ]

    def test_live_excludes_open_last_speaker_turn(self):
        result = closed_utterances(self._segments(), lifecycle_status="LIVE")
        self.assertEqual(1, len(result))
        self.assertEqual("첫 문장 둘째 문장", result[0]["text"])

    def test_transient_unknown_partial_does_not_close_live_turn(self):
        segments = self._segments()[:2]
        segments[-1]["speaker_label"] = "-1"
        segments[-1]["is_final"] = False
        self.assertEqual([], closed_utterances(segments, lifecycle_status="LIVE"))

    def test_live_does_not_summarize_a_closed_but_unfinalized_source_turn(self):
        segments = self._segments()[:2]
        segments[0]["is_final"] = False
        segments[1]["speaker_label"] = "1"
        result = closed_utterances(segments, lifecycle_status="LIVE")
        self.assertEqual([], result)


    def test_ended_includes_final_speaker_turn(self):
        result = closed_utterances(self._segments(), lifecycle_status="ENDED")
        self.assertEqual(2, len(result))
        self.assertEqual("답변 시작", result[-1]["text"])


if __name__ == "__main__":
    def test_worker_and_backfill_use_the_same_snapshot_as_the_screen(self):
        backend = Path(__file__).resolve().parents[1]
        worker = (backend / "app/ingestion/summary_worker.py").read_text()
        backfill = (backend / "app/ingestion/summary_backfill.py").read_text()
        self.assertIn("broadcast_transcript_snapshot", worker)
        self.assertIn("ended_transcript_snapshot", backfill)
        self.assertNotIn("final_caption_revisions", worker)
        self.assertNotIn("final_caption_revisions", backfill)

    unittest.main()
