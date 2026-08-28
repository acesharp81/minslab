from __future__ import annotations

import unittest
from unittest import mock

from app.services.summary_cache import cache_missing_summaries


class SummaryCacheTests(unittest.TestCase):
    def test_cached_content_is_not_sent_to_gemini_again(self):
        utterance = {
            "content_hash": "a" * 64,
            "text": "긴 발언 " * 50,
            "source_speaker_label": "1",
            "segment_count": 5,
        }
        repository = mock.Mock()
        repository.existing_hashes.return_value = {utterance["content_hash"]}
        repository.deferred_hashes.return_value = set()
        repository.daily_usage.return_value = 0
        client = mock.Mock(
            provider="gemini", model="gemini-3.7-flash",
            prompt_version="assembly-conversation-summary/2.0",
        )
        with mock.patch(
            "app.services.summary_cache.SummaryRepository",
            return_value=repository,
        ):
            stats = cache_missing_summaries(
                mock.Mock(), "broadcast-id", [utterance], client,
            )
        client.summarize.assert_not_called()
        repository.save_many.assert_not_called()
        self.assertEqual(stats["cached"], 1)
        self.assertEqual(stats["api_requests"], 0)


if __name__ == "__main__":
    unittest.main()
