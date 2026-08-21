from __future__ import annotations

import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.adapters.national_assembly.catalog import SOURCE_CATALOG, SourceStatus, public_catalog


class SourceCatalogTests(unittest.TestCase):
    def test_all_phase_two_sources_have_verified_contracts(self):
        self.assertEqual(len(SOURCE_CATALOG), 8)
        public = public_catalog()
        self.assertTrue(all(source["status"] == SourceStatus.CONTRACT_VERIFIED for source in public))
        self.assertTrue(all(source["callable"] for source in public))
        self.assertTrue(all(source["resource"] for source in public))

    def test_catalog_keys_and_official_pages_are_unique(self):
        self.assertEqual(len({source.key for source in SOURCE_CATALOG}), len(SOURCE_CATALOG))
        self.assertEqual(len({source.data_go_kr_url for source in SOURCE_CATALOG}), len(SOURCE_CATALOG))

    def test_public_catalog_never_exposes_an_api_key(self):
        serialized = repr(public_catalog()).lower()
        self.assertNotIn("api_key", serialized)
        self.assertNotIn("servicekey", serialized)


if __name__ == "__main__":
    unittest.main()
