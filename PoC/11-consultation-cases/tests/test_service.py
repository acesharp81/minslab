from __future__ import annotations

import asyncio
import importlib.util
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "service.py"
spec = importlib.util.spec_from_file_location("poc11_test_service", MODULE_PATH)
service = importlib.util.module_from_spec(spec)
spec.loader.exec_module(service)


def example(index):
    return {"consQustCntn": f"질문 {index}?", "nobdAnsrCntn": f"답변 {index}<br />두 번째 줄",
            "datSourceNm": "국민콜110", "inttCode": "1140100", "kywdNm": "민원"}


class CollectionTests(unittest.TestCase):
    def test_api_response_normalization_and_html_text(self):
        items, total = service._items({"header": {"resultCode": "00"}, "body": {
            "items": {"item": [{"nobdNm": "질문?", "nobdAnsrCntn": "<p>답변<br>다음</p>"}]},
            "totalCount": "1"}})
        self.assertEqual(total, 1)
        record = service._record(items[0], {"pageNo": 1}, "2026-10-06T03:00:00+09:00")
        self.assertEqual(record["question"], "질문?")
        self.assertEqual(record["answer"], "답변\n다음")
        self.assertIn("nobdNm", record["raw"])
        self.assertEqual(service._items({"response": {"header": {"resultCode": "03"}}}), ([], 0))

    def test_call_cap_resume_deduplication_and_version_files(self):
        with tempfile.TemporaryDirectory() as temporary, mock.patch.dict("os.environ", {
            "POC11_START_DATE": "2019-01-01", "POC11_LOOKBACK_DAYS": "7",
            "POC11_INTT_CODE": "", "POC11_QUERY": ""}), mock.patch.object(service, "API_CALL_LIMIT", 12):
            folder = Path(temporary)
            calls = []
            def fetch(params, key):
                calls.append(dict(params))
                self.assertEqual(key, "test-key")
                if params["basDt"] != "20190101":
                    return [], 0
                first = (params["pageNo"] - 1) * 100
                return [example(i) for i in range(first, min(first + 100, 1500))], 1500

            service.collect_once(key="test-key", today=date(2019, 1, 2), fetcher=fetch, data_dir=folder)
            first = json.loads((folder / "current.json").read_text())
            state = json.loads((folder / "state.json").read_text())
            self.assertEqual(first["record_count"], 1200)
            self.assertNotIn("records", first)
            self.assertEqual(first["version"], 1)
            self.assertEqual(state["last_fetched"], 1200)
            self.assertEqual(state["day_api_calls"], 12)
            self.assertEqual(state["cursor_page"], 13)
            self.assertEqual(state["cursor_end_date"], "2019-01-02")
            self.assertEqual(len(calls), 12)
            self.assertNotIn("serviceKey", (folder / "parts" / first["parts"][0]["json_file"]).read_text())
            self.assertTrue((folder / "versions" / "v000001.md").is_file())

            service.collect_once(key="test-key", today=date(2019, 1, 3), fetcher=fetch, data_dir=folder)
            second = json.loads((folder / "current.json").read_text())
            self.assertEqual(second["record_count"], 1500)
            self.assertEqual(second["version"], 2)
            self.assertEqual(calls[12]["endDt"], "20190102")
            self.assertTrue((folder / "versions" / "v000002.json").is_file())
            markdown = "".join((folder / "parts" / part["md_file"]).read_text() for part in second["parts"])
            self.assertIn("**질문:** 질문 1499?", markdown)
            self.assertIn("두 번째 줄", markdown)
            before = len(calls)
            service.collect_once(key="test-key", today=date(2019, 1, 3), fetcher=fetch, data_dir=folder)
            self.assertEqual(len(calls), before)

    def test_split_files_under_limit_and_download(self):
        with tempfile.TemporaryDirectory() as temporary, mock.patch.dict("os.environ", {
            "POC11_START_DATE": "2026-10-01", "POC11_INTT_CODE": "", "POC11_QUERY": ""}), \
             mock.patch.object(service, "PART_TARGET_BYTES", 3000), \
             mock.patch.object(service, "MAX_FILE_BYTES", 4000), \
             mock.patch.object(service, "DATA", Path(temporary)):
            folder = Path(temporary)
            service.collect_once(key="test-key", today=date(2026, 10, 6),
                                 fetcher=lambda params, key: ([example(i) for i in range(35)], 35), data_dir=folder)
            manifest = json.loads((folder / "current.json").read_text())
            self.assertGreater(len(manifest["parts"]), 1)
            self.assertEqual(sum(part["count"] for part in manifest["parts"]), 35)
            for part in manifest["parts"]:
                self.assertLessEqual((folder / "parts" / part["json_file"]).stat().st_size, 4000)
                self.assertLessEqual((folder / "parts" / part["md_file"]).stat().st_size, 4000)
            self.assertLessEqual((folder / "current.json").stat().st_size, 4000)
            self.assertLessEqual((folder / "current.md").stat().st_size, 4000)

            async def download():
                sent = []
                async def send(message): sent.append(message)
                await service.handle_http({"path": "/poc/consultation-cases/download/parts/" + manifest["parts"][0]["json_file"],
                                           "method": "GET", "headers": []}, None, send)
                return sent
            response = asyncio.run(download())
            self.assertEqual(response[0]["status"], 200)
            self.assertIn(b'"records"', response[1]["body"])

    def test_migrate_existing_single_file(self):
        with tempfile.TemporaryDirectory() as temporary, mock.patch.dict("os.environ", {"POC11_START_DATE": "2026-10-01"}):
            folder = Path(temporary)
            folder.mkdir(exist_ok=True)
            legacy = service._initial_dataset("2026-10-06T03:00:00+09:00", service.settings())
            legacy["schema_version"] = 1
            legacy["version"] = 1
            legacy["records"] = [service._record(example(i), {"pageNo": 1, "numOfRows": 100}, "2026-10-06T03:00:00+09:00") for i in range(3)]
            legacy.pop("parts")
            legacy.pop("record_count")
            (folder / "current.json").write_text(json.dumps(legacy))
            service.collect_once(key="test-key", today=date(2026, 10, 6),
                                 fetcher=lambda params, key: ([], 0), data_dir=folder)
            manifest = json.loads((folder / "current.json").read_text())
            self.assertEqual(manifest["record_count"], 3)
            self.assertEqual(manifest["version"], 1)
            self.assertTrue((folder / "parts" / manifest["parts"][0]["json_file"]).is_file())

    def test_error_preserves_previous_version(self):
        with tempfile.TemporaryDirectory() as temporary, mock.patch.dict("os.environ", {"POC11_START_DATE": "2026-10-01"}):
            folder = Path(temporary)
            service.collect_once(key="test-key", today=date(2026, 10, 6),
                                 fetcher=lambda params, key: ([example(1)], 1), data_dir=folder)
            before = (folder / "current.json").read_bytes()
            def fail(params, key):
                raise ValueError("upstream temporarily unavailable")
            service.collect_once(key="test-key", today=date(2026, 10, 7), fetcher=fail, data_dir=folder)
            self.assertEqual((folder / "current.json").read_bytes(), before)
            state = json.loads((folder / "state.json").read_text())
            self.assertIn("unavailable", state["last_error"])
            self.assertEqual(state["day_fetched"], 0)


class HttpTests(unittest.IsolatedAsyncioTestCase):
    async def test_status_and_missing_download(self):
        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(service, "DATA", Path(temporary)):
            async def call(path):
                sent = []
                async def send(message): sent.append(message)
                await service.handle_http({"path": path, "method": "GET", "headers": []}, None, send)
                return sent
            response = await call("/poc/consultation-cases/api/status")
            self.assertEqual(response[0]["status"], 200)
            self.assertEqual(json.loads(response[1]["body"])["total_collected"], 0)
            missing = await call("/poc/consultation-cases/download/current.md")
            self.assertEqual(missing[0]["status"], 404)
            page = await call("/poc/consultation-cases/")
            self.assertEqual(page[0]["status"], 200)
            self.assertIn(b"const prefix = '/poc/consultation-cases'", page[1]["body"])
