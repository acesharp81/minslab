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

    def test_short_answers_are_classified_for_watched_meetings_and_cached(self):
        from types import SimpleNamespace
        item = {"content_hash": "b" * 64, "text": "네, 제출하겠습니다.", "segment_count": 1}
        repository = mock.Mock()
        repository.existing_hashes.return_value = set()
        repository.deferred_hashes.return_value = set()
        repository.save_many.return_value = 1
        client = mock.Mock(provider="gemini", model="fixture", prompt_version="fixture")
        client.summarize.return_value = SimpleNamespace(items=[{
            "content_hash": item["content_hash"], "summary": "자료 제출을 약속했다.",
            "live_insight": {"topic": "예산 자료 제출", "topic_key": "예산 자료"},
        }], usage_metadata={})
        with mock.patch("app.services.summary_cache.SummaryRepository", return_value=repository):
            stats = cache_missing_summaries(mock.Mock(), "broadcast", [item, item], client,
                                           include_short=True, batch_items=8)
        self.assertEqual(stats["saved"], 1)
        self.assertEqual(len(client.summarize.call_args.args[0]), 1)
        self.assertEqual(repository.save_many.call_args.args[1][0]["original_char_count"], len(item["text"]))

    def test_configuration_error_aborts_instead_of_repeating_for_every_batch(self):
        import requests
        repository = mock.Mock()
        repository.existing_hashes.return_value = set()
        repository.deferred_hashes.return_value = set()
        response = requests.Response()
        response.status_code = 400
        client = mock.Mock(provider="gemini", model="fixture", prompt_version="fixture")
        client.summarize.side_effect = requests.HTTPError("mandatory reasoning", response=response)
        items = [{"content_hash": str(i), "text": "짧은 답변"} for i in range(5)]
        with mock.patch("app.services.summary_cache.SummaryRepository", return_value=repository):
            with self.assertRaises(requests.HTTPError):
                cache_missing_summaries(mock.Mock(), "broadcast", items, client, include_short=True)
        client.summarize.assert_called_once()
        self.assertEqual(repository.record_failure.call_count, 2)

    def test_transient_provider_bad_request_retries_with_reserved_quota(self):
        from types import SimpleNamespace

        import requests
        repository = mock.Mock()
        repository.existing_hashes.return_value = set()
        repository.deferred_hashes.return_value = set()
        repository.reserve_daily_request.side_effect = [1, 2]
        repository.daily_usage.return_value = 2
        repository.save_many.return_value = 1
        response = requests.Response()
        response.status_code = 400
        client = mock.Mock(provider="openrouter", model="fixture", prompt_version="fixture")
        client.summarize.side_effect = [
            requests.HTTPError('OpenRouter 400: {"msg":"bad request"}', response=response),
            SimpleNamespace(items=[{"content_hash": "a", "summary": "자료 제출을 약속했다.", "live_insight": {"topic": "자료 제출"}}], usage_metadata={}),
        ]
        with mock.patch("app.services.summary_cache.SummaryRepository", return_value=repository), \
             mock.patch("app.services.summary_cache.time.sleep"):
            result = cache_missing_summaries(mock.Mock(), "broadcast",
                [{"content_hash": "a", "text": "네, 제출하겠습니다."}], client, include_short=True)
        self.assertEqual(result["saved"], 1)
        self.assertEqual(result["api_requests"], 2)
        self.assertEqual(repository.reserve_daily_request.call_count, 2)
        repository.record_failure.assert_not_called()

    def test_malformed_batch_is_split_and_partial_response_retries_only_omissions(self):
        from types import SimpleNamespace
        repository = mock.Mock()
        repository.existing_hashes.return_value = set()
        repository.deferred_hashes.return_value = set()
        repository.save_many.side_effect = lambda broadcast, rows, **kwargs: len(rows)
        client = mock.Mock(provider="gemini", model="fixture", prompt_version="fixture")
        calls = []
        def summarize(batch):
            calls.append([u["content_hash"] for u in batch])
            if len(batch) > 2:
                raise ValueError("truncated JSON")
            # Return a complete first item, simulating a partly cut response.
            return SimpleNamespace(items=[{"content_hash": batch[0]["content_hash"],
                "summary": "자료 제출을 약속했다.", "live_insight": {"topic": "자료 제출"}}], usage_metadata={})
        client.summarize.side_effect = summarize
        with mock.patch("app.services.summary_cache.SummaryRepository", return_value=repository), \
             mock.patch("app.services.summary_cache.time.sleep"):
            result = cache_missing_summaries(mock.Mock(), "broadcast",
                [{"content_hash": str(i), "text": "네, 제출하겠습니다."} for i in range(4)],
                client, include_short=True, batch_items=8)
        self.assertEqual(4, result["saved"])
        self.assertEqual(0, result["failed"])
        saved = [row["content_hash"] for call in repository.save_many.call_args_list for row in call.args[1]]
        self.assertEqual(["0", "1", "2", "3"], sorted(saved))
        repository.record_failure.assert_not_called()


if __name__ == "__main__":
    unittest.main()


def test_short_unwatched_legacy_task_is_reviewed_before_new_long_turn():
    from types import SimpleNamespace
    repo=mock.Mock()
    repo.existing_hashes.return_value=set()
    repo.deferred_hashes.return_value=set()
    repo.save_many.side_effect=lambda bid,items,**kwargs:len(items)
    client=mock.Mock(provider='gemini',model='fixture',prompt_version='fixture')
    seen=[]
    def summarize(batch):
        seen.extend(u['content_hash'] for u in batch)
        return SimpleNamespace(items=[{'content_hash':u['content_hash'],'summary':'답변했다.','live_insight':{'task':None}} for u in batch],usage_metadata={})
    client.summarize.side_effect=summarize
    with mock.patch('app.services.summary_cache.SummaryRepository',return_value=repo),mock.patch('app.services.summary_cache.time.sleep'):
        result=cache_missing_summaries(mock.Mock(),'bid',[
            {'content_hash':'new','text':'긴 발언 '*50},
            {'content_hash':'old','text':'예 그렇습니다.'}],client,review_hashes={'old'})
    assert seen==['old','new']
    assert result['saved']==2
