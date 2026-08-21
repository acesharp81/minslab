from __future__ import annotations

import unittest

from app.services.cross_institution_flow import build_cross_institution_flow


class CrossInstitutionFlowTests(unittest.TestCase):
    def test_links_only_exact_shared_policy_taxonomy_with_both_evidence_sides(self):
        executive = [{
            "meeting_number": 35, "title": "제35회 국무회의 브리핑",
            "published_date": "2026.08.11", "source_url": "https://www.korea.kr/example",
            "agendas": [{
                "topic": "물가 대응과 재정 운용", "summary": "예산과 재정 대책을 마련합니다.",
                "ministries": ["재정경제부"], "source_span_id": "agenda-1",
            }],
        }]
        legislative = {"items": [{
            "topic": "재정·예산", "statement_count": 22,
            "committees": [{"label": "예산결산특별위원회", "count": 21}],
            "ministries": [], "bills": [],
            "evidence_keywords": ["재정"],
            "evidence": {
                "source_span_id": "spk_sub12-2", "text": "재정 발언",
                "conference_date": "2026-08-12",
            },
        }]}
        result = build_cross_institution_flow(executive, legislative)
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["items"][0]["topic"], "재정·예산")
        self.assertEqual(result["items"][0]["executive_evidence"]["source_span_id"], "agenda-1")
        self.assertEqual(result["items"][0]["legislative_evidence"]["source_span_id"], "spk_sub12-2")
        self.assertEqual(result["items"][0]["shared_evidence_keywords"], ["재정"])
        self.assertEqual(result["items"][0]["temporal_relation"], "EXECUTIVE_BEFORE_LEGISLATURE")
        self.assertEqual(result["items"][0]["review_status"], "DRAFT")

    def test_does_not_link_same_topic_without_shared_evidence_keyword(self):
        executive = [{"agendas": [{"topic": "공무원 제도", "summary": "공무원 정원 조정"}]}]
        legislative = {"items": [{
            "topic": "지방·행정", "statement_count": 1,
            "evidence_keywords": ["지방", "선거"],
        }]}
        result = build_cross_institution_flow(executive, legislative)
        self.assertEqual(result["items"], [])

    def test_does_not_link_on_weak_generic_shared_keyword_alone(self):
        executive = [{"agendas": [{"topic": "지방대학 지원", "summary": "지방 인재 육성"}]}]
        legislative = {"items": [{
            "topic": "지방·행정", "statement_count": 1,
            "evidence_keywords": ["지방"],
        }]}
        result = build_cross_institution_flow(executive, legislative)
        self.assertEqual(result["items"], [])

        executive = [{"agendas": [{"topic": "사법 제도", "summary": "사법 제도 정비"}]}]
        legislative = {"items": [{
            "topic": "법무·사법", "statement_count": 1,
            "evidence_keywords": ["사법"],
        }]}
        result = build_cross_institution_flow(executive, legislative)
        self.assertEqual(result["items"], [])

    def test_does_not_link_when_legislature_has_no_same_topic(self):
        executive = [{
            "agendas": [{"topic": "재난 안전", "summary": "소방 대책", "source_span_id": "agenda-1"}],
        }]
        result = build_cross_institution_flow(executive, {"items": [{"topic": "재정·예산"}]})
        self.assertEqual(result["items"], [])

    def test_generic_law_and_damage_words_are_not_cross_institution_links(self):
        executive = [{"agendas": [
            {"topic": "지원에 관한 법률", "summary": "일반 제도 정비"},
            {"topic": "지원 대책", "summary": "경제적 피해를 지원"},
        ]}]
        legislative = {"items": [
            {"topic": "법무·사법", "statement_count": 1},
            {"topic": "재난·안전", "statement_count": 1},
        ]}
        result = build_cross_institution_flow(executive, legislative)
        self.assertEqual(result["items"], [])


if __name__ == "__main__":
    unittest.main()
