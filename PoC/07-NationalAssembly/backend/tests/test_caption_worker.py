from __future__ import annotations

import json
import tempfile
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.ingestion.caption_worker import persist_caption_message


class RecordingSink:
    def __init__(self):
        self.revisions = []

    def append_caption_revision(self, broadcast_id, revision):
        self.revisions.append((broadcast_id, revision))
        return uuid.UUID("00000000-0000-4000-8000-000000000002"), True


class CaptionWorkerTests(unittest.TestCase):
    def test_raw_message_is_saved_before_normalized_revision(self):
        sink = RecordingSink()
        broadcast_id = uuid.UUID("00000000-0000-4000-8000-000000000001")
        message = json.dumps({
            "segment": 7,
            "transcript": "법률 지원을 점검합니다",
            "transcripts": [["위원장", "-법률 지원을 점검합니다"]],
            "scd": "A",
            "final": False,
        }, ensure_ascii=False)
        with tempfile.TemporaryDirectory() as directory:
            result = persist_caption_message(
                broadcast_id=broadcast_id,
                external_id="SIM-LAW-001",
                source_url="wss://example.invalid/aistt/law/hls",
                raw_message=message,
                received_at=datetime(2026, 8, 12, tzinfo=timezone.utc),
                raw_dir=Path(directory),
                sink=sink,
            )
            raw_path = sink.revisions[0][1].source.raw_path
            self.assertTrue(raw_path.is_file())
            self.assertEqual(raw_path.read_text(encoding="utf-8"), message)
        revision = sink.revisions[0][1]
        self.assertEqual(revision.source_segment_id, "7")
        self.assertEqual(revision.speaker_label, "위원장")
        self.assertFalse(revision.is_final)
        self.assertEqual(revision.source.content_hash, result["content_hash"])
        self.assertEqual(revision.source.metadata["broadcast_external_id"], "SIM-LAW-001")

    def test_repeated_raw_message_is_marked_duplicate(self):
        sink = RecordingSink()
        message = '{"segment":8,"transcript":"예산을 점검합니다","final":true}'
        with tempfile.TemporaryDirectory() as directory:
            arguments = {
                "broadcast_id": uuid.uuid4(),
                "external_id": "SIM-BUDGET-001",
                "source_url": "wss://example.invalid/aistt/budget/hls",
                "raw_message": message,
                "received_at": datetime(2026, 8, 12, tzinfo=timezone.utc),
                "raw_dir": Path(directory),
                "sink": sink,
            }
            first = persist_caption_message(**arguments)
            second = persist_caption_message(**arguments)
        self.assertFalse(first["raw_duplicate"])
        self.assertTrue(second["raw_duplicate"])
        self.assertEqual(first["content_hash"], second["content_hash"])


if __name__ == "__main__":
    unittest.main()
