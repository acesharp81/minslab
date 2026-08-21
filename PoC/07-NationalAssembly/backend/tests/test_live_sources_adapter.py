from __future__ import annotations

import unittest
from pathlib import Path

from app.adapters.live_sources import (
    parse_assembly_caption_message,
    parse_assembly_live_list,
    parse_assembly_live_play,
    parse_ktv_player_contract,
)


FIXTURES = Path(__file__).parent / "fixtures"


class LiveSourcesAdapterTests(unittest.TestCase):
    def test_parses_only_three_target_committees(self):
        result = parse_assembly_live_list((FIXTURES / "synthetic_assembly_live_list.json").read_bytes())
        self.assertEqual(result["count"], 3)
        self.assertEqual(result["live_count"], 1)
        live = next(item for item in result["items"] if item["is_live"])
        self.assertEqual(live["committee_name"], "법제사법위원회")
        self.assertTrue(live["has_caption_service"])

    def test_ktv_contract_does_not_invent_caption_track(self):
        result = parse_ktv_player_contract((FIXTURES / "synthetic_ktv_player.html").read_bytes())
        self.assertEqual(result["content_id"], "999999")
        self.assertTrue(result["player_detected"])
        self.assertFalse(result["machine_caption_track_detected"])
        self.assertEqual(result["caption_contract_status"], "UNVERIFIED")

    def test_parses_live_play_caption_websocket_contract(self):
        result = parse_assembly_live_play((FIXTURES / "synthetic_assembly_live_play.json").read_bytes())
        self.assertTrue(result["is_live"])
        self.assertEqual(result["caption_capture_status"], "READY_TO_CAPTURE")
        self.assertEqual(result["caption_websocket_url"], "wss://example.invalid:8091/aistt/law/hls")
        self.assertEqual(result["stream_url"], "https://example.invalid/law.m3u8")

    def test_parses_caption_revisions_and_speaker_segments(self):
        result = parse_assembly_caption_message(
            '{"segment":7,"transcript":"법률 지원을 점검합니다","transcripts":[["1","-법률 지원"]],"scd":"A","final":true}'
        )
        self.assertEqual(result["segment_id"], "7")
        self.assertTrue(result["is_final"])
        self.assertEqual(result["speaker_segments"][0]["text"], "법률 지원")


if __name__ == "__main__":
    unittest.main()
