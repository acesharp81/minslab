from __future__ import annotations

import json
import unittest
from unittest import mock

from app.services.mistral_summary import MistralSummaryClient


class FakeResponse:
    status_code = 200

    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class MistralSummaryTests(unittest.TestCase):
    def test_uses_official_endpoint_structured_output_and_expected_ids(self):
        content_hash = "a" * 64
        response = FakeResponse({
            "id": "mistral-request-1",
            "choices": [{"message": {"content": json.dumps({
                "summaries": [
                    {
                        "id": content_hash,
                        "summary": "예산 근거와 집행 일정을 질의했다.",
                        "topic": "추가경정예산 집행 일정",
                        "topic_key": "추경 예산 집행",
                        "role": "QUESTION",
                        "task": "부처별 집행 일정을 제출한다.",
                        "owners": ["기획재정부"],
                    },
                    {
                        "id": "unexpected", "summary": "저장 금지",
                        "topic": "저장 금지", "topic_key": "저장 금지",
                        "role": "STATEMENT", "task": "", "owners": [],
                    },
                ],
            }, ensure_ascii=False)}}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 10},
        })
        utterance = {
            "content_hash": content_hash,
            "speaker_label": "화자 1",
            "text": "국회 발언 원문 " * 30,
        }
        with mock.patch(
            "app.services.mistral_summary.requests.post", return_value=response,
        ) as request:
            result = MistralSummaryClient("secret").summarize([utterance])
        self.assertEqual(result.items, [{
            "content_hash": content_hash,
            "summary": "예산 근거와 집행 일정을 질의했다.",
            "live_insight": {
                "topic": "추가경정예산 집행 일정",
                "topic_key": "추경 예산 집행",
                "role": "QUESTION",
                "task": "부처별 집행 일정을 제출한다.",
                "owners": ["기획재정부"],
                "status": "PROVISIONAL",
            },
        }])
        self.assertEqual(request.call_args.args[0], "https://api.mistral.ai/v1/chat/completions")
        self.assertEqual(
            request.call_args.kwargs["headers"]["Authorization"], "Bearer secret"
        )
        body = request.call_args.kwargs["json"]
        self.assertEqual(body["model"], "mistral-small-2603")
        self.assertEqual(body["reasoning_effort"], "none")
        self.assertEqual(body["response_format"]["type"], "json_schema")
        required = body["response_format"]["json_schema"]["schema"] \
            ["properties"]["summaries"]["items"]["required"]
        self.assertIn("topic_key", required)
        self.assertIn("owners", required)


if __name__ == "__main__":
    unittest.main()
