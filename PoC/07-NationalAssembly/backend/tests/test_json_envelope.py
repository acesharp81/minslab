from __future__ import annotations

import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.adapters.national_assembly.base import AdapterError
from app.adapters.national_assembly.json_envelope import parse_json_envelope


FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_schedule_response.json"


class JsonEnvelopeTests(unittest.TestCase):
    def test_parses_verified_open_assembly_shape(self):
        envelope = parse_json_envelope(FIXTURE.read_bytes(), expected_resource="ALLSCHEDULE")
        self.assertTrue(envelope.ok)
        self.assertEqual(envelope.total_count, 1)
        self.assertEqual(len(envelope.rows), 1)

    def test_accepts_official_empty_result(self):
        envelope = parse_json_envelope(
            b'{"RESULT":{"CODE":"INFO-200","MESSAGE":"no data"}}',
            expected_resource="ALLSCHEDULE",
        )
        self.assertTrue(envelope.empty)
        self.assertEqual(envelope.rows, ())

    def test_rejects_wrong_resource(self):
        with self.assertRaises(AdapterError):
            parse_json_envelope(FIXTURE.read_bytes(), expected_resource="OTHER")


if __name__ == "__main__":
    unittest.main()
