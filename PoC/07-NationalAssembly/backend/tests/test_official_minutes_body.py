from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from app.adapters.national_assembly.base import AdapterError, SourcePayload
from app.adapters.official_minutes_body import (
    OfficialMinutesBodyAdapter,
    explicit_spoken_agenda_ref,
    normalized_match_text,
    semantic_content_hash,
)
from app.ingestion.official_minutes_body import body_view_url


FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_official_minutes_body.html"


class OfficialMinutesBodyTests(unittest.TestCase):
    def test_parses_source_spans_speakers_agenda_and_temporary_stage(self):
        payload = SourcePayload(
            "committee_minutes_body", FIXTURE.read_bytes(), "text/html; charset=UTF-8",
            datetime.now(timezone.utc),
            "https://record.assembly.go.kr/assembly/viewer/minutes/xml.do?id=1&type=view", 200,
        )
        body = OfficialMinutesBodyAdapter().parse(payload)
        self.assertEqual(body.conference_id, "N000001")
        self.assertEqual(body.publication_stage, "TEMPORARY")
        self.assertEqual(len(body.utterances), 3)
        self.assertEqual(body.utterances[1].source_span_id, "spk_sub3-1")
        self.assertEqual(body.utterances[1].agenda_item_ref, "item5")
        self.assertEqual(body.utterances[1].speaker_name, "김위원")

    def test_view_url_only_accepts_official_https_host_and_numeric_id(self):
        value = body_view_url(
            "https://record.assembly.go.kr/assembly/viewer/minutes/xml.do?id=57073&type=summary"
        )
        self.assertIn("id=57073", value)
        self.assertIn("type=view", value)
        with self.assertRaises(AdapterError):
            body_view_url("https://example.invalid/assembly/viewer/minutes/xml.do?id=57073")

    def test_normalized_match_is_exact_character_based(self):
        self.assertEqual(normalized_match_text("선거 관리·부실"), "선거관리부실")

    def test_explicit_spoken_item_number_is_narrowly_detected(self):
        self.assertEqual(explicit_spoken_agenda_ref("15항 관련해서 말씀드리겠습니다."), "item15")
        self.assertEqual(explicit_spoken_agenda_ref("제3번 안건에 대해 질의하겠습니다."), "item3")
        self.assertIsNone(explicit_spoken_agenda_ref("예산 15항목을 검토했습니다."))

    def test_semantic_hash_ignores_source_wrapper_but_tracks_meaning(self):
        payload = SourcePayload(
            "committee_minutes_body", FIXTURE.read_bytes(), "text/html; charset=UTF-8",
            datetime.now(timezone.utc),
            "https://record.assembly.go.kr/assembly/viewer/minutes/xml.do?id=1&type=view", 200,
        )
        body = OfficialMinutesBodyAdapter().parse(payload)
        self.assertEqual(semantic_content_hash(body), semantic_content_hash(replace(body)))
        self.assertNotEqual(
            semantic_content_hash(body),
            semantic_content_hash(replace(body, publication_stage="FINAL")),
        )


if __name__ == "__main__":
    unittest.main()
