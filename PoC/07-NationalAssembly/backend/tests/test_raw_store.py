from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.adapters.national_assembly.base import SourcePayload
from app.storage.raw_store import RawStore


class RawStoreTests(unittest.TestCase):
    def test_detects_html_and_pdf_without_mislabelling_as_xml(self):
        self.assertEqual(RawStore._detect_format(b"<!doctype html>", "text/html"), "html")
        self.assertEqual(RawStore._detect_format(b"%PDF-1.4", "application/octet-stream"), "pdf")

    def test_preserves_content_and_marks_duplicate(self):
        payload = SourcePayload(
            source_key="assembly_schedule",
            content=b'{"test":true}',
            content_type="application/xml",
            retrieved_at=datetime(2099, 1, 2, tzinfo=timezone.utc),
            source_url="https://example.invalid/source?Type=json",
            http_status=200,
        )
        with tempfile.TemporaryDirectory() as directory:
            store = RawStore(Path(directory))
            first = store.save(payload, parser_version="test/1")
            second = store.save(payload, parser_version="test/1")
            self.assertFalse(first.duplicate)
            self.assertTrue(second.duplicate)
            self.assertEqual(first.content_path.read_bytes(), payload.content)
            self.assertEqual(first.content_path.suffix, ".json")
            manifest = json.loads(first.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["content_hash"], first.content_hash)
            self.assertNotIn("KEY", manifest["source_url"])
            self.assertEqual(manifest["detected_format"], "json")
            self.assertEqual(manifest["parser_version"], "test/1")


if __name__ == "__main__":
    unittest.main()
