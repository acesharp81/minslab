from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from app.adapters.national_assembly.base import SourcePayload
from app.ingestion.live_monitor import probe_assembly_live_once


FIXTURES = Path(__file__).parent / "fixtures"


class LiveMonitorTests(unittest.TestCase):
    def test_live_target_fetches_play_contract_and_saves_status(self):
        listing = (FIXTURES / "synthetic_assembly_live_list.json").read_bytes()
        play = (FIXTURES / "synthetic_assembly_live_play.json").read_bytes()

        def fake_fetch(source_key: str, url: str):
            content = play if source_key == "assembly_live_play" else listing
            return SourcePayload(source_key, content, "application/json", datetime.now(timezone.utc), url, 200)

        class RecordingSink:
            def __init__(self):
                self.observations = []
                self.active = []

            def observe_broadcast(self, observation):
                self.observations.append(observation)

            def finish_poll(self, active_external_ids, observed_at):
                self.active = active_external_ids
                return 0

        sink = RecordingSink()
        with tempfile.TemporaryDirectory() as directory, patch(
            "app.ingestion.live_monitor.fetch_public_source", side_effect=fake_fetch
        ):
            root = Path(directory)
            result = probe_assembly_live_once(
                root / "raw", root / "processed/status.json", lifecycle_sink=sink
            )
            self.assertEqual(result["assembly"]["live_count"], 1)
            self.assertEqual(len(result["assembly"]["play_contracts"]), 1)
            self.assertEqual(result["assembly"]["play_contracts"][0]["caption_capture_status"], "READY_TO_CAPTURE")
            self.assertTrue((root / "processed/status.json").is_file())
            self.assertEqual(len(sink.observations), 1)
            self.assertEqual(sink.observations[0].external_id, "SIM-LAW-001")
            self.assertEqual(sink.active, ["SIM-LAW-001"])

    def test_off_air_poll_finishes_previous_broadcasts(self):
        listing = json.loads(
            (FIXTURES / "synthetic_assembly_live_list.json").read_text(encoding="utf-8")
        )
        for row in listing["xlist"]:
            row["xstat"] = "0"
            row["xcgcd"] = ""

        class RecordingSink:
            active = None

            def observe_broadcast(self, observation):
                raise AssertionError("off-air poll must not observe a broadcast")

            def finish_poll(self, active_external_ids, observed_at):
                self.active = active_external_ids
                return 1

        sink = RecordingSink()

        def fake_fetch(source_key: str, url: str):
            return SourcePayload(
                source_key, json.dumps(listing).encode(), "application/json",
                datetime.now(timezone.utc), url, 200,
            )

        with tempfile.TemporaryDirectory() as directory, patch(
            "app.ingestion.live_monitor.fetch_public_source", side_effect=fake_fetch
        ):
            root = Path(directory)
            probe_assembly_live_once(
                root / "raw", root / "processed/status.json", lifecycle_sink=sink
            )
        self.assertEqual(sink.active, [])


if __name__ == "__main__":
    unittest.main()
