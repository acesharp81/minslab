from __future__ import annotations

import unittest
import uuid
from datetime import datetime, timedelta, timezone

from app.services.broadcast_review_v2 import build_broadcast_review, merge_speaker_turns
from app.services.transcript_presentation import (
    apply_speaker_overrides,
    default_speaker_name,
    executive_meeting_content_segments,
    group_transcript_segments,
    utterance_evidence_aliases,
)


class TranscriptPresentationTests(unittest.TestCase):
    def test_internal_audio_diarization_code_is_not_exposed_as_a_name(self):
        from app.services.transcript_presentation import default_speaker_name

        self.assertEqual("화자 미확인", default_speaker_name("chunk-12:speaker_0"))

    def segment(self, index: int, speaker: str, text: str, seconds: int) -> dict:
        return {
            "segment_id": uuid.UUID(int=index),
            "revision_id": uuid.UUID(int=100 + index),
            "broadcast_id": uuid.UUID(int=999),
            "cursor": index,
            "speaker_label": speaker,
            "text": text,
            "received_at": datetime(2026, 8, 21, tzinfo=timezone.utc)
            + timedelta(seconds=seconds),
            "is_final": True,
        }

    def test_executive_meeting_content_starts_at_formal_opening(self):
        raw = [
            self.segment(1, "0", "KTV 사전 인터뷰입니다.", 0),
            self.segment(2, "0", "제38회 국무회의를 시작하겠습니다.", 10),
            self.segment(3, "1", "첫 번째 안건입니다.", 20),
        ]
        filtered = executive_meeting_content_segments(raw)
        self.assertEqual([item["text"] for item in filtered], [
            "제38회 국무회의를 시작하겠습니다.", "첫 번째 안건입니다.",
        ])

    def test_executive_meeting_content_preserves_stream_before_opening_is_seen(self):
        raw = [self.segment(1, "0", "방송 준비 중입니다.", 0)]
        self.assertEqual(executive_meeting_content_segments(raw), raw)

    def test_numeric_source_labels_are_explicitly_unidentified(self):
        self.assertEqual(default_speaker_name("0"), "화자 0 · 이름 미확인")
        self.assertEqual(default_speaker_name("-1"), "화자 미확인")

    def test_saved_evidence_id_matches_expanded_source_piece(self):
        parent = "659b4823-49bd-494b-bc57-01396318798f"
        self.assertEqual({parent, parent + ":0"}, utterance_evidence_aliases(parent + ":0"))


    def test_multiple_source_speakers_in_one_caption_are_separate_turns(self):
        raw = self.segment(1, "1", "질문 답변 추가 질문", 0)
        raw["source_segment_id"] = "7"
        raw["source_speaker_segments"] = [
            {"speaker": "1", "text": "질문"},
            {"speaker": "0", "text": "답변"},
            {"speaker": "1", "text": "추가 질문"},
        ]
        utterances = group_transcript_segments(apply_speaker_overrides([raw], {}))
        self.assertEqual(len(utterances), 3)
        self.assertEqual(
            [item["text"] for item in utterances], ["질문", "답변", "추가 질문"])
        self.assertEqual(
            [item["source_speaker_label"] for item in utterances], ["1", "0", "1"])
        self.assertTrue(all(":" in str(item["utterance_id"]) for item in utterances))

    def test_consecutive_same_speaker_segments_become_one_utterance(self):
        raw = [
            self.segment(1, "1", "첫 문장", 0),
            self.segment(2, "1", "둘째 문장", 5),
            self.segment(3, "0", "응답입니다", 8),
        ]
        presented = apply_speaker_overrides(
            raw, {(uuid.UUID(int=999), "1"): "위원장"},
        )
        utterances = group_transcript_segments(presented)
        self.assertEqual(len(utterances), 2)
        self.assertEqual(utterances[0]["text"], "첫 문장 둘째 문장")
        self.assertEqual(utterances[0]["segment_count"], 2)
        self.assertEqual(utterances[0]["speaker_label"], "위원장")
        self.assertEqual(utterances[1]["speaker_label"], "화자 0 · 이름 미확인")

    def test_same_speaker_stays_one_turn_even_after_long_silence(self):
        raw = apply_speaker_overrides([
            self.segment(1, "1", "앞 발언", 0),
            self.segment(2, "1", "한참 뒤 발언", 30),
        ], {})
        utterances = group_transcript_segments(raw)
        self.assertEqual(len(utterances), 1)
        self.assertEqual(utterances[0]["summary"], "앞 발언 한참 뒤 발언")


    def test_same_speaker_is_split_across_a_long_recess(self):
        raw = apply_speaker_overrides([
            self.segment(1, "1", "정회 전 발언", 0),
            self.segment(2, "1", "속개 후 발언", 6 * 60),
        ], {})
        utterances = group_transcript_segments(raw)
        self.assertEqual(2, len(utterances))
        self.assertEqual(["정회 전 발언", "속개 후 발언"], [
            item["text"] for item in utterances
        ])

    def test_transient_unknown_partial_stays_in_current_speaker_turn(self):
        first = self.segment(1, "1", "확정된 앞 발언", 0)
        partial = self.segment(2, "-1", "실시간으로 들어오는 다음 부분", 2)
        partial["is_final"] = False
        utterances = group_transcript_segments(apply_speaker_overrides([first, partial], {}))
        self.assertEqual(len(utterances), 1)
        self.assertEqual(utterances[0]["source_speaker_label"], "1")
        self.assertEqual(
            utterances[0]["text"],
            "확정된 앞 발언 실시간으로 들어오는 다음 부분",
        )
    def test_long_utterance_has_short_extract_and_full_original(self):
        raw = apply_speaker_overrides([
            self.segment(1, "1", "가" * 200, 0),
            self.segment(2, "1", "나" * 50, 30),
        ], {})
        utterance = group_transcript_segments(raw)[0]
        self.assertTrue(utterance["summary"].endswith("…"))
        self.assertLessEqual(len(utterance["summary"]), 181)
        self.assertEqual(len(utterance["text"]), 251)

    def test_review_uses_merged_turn_as_quote_and_keeps_evidence(self):
        segments = [
            {"revision_id": uuid.UUID(int=1), "cursor": 1, "text": "법무부의", "speaker_label": "1"},
            {"revision_id": uuid.UUID(int=2), "cursor": 2, "text": "결산을 점검합니다", "speaker_label": "1"},
            {"revision_id": uuid.UUID(int=3), "cursor": 3, "text": "답변합니다", "speaker_label": "0"},
        ]
        turns = merge_speaker_turns(segments)
        self.assertEqual(turns[0]["text"], "법무부의 결산을 점검합니다")
        result = build_broadcast_review({"committee_name": "법제사법위원회"}, segments)
        topic = next(item for item in result if item["topic"] == "재정·예산")
        self.assertEqual(topic["major_quote"], "법무부의 결산을 점검합니다")
        self.assertEqual(topic["evidence_revision_ids"], [uuid.UUID(int=1), uuid.UUID(int=2)])


if __name__ == "__main__":
    unittest.main()
