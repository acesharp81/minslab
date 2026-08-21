from __future__ import annotations

import json
import unittest
from pathlib import Path

from app.experiments.live_replay import replay_live_fixture
from app.services.live_magazine import filter_magazine_payload


FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_live_broadcast.json"


class LiveMagazineServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        cls.payload = replay_live_fixture(fixture)

    def test_filters_n_previous_cards_by_institution(self):
        result = filter_magazine_payload(self.payload, institution="EXECUTIVE", limit=1)
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["available_count"], 2)
        self.assertEqual(result["items"][0]["institution"], "EXECUTIVE")
        self.assertEqual(result["rotation_ms"], 5_000)

    def test_filters_by_related_committee_scope(self):
        result = filter_magazine_payload(self.payload, scope="법제사법위원회")
        self.assertEqual(result["count"], 1)
        self.assertIn("법제사법위원회", result["items"][0]["committees"])

    def test_rejects_unmarked_payload(self):
        with self.assertRaises(ValueError):
            filter_magazine_payload({"simulation": False})
