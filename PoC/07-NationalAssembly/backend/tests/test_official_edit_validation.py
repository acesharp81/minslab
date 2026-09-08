from __future__ import annotations

import unittest

from app.services.official_edit_validation import filter_supported_official_edits


class OfficialEditValidationTests(unittest.TestCase):
    def setUp(self):
        self.brief = {
            "headline": "소년법과 보호시설 개선 논의", "summary": "시설 확충을 논의했다.",
            "topics": [{
                "id": "topic-1", "title": "소년법 시설 개선",
                "summary": "청소년 보호시설과 교육 지원", "ministries": ["법무부"],
            }],
            "tasks": [{
                "id": "task-1", "title": "보호시설 확충",
                "summary": "", "ministries": ["법무부"],
            }],
        }
        self.rows = [{
            "utterance_id": "official-1", "text": "노후 등기 전산 장비 예산 불용액을 점검합니다.",
            "ministries": ["기획재정부"],
        }]

    def test_deletion_is_never_automatically_applied(self):
        edits = filter_supported_official_edits({"edits": [{
            "entity_type": "topic", "entity_id": "topic-1",
            "operation": "DELETE", "field": "entity",
            "official_utterance_ids": ["official-1"],
        }]}, self.brief, self.rows)
        self.assertEqual(edits, [])

    def test_unrelated_ministry_change_is_rejected(self):
        edits = filter_supported_official_edits({"edits": [{
            "entity_type": "task", "entity_id": "task-1",
            "operation": "UPDATE", "field": "ministries",
            "new_values": ["법무부", "행정안전부"],
            "official_utterance_ids": ["official-1"],
        }]}, self.brief, self.rows)
        self.assertEqual(edits, [])

    def test_style_only_summary_rewrite_is_rejected(self):
        self.brief["topics"][0]["summary"] = (
            "비상계엄 관련 대법원과 법원행정처의 회의 및 입장을 점검했다."
        )
        rows = [{
            "utterance_id": "official-2",
            "text": "비상계엄 관련 대법원과 법원행정처의 회의 및 입장을 점검했습니다.",
            "ministries": [],
        }]
        edits = filter_supported_official_edits({"edits": [{
            "entity_type": "topic", "entity_id": "topic-1",
            "operation": "UPDATE", "field": "summary",
            "new_text": "대법원과 법원행정처가 비상계엄 관련 회의와 입장을 점검했다.",
            "official_utterance_ids": ["official-2"],
        }]}, self.brief, rows)
        self.assertEqual(edits, [])

    def test_reordered_bullet_summary_is_rejected_as_style_only(self):
        self.brief["topics"][0]["summary"] = (
            "대법원과 법원행정처의 비상계엄 관련 회의 및 입장을 점검했다."
        )
        rows = [{
            "utterance_id": "official-2",
            "text": "비상계엄 관련 회의 및 입장: 대법원·법원행정처 점검.",
            "ministries": [],
        }]
        edits = filter_supported_official_edits({"edits": [{
            "entity_type": "topic", "entity_id": "topic-1",
            "operation": "UPDATE", "field": "summary",
            "new_text": rows[0]["text"],
            "official_utterance_ids": ["official-2"],
        }]}, self.brief, rows)
        self.assertEqual(edits, [])

    def test_large_rewrite_is_kept_for_comparison_but_marked_suppressed(self):
        self.brief["topics"][0]["summary"] = (
            "법무부는 청소년 보호시설 운영 현황과 교육 지원 계획을 "
            "종합적으로 점검했다."
        )
        official = (
            "청소년 교육 지원 및 보호시설 운영 현황: 법무부 점검, "
            "정원 확대 계획을 공식 발표했다."
        )
        rows = [{
            "utterance_id": "official-2", "text": official,
            "ministries": ["법무부"],
        }]
        edits = filter_supported_official_edits({"edits": [{
            "entity_type": "topic", "entity_id": "topic-1",
            "operation": "UPDATE", "field": "summary",
            "new_text": official,
            "official_utterance_ids": ["official-2"],
        }]}, self.brief, rows)
        self.assertEqual(len(edits), 1)
        self.assertEqual(
            edits[0]["presentation_status"], "FULL_REWRITE_SUPPRESSED",
        )

    def test_meaningful_sentence_append_is_accepted(self):
        before = "청소년 보호시설과 교육 지원을 점검했다."
        self.brief["topics"][0]["summary"] = before
        after = (
            f"{before} 법무부는 보호시설 정원 확대 계획을 추가로 밝혔다."
        )
        rows = [{"utterance_id": "official-2", "text": after, "ministries": ["법무부"]}]
        edits = filter_supported_official_edits({"edits": [{
            "entity_type": "topic", "entity_id": "topic-1",
            "operation": "UPDATE", "field": "summary",
            "new_text": after,
            "official_utterance_ids": ["official-2"],
        }]}, self.brief, rows)
        self.assertEqual(len(edits), 1)

    def test_duplicate_official_topic_addition_is_rejected(self):
        self.rows[0]["text"] = "소년법 시설 개선과 보호시설 확충을 논의했습니다."
        edits = filter_supported_official_edits({"edits": [{
            "entity_type": "topic", "entity_id": "", "operation": "ADD",
            "field": "entity", "title": "소년법 시설 개선",
            "summary": "소년법 시설 개선과 보호시설 확충을 논의했다.",
            "official_utterance_ids": ["official-1"],
        }]}, self.brief, self.rows)
        self.assertEqual(edits, [])

    def test_evidence_backed_addition_is_accepted(self):
        edits = filter_supported_official_edits({"edits": [{
            "entity_type": "topic", "entity_id": "", "operation": "ADD",
            "field": "entity", "title": "등기 전산 장비 예산 집행",
            "summary": "등기 전산 장비 불용액을 점검했다.",
            "official_utterance_ids": ["official-1"],
        }]}, self.brief, self.rows)
        self.assertEqual(len(edits), 1)

    def test_related_judiciary_topic_addition_is_rejected(self):
        self.brief["topics"] = [{
            "id": "topic-1", "title": "대법관 제청 지연과 사법부 독립성 훼손 논란",
            "summary": "대법관 제청 지연과 사법부 독립성 문제를 논의했다.",
        }]
        self.rows[0]["text"] = "대법원장 직권남용과 사법부 독립성 훼손 논란을 지적했다."
        edits = filter_supported_official_edits({"edits": [{
            "entity_type": "topic", "entity_id": "", "operation": "ADD",
            "field": "entity", "title": "대법원장 직권남용 및 사법부 독립성 훼손 논란",
            "summary": "대법원장 직권남용과 사법부 독립성 훼손을 논의했다.",
            "official_utterance_ids": ["official-1"],
        }]}, self.brief, self.rows)
        self.assertEqual(edits, [])


if __name__ == "__main__":
    unittest.main()
