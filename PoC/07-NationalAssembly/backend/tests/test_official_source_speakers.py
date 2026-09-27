from __future__ import annotations

import unittest

from app.services.official_source_speakers import source_first_speaker_points
from app.services.transcript_presentation import (
    expand_source_speaker_segments, utterance_content_hash,
)
from app.services.official_reconciliation import align_live_segments


class OfficialSourceSpeakerTests(unittest.TestCase):
    def test_official_text_replaces_wrong_summary_and_splits_speakers(self) -> None:
        brief = {"topics": [{"speaker_points": [{
            "id": "point-1", "speaker_label": "화자 0",
            "summary": "관련 없는 사업을 추진했다.",
            "evidence_ids": ["live-1"],
            "official_evidence_ids": ["official-1", "official-2"],
        }]}]}
        official = [
            {"utterance_id": "official-1", "speaker_label": "김위원",
             "text": "사업 추진을 중단했습니다."},
            {"utterance_id": "official-2", "speaker_label": "박장관",
             "text": "추가 검토를 요청합니다."},
        ]
        result, stats = source_first_speaker_points(brief, official)
        points = result["topics"][0]["speaker_points"]
        self.assertEqual([point["speaker_label"] for point in points],
                         ["김위원", "박장관"])
        self.assertEqual([point["summary"] for point in points],
                         ["사업 추진을 중단했습니다.", "추가 검토를 요청합니다."])
        self.assertEqual([point["official_evidence_ids"] for point in points],
                         [["official-1"], ["official-2"]])
        self.assertEqual(stats["split_speaker_points"], 1)
        self.assertEqual(brief["topics"][0]["speaker_points"][0]["summary"],
                         "관련 없는 사업을 추진했다.")

    def test_official_view_neutralizes_unverified_summary_attribution(self) -> None:
        brief = {"topics": [{
            "summary": "화자 0은 질의하고 화자1은 답변했다.",
            "_official_diffs": {"summary": [{"kind": "added", "text": "화자 0"}]},
            "speaker_points": [{
                "id": "point-1", "speaker_label": "화자 0",
                "summary": "질문했다.", "official_evidence_ids": ["official-1"],
            }],
        }]}
        result, _ = source_first_speaker_points(brief, [{
            "utterance_id": "official-1", "speaker_label": "김위원",
            "text": "질의하겠습니다.",
        }])
        topic = result["topics"][0]
        self.assertEqual(topic["summary"], "발언자는 질의하고 발언자는 답변했다.")
        self.assertEqual(topic["provisional_summary"], brief["topics"][0]["summary"])
        self.assertEqual(topic["speaker_points"][0]["speaker_label"], "김위원")
        self.assertNotIn("summary", topic["_official_diffs"])
        self.assertEqual(brief["topics"][0]["summary"], "화자 0은 질의하고 화자1은 답변했다.")

    def test_split_caption_does_not_inherit_revision_wide_speaker(self) -> None:
        pieces = expand_source_speaker_segments([{
            "segment_id": "segment-1", "revision_id": "revision-1",
            "official_reconciliation": {
                "status": "MATCHED", "official_speaker_name": "첫 화자",
            },
            "source_speaker_segments": [
                {"speaker": "0", "text": "첫 발언"},
                {"speaker": "1", "text": "둘째 발언"},
            ],
        }])
        self.assertEqual(len(pieces), 2)
        self.assertTrue(all(
            piece["official_reconciliation"] is None for piece in pieces
        ))

    def test_split_caption_uses_only_text_hash_guarded_part_match(self) -> None:
        left = "첫 번째 위원 발언입니다"
        right = "두 번째 장관 답변입니다"
        pieces = expand_source_speaker_segments([{
            "segment_id": "segment-2", "revision_id": "revision-2",
            "source_speaker_segments": [
                {"speaker": "0", "text": left},
                {"speaker": "1", "text": right},
            ],
            "source_part_reconciliations": {
                0: {"status": "MATCHED", "source_text_hash": utterance_content_hash(left),
                    "official_speaker_name": "위원"},
                1: {"status": "MATCHED", "source_text_hash": "old-hash",
                    "official_speaker_name": "잘못된 이름"},
            },
        }])
        self.assertEqual(pieces[0]["official_reconciliation"]["official_speaker_name"],
                         "위원")
        self.assertIsNone(pieces[1]["official_reconciliation"])

    def test_split_revision_can_keep_part_matches_without_revision_guess(self) -> None:
        first = "첫 번째 위원이 회의 안건에 관하여 구체적으로 질의합니다"
        second = "두 번째 장관이 관련 사업의 추진 여부를 명확히 답변합니다"
        segments = [{
            "revision_id": "revision", "segment_id": f"segment:{index}",
            "text": text, "source_part_index": index, "source_part_count": 2,
        } for index, text in enumerate((first, second))]
        official = [{
            "utterance_id": f"official-{index}", "sequence_number": index + 1,
            "speaker_name": name, "text": text,
        } for index, (name, text) in enumerate((("위원", first), ("장관", second)))]
        self.assertEqual(len(align_live_segments(segments, official)), 0)
        matches = align_live_segments(
            segments, official, retain_conflicted_revisions=True,
        )
        self.assertEqual([row["source_part_index"] for row in matches], [0, 1])
        self.assertEqual([row["official_speaker_name"] for row in matches],
                         ["위원", "장관"])

    def test_missing_current_document_source_is_draft_only(self) -> None:
        brief = {"topics": [{"speaker_points": [{
            "id": "point-2", "speaker_label": "기존 이름",
            "summary": "초안 요지", "evidence_ids": ["live-2"],
            "official_evidence_ids": ["old-document-utterance"],
        }]}]}
        result, stats = source_first_speaker_points(brief, [])
        topic = result["topics"][0]
        self.assertEqual(topic["speaker_points"], [])
        self.assertEqual(topic["draft_only_speaker_points"][0]["speaker_label"],
                         "화자 미확인")
        self.assertEqual(topic["draft_only_speaker_points"][0]["evidence_ids"],
                         ["live-2"])
        self.assertEqual(stats["missing_source_ids"], 1)


if __name__ == "__main__":
    unittest.main()
