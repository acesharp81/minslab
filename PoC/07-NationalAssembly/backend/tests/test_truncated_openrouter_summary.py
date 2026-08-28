from __future__ import annotations

import unittest

from app.services.openrouter_summary import parse_summary_items


class TruncatedOpenRouterSummaryTests(unittest.TestCase):
    def test_recovers_only_complete_objects_from_truncated_wrapper(self):
        text = '{"summaries":[{"id":"one","summary":"완료"},{"id":"two","summary":"잘림'
        self.assertEqual(
            parse_summary_items(text), [{"id": "one", "summary": "완료"}]
        )


if __name__ == "__main__":
    unittest.main()
