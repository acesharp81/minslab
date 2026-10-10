from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock


BASE = Path(__file__).resolve().parents[1]


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, BASE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


board = load("poc11_board_test", "board_collector.py")
service = load("poc11_service_board_test", "service.py")


class BoardTests(unittest.TestCase):
    def test_multi_case_hwp_text_becomes_existing_qa_shape(self):
        extracted = """2020년도 민원상담 사례
① 첫째 사례
(내용) 첫째 질문
(답변) 첫째 답변
② 둘째 사례
(내용) 둘째 질문
(답변) 둘째 답변
"""
        sections = board.qa_sections(extracted, "2020년 사례집")
        self.assertEqual(len(sections), 2)
        self.assertEqual(sections[0][:2], ("첫째 질문", "첫째 답변"))
        self.assertEqual(sections[1][:2], ("둘째 질문", "둘째 답변"))
        post = {"board_seq": "103", "title": "2020년 사례집", "page_index": 2,
                "source_url": "https://counseling.go.kr/example", "body": "붙임 참조",
                "attachment_name": "cases.hwp", "posted_at": "2024-01-18"}
        records = board.records_for_post(post, extracted, "abc", "extract-hwp", "2026-10-06T03:00:00+09:00")
        api_fields = set(service._record({"consQustCntn": "질문", "nobdAnsrCntn": "답변"}, {}, "now"))
        self.assertEqual(set(records[0]), api_fields)
        self.assertEqual(records[0]["raw"]["attachment_text"], extracted)
        self.assertEqual(records[1]["request_params"]["boardSeq"], "103")
        self.assertIn("**원문:** https://counseling.go.kr/example", service.render_markdown({"version": 1, "records": records}))

    def test_unstructured_attachment_uses_labeled_topic_and_full_body(self):
        sections = board.qa_sections("□ 추진경과\n조정 과정을 설명합니다.", "협의조정 사례")
        self.assertEqual(sections[0][0], "[상담 주제] 협의조정 사례")
        self.assertIn("조정 과정", sections[0][1])

    def test_coordination_document_maps_issue_to_question_and_resolution_to_answer(self):
        extracted = """□ 사실확인
 ○ 안건내용
도로 침수 문제의 조정을 요청함
 ○ 관련기관 : 시청
□ 조정협의내용
시청은 배수로를 보수한다.
민원센터는 이행을 점검한다.
"""
        sections = board.qa_sections(extracted, "협의조정 사례")
        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0][0], "도로 침수 문제의 조정을 요청함")
        self.assertIn("이행을 점검", sections[0][1])
        self.assertEqual(sections[0][2:], ("attachment_issue", "attachment_resolution"))

    def test_board_collection_publishes_same_parts_and_deduplicates(self):
        class FakeBoard:
            def all_posts(self, client):
                return [{"board_seq": "7", "title": "테스트 상담", "page_index": 1}]
            def fetch_post(self, client, item, folder):
                return ({**item, "source_url": "https://counseling.go.kr/7", "body": "본문",
                         "attachment_name": "case.hwp"}, "(내용) 질문\n(답변) 답변", "sha", "extract-hwp")
            records_for_post = staticmethod(board.records_for_post)

        with tempfile.TemporaryDirectory() as temporary, \
             mock.patch.object(service, "_board_module", return_value=FakeBoard()), \
             mock.patch.object(service.httpx, "Client"):
            folder = Path(temporary)
            result = service.collect_board_once(data_dir=folder, today=date(2026, 10, 6))
            self.assertEqual(result["total_collected"], 1)
            self.assertEqual(result["board_collected"], 1)
            self.assertEqual(result["board_last_error"], None)
            manifest = json.loads((folder / "current.json").read_text())
            self.assertEqual(manifest["record_count"], 1)
            self.assertIn(service.BOARD_SOURCE, manifest["sources"])
            part = json.loads((folder / "parts" / manifest["parts"][0]["json_file"]).read_text())
            self.assertEqual(part["records"][0]["question"], "질문")
            self.assertEqual(part["records"][0]["answer"], "답변")
            again = service.collect_board_once(data_dir=folder, today=date(2026, 10, 6))
            self.assertEqual(again["total_collected"], 1)
            self.assertEqual(again["current_version"], 1)


if __name__ == "__main__":
    unittest.main()
