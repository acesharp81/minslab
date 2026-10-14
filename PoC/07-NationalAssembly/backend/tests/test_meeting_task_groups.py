import unittest

from app.services.meeting_brief import link_tasks_to_topics
from app.services.meeting_task_groups import group_document_submission_tasks


class MeetingTaskGroupsTest(unittest.TestCase):
    def test_document_requests_are_one_follow_up_with_original_evidence(self) -> None:
        brief = {"tasks": [
        {"id": "task-1", "title": "예산 집행 자료 제출 요구", "status": "OPEN",
         "topic_id": "topic-1", "ministries": ["기획예산처"],
         "evidence_ids": ["utterance-1"], "official_evidence_ids": ["official-1"]},
        {"id": "task-2", "title": "인사 내역 자료 제출", "status": "OPEN",
         "topic_id": "topic-2", "ministries": ["행정안전부"],
         "evidence_ids": ["utterance-2"], "official_evidence_ids": ["official-2"]},
        {"id": "task-3", "title": "자료 제출 및 제도 개선 검토", "status": "OPEN",
         "topic_id": "topic-2", "evidence_ids": ["utterance-3"]},
        {"id": "task-4", "title": "이전 자료 제출 완료", "status": "RESOLVED",
         "topic_id": "topic-1", "evidence_ids": ["utterance-4"]},
        {"id": "task-5", "title": "담당자 출석 및 자료 제출", "status": "OPEN",
         "topic_id": "topic-1", "evidence_ids": ["utterance-5"]},
        ]}

        groups = group_document_submission_tasks(brief)

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["title"], "자료 제출 요구")
        self.assertEqual(groups[0]["task_ids"], ["task-1", "task-2"])
        self.assertEqual(groups[0]["topic_ids"], ["topic-1", "topic-2"])
        self.assertEqual(groups[0]["ministries"], ["기획예산처", "행정안전부"])
        self.assertEqual(groups[0]["evidence_ids"], ["utterance-1", "utterance-2"])
        self.assertEqual(groups[0]["official_evidence_ids"], ["official-1", "official-2"])
        self.assertEqual(len(brief["tasks"]), 5)

    def test_single_document_request_stays_an_individual_task(self) -> None:
        brief = {"tasks": [{
            "id": "task-1", "title": "감사 자료 제출", "status": "OPEN",
            "topic_id": "topic-1", "evidence_ids": ["utterance-1"],
        }]}

        self.assertEqual(group_document_submission_tasks(brief), [])

    def test_duplicate_topic_id_keeps_lineage_target_and_relinks_task(self) -> None:
        brief = {
            "topics": [
                {"id": "topic-18", "title": "청소년 디지털 기록 삭제", "evidence_ids": ["a"]},
                {"id": "topic-18", "title": "교사-학생 관계 단절", "evidence_ids": ["b"]},
            ],
            "tasks": [{"id": "task-1", "title": "디지털 기록 삭제 기준 검토",
                       "topic_title": "청소년 디지털 기록 삭제", "evidence_ids": ["a"]}],
            "live_topic_lineage": {"clusters": [{
                "title": "교사-학생 관계 단절",
                "final_topic_ids": ["topic-18"],
            }]},
        }

        result = link_tasks_to_topics(brief)

        self.assertEqual([topic["id"] for topic in result["topics"]], ["topic-3", "topic-18"])
        self.assertEqual(result["tasks"][0]["topic_id"], "topic-3")
        self.assertEqual(brief["topics"][0]["id"], "topic-18")

    def test_ambiguous_lineage_keeps_duplicate_for_review(self) -> None:
        brief = {
            "topics": [
                {"id": "topic-2", "title": "주택 공급", "evidence_ids": ["a"]},
                {"id": "topic-2", "title": "기후 보험", "evidence_ids": ["b"]},
            ],
            "tasks": [],
            "live_topic_lineage": {"clusters": [{
                "title": "주택 정책", "final_topic_ids": ["topic-2"],
            }]},
        }

        result = link_tasks_to_topics(brief)

        self.assertEqual([topic["id"] for topic in result["topics"]], ["topic-2", "topic-2"])

    def test_conflicting_lineage_references_keep_duplicate_for_review(self) -> None:
        brief = {
            "topics": [
                {"id": "topic-2", "title": "교사 학생 관계", "evidence_ids": ["a"]},
                {"id": "topic-2", "title": "기후 보험 지급", "evidence_ids": ["b"]},
            ],
            "tasks": [],
            "live_topic_lineage": {"clusters": [
                {"title": "교사 학생 관계", "final_topic_ids": ["topic-2"]},
                {"title": "기후 보험 지급", "final_topic_ids": ["topic-2"]},
            ]},
        }

        result = link_tasks_to_topics(brief)

        self.assertEqual([topic["id"] for topic in result["topics"]], ["topic-2", "topic-2"])
