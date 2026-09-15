from __future__ import annotations

import unittest

from app.services.meeting_topic_groups import (
    GROUPING_METHOD,
    GROUPING_VERSION,
    attach_meeting_topic_groups,
    build_meeting_topic_groups,
)


def topic(topic_id: str, title: str, *, evidence_id: str | None = None) -> dict:
    return {
        "id": topic_id,
        "title": title,
        "summary": f"{title}에 관한 발언을 정리했다.",
        "evidence_ids": [evidence_id or f"evidence-{topic_id}"],
        "speaker_points": [],
    }


class MeetingTopicGroupTests(unittest.TestCase):
    def test_groups_detail_topics_by_policy_target_without_collapsing_them(self):
        brief = {
            "topics": [
                topic("topic-1", "한미 핵 공유 및 전술핵 재배치 제안 비판"),
                topic("topic-2", "북한 핵 잠수함 공개 및 탐지 능력 우려"),
                topic("topic-3", "북핵 위협에 대한 실질적 핵 억제력 확보 요구"),
                topic("topic-4", "남북 관계 및 선제적 조치"),
            ],
            "tasks": [],
        }

        groups = build_meeting_topic_groups(brief)

        nuclear = next(group for group in groups if group["key"] == "north-korea-nuclear")
        self.assertEqual(nuclear["title"], "북핵 위협·억제 대응")
        self.assertEqual(nuclear["topic_ids"], ["topic-1", "topic-2", "topic-3"])
        self.assertEqual(nuclear["topic_count"], 3)
        self.assertEqual(len(groups), 2)
        self.assertEqual(len(brief["topics"]), 4)

    def test_keeps_opposing_stances_as_separate_children(self):
        brief = {
            "topics": [
                topic("for", "호르무즈 파병 필요성 제안"),
                topic("against", "한국의 이란 관련 파병 검토 반대 입장"),
            ],
            "tasks": [],
        }

        groups = build_meeting_topic_groups(brief)

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["title"], "중동 정세·파병")
        self.assertEqual(groups[0]["topic_ids"], ["for", "against"])

    def test_title_fallback_merges_only_the_same_extracted_target(self):
        brief = {
            "topics": [
                topic("one", "공공데이터 공개 관련 문제점"),
                topic("two", "공공데이터 공개 개선 방안"),
                topic("three", "별도 신규 정책 검토"),
            ],
            "tasks": [],
        }

        groups = build_meeting_topic_groups(brief)

        data_group = next(group for group in groups if group["title"] == "공공데이터 공개")
        self.assertEqual(data_group["topic_ids"], ["one", "two"])
        self.assertEqual(len(groups), 2)

    def test_dynamically_groups_unknown_targets_only_with_strong_shared_anchors(self):
        brief = {
            "topics": [
                topic("one", "공공 와이파이 음영지역 해소"),
                topic("two", "공공 와이파이 이용자 인증 개선"),
                topic("three", "반려동물 등록칩 교체 주기"),
            ],
            "tasks": [],
        }

        groups = build_meeting_topic_groups(brief)

        platform = next(
            group for group in groups
            if group["assignment_method"] == "DYNAMIC_SEMANTIC"
        )
        self.assertEqual(platform["topic_ids"], ["one", "two"])
        self.assertEqual(platform["topic_count"], 2)
        self.assertEqual(
            next(group for group in groups if "three" in group["topic_ids"])[
                "assignment_method"
            ],
            "TITLE_FALLBACK",
        )

    def test_does_not_force_weakly_related_unknown_topics_into_one_group(self):
        brief = {
            "topics": [
                topic("one", "공소장 직제 입법예고 절차"),
                topic("two", "공유재산 임대료 산정 기준"),
                topic("three", "방송사 재허가 심사 기준"),
            ],
            "tasks": [],
        }

        groups = build_meeting_topic_groups(brief)

        self.assertEqual(len(groups), 3)
        self.assertTrue(all(group["topic_count"] == 1 for group in groups))

    def test_does_not_treat_evaluation_or_legislation_words_as_targets(self):
        brief = {
            "topics": [
                topic("one", "청년도약계좌 전환 정책의 신뢰성 문제"),
                topic("two", "ISA 세제 전환 정책의 신뢰성 문제"),
                topic("three", "청탁 판단의 부당성 검토"),
                topic("four", "기소유예 처분의 부당성 검토"),
                topic("five", "방송법 개정안 처리"),
                topic("six", "공유재산법 개정안 처리"),
            ],
            "tasks": [],
        }

        groups = build_meeting_topic_groups(brief)

        self.assertFalse(any(
            group["assignment_method"] == "DYNAMIC_SEMANTIC"
            for group in groups
        ))

    def test_every_detail_topic_is_assigned_once_and_evidence_is_unioned(self):
        brief = {
            "topics": [
                topic("one", "경찰 수사관행 개선", evidence_id="evidence-1"),
                topic("two", "경찰 수사 인력 확충", evidence_id="evidence-2"),
                topic("three", "주택 공급 확대", evidence_id="evidence-3"),
            ],
            "tasks": [
                {"id": "task-1", "topic_id": "one"},
                {"id": "task-2", "topic_id": "two"},
            ],
        }

        groups = build_meeting_topic_groups(brief)
        assigned = [topic_id for group in groups for topic_id in group["topic_ids"]]
        police = next(group for group in groups if group["key"] == "police-investigation")

        self.assertCountEqual(assigned, ["one", "two", "three"])
        self.assertEqual(len(assigned), len(set(assigned)))
        self.assertEqual(police["evidence_ids"], ["evidence-1", "evidence-2"])
        self.assertEqual(police["task_ids"], ["task-1", "task-2"])

    def test_groups_promoted_plenary_topics_by_policy_target(self):
        brief = {
            "topics": [
                topic("ev-1", "국산 전기차 생태계 보존과 지원 정책 전환"),
                topic("ev-2", "전기차 전략산업 확인 요청"),
                topic("ship-1", "조선업 전략적 위치와 정부의 대응"),
                topic("ship-2", "미국 파견 인력 비자 문제 및 조선소 배치 연계 논의"),
                topic("ship-3", "한국형 화물창 선박 발주 계획"),
                topic("ai-1", "AI 산업 대전환과 경제 안보 인프라 구축"),
                topic("ai-2", "AI 규제 유예 논의"),
                topic("ai-3", "GTC 코리아 개최를 통한 글로벌 AI 투자 유치"),
            ],
            "tasks": [],
        }

        groups = build_meeting_topic_groups(brief)

        self.assertEqual(len(groups), 3)
        self.assertEqual(
            next(group for group in groups if group["key"] == "automotive-ev")[
                "topic_count"
            ],
            2,
        )
        self.assertEqual(
            next(
                group for group in groups if group["key"] == "shipbuilding-maritime"
            )["topic_count"],
            3,
        )
        self.assertEqual(
            next(
                group for group in groups if group["key"] == "ai-digital-infrastructure"
            )["topic_count"],
            3,
        )

    def test_repairs_truncated_shipbuilding_terms_in_read_model(self):
        brief = {
            "headline": "로 소송 및 회유 전략",
            "summary": "한국형 하물창과 마스카 사안을 논의했다.",
            "topics": [
                {
                    **topic("royalty", "로 자금 활용 및 내국인 인력 충원"),
                    "summary": "외국 기업에 지급된 로가 내국인 인건비로 전환 가능하다.",
                },
                topic("lawsuit", "로 소송 및 회유 전략 대응"),
            ],
            "tasks": [
                {
                    "id": "task-1",
                    "topic_id": "royalty",
                    "title": "로 자금 내국인 인건비 전환 방안 검토",
                }
            ],
        }

        attached = attach_meeting_topic_groups(brief)

        self.assertEqual(attached["headline"], "로열티 관련 소송 및 회유 전략")
        self.assertIn("한국형 화물창", attached["summary"])
        self.assertIn("마스가(MASGA)", attached["summary"])
        self.assertEqual(
            attached["topics"][0]["title"],
            "로열티 자금 활용 및 내국인 인력 충원",
        )
        self.assertIn("지급된 로열티가", attached["topics"][0]["summary"])
        self.assertEqual(
            attached["topic_groups"][0]["title"], "조선업·해양산업"
        )
        self.assertEqual(brief["headline"], "로 소송 및 회유 전략")

    def test_attach_adds_versioned_read_model_without_mutating_source(self):
        brief = {"topics": [topic("one", "주택 공급 확대")], "tasks": []}

        attached = attach_meeting_topic_groups(brief)

        self.assertNotIn("topic_groups", brief)
        self.assertEqual(attached["topic_grouping"]["version"], GROUPING_VERSION)
        self.assertEqual(attached["topic_grouping"]["method"], GROUPING_METHOD)
        self.assertEqual(attached["topic_grouping"]["group_count"], 1)
        self.assertEqual(attached["topic_grouping"]["detailed_topic_count"], 1)
        self.assertEqual(attached["topic_grouping"]["ontology_topic_count"], 1)
        self.assertEqual(attached["topic_grouping"]["ontology_coverage"], 1.0)
        self.assertEqual(attached["topic_grouping"]["quality_status"], "PASS")

    def test_flags_low_ontology_coverage_for_review(self):
        brief = {
            "topics": [
                topic("one", "반려동물 등록칩 교체 주기"),
                topic("two", "도시양봉 허가 기준"),
                topic("three", "공공 와이파이 음영지역 해소"),
                topic("four", "해양레저 면허 갱신"),
                topic("five", "게임물 등급 분류 절차"),
            ],
            "tasks": [],
        }

        grouping = attach_meeting_topic_groups(brief)["topic_grouping"]

        self.assertEqual(grouping["quality_status"], "REVIEW_REQUIRED")
        self.assertEqual(grouping["ontology_topic_count"], 0)
        self.assertEqual(grouping["unclassified_topic_count"], 5)
        self.assertIn("ONTOLOGY_COVERAGE_LOW", grouping["review_reasons"])

    def test_groups_plenary_details_under_shared_policy_targets(self):
        brief = {
            "topics": [
                topic("medical-1", "공공병원 확충 정책"),
                topic("medical-2", "국립의전원 교육 체제 설계 방향"),
                topic("media-1", "정부 광고 개혁 및 집행 기준"),
                topic("media-2", "TBS 정상화 지연"),
                topic("labor-1", "플랫폼 노동자의 폭염 노동 보호 공백"),
                topic("labor-2", "일하는 사람 기본법 발의"),
                topic("water-1", "용수 공급 계획 변경 및 확대"),
                topic("water-2", "가뭄 대응 물 관리 원칙"),
                topic("education-1", "교권 개선 논의 현황"),
                topic("education-2", "지방인재장학금의 수도권 공립대생 배제"),
            ],
            "tasks": [],
        }

        groups = build_meeting_topic_groups(brief)
        by_key = {group["key"]: group for group in groups}

        self.assertEqual(2, by_key["healthcare-medical-system"]["topic_count"])
        self.assertEqual(2, by_key["media-public-communication"]["topic_count"])
        self.assertEqual(2, by_key["youth-employment"]["topic_count"])
        self.assertEqual(2, by_key["water-resources-climate"]["topic_count"])
        self.assertEqual(2, by_key["education"]["topic_count"])
        self.assertEqual("assembly-meeting-topic-grouping/1.3", GROUPING_VERSION)


if __name__ == "__main__":
    unittest.main()
