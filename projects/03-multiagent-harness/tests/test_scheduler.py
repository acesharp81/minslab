from __future__ import annotations

import unittest

from harness_engine import AGENTS
from scheduler import CapabilityRouter, HierarchicalScheduler, SchedulerError, WorkItem, incident_response_work_items


class SchedulerTests(unittest.TestCase):
    def test_shared_pool_distributes_work(self) -> None:
        router = CapabilityRouter(AGENTS)
        first = WorkItem("a", "자료 A", "collect", "evidence-coordinator")
        second = WorkItem("b", "자료 B", "collect", "evidence-coordinator")
        self.assertNotEqual(router.assign(first), router.assign(second))

    def test_incident_workflow_has_parallel_waves(self) -> None:
        scheduler = HierarchicalScheduler(AGENTS)
        plan = scheduler.plan(incident_response_work_items())
        self.assertEqual(set(plan["waves"][0]), {"collect-facts", "collect-public"})
        self.assertIn("summarize-evidence", plan["waves"][1])
        self.assertEqual(set(plan["waves"][2]), {"technical-analysis", "legal-review"})

    def test_cycle_is_rejected(self) -> None:
        work = [
            WorkItem("a", "A", "collect", "x", depends_on=("b",)),
            WorkItem("b", "B", "collect", "x", depends_on=("a",)),
        ]
        with self.assertRaises(SchedulerError):
            HierarchicalScheduler.validate(work)


if __name__ == "__main__":
    unittest.main()
