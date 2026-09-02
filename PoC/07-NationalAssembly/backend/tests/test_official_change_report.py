from __future__ import annotations

import json
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from app.db.official_change_report_repository import OfficialChangeReportRepository
from app.services.official_change_report import (
    OpenRouterOfficialChangeReportClient,
    deterministic_unchanged_report,
)


PROJECT_DIR = Path(__file__).resolve().parents[2]


class _Response:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        content = {
            "overall_assessment": "일부 사실 보완",
            "summary": "담당 기관과 확정 표현이 공식 자료 기준으로 보완됐습니다.",
            "items": [{
                "title": "담당 기관 보완",
                "explanation": "잠정 표현에 공식 담당 기관이 추가됐습니다.",
                "importance": "보완",
                "change_ids": ["change-1", "not-provided"],
            }],
            "speaker_note": "공식 회의록 기준으로 화자를 대조했습니다.",
        }
        return {
            "id": "request-1",
            "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(content)}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 40},
        }


class OfficialChangeReportTests(unittest.TestCase):
    def test_no_change_report_is_deterministic_and_requires_no_api(self):
        report = deterministic_unchanged_report({
            "changes": [], "speaker_stats": {"confirmed_speakers": 3},
        })
        self.assertEqual("의미 변경 없음", report["overall_assessment"])
        self.assertEqual([], report["items"])
        self.assertIn("3명", report["speaker_note"])

    @patch("app.services.official_change_report.requests.post", return_value=_Response())
    def test_provider_can_only_group_server_verified_change_ids(self, post):
        source = {
            "id": "change-1", "entity_type": "task", "operation": "UPDATE",
            "field": "title", "before": "대책을 검토한다",
            "after": "행정안전부가 대책을 추진한다",
            "presentation_status": "",
        }
        result = OpenRouterOfficialChangeReportClient(
            "test-key", model="test/model", base_url="https://example.invalid",
        ).generate({"meeting_title": "회의", "changes": [source]})
        item = result.report["items"][0]
        self.assertEqual(["change-1"], item["change_ids"])
        self.assertEqual("대책을 검토한다", item["changes"][0]["before"])
        self.assertEqual("행정안전부가 대책을 추진한다", item["changes"][0]["after"])
        request = post.call_args.kwargs["json"]
        self.assertEqual("deny", request["provider"]["data_collection"])
        self.assertFalse(request["provider"]["allow_fallbacks"])

    def test_snapshot_hash_is_stable_and_assigns_local_change_ids(self):
        integration_id = uuid.uuid4()
        row = (
            integration_id, "회의", {"headline": "잠정"}, {"headline": "공식"},
            [{"entity_type": "topic", "operation": "UPDATE", "before": "전", "after": "후"}],
            {"confirmed_speakers": 2},
        )
        left = OfficialChangeReportRepository._snapshot(row)
        right = OfficialChangeReportRepository._snapshot(row)
        self.assertEqual(left[2], right[2])
        self.assertEqual("change-1", left[1]["changes"][0]["id"])

    def test_worker_and_migration_have_separate_and_global_limits(self):
        worker = (PROJECT_DIR / "backend/app/ingestion/topic_report_worker.py").read_text(encoding="utf-8")
        migration = (PROJECT_DIR / "backend/migrations/0039_official_change_reports.sql").read_text(encoding="utf-8")
        self.assertIn("official_change_report_daily_limit", worker)
        self.assertIn('reserve_daily_request(\n            "openrouter"', worker)
        self.assertIn("meeting_official_change_reports", migration)
        self.assertIn("official_change_report_daily_usage", migration)


if __name__ == "__main__":
    unittest.main()
