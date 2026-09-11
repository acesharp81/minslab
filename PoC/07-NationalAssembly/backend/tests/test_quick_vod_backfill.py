from __future__ import annotations

import unittest
import uuid
import inspect
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from app.ingestion.quick_vod_backfill import (
    concatenate_transport_streams,
    parse_event_playlist,
    persist_backfill_transcription,
    recoverable_duration,
)


class RecordingLiveRepository:
    def __init__(self):
        self.revisions = []

    def append_caption_revision(self, broadcast_id, revision):
        self.revisions.append((broadcast_id, revision))
        return uuid.uuid4(), True


class QuickVodBackfillTests(unittest.TestCase):
    def test_psycopg_like_wildcard_is_escaped(self):
        source = inspect.getsource(__import__(
            "app.ingestion.quick_vod_backfill", fromlist=["main"],
        ))
        self.assertIn("LIKE 'qvod-backfill-%%'", source)

    def test_event_playlist_is_parsed_without_inventing_segment_urls(self):
        content = b"""#EXTM3U
#EXT-X-PLAYLIST-TYPE:EVENT
#EXTINF:60.1,
Playlist0.ts
#EXTINF:59.9,
Playlist1.ts
#EXTINF:60.0,
Playlist2.ts
"""
        segments = parse_event_playlist(
            content, "http://qvod.webcast.go.kr/bon/quickvod/test/playlist.m3u8",
        )
        self.assertEqual(3, len(segments))
        self.assertEqual(
            "http://qvod.webcast.go.kr/bon/quickvod/test/Playlist0.ts",
            segments[0].url,
        )
        self.assertEqual((2, 120.0), recoverable_duration(segments, 124.0))

    def test_partial_segment_at_live_boundary_is_excluded(self):
        content = b"#EXTM3U\n#EXT-X-PLAYLIST-TYPE:EVENT\n#EXTINF:60,\na.ts\n#EXTINF:60,\nb.ts\n"
        segments = parse_event_playlist(content, "https://example.test/playlist.m3u8")
        self.assertEqual((1, 60.0), recoverable_duration(segments, 119.999))

    def test_transport_streams_are_concatenated_in_playlist_order(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "000000.ts"
            second = root / "000001.ts"
            target = root / "combined.ts"
            first.write_bytes(b"first-segment")
            second.write_bytes(b"second-segment")

            concatenate_transport_streams([first, second], target)

            self.assertEqual(b"first-segmentsecond-segment", target.read_bytes())

    def test_sliding_live_playlist_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "not an EVENT playlist"):
            parse_event_playlist(
                b"#EXTM3U\n#EXTINF:6,\nlive.ts\n",
                "https://example.test/live.m3u8",
            )

    def test_backfill_preserves_original_timeline_and_source(self):
        repository = RecordingLiveRepository()
        start_at = datetime(2026, 9, 9, 14, 9, tzinfo=timezone.utc)
        result = SimpleNamespace(
            response_payload={"text": "복구 발언"},
            segments=[{
                "text": "복구 발언", "speaker": "speaker_0",
                "start_seconds": 61.5, "end_seconds": 65.25,
            }],
        )
        artifact = SimpleNamespace(content_hash="a" * 64, content_path="/tmp/raw")
        inserted = persist_backfill_transcription(
            broadcast_id=uuid.uuid4(),
            playlist_url="https://example.test/quick/playlist.m3u8",
            playlist_start_at=start_at,
            duration_seconds=120.0,
            audio_artifact=artifact,
            response_artifact=artifact,
            result=result,
            model="voxtral-mini-latest",
            live_repository=repository,
        )
        revision = repository.revisions[0][1]
        self.assertEqual(1, inserted)
        self.assertEqual(61500, revision.start_offset_ms)
        self.assertEqual(65250, revision.end_offset_ms)
        self.assertEqual(start_at.timestamp() + 65.25, revision.received_at.timestamp())
        self.assertEqual("assembly_quick_vod_transcription", revision.source.source_type)
        self.assertTrue(revision.source_segment_id.startswith("qvod-backfill-"))


if __name__ == "__main__":
    unittest.main()
