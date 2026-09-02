from __future__ import annotations

import unittest

from app.db.meeting_brief_repository import MeetingBriefRepository
from app.services.live_topic_lineage import (
    LINEAGE_VERSION,
    attach_live_topic_lineage,
    build_live_topic_clusters,
)


def utterance(
    utterance_id: str,
    topic: str,
    topic_key: str,
    *,
    owners: list[str] | None = None,
    task: str | None = None,
) -> dict[str, object]:
    return {
        "utterance_id": utterance_id,
        "live_insight": {
            "topic": topic,
            "topic_key": topic_key,
            "owners": owners or [],
            "task": task,
        },
    }


class LiveTopicLineageTests(unittest.TestCase):
    def test_similar_live_titles_are_clustered_without_llm(self):
        clusters, insight_count, title_count = build_live_topic_clusters(
            [
                utterance(
                    "u-1",
                    "청와대 복귀 예비비 지출내역 미공개",
                    "청와대 복귀 예비비 지출내역",
                    owners=["대통령비서실"],
                ),
                utterance(
                    "u-2",
                    "청와대 예비비 지출내역 공개 요청",
                    "청와대 예비비 지출내역",
                    owners=["대통령비서실"],
                ),
            ]
        )
        self.assertEqual(2, insight_count)
        self.assertEqual(2, title_count)
        self.assertEqual(1, len(clusters))
        self.assertEqual(["u-1", "u-2"], clusters[0]["utterance_ids"])

    def test_direct_evidence_maps_cluster_and_preserves_aliases(self):
        brief = {
            "topics": [
                {
                    "id": "topic-1",
                    "title": "청와대 복귀 예비비 지출내역 공개 요구",
                    "summary": "예비비 집행 자료 제출을 요구하였다.",
                    "speaker_points": [],
                    "evidence_ids": ["u-1"],
                }
            ],
            "tasks": [],
        }
        result = attach_live_topic_lineage(
            brief,
            [
                utterance(
                    "u-1",
                    "청와대 복귀 예비비 지출내역 미공개",
                    "청와대 복귀 예비비 지출내역",
                ),
                utterance(
                    "u-2",
                    "청와대 예비비 지출내역 공개 요청",
                    "청와대 예비비 지출내역",
                ),
            ],
        )
        lineage = result["live_topic_lineage"]
        self.assertEqual(LINEAGE_VERSION, lineage["version"])
        self.assertEqual(0, lineage["additional_llm_calls"])
        self.assertEqual(1, lineage["cluster_count"])
        self.assertEqual(1, lineage["mapped_cluster_count"])
        self.assertEqual("COMPLETE", lineage["coverage_status"])
        self.assertEqual("DIRECT_EVIDENCE", lineage["clusters"][0]["mapping_status"])
        self.assertEqual(["topic-1"], lineage["clusters"][0]["final_topic_ids"])
        self.assertEqual(
            ["live-topic-1"],
            result["topics"][0]["live_topic_cluster_ids"],
        )

    def test_cross_topic_evidence_is_kept_as_unlinked_ambiguous_candidate(self):
        brief = {
            "topics": [
                {
                    "id": "topic-1",
                    "title": "결혼 페널티",
                    "summary": "결혼 지원 제도를 논의했다.",
                    "speaker_points": [],
                    "evidence_ids": ["u-1"],
                },
                {
                    "id": "topic-2",
                    "title": "새만금 국유지 정리",
                    "summary": "국유지 관리 절차를 논의했다.",
                    "speaker_points": [],
                    "evidence_ids": ["u-2"],
                },
            ],
            "tasks": [],
        }
        result = attach_live_topic_lineage(
            brief,
            [
                utterance(
                    "u-1",
                    "부처 칸막이 해소와 정부 통합 운영",
                    "부처 칸막이 정부 통합",
                    owners=["국무조정실"],
                ),
                utterance(
                    "u-2",
                    "부처 칸막이로 인한 국민 불편 해소",
                    "부처 칸막이 정부 통합",
                    owners=["국무조정실"],
                ),
                utterance(
                    "u-3",
                    "전혀 별개의 산림 재난 대응",
                    "산림 재난 대응",
                    owners=["산림청"],
                ),
            ],
        )
        lineage = result["live_topic_lineage"]
        cross = lineage["clusters"][0]
        self.assertEqual("MULTIPLE_FINAL_TOPICS", cross["mapping_status"])
        self.assertEqual([], cross["final_topic_ids"])
        self.assertEqual(1, lineage["ambiguous_cluster_count"])
        self.assertEqual(1, lineage["unmapped_cluster_count"])
        self.assertEqual("PARTIAL", lineage["coverage_status"])

    def test_synthesis_assignment_prevents_separate_unmapped_topics(self):
        brief = {
            "topics": [
                {
                    "id": "topic-1",
                    "title": "예산 집행",
                    "summary": "예산 집행을 점검하였다.",
                    "speaker_points": [],
                    "evidence_ids": ["u-1"],
                    "live_topic_cluster_ids": ["live-topic-1", "live-topic-2"],
                }
            ],
            "tasks": [],
            "live_topic_assignment": {
                "source_count": 2,
                "model_assigned_count": 2,
                "fallback_assigned_count": 0,
                "unassigned_count": 0,
                "fallback_cluster_ids": [],
            },
        }
        utterances = [
            utterance("u-1", "예산 집행 점검", "예산 집행"),
            utterance("u-2", "재정 집행 확인", "재정 집행"),
        ]
        utterances[0]["meeting_session_id"] = "session-1"
        utterances[1]["meeting_session_id"] = "session-2"
        result = attach_live_topic_lineage(brief, utterances)
        lineage = result["live_topic_lineage"]
        self.assertEqual(0, lineage["unmapped_cluster_count"])
        self.assertEqual("COMPLETE", lineage["coverage_status"])
        self.assertEqual(["session-1"], lineage["clusters"][0]["session_ids"])
        self.assertEqual(["session-2"], lineage["clusters"][1]["session_ids"])

    def test_lineage_cluster_evidence_ids_are_available_to_existing_api(self):
        brief = {
            "brief": {
                "live_topic_lineage": {
                    "clusters": [
                        {
                            "id": "live-topic-7",
                            "utterance_ids": ["u-1", "u-2"],
                        }
                    ],
                },
            },
        }
        self.assertEqual(
            ["u-1", "u-2"],
            MeetingBriefRepository(None).evidence_ids(
                brief,
                "live_topic_cluster",
                "live-topic-7",
            ),
        )


if __name__ == "__main__":
    unittest.main()
