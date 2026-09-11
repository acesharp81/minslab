from __future__ import annotations

import json
import unittest
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.db.official_change_report_repository import OfficialChangeReportRepository
from app.services.official_change_report import (
    OpenRouterOfficialChangeReportClient,
    _parse,
    deterministic_changed_report,
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
    def test_parser_recovers_json_surrounded_by_model_commentary(self):
        parsed = _parse(
            "결과입니다.\n```json\n"
            '{"overall_assessment":"일부 사실 보완","items":[]}'
            "\n```\n감사합니다."
        )
        self.assertEqual("일부 사실 보완", parsed["overall_assessment"])

    def test_parser_accepts_block_content(self):
        parsed = _parse([
            {"type": "text", "text": '{"summary":"공식 보완"}'},
        ])
        self.assertEqual("공식 보완", parsed["summary"])

    def test_changed_fallback_only_uses_verified_change_ids(self):
        source = {
            "id": "change-1", "title": "담당 기관 확정",
            "operation": "UPDATE", "field": "ministry",
            "before": "관계 부처 검토", "after": "행정안전부가 추진",
        }
        report = deterministic_changed_report({
            "changes": [source], "speaker_stats": {"confirmed_speakers": 2},
        })
        self.assertEqual(["change-1"], report["items"][0]["change_ids"])
        self.assertEqual([source], report["items"][0]["changes"])
        self.assertIn("2명", report["speaker_note"])

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
        self.assertEqual(1, result.usage_metadata["api_requests"])
        request = post.call_args.kwargs["json"]
        self.assertEqual("allow", request["provider"]["data_collection"])
        self.assertTrue(request["provider"]["allow_fallbacks"])

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
        changed_display = json.loads(json.dumps(left[1]))
        changed_display["changes"][0]["display_after"] = "표시 문장부호만 변경."
        self.assertEqual(
            left[2], OfficialChangeReportRepository._input_hash(changed_display),
        )

    def test_same_input_hash_reuses_ready_report_across_integration_versions(self):
        source_integration = uuid.uuid4()
        target_integration = uuid.uuid4()
        meeting_row = (
            target_integration, "회의", {"headline": "잠정"},
            {"headline": "공식"},
            [{"entity_type": "topic", "operation": "UPDATE", "before": "전", "after": "후"}],
            {"confirmed_speakers": 2},
        )
        rows_cursor = MagicMock()
        rows_cursor.fetchall.return_value = [meeting_row]
        reuse_cursor = MagicMock()
        reuse_cursor.fetchone.return_value = (source_integration, {"summary": "저장 결과"})
        save_cursor = MagicMock()
        save_cursor.fetchone.return_value = (uuid.uuid4(),)
        connection = MagicMock()
        connection.execute.side_effect = [rows_cursor, reuse_cursor, save_cursor]

        changed = OfficialChangeReportRepository(connection).sync_pending(
            provider="openrouter", model="test/model",
            prompt_version="official-change-report/1.0", limit=20,
        )

        self.assertEqual(1, changed)
        save_sql = connection.execute.call_args_list[2].args[0]
        save_params = connection.execute.call_args_list[2].args[1]
        self.assertIn("'READY'", save_sql)
        self.assertEqual(0, save_params[-1].obj["api_requests"])
        self.assertEqual(
            "CROSS_INTEGRATION_INPUT_HASH", save_params[-1].obj["reuse_reason"],
        )

    def test_legacy_snapshot_hash_can_reuse_and_rebind_current_display_change(self):
        current = {
            "meeting_title": "회의", "provisional_headline": "잠정",
            "official_headline": "공식", "speaker_stats": {},
            "changes": [{
                "id": "change-1", "entity_type": "topic",
                "operation": "UPDATE", "field": "summary", "title": "",
                "before": "전", "after": "후", "display_after": "후.",
                "presentation_status": "", "official_utterance_ids": ["new-id"],
            }],
        }
        report = {"items": [{
            "change_ids": ["change-1"],
            "changes": [{"id": "change-1", "display_after": "후"}],
        }]}
        rebound = OfficialChangeReportRepository._rebind_report_changes(
            report, current,
        )
        self.assertEqual(
            "후.", rebound["items"][0]["changes"][0]["display_after"],
        )
        self.assertEqual(
            ["new-id"],
            rebound["items"][0]["changes"][0]["official_utterance_ids"],
        )

    def test_worker_and_migration_have_separate_and_global_limits(self):
        worker = (PROJECT_DIR / "backend/app/ingestion/topic_report_worker.py").read_text(encoding="utf-8")
        migration = (PROJECT_DIR / "backend/migrations/0039_official_change_reports.sql").read_text(encoding="utf-8")
        self.assertIn("official_change_report_daily_limit", worker)
        self.assertIn('reserve_daily_request(\n            "openrouter"', worker)
        self.assertIn("meeting_official_change_reports", migration)
        self.assertIn("official_change_report_daily_usage", migration)


if __name__ == "__main__":
    unittest.main()
