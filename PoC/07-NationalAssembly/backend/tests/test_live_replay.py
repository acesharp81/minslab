from __future__ import annotations

import json
import unittest
from pathlib import Path

from app.experiments.live_replay import replay_live_fixture


FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_live_broadcast.json"


class LiveReplayTests(unittest.TestCase):
    def test_replay_preserves_revisions_and_builds_magazine_cards(self):
        result = replay_live_fixture(json.loads(FIXTURE.read_text(encoding="utf-8")))

        self.assertTrue(result["simulation"])
        self.assertEqual(result["authority_status"], "PROVISIONAL")
        self.assertEqual(result["reconciliation_status"], "UNRESOLVED")
        self.assertEqual(result["event_count"], 12)
        self.assertEqual(result["segment_count"], 4)
        self.assertEqual(len(result["magazine"]), 4)
        self.assertEqual(result["segments"][0]["revision_count"], 3)
        self.assertIn("재난 대응", result["segments"][0]["topics"])
        self.assertIn("행정안전부", result["segments"][0]["ministries"])
        self.assertIn("법제사법위원회", result["segments"][2]["committees"])

    def test_non_simulation_input_is_rejected(self):
        with self.assertRaises(ValueError):
            replay_live_fixture({"simulation": False})

    def test_emitted_events_are_in_live_timeline_order(self):
        emitted: list[dict[str, object]] = []
        replay_live_fixture(
            json.loads(FIXTURE.read_text(encoding="utf-8")),
            emit=emitted.append,
        )
        self.assertEqual([event["at_ms"] for event in emitted], sorted(event["at_ms"] for event in emitted))


if __name__ == "__main__":
    unittest.main()
