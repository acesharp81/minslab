from __future__ import annotations

import unittest

from app.services.meeting_topic_groups import (
    attach_meeting_topic_groups,
    build_meeting_topic_groups,
)


def topic(topic_id: str, title: str, summary: str = "") -> dict[str, object]:
    return {
        "id": topic_id,
        "title": title,
        "summary": summary,
        "evidence_ids": [f"evidence-{topic_id}"],
        "speaker_points": [],
    }


class OntologyAuditTests(unittest.TestCase):
    def test_local_council_discussion_stays_together_despite_budget_terms(self) -> None:
        brief = {"topics": [
            topic("law", "지방의회법 제정과 의회 역할 강화"),
            topic("staff", "정책지원관의 배정 방식 개선"),
            topic("budget", "지방의회 정책지원관 제도 확대", "증원 예산 부담"),
            topic("capacity", "경남도의회 인력 부족과 지방의정 역량"),
        ], "tasks": []}
        grouped = attach_meeting_topic_groups(brief)
        council = next(group for group in grouped["topic_groups"]
                       if group["key"] == "local-council-autonomy")
        self.assertEqual(council["topic_ids"], ["law", "staff", "budget", "capacity"])
        self.assertEqual(grouped["topic_grouping"]["integrity_status"], "PASS")

    def test_plenary_bills_follow_subject_instead_of_shared_vote_words(self) -> None:
        brief = {"topics": [
            topic("budget", "농어촌 구조개선 특별회계법 일부 개정 법률안 부결"),
            topic("farming", "도시와 농어촌 간 교류 촉진법 개정안 가결"),
            topic("animal", "동물보호법 개정안 가결"),
            topic("medical", "응급의료법 개정안에 대한 반대토론"),
            topic("digital", "데이터 산업진흥 및 이용촉진 기본법 개정안 가결",
                  "과학기술정보방송통신위원회 수정안 가결"),
        ], "tasks": []}
        assigned = {topic_id: group["key"]
                    for group in build_meeting_topic_groups(brief)
                    for topic_id in group["topic_ids"]}
        self.assertEqual(assigned, {
            "budget": "budget-public-finance", "farming": "agriculture-rural",
            "animal": "animal-welfare", "medical": "healthcare-medical-system",
            "digital": "ai-digital-infrastructure",
        })

    def test_specific_subject_beats_incidental_summary_keyword(self) -> None:
        brief = {"topics": [
            topic("wildlife", "생물 관리 방안 및 관계기관 협의", "생물 관리 방안"),
            topic("welfare", "국민기초생활보장법 일부개정법률안",
                  "법원행정처와 협의한다."),
        ], "tasks": []}
        assigned = {topic_id: group["key"]
                    for group in build_meeting_topic_groups(brief)
                    for topic_id in group["topic_ids"]}
        self.assertEqual(assigned["wildlife"], "environment-waste")
        self.assertEqual(assigned["welfare"], "welfare-care-family")


if __name__ == "__main__":
    unittest.main()
