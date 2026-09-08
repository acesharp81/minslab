from __future__ import annotations

import unittest

from app.services.cross_institution_flow import (
    build_cross_institution_flow,
    build_specific_cross_institution_flow,
)


class CrossInstitutionFlowTests(unittest.TestCase):
    def test_specific_flow_links_same_concrete_topic(self):
        executive = [{
            "meeting_number": 36,
            "title": "제36회 국무회의",
            "published_date": "2026.08.18",
            "source_url": "https://example.test/cabinet",
            "agendas": [{
                "topic": "중대범죄수사청 조직 및 운영에 관한 법률 시행령안",
                "summary": "중대범죄수사청의 기구와 정원을 정한다.",
                "ministries": ["행정안전부"],
            }],
        }]
        issues = {"items": [{
            "id": "issue-correct",
            "topic": "중대범죄수사청 조직·운영 법률 개정안 가결",
            "summary": "중대범죄수사청 조직과 운영 기준을 심사했다.",
            "mention_count": 4,
            "meeting_count": 1,
            "ministries": ["행정안전부"],
            "bills": [],
            "latest_legislative_meeting": {
                "broadcast_id": "broadcast-1",
                "committee_name": "법제사법위원회",
                "date": "2026-08-17",
                "summary": "중대범죄수사청 조직과 운영 기준을 심사했다.",
                "authority_status": "PROVISIONAL",
            },
        }]}

        result = build_specific_cross_institution_flow(executive, issues)

        self.assertEqual(result["count"], 1)
        self.assertIn("중대범죄수사청", result["items"][0]["topic"])
        self.assertEqual(result["items"][0]["match_method"], "SPECIFIC_REPORT_TOPIC_TOKEN_V1")

    def test_specific_flow_rejects_broad_word_mismatches(self):
        executive = [{
            "meeting_number": 36,
            "title": "제36회 국무회의",
            "published_date": "2026.08.18",
            "agendas": [
                {
                    "topic": "중대범죄수사청 조직 및 운영에 관한 법률 시행령안",
                    "summary": "수사기관 운영 세부사항을 정한다.",
                    "ministries": ["행정안전부"],
                },
                {
                    "topic": "2027년도 예산안 및 국가재정운용계획",
                    "summary": "국가 예산과 재정 계획을 심의한다.",
                    "ministries": ["기획재정부"],
                },
            ],
        }]
        common = {
            "mention_count": 1, "meeting_count": 1, "bills": [],
            "latest_legislative_meeting": {
                "broadcast_id": "broadcast-1", "committee_name": "행정안전위원회",
                "date": "2026-08-17", "authority_status": "PROVISIONAL",
            },
        }
        issues = {"items": [
            {
                **common, "id": "wrong-investigation",
                "topic": "선거관리 특별검사 임명 법률안",
                "summary": "선거 관련 특별검사의 수사 대상을 정한다.",
                "ministries": ["행정안전부"],
            },
            {
                **common, "id": "wrong-budget",
                "topic": "경찰 수사인력 배분 문제",
                "summary": "경찰 인력과 예산 배분을 지적했다.",
                "ministries": ["행정안전부"],
            },
        ]}

        result = build_specific_cross_institution_flow(executive, issues)

        self.assertEqual(result["items"], [])

    def test_specific_flow_rejects_different_special_laws_and_ai_policies(self):
        executive = [{"agendas": [
            {
                "topic": "반도체산업 경쟁력 강화 및 지원에 관한 특별법 시행령안",
                "summary": "반도체산업 지원 기준을 정한다.",
            },
            {
                "topic": "인공지능 발전과 신뢰 기반 조성 기본법 시행령",
                "summary": "인공지능 산업의 신뢰 기준을 정한다.",
            },
        ]}]
        common = {
            "mention_count": 1, "meeting_count": 1, "ministries": [], "bills": [],
            "latest_legislative_meeting": {
                "broadcast_id": "broadcast-1", "committee_name": "행정안전위원회",
                "date": "2026-08-17", "authority_status": "PROVISIONAL",
            },
        }
        issues = {"items": [
            {
                **common, "id": "itaewon",
                "topic": "10·29 이태원 참사 특별법 활동기간 연장",
                "summary": "특별조사위원회 활동기간을 연장한다.",
            },
            {
                **common, "id": "ai-exam",
                "topic": "AI 기반 수능 대체와 채점 공정성 우려",
                "summary": "AI 채점의 공정성 문제를 논의했다.",
            },
        ]}

        result = build_specific_cross_institution_flow(executive, issues)

        self.assertEqual(result["items"], [])

    def test_specific_flow_rejects_same_year_and_generic_budget_only(self):
        executive = [{"agendas": [{
            "topic": "2027년도 예산안",
            "summary": "내년도 국가 예산안을 심의한다.",
        }]}]
        issues = {"items": [{
            "id": "budget-subtopic",
            "topic": "2027년 예산안의 지역별 청년 지원 정책",
            "summary": "청년 지원 예산의 지역별 배분을 논의했다.",
            "mention_count": 1,
            "meeting_count": 1,
            "ministries": [],
            "bills": [],
            "latest_legislative_meeting": {
                "broadcast_id": "broadcast-1",
                "committee_name": "예산결산특별위원회",
                "date": "2026-08-17",
                "authority_status": "PROVISIONAL",
            },
        }]}

        result = build_specific_cross_institution_flow(executive, issues)

        self.assertEqual(result["items"], [])

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
