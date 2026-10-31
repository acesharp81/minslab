from __future__ import annotations

import json
import unittest
from unittest import mock

from app.services.openrouter_summary import (
    PROMPT_VERSION,
    OpenRouterSummaryClient,
    add_conversation_context,
    mixes_immediate_reply_task,
)
from app.services.transcript_presentation import utterance_content_hash


class FakeResponse:
    status_code = 200

    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class OpenRouterSummaryTests(unittest.TestCase):
    def test_uses_bearer_key_and_keeps_only_expected_ids(self):
        text = "국회 발언 원문 " * 30
        content_hash = utterance_content_hash(text)
        content = json.dumps({"summaries": [
            {
                "id": content_hash,
                "summary": "예산 근거와 추진 일정을 질의했다.",
                "topic": "예산 추진 일정", "topic_key": "예산 추진",
                "role": "QUESTION", "task": "", "owners": ["기획재정부"],
            },
            {
                "id": "unexpected", "summary": "저장 금지",
                "topic": "저장 금지", "topic_key": "저장 금지",
                "role": "STATEMENT", "task": "", "owners": [],
            },
        ]}, ensure_ascii=False)
        response = FakeResponse({
            "id": "request-1", "provider": "Google",
            "choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 8},
        })
        with mock.patch(
            "app.services.openrouter_summary.requests.post", return_value=response,
        ) as request:
            result = OpenRouterSummaryClient("secret").summarize([{
                "content_hash": content_hash, "speaker_label": "화자 1", "text": text,
            }])
        self.assertEqual(result.items[0]["content_hash"], content_hash)
        self.assertEqual(result.items[0]["live_insight"]["topic_key"], "예산 추진")
        self.assertEqual(len(result.items), 1)
        self.assertEqual(
            request.call_args.kwargs["headers"]["Authorization"], "Bearer secret"
        )
        self.assertNotIn("secret", request.call_args.args[0])
        self.assertEqual(request.call_args.kwargs["json"]["reasoning"], {"enabled": False, "exclude": True})
        self.assertEqual(["nvidia/nemotron-3.5-super-vl:free"], request.call_args.kwargs["json"]["models"])
        self.assertGreaterEqual(request.call_args.kwargs["json"]["max_tokens"], 8192)

    def test_mixed_oral_reply_is_rejected_but_written_followup_survives(self):
        def item(task):
            return {"live_insight": {"task": task}}
        source = "안전점검 결과를 다음 주까지 제출해 주십시오. 오늘 점검한 학교 수는 이 자리에서 답해 주십시오."
        self.assertTrue(mixes_immediate_reply_task(item("점검 결과 제출, 학교 수 답변"), source))
        self.assertFalse(mixes_immediate_reply_task(item("점검 결과 제출"), source))
        self.assertFalse(mixes_immediate_reply_task(item("점검 결과 서면 답변 제출"),
            "점검 결과는 다음 주까지 서면으로 답변해 주십시오."))
        self.assertFalse(mixes_immediate_reply_task(item(None), source))

    def test_rejected_mixed_task_is_returned_to_pool_without_losing_other_summary(self):
        source = "안전점검 결과를 다음 주까지 제출해 주십시오. 오늘 점검한 학교 수는 이 자리에서 답해 주십시오."
        content_hash = utterance_content_hash(source)
        raw = {"id": content_hash, "summary": "점검 결과 제출과 학교 수 답변을 요구했다.",
               "topic": "안전점검 결과", "topic_key": "안전점검", "role": "REQUEST",
               "task": "점검 결과 제출, 학교 수 답변", "owners": [],
               "task_kind": "FOLLOW_UP_REQUEST", "task_evidence_quote": source}
        response = FakeResponse({"choices": [{"message": {"content": json.dumps({"summaries": [raw]}, ensure_ascii=False)}}]})
        with mock.patch("app.services.openrouter_summary.requests.post", return_value=response):
            result = OpenRouterSummaryClient("fixture").summarize([{"content_hash": content_hash, "text": source}])
        self.assertEqual([], result.items)
        self.assertEqual([content_hash], result.usage_metadata["rejected_ids"])
        self.assertEqual("IMMEDIATE_REPLY_MIXED_IN_FOLLOW_UP", result.usage_metadata["quality_rejections"][content_hash])

    def test_other_models_keep_reasoning_enabled_by_provider(self):
        response = FakeResponse({"choices": [{"message": {"content": '{"summaries": []}'}}]})
        with mock.patch("app.services.openrouter_summary.requests.post", return_value=response) as request:
            OpenRouterSummaryClient("fixture", model="liquid/lfm-2.5-2.6b:free").summarize([])
        self.assertEqual({"effort": "low", "exclude": True}, request.call_args.kwargs["json"]["reasoning"])
        self.assertEqual(["liquid/lfm-2.5-2.6b:free"], request.call_args.kwargs["json"]["models"])

    def test_dots_direct_json_does_not_fall_back_to_required_reasoning_model(self):
        response = FakeResponse({"choices": [{"message": {"content": '{"summaries": []}'}}]})
        with mock.patch("app.services.openrouter_summary.requests.post", return_value=response) as request:
            OpenRouterSummaryClient("fixture", model="dots-studio/dots-3-note-preview:free").summarize([])
        body = request.call_args.kwargs["json"]
        self.assertEqual(["dots-studio/dots-3-note-preview:free"], body["models"])
        self.assertEqual({"enabled": False, "exclude": True}, body["reasoning"])
        self.assertEqual(8192, body["max_tokens"])

    def test_uses_complete_target_and_adjacent_turns_as_context(self):
        utterances = [
            {
                "content_hash": str(index) * 64,
                "speaker_label": str(index),
                "text": f"발언 {index} 전체 원문",
            }
            for index in range(1, 5)
        ]
        contextualized = add_conversation_context(utterances)
        target = contextualized[2]
        self.assertEqual(
            [item["position"] for item in target["conversation_context"]],
            ["before", "before", "target", "after"],
        )
        self.assertEqual(
            [item["text"] for item in target["conversation_context"]],
            [item["text"] for item in utterances],
        )
        self.assertEqual(target["text"], utterances[2]["text"])
        self.assertEqual(PROMPT_VERSION, "assembly-conversation-summary/2.4")


if __name__ == "__main__":
    unittest.main()
