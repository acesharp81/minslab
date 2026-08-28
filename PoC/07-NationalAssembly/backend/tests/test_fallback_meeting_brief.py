from __future__ import annotations

import unittest

from app.services.fallback_meeting_brief import build_fallback_meeting_brief


class FallbackMeetingBriefTests(unittest.TestCase):
    def test_builds_result_shape_from_saved_evidence_without_llm(self):
        utterances = [{
            "utterance_id": "u-1",
            "revision_ids": ["r-1", "r-2"],
            "speaker_label": "위원장",
            "text": "예산 집행 현황을 점검하고 보완 계획을 보고해야 합니다.",
            "insight_hints": [{
                "topic": "예산·재정 집행",
                "task": "보완 계획을 보고해야 합니다.",
                "task_status": "OPEN",
                "resolution": False,
                "ministries": ["기획재정부"],
            }],
        }]
        review_topics = [{
            "topic": "예산·재정 집행",
            "major_quote": "예산 집행 현황과 보완 계획을 점검했습니다.",
            "speaker_label": "위원장",
            "evidence_revision_ids": ["r-1", "r-2"],
            "representative_revision_id": "r-1",
        }]
        result = build_fallback_meeting_brief(
            {"title": "제01차 예산결산특별위원회", "committee_name": "예산결산특별위원회"},
            utterances,
            review_topics,
        )
        self.assertEqual("DETERMINISTIC_FALLBACK", result["result_kind"])
        self.assertEqual(["u-1"], result["topics"][0]["evidence_ids"])
        self.assertEqual("위원장", result["topics"][0]["speaker_points"][0]["speaker_label"])
        self.assertEqual(["u-1"], result["tasks"][0]["evidence_ids"])
        self.assertEqual(1, result["utterance_count"])


    def test_limits_topic_evidence_to_three_and_prioritizes_representative(self):
        utterances = [
            {
                "utterance_id": f"u-{index}",
                "revision_ids": [f"r-{index}"],
                "speaker_label": f"화자 {index}",
                "text": f"근거 {index}",
                "insight_hints": [],
            }
            for index in range(1, 5)
        ]
        result = build_fallback_meeting_brief(
            {"title": "회의", "committee_name": "위원회"},
            utterances,
            [{
                "topic": "주제",
                "major_quote": "대표 발언",
                "evidence_revision_ids": ["r-1", "r-2", "r-3", "r-4"],
                "representative_revision_id": "r-4",
            }],
        )
        self.assertEqual(["u-4", "u-1", "u-2"], result["topics"][0]["evidence_ids"])

if __name__ == "__main__":
    unittest.main()
