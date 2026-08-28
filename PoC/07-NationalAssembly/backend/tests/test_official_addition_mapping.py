from __future__ import annotations

import unittest

from app.services.official_reconciliation import apply_official_edits
from app.services.integrated_brief_evidence import (
    attach_official_evidence_from_changes,
    official_evidence_ids,
)


class OfficialAdditionMappingTests(unittest.TestCase):
    def setUp(self):
        self.base = {
            "headline": "회의", "summary": "요약",
            "topics": [{
                "id": "topic-1", "title": "소년법 시설 개선",
                "summary": "청소년 보호시설과 교육 지원을 논의했다.",
            }],
            "tasks": [],
        }

    def test_unrelated_task_is_not_forced_into_existing_topic(self):
        integrated, changes = apply_official_edits(self.base, [{
            "entity_type": "task", "entity_id": "", "operation": "ADD",
            "field": "entity", "new_text": "", "new_values": [],
            "title": "등기 전산 장비 예산 불용액 원인 분석", "summary": "",
            "topic_id": "topic-1", "ministries": ["기획재정부"],
            "official_utterance_ids": ["official-1"],
        }])
        self.assertEqual(integrated["tasks"], [])
        self.assertEqual(changes, [])

    def test_new_topic_alias_connects_new_task(self):
        edits = [
            {
                "entity_type": "task", "entity_id": "", "operation": "ADD",
                "field": "entity", "new_text": "", "new_values": [],
                "title": "등기 전산 장비 예산 불용액 원인 분석", "summary": "",
                "topic_id": "new-topic-1", "ministries": ["기획재정부"],
                "official_utterance_ids": ["official-1"],
            },
            {
                "entity_type": "topic", "entity_id": "", "operation": "ADD",
                "field": "entity", "new_text": "", "new_values": [],
                "title": "등기 특별회계 예산 집행", "summary": "전산 장비 불용액을 논의했다.",
                "topic_id": "new-topic-1", "ministries": ["기획재정부"],
                "official_utterance_ids": ["official-1"],
            },
        ]
        integrated, changes = apply_official_edits(self.base, edits)
        self.assertEqual(len(integrated["topics"]), 2)
        self.assertEqual(len(integrated["tasks"]), 1)
        self.assertEqual(integrated["tasks"][0]["topic_id"], "official-topic-2")
        self.assertEqual(len(changes), 2)

    def test_cached_added_topic_recovers_official_evidence_from_change(self):
        cached = {
            "topics": [{
                "id": "official-topic-9",
                "title": "가상자산 민사집행규정 개정 논의",
            }],
            "tasks": [],
        }
        repaired = attach_official_evidence_from_changes(cached, [{
            "entity_type": "topic",
            "entity_id": "official-topic-9",
            "operation": "ADD",
            "official_utterance_ids": ["official-virtual-asset-1"],
        }])
        self.assertEqual(
            official_evidence_ids(repaired, "topic", "official-topic-9"),
            ["official-virtual-asset-1"],
        )
        self.assertNotIn("official_evidence_ids", cached["topics"][0])


if __name__ == "__main__":
    unittest.main()
