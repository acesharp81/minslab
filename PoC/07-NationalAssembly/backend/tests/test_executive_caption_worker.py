from __future__ import annotations

import unittest
import uuid
import tempfile
import inspect
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.ingestion.executive_caption_worker import (
    audio_duration_ms,
    completed_segment_paths,
    persist_transcription,
    segment_number,
)


class FakeLiveRepository:
    def __init__(self):
        self.revisions = []

    def append_caption_revision(self, broadcast_id, revision):
        self.revisions.append((broadcast_id, revision))
        return uuid.uuid4(), True


class FakeAudioRepository:
    def __init__(self):
        self.completed = None
        self.usage = None

    def complete(self, chunk_id, **kwargs):
        self.completed = (chunk_id, kwargs)

    def record_usage(self, **kwargs):
        self.usage = kwargs


class ExecutiveCaptionWorkerTests(unittest.TestCase):
    def test_worker_logs_only_operational_progress_fields(self):
        source = inspect.getsource(__import__(
            "app.ingestion.executive_caption_worker", fromlist=["main"],
        ))
        self.assertIn('"event": "executive.audio.started"', source)
        self.assertIn('"event": "executive.audio.progress"', source)
        self.assertNotIn('"transcript_text"', source)

    def test_audio_duration_uses_ffprobe_and_has_safe_fallback(self):
        with patch(
            "app.ingestion.executive_caption_worker.subprocess.run",
            return_value=SimpleNamespace(returncode=0, stdout="2.345\n"),
        ):
            self.assertEqual(
                2345, audio_duration_ms(Path("/tmp/chunk.mp3"), fallback_seconds=60),
            )
        with patch(
            "app.ingestion.executive_caption_worker.subprocess.run",
            return_value=SimpleNamespace(returncode=1, stdout=""),
        ):
            self.assertEqual(
                60000, audio_duration_ms(Path("/tmp/chunk.mp3"), fallback_seconds=60),
            )

    def test_continuous_segmenter_keeps_current_file_out_of_consumer_queue(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            paths = [directory / f"chunk-{index:06d}.mp3" for index in range(3)]
            for path in paths:
                path.write_bytes(b"ID3" + b"0" * 1024)
            self.assertEqual(paths[:2], completed_segment_paths(directory, segmenter_running=True))
            self.assertEqual(paths, completed_segment_paths(directory, segmenter_running=False))
            self.assertEqual(2, segment_number(paths[2]))

    def test_diarized_chunk_enters_common_caption_revision_path(self):
        broadcast_id = uuid.uuid4()
        chunk_id = uuid.uuid4()
        chunk = {
            "chunk_id": chunk_id, "broadcast_id": broadcast_id,
            "chunk_number": 2, "content_hash": "a" * 64,
            "raw_path": "/tmp/chunk.mp3", "duration_ms": 60000,
            "start_offset_ms": 119500,
        }
        result = SimpleNamespace(
            segments=[
                {"text": "첫 번째 발언입니다.", "start_seconds": 1.0, "end_seconds": 3.0, "speaker": "speaker_0"},
                {"text": "답변입니다.", "start_seconds": 3.0, "end_seconds": 5.0, "speaker": "speaker_1"},
            ],
            response_payload={"text": "첫 번째 발언입니다. 답변입니다."},
            usage_metadata={"request_id": "req-1", "audio_seconds": 60.0, "cost_usd": 0.003},
        )
        live = FakeLiveRepository()
        audio = FakeAudioRepository()
        inserted = persist_transcription(
            chunk=chunk, result=result, stream_url="https://example.test/live.m3u8",
            live_repository=live, audio_repository=audio,
            model="voxtral-mini-latest",
        )
        self.assertEqual(2, inserted)
        self.assertEqual(["chunk-2:speaker_0", "chunk-2:speaker_1"], [row[1].speaker_label for row in live.revisions])
        self.assertTrue(all(row[1].is_final for row in live.revisions))
        self.assertEqual([120500, 122500], [row[1].start_offset_ms for row in live.revisions])
        self.assertEqual(chunk_id, audio.completed[0])
        self.assertEqual("req-1", audio.usage["request_id"])

    def test_chunk_boundary_can_continue_previous_speaker_without_merging_other_turns(self):
        chunk = {
            "chunk_id": uuid.uuid4(), "broadcast_id": uuid.uuid4(),
            "chunk_number": 3, "content_hash": "b" * 64,
            "raw_path": "/tmp/chunk.mp3", "duration_ms": 60000,
        }
        result = SimpleNamespace(
            segments=[
                {"text": "앞 발언의 계속입니다.", "start_seconds": 0.0, "end_seconds": 2.0, "speaker": "speaker_0"},
                {"text": "새 답변입니다.", "start_seconds": 2.0, "end_seconds": 4.0, "speaker": "speaker_1"},
                {"text": "다시 질의합니다.", "start_seconds": 4.0, "end_seconds": 5.0, "speaker": "speaker_0"},
            ],
            response_payload={"text": "test"},
            usage_metadata={"request_id": "req-2", "audio_seconds": 60.0, "cost_usd": 0.003},
        )
        live, audio = FakeLiveRepository(), FakeAudioRepository()
        persist_transcription(
            chunk=chunk, result=result, stream_url="https://example.test/live.m3u8",
            live_repository=live, audio_repository=audio,
            model="voxtral-mini-latest", continuation_speaker="chunk-2:speaker_1",
        )
        self.assertEqual(
            ["chunk-2:speaker_1", "chunk-3:speaker_1", "chunk-2:speaker_1"],
            [row[1].speaker_label for row in live.revisions],
        )


if __name__ == "__main__":
    unittest.main()
