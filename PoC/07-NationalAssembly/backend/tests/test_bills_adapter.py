from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.adapters.national_assembly.base import SourcePayload
from app.adapters.national_assembly.bills import BillsAdapter

FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_bills_response.json"


class BillsAdapterTests(unittest.TestCase):
    def test_parses_indexed_and_full_official_fields(self):
        payload = SourcePayload("bills", FIXTURE.read_bytes(), "application/json", datetime.now(timezone.utc), "https://example.invalid", 200)
        row = BillsAdapter().parse(payload)[0]
        self.assertEqual(row.bill_id, "PRC_SYNTHETIC_001")
        self.assertEqual(row.process_stage_code, "공포")
        self.assertEqual(row.official_data["PROM_LAW_NM"], "합성법")
        self.assertEqual(len(row.source_record_key), 64)


if __name__ == "__main__":
    unittest.main()
