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

    def test_attach_adds_versioned_read_model_without_mutating_source(self):
        brief = {"topics": [topic("one", "주택 공급 확대")], "tasks": []}

        attached = attach_meeting_topic_groups(brief)

        self.assertNotIn("topic_groups", brief)
        self.assertEqual(attached["topic_grouping"]["version"], GROUPING_VERSION)
        self.assertEqual(attached["topic_grouping"]["method"], GROUPING_METHOD)
        self.assertEqual(attached["topic_grouping"]["group_count"], 1)
        self.assertEqual(attached["topic_grouping"]["detailed_topic_count"], 1)


if __name__ == "__main__":
    unittest.main()
