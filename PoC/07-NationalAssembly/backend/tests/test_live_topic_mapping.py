from __future__ import annotations

import unittest

from app.services.live_topic_mapping import (
    MAPPING_VERSION,
    apply_semantic_mapping,
    build_semantic_mapping_prompt,
    normalize_semantic_mapping,
    revalidate_stored_semantic_mapping,
    semantic_mapping_input_hash,
    unresolved_live_topic_clusters,
)


class LiveTopicMappingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.brief = {
            "topics": [
                {
                    "id": "topic-1",
                    "title": "예산 집행",
                    "summary": "예산 집행 현황을 점검하였다.",
                    "speaker_points": [],
                    "live_topic_cluster_ids": ["live-topic-1"],
                },
                {
                    "id": "topic-2",
                    "title": "재난 대응",
                    "summary": "재난 대응 체계를 점검하였다.",
                    "speaker_points": [],
                    "live_topic_cluster_ids": [],
                },
            ],
            "tasks": [],
            "live_topic_assignment": {
                "fallback_cluster_ids": [],
                "additional_llm_calls": 0,
            },
            "live_topic_lineage": {
                "additional_llm_calls": 0,
                "mapped_cluster_count": 1,
                "ambiguous_cluster_count": 1,
                "unmapped_cluster_count": 1,
                "coverage_status": "PARTIAL",
                "clusters": [
                    {
                        "id": "live-topic-1",
                        "title": "예산 집행 점검",
                        "mapping_status": "DIRECT_EVIDENCE",
                        "final_topic_ids": ["topic-1"],
                    },
                    {
                        "id": "live-topic-2",
                        "title": "재정 집행 확인",
                        "aliases": [],
                        "owners": ["기획재정부"],
                        "tasks": [],
                        "utterance_count": 2,
                        "mapping_status": "UNMAPPED",
                        "final_topic_ids": [],
                    },
                    {
                        "id": "live-topic-3",
                        "title": "재난 안전 체계",
                        "aliases": [],
                        "owners": ["행정안전부"],
                        "tasks": [],
                        "utterance_count": 1,
                        "mapping_status": "LEXICAL_CANDIDATE",
                        "final_topic_ids": [],
                    },
                ],
            },
        }

    def test_prompt_contains_only_unresolved_clusters(self):
        clusters = unresolved_live_topic_clusters(self.brief)
        prompt = build_semantic_mapping_prompt(self.brief, clusters)
        self.assertNotIn('"id": "live-topic-1"', prompt)
        self.assertIn('"id": "live-topic-2"', prompt)
        self.assertIn('"id": "live-topic-3"', prompt)

    def test_normalize_keeps_low_confidence_and_omissions_unresolved(self):
        clusters = unresolved_live_topic_clusters(self.brief)
        result = normalize_semantic_mapping(
            {
                "assignments": [
                    {
                        "cluster_id": "live-topic-2",
                        "topic_id": "topic-1",
                        "confidence": "HIGH",
                    },
                    {
                        "cluster_id": "live-topic-3",
                        "topic_id": "topic-2",
                        "confidence": "LOW",
                    },
                ],
                "unresolved_cluster_ids": [],
            },
            self.brief["topics"],
            clusters,
        )
        self.assertEqual(1, len(result["assignments"]))
        self.assertEqual(["live-topic-3"], result["unresolved_cluster_ids"])

    def test_normalize_rejects_high_confidence_without_policy_term_overlap(self):
        clusters = unresolved_live_topic_clusters(self.brief)
        result = normalize_semantic_mapping(
            {
                "assignments": [
                    {
                        "cluster_id": "live-topic-2",
                        "topic_id": "topic-2",
                        "confidence": "HIGH",
                    }
                ],
                "unresolved_cluster_ids": ["live-topic-3"],
            },
            self.brief["topics"],
            clusters,
        )
        self.assertEqual([], result["assignments"])
        self.assertEqual(
            {"live-topic-2", "live-topic-3"},
            set(result["unresolved_cluster_ids"]),
        )

    def test_apply_updates_lineage_without_changing_report_contents(self):
        clusters = unresolved_live_topic_clusters(self.brief)
        digest = semantic_mapping_input_hash(self.brief["topics"], clusters)
        result = apply_semantic_mapping(
            self.brief,
            {
                "assignments": [
                    {
                        "cluster_id": "live-topic-2",
                        "topic_id": "topic-1",
                        "confidence": "HIGH",
                    },
                    {
                        "cluster_id": "live-topic-3",
                        "topic_id": "topic-2",
                        "confidence": "MEDIUM",
                    },
                ],
                "unresolved_cluster_ids": [],
            },
            input_hash=digest,
            model="openrouter-free",
            request_id="request-1",
        )
        self.assertEqual("예산 집행", result["topics"][0]["title"])
        self.assertEqual(3, result["live_topic_lineage"]["mapped_cluster_count"])
        self.assertEqual("COMPLETE", result["live_topic_lineage"]["coverage_status"])
        self.assertEqual(
            ["live-topic-1", "live-topic-2"],
            result["topics"][0]["live_topic_cluster_ids"],
        )
        assignment = result["live_topic_assignment"]
        self.assertEqual(MAPPING_VERSION, assignment["semantic_mapping_version"])
        self.assertEqual(1, assignment["additional_llm_calls"])
        self.assertEqual(2, assignment["semantic_assigned_count"])

    def test_revalidate_removes_stored_unsupported_assignment_without_new_call(self):
        cluster = self.brief["live_topic_lineage"]["clusters"][1]
        cluster.update(
            {
                "title": "국민연금 국내 주식 비중 조정",
                "mapping_status": "SEMANTIC_ASSIGNED",
                "final_topic_ids": ["topic-2"],
                "match_score": 0.9,
            }
        )
        self.brief["topics"][1]["live_topic_cluster_ids"] = ["live-topic-2"]
        self.brief["live_topic_assignment"].update(
            {
                "semantic_mapping_version": "assembly-live-topic-mapping/1.0",
                "semantic_mapping_status": "COMPLETED",
                "semantic_assigned_cluster_ids": ["live-topic-2"],
                "additional_llm_calls": 1,
            }
        )
        result = revalidate_stored_semantic_mapping(self.brief)
        restored = result["live_topic_lineage"]["clusters"][1]
        self.assertEqual("UNMAPPED", restored["mapping_status"])
        self.assertEqual([], restored["final_topic_ids"])
        self.assertEqual([], result["topics"][1]["live_topic_cluster_ids"])
        self.assertEqual(
            1, result["live_topic_assignment"]["additional_llm_calls"],
        )


if __name__ == "__main__":
    unittest.main()
