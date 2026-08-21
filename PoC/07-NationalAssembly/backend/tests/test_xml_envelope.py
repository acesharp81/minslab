from __future__ import annotations

import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.adapters.national_assembly.base import AdapterError
from app.adapters.national_assembly.xml_envelope import parse_xml_envelope


FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_open_api_response.xml"


class XmlEnvelopeTests(unittest.TestCase):
    def test_parses_synthetic_envelope_without_source_field_assumptions(self):
        envelope = parse_xml_envelope(FIXTURE.read_bytes())
        self.assertEqual(envelope.result_code, "00")
        self.assertEqual(envelope.result_message, "TEST_OK")
        self.assertEqual(envelope.total_count, 1)
        self.assertEqual(envelope.rows[0]["EXTERNAL_ID"], "fixture-001")
        self.assertIsNone(envelope.rows[0]["OPTIONAL_VALUE"])

    def test_rejects_malformed_xml(self):
        with self.assertRaises(AdapterError):
            parse_xml_envelope(b"<response><broken></response>")

    def test_rejects_invalid_count(self):
        with self.assertRaises(AdapterError):
            parse_xml_envelope(b"<response><totalCount>many</totalCount></response>")


if __name__ == "__main__":
    unittest.main()
