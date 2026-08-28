from __future__ import annotations

import unittest

from app.services.official_edit_validation import filter_supported_official_edits


class OfficialTopicEvidenceGateTests(unittest.TestCase):
    def test_unrelated_official_sentence_cannot_be_appended_to_topic(self):
        brief = {
            "headline": "회의", "summary": "요약",
            "topics": [{
                "id": "topic-1", "title": "소년법 보호시설 개선",
                "summary": "청소년 시설과 교육 지원을 논의했다.",
            }], "tasks": [],
        }
        after = (
            "청소년 시설과 교육 지원을 논의했다. "
            "또한 등기 전산 장비 불용액과 특별회계 예산을 점검했다."
        )
        edits = filter_supported_official_edits({"edits": [{
            "entity_type": "topic", "entity_id": "topic-1",
            "operation": "UPDATE", "field": "summary", "new_text": after,
            "official_utterance_ids": ["official-1"],
        }]}, brief, [{
            "utterance_id": "official-1",
            "text": "등기 전산 장비 불용액과 특별회계 예산을 점검했다.",
            "ministries": ["기획재정부"],
        }])
        self.assertEqual(edits, [])


if __name__ == "__main__":
    unittest.main()
