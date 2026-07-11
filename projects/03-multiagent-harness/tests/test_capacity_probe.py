from __future__ import annotations

import unittest

from capacity_probe import build_probe_plan, preflight


class CapacityProbeTests(unittest.TestCase):
    def test_plan_is_capped(self) -> None:
        plan = build_probe_plan(
            "openrouter:openai/gpt-4o-mini",
            concurrency=99,
            requests=2,
            max_tokens=999,
            confirmed=False,
        )
        self.assertEqual(plan.concurrency, 2)
        self.assertEqual(plan.requests, 2)
        self.assertEqual(plan.max_tokens, 32)

    def test_preflight_does_not_claim_live_call(self) -> None:
        result = preflight()
        self.assertEqual(result["mode"], "preflight")
        self.assertIn("실행하지 않았습니다", result["notice"])


if __name__ == "__main__":
    unittest.main()
