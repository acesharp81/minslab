from __future__ import annotations

import unittest
from unittest import mock
from uuid import UUID

from app.db.openai_daily_budget import DailyTokenLimitReached
from app.ingestion.meeting_brief_worker import (
    map_unlinked_brief_once,
    process_available,
)
from app.services.meeting_brief import OpenAIMeetingBriefClient


class OpenAILiveTopicMappingTests(unittest.TestCase):
    def test_direct_openai_mapping_uses_its_configured_model(self) -> None:
        client = OpenAIMeetingBriefClient(
            "test-key",
            model="gpt-5.4-mini",
            base_url="https://example.invalid/v1",
            reserve_tokens=mock.Mock(),
            settle_tokens=mock.Mock(),
        )
        topics = [{
            "id": "topic-1", "title": "승강기 안전", "summary": "",
            "speaker_points": [],
        }]
        clusters = [{"id": "cluster-1", "title": "승강기 안전"}]
        with mock.patch.object(
            client, "_post",
            return_value=({
                "assignments": [{
                    "cluster_id": "cluster-1",
                    "topic_id": "topic-1",
                    "confidence": "HIGH",
                }],
                "unresolved_cluster_ids": [],
            }, {}),
        ) as post:
            mapped, _ = client.map_live_topics(
                {"topics": topics}, clusters,
            )
        self.assertEqual(post.call_args.kwargs["model_override"], None)
        self.assertEqual(len(mapped["assignments"]), 1)

    def test_idle_cycle_maps_recent_openai_report(self) -> None:
        broadcast_id = UUID("00000000-0000-0000-0000-000000000001")
        worker = "app.ingestion.meeting_brief_worker"
        with (
            mock.patch(f"{worker}.eligible_broadcast_ids", return_value=[]),
            mock.patch(
                f"{worker}.recent_openai_mapping_candidate",
                return_value=broadcast_id,
            ),
            mock.patch(
                f"{worker}.openai_mapping_budget_available",
                return_value=True,
            ),
            mock.patch(f"{worker}.get_settings"),
            mock.patch(
                f"{worker}.map_existing_brief_one",
                return_value={"status": "COMPLETED", "after_unresolved": 4},
            ) as map_brief,
        ):
            result = process_available()
        map_brief.assert_called_once_with(
            broadcast_id, provider_override="openai",
        )
        self.assertEqual(result[0]["workload"], "LIVE_TOPIC_MAPPING")

    def test_pending_report_keeps_priority_at_daily_limit(self) -> None:
        broadcast_id = UUID("00000000-0000-0000-0000-000000000001")
        worker = "app.ingestion.meeting_brief_worker"
        with (
            mock.patch(
                f"{worker}.eligible_broadcast_ids",
                return_value=[broadcast_id],
            ),
            mock.patch(
                f"{worker}.generate_one",
                side_effect=DailyTokenLimitReached("limit"),
            ),
            mock.patch(
                f"{worker}.recent_openai_mapping_candidate",
            ) as candidate,
        ):
            result = process_available()
        candidate.assert_not_called()
        self.assertEqual(result[0]["status"], "DAILY_TOKEN_LIMIT")

    def test_daily_limit_defers_without_caching_a_failure(self) -> None:
        brief = {
            "topics": [{
                "id": "topic-1", "title": "승강기 안전", "summary": "",
                "evidence_ids": ["utterance-1"], "speaker_points": [],
            }],
            "tasks": [],
            "live_topic_lineage": {
                "clusters": [{
                    "id": "cluster-1", "title": "승강기 안전",
                    "mapping_status": "UNMAPPED",
                }],
                "unmapped_cluster_count": 1,
            },
        }
        client = mock.Mock(
            model="gpt-5.4-mini",
            map_live_topics=mock.Mock(
                side_effect=DailyTokenLimitReached("limit")
            ),
        )
        mapped, result = map_unlinked_brief_once(brief, client)
        self.assertEqual(result["status"], "DEFERRED")
        self.assertNotIn(
            "semantic_mapping_version",
            mapped.get("live_topic_assignment") or {},
        )


if __name__ == "__main__":
    unittest.main()
