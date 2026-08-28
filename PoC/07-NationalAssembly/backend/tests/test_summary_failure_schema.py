from __future__ import annotations

import unittest
from pathlib import Path


class SummaryFailureSchemaTests(unittest.TestCase):
    def test_failure_retry_table_is_separate_from_success_cache(self):
        sql = (Path(__file__).parents[1] / "migrations" / "0021_transcript_summary_failures.sql").read_text()
        self.assertIn("CREATE TABLE transcript_utterance_summary_failures", sql)
        self.assertIn("retry_after timestamptz NOT NULL", sql)
        self.assertIn("PRIMARY KEY (broadcast_id, content_hash, provider, model, prompt_version)", sql)


if __name__ == "__main__":
    unittest.main()
