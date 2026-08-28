from __future__ import annotations

import json
import unittest
from unittest import mock

from app.services.gemini_summary import GeminiSummaryClient, iter_summary_batches
from app.services.transcript_presentation import utterance_content_hash


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


class GeminiSummaryTests(unittest.TestCase):
    def test_structured_summary_response_keeps_only_expected_ids(self):
        text = "국회 발언 원문 " * 30
        content_hash = utterance_content_hash(text)
        response_text = json.dumps([
            {"id": content_hash, "summary": "핵심 정책의 추진 일정과 예산 근거를 질의했다."},
            {"id": "unexpected", "summary": "저장하면 안 됨"},
        ], ensure_ascii=False)
        payload = {
            "candidates": [{"content": {"parts": [{"text": response_text}]}}],
            "usageMetadata": {"promptTokenCount": 10},
        }
        with mock.patch(
            "app.services.gemini_summary.requests.post",
            return_value=FakeResponse(payload),
        ) as request:
            result = GeminiSummaryClient("secret", model="gemini-3.7-flash").summarize([{
                "content_hash": content_hash,
                "speaker_label": "화자 1",
                "text": text,
            }])
        self.assertEqual(result.items, [{
            "content_hash": content_hash,
            "summary": "핵심 정책의 추진 일정과 예산 근거를 질의했다.",
        }])
        self.assertNotIn("secret", request.call_args.args[0])
        self.assertEqual(request.call_args.kwargs["headers"]["x-goog-api-key"], "secret")

    def test_batches_bound_request_count_and_size(self):
        items = [{"text": "가" * 10, "content_hash": str(index)} for index in range(25)]
        batches = list(iter_summary_batches(items))
        self.assertEqual([len(batch) for batch in batches], [6, 6, 6, 6, 1])


if __name__ == "__main__":
    unittest.main()
