from __future__ import annotations

import unittest

from app.services.meeting_topic_groups import (
    attach_meeting_topic_groups,
    build_meeting_topic_ontology,
)


def classified(*titles: str) -> dict[str, str]:
    brief = {
        "topics": [
            {
                "id": f"topic-{index}",
                "title": title,
                "summary": "",
                "evidence_ids": [f"utterance-{index}"],
                "speaker_points": [],
            }
            for index, title in enumerate(titles, start=1)
        ],
        "tasks": [],
    }
    return {
        topic_id: group["key"]
        for group in attach_meeting_topic_groups(brief)["topic_groups"]
        for topic_id in group["topic_ids"]
    }


class CurrentOntologyAuditTests(unittest.TestCase):
    def test_new_subjects_keep_distinct_policy_targets(self) -> None:
        result = classified(
            "긴급조치 재심과 국가권력 피해자 명예회복",
            "진실화해위원회 조사 역량 강화",
            "원유 확보 방식 검토",
            "면세유 가격 상승에 따른 농가 부담",
            "장례식장 불공정 약관 개정",
            "헤이그 협약 아동 인도 집행",
        )
        self.assertEqual(result, {
            "topic-1": "historical-justice",
            "topic-2": "historical-justice",
            "topic-3": "energy-electricity",
            "topic-4": "agriculture-rural",
            "topic-5": "consumer-financial-protection",
            "topic-6": "prosecution-judiciary",
        })

    def test_october_audit_targets_use_distinct_branches(self) -> None:
        result = classified(
            "투표지 공개 재검표 촉구",
            "고액 후원 내역 기재 누락",
            "특별정려금 지급 대상 범위",
            "소방감리 제도개선 및 상주감리 확대",
            "망 분리 미완료",
            "중대재해처벌법 양형기준 감경 범위",
            "허위 답변 정정 및 사과 요구",
        )
        self.assertEqual(result, {
            "topic-1": "elections-public-opinion",
            "topic-2": "public-integrity-funds",
            "topic-3": "civil-service-personnel",
            "topic-4": "public-safety-health",
            "topic-5": "privacy-communications",
            "topic-6": "prosecution-judiciary",
            "topic-7": "government-operations",
        })

    def test_specific_summary_can_classify_generic_report_title(self) -> None:
        brief = {
            "topics": [{
                "id": "topic-1",
                "title": "인사혁신처 국정감사 업무보고",
                "summary": "인사관리체계 개선과 공직적격성평가 전환을 보고했다.",
                "evidence_ids": ["utterance-1"],
                "speaker_points": [],
            }, {
                "id": "topic-2",
                "title": "소명서 제출 및 관리 부실 문제 제기",
                "summary": "후원자 연락처를 확보했으나 소명 답변을 받지 못했다.",
                "evidence_ids": ["utterance-2"],
                "speaker_points": [],
            }],
            "tasks": [],
        }
        groups = attach_meeting_topic_groups(brief)["topic_groups"]
        result = {topic_id: group["key"] for group in groups for topic_id in group["topic_ids"]}
        self.assertEqual(result, {
            "topic-1": "civil-service-personnel",
            "topic-2": "public-integrity-funds",
        })

    def test_ambiguous_or_garbled_subjects_stay_for_review(self) -> None:
        result = classified(
            "서울청 시스템 설치 현황",
            "안표 과징금 및 신고 포상금 정책",
        )
        self.assertTrue(all(key.startswith("title-") for key in result.values()))

    def test_new_target_is_in_star_map_domain(self) -> None:
        ontology = build_meeting_topic_ontology()
        historical = next(
            group for group in ontology["groups"]
            if group["key"] == "historical-justice"
        )
        self.assertEqual(historical["domain_key"], "society")


if __name__ == "__main__":
    unittest.main()
