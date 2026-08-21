from __future__ import annotations

import unittest

from app.services.official_transcript_insights import classify_official_utterance


class OfficialTranscriptInsightTests(unittest.TestCase):
    def test_election_statement_maps_to_topic_and_ministry(self):
        result = classify_official_utterance("선관위 투표용지 부족으로 국민의 참정권이 침해됐습니다.")
        self.assertIn("선거·참정권", result["topics"])
        self.assertIn("행정안전부", result["ministries"])
        self.assertEqual(result["utterance_kind"], "POLICY")
        self.assertIn("선관위", result["evidence_keywords"])

    def test_unknown_statement_is_not_invented_as_policy(self):
        result = classify_official_utterance("수고하셨습니다.")
        self.assertEqual(result["topics"], ["기타 발언"])
        self.assertEqual(result["ministries"], [])
        self.assertEqual(result["utterance_kind"], "OTHER")

    def test_committee_name_does_not_create_policy_or_ministry_false_positive(self):
        result = classify_official_utterance(
            "성원이 되었으므로 제437회 국회 제6차 법제사법위원회를 개회합니다."
        )
        self.assertEqual(result["utterance_kind"], "PROCEDURAL")
        self.assertEqual(result["topics"], ["절차·의결"])
        self.assertEqual(result["ministries"], [])


if __name__ == "__main__":
    unittest.main()
