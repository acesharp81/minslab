from __future__ import annotations

import unittest

from harness_engine import AGENTS, DEFAULT_MODELS, build_demo_run, harness_config


class HarnessEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.run = build_demo_run("가상 예약시스템 장애 대응 패키지")

    def test_agent_ids_are_unique(self) -> None:
        ids = [agent.id for agent in AGENTS]
        self.assertEqual(len(ids), len(set(ids)))

    def test_event_timeline_is_monotonic(self) -> None:
        times = [event["at_ms"] for event in self.run["events"]]
        self.assertEqual(times, sorted(times))
        self.assertEqual(
            [event["seq"] for event in self.run["events"]],
            list(range(1, len(self.run["events"]) + 1)),
        )

    def test_visual_contract_contains_critical_events(self) -> None:
        event_types = {event["type"] for event in self.run["events"]}
        required = {
            "meeting.requested",
            "inference.queued",
            "inference.started",
            "artifact.created",
            "handoff.requested",
            "review.started",
            "review.item",
            "review.failed",
            "review.passed",
            "submission.requested",
            "run.completed",
        }
        self.assertTrue(required.issubset(event_types))

    def test_each_quality_gate_has_visible_review_events(self) -> None:
        events = self.run["events"]
        gates = {
            event["data"]["gate"]
            for event in events
            if event["type"] == "review.started"
        }
        self.assertEqual(gates, {"evidence", "analysis", "draft", "risk"})

    def test_artifact_catalog_matches_created_events(self) -> None:
        catalog = self.run["artifacts"]
        catalog_ids = {item["id"] for item in catalog}
        created_ids = {
            event["data"]["artifact_id"]
            for event in self.run["events"]
            if event["type"] == "artifact.created"
        }
        self.assertEqual(catalog_ids, created_ids)
        self.assertEqual(len(catalog), 9)
        self.assertTrue(all(item["content"].startswith("#") for item in catalog))
        self.assertTrue(all(item["summary"] for item in catalog))

    def test_handoffs_reference_known_agents(self) -> None:
        agent_ids = {agent.id for agent in AGENTS}
        for event in self.run["events"]:
            if event["type"] != "handoff.requested":
                continue
            self.assertIn(event["data"]["from_id"], agent_ids)
            self.assertIn(event["data"]["to_id"], agent_ids)

    def test_provider_limits_are_conservative(self) -> None:
        limits = {item.provider: item.max_in_flight for item in DEFAULT_MODELS}
        self.assertEqual(limits["ollama"], 1)
        self.assertEqual(limits["huggingface"], 1)
        self.assertEqual(limits["openrouter"], 2)

    def test_config_has_hierarchy_and_pools(self) -> None:
        config = harness_config()
        self.assertGreaterEqual(len(config["agents"]), 10)
        self.assertGreaterEqual(len(config["pools"]), 2)
        self.assertGreaterEqual(len(config["phases"]), 6)


if __name__ == "__main__":
    unittest.main()
