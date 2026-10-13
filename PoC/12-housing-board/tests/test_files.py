import tempfile
import unittest
from pathlib import Path

from helpers import SPEC, TODAY, make_region, raw_csv, rules_of
from datacheck.readers import read_csv
from datacheck.validate import validate_region


def run(**kw):
    with tempfile.TemporaryDirectory() as tmp:
        return validate_region(make_region(tmp, **kw), SPEC, TODAY)


def problems(res):
    """error·warn 규칙 ID 목록 (info 제외)."""
    return [i.rule for i in res.issues if i.severity != "info"]


class FileLevel(unittest.TestCase):
    def test_base_region_has_no_problems(self):
        res = run()
        self.assertEqual(problems(res), [])  # info(요약)는 문제가 아니다
        self.assertFalse(res.rejected)
        self.assertEqual(sorted(res.tables), sorted(["regions.csv", "region_codes.csv", "sources.csv",
                                                     "zones.csv", "projects.csv", "events.csv", "dongs.csv"]))

    def test_e001_missing_required_file_rejects_region(self):
        res = run(drop=("events.csv",))
        self.assertIn("E001", rules_of(res))
        self.assertTrue(res.rejected)

    def test_optional_files_may_be_absent(self):
        res = run(drop=("dongs.csv",))
        self.assertEqual(problems(res), [])

    def test_e002_missing_required_column(self):
        res = run(raw={"events.csv": raw_csv(["region_slug", "project_id"], [["test-region", "z1-A1"]])})
        self.assertIn("E002", rules_of(res))
        self.assertIn("events.csv", res.rejected_files)
        self.assertNotIn("events.csv", res.tables)
        self.assertFalse(res.rejected)  # 파일만 거부, 지역은 계속 검사

    def test_e002_duplicate_header(self):
        header = SPEC.files["events.csv"].column_names + ["note"]
        res = run(raw={"events.csv": raw_csv(header, [])})
        [issue] = [i for i in res.issues if i.rule == "E002"]
        self.assertIn("중복", issue.message)

    def test_e002_cp949_file_gets_fix_hint(self):  # Review Focus 1
        cols = SPEC.files["sources.csv"].column_names
        row = ["src-a", "출처", "기관", "라이선스", "", "", "Y", ""]
        res = run(raw={"sources.csv": raw_csv(cols, [row], encoding="cp949")})
        [issue] = [i for i in res.issues if i.rule == "E002"]
        self.assertIn("UTF-8", issue.message)
        self.assertIn("다시 저장", issue.message)
        self.assertIn("sources.csv", res.rejected_files)

    def test_e003_region_slug_must_match_folder(self):
        res = run(slug="other-slug")
        self.assertIn("E003", rules_of(res))
        self.assertTrue(res.rejected)

    def test_e003_regions_csv_must_have_exactly_one_row(self):
        res = run(edits={"regions.csv": lambda rows: rows.append(dict(region_slug="test-region", region_name="둘째"))})
        self.assertIn("E003", rules_of(res))
        self.assertTrue(res.rejected)

    def test_w001_unknown_column_is_only_a_warning(self):
        header = SPEC.files["regions.csv"].column_names + ["memo"]
        row = ["test-region", "테스트구", "", "", "", "", "", "", "메모"]
        res = run(raw={"regions.csv": raw_csv(header, [row])})
        self.assertEqual(problems(res), ["W001"])
        self.assertIn("regions.csv", res.tables)

    def test_excel_noise_bom_crlf_blank_lines_quoted_comma(self):  # Review Focus 2
        text = "﻿region_slug,region_name\r\ntest-region,\"테스트, 구\"\r\n\r\n\r\n"
        res = run(raw={"regions.csv": text.encode("utf-8")})
        self.assertEqual(problems(res), [])
        [row] = res.tables["regions.csv"].rows
        self.assertEqual(row.get("region_name"), "테스트, 구")

    def test_trailing_empty_header_cells_from_excel_are_ignored(self):
        header = ["region_slug", "region_name", "", ""]  # 엑셀이 서식만 남은 오른쪽 열까지 내보낸 경우
        res = run(raw={"regions.csv": raw_csv(header, [["test-region", "테스트구", "", ""]])})
        self.assertEqual(problems(res), [])
        self.assertEqual(res.tables["regions.csv"].header, ["region_slug", "region_name"])

    def test_header_only_tables_pass(self):  # Review Focus 3
        empty = lambda rows: rows.clear()
        res = run(edits={"zones.csv": empty, "dongs.csv": empty})
        self.assertEqual([i for i in res.issues if i.rule in ("E001", "E002")], [])
        self.assertEqual(res.tables["zones.csv"].rows, [])


class ReadCsv(unittest.TestCase):
    def test_rows_keep_their_spreadsheet_position_when_blank_rows_are_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "t.csv"
            p.write_text("a,b\n1,2\n,\n3,4\n", encoding="utf-8")  # 2번째 행: 엑셀에서 내용만 지운 빈 행
            t = read_csv(p, "t.csv")
        self.assertEqual([(r.n, r.get("a"), r.get("b")) for r in t.rows], [(1, "1", "2"), (3, "3", "4")])
        self.assertEqual(t.rows[0].get("missing"), "")


if __name__ == "__main__":
    unittest.main()
