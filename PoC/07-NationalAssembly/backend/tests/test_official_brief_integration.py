from __future__ import annotations

import unittest

from app.services.official_brief_integration import (
    MATCH_METHOD,
    build_official_brief_integration,
    semantic_tokens,
)


class OfficialBriefIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.live_brief = {
            "brief": {
                "topics": [
                    {
                        "id": "topic-1",
                        "title": "대법관 임명 절차와 사법부 독립성 논란",
                        "summary": "대법관 후보 임명 지연과 절차적 정당성을 논의했다.",
                    },
                    {
                        "id": "topic-2",
                        "title": "재난 피해 복구 대책",
                        "summary": "호우 피해 복구 방안을 논의했다.",
                    },
                ],
                "tasks": [
                    {
                        "id": "task-1",
                        "title": "대법관 임명 절차의 사전 조율 및 절차 준수",
                        "topic_title": "대법관 임명 절차와 사법부 독립성 논란",
                        "ministries": ["법원행정처"],
                    }
                ],
            }
        }
        self.official_rows = [
            {
                "utterance_id": "official-1",
                "sequence_number": 17,
                "speaker_name": "위원장",
                "speaker_role": "위원장",
                "text": (
                    "법원행정처는 대법관 후보 임명 절차를 사전에 조율하고 "
                    "절차적 정당성을 준수해야 합니다."
                ),
                "source_locator": {"span_id": "s17"},
                "topics": ["법무·사법"],
                "ministries": ["법무부"],
                "utterance_kind": "POLICY",
                "evidence_keywords": ["법무"],
                "agenda_titles": ["1. 대법원 현안보고"],
            },
            {
                "utterance_id": "official-2",
                "sequence_number": 18,
                "speaker_name": "위원장",
                "text": "성원이 되었으므로 회의를 시작하겠습니다.",
                "topics": ["절차·의결"],
                "ministries": [],
                "utterance_kind": "PROCEDURAL",
                "agenda_titles": [],
            },
        ]

    def test_semantic_tokens_normalize_common_korean_particles(self):
        tokens = semantic_tokens("대법관 임명 절차와 절차를 확인한다")
        self.assertIn("절차", tokens)
        self.assertNotIn("절차와", tokens)
        self.assertNotIn("절차를", tokens)

    def test_links_live_topic_and_task_to_related_official_evidence(self):
        result = build_official_brief_integration(
            self.live_brief, self.official_rows,
        )
        self.assertEqual(result["match_method"], MATCH_METHOD)
        self.assertEqual(result["topics"][0]["status"], "OFFICIAL_RELATED")
        self.assertEqual(result["topics"][1]["status"], "NOT_LINKED")
        self.assertEqual(result["tasks"][0]["status"], "OFFICIAL_RELATED")
        evidence = result["topics"][0]["official_evidence"][0]
        self.assertEqual(evidence["utterance_id"], "official-1")
        self.assertEqual(evidence["speaker_name"], "위원장")
        self.assertIn("대법관", evidence["shared_terms"])
        self.assertEqual(
            result["summary"],
            {
                "official_policy_utterances": 1,
                "live_topic_count": 2,
                "related_topic_count": 1,
                "live_task_count": 1,
                "related_task_count": 1,
            },
        )

    def test_does_not_present_related_evidence_as_official_approval(self):
        result = build_official_brief_integration(
            self.live_brief, self.official_rows,
        )
        self.assertIn("확정·승인", result["interpretation"])
        self.assertNotEqual(result["tasks"][0]["status"], "OFFICIAL_CONFIRMED")


    def test_ministry_names_alone_do_not_create_a_related_match(self):
        brief = {
            "brief": {
                "topics": [],
                "tasks": [{
                    "id": "task-budget",
                    "title": "민생 비송사건 처리 기간 단축과 인력 확충",
                    "topic_title": "민생 비송사건",
                    "ministries": ["법무부", "기획재정부"],
                }],
            }
        }
        unrelated = [{
            **self.official_rows[0],
            "text": "법무부와 기획재정부의 일반 업무보고입니다.",
            "ministries": ["법무부", "기획재정부"],
        }]
        result = build_official_brief_integration(brief, unrelated)
        self.assertEqual(result["tasks"][0]["status"], "NOT_LINKED")


if __name__ == "__main__":
    unittest.main()
