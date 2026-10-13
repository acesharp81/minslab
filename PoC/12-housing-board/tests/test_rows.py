import tempfile
import unittest

from helpers import SPEC, TODAY, make_region, rules_of
from datacheck.validate import validate_region


def run(**kw):
    with tempfile.TemporaryDirectory() as tmp:
        return validate_region(make_region(tmp, **kw), SPEC, TODAY)


def issues(res, rule):
    return [i for i in res.issues if i.rule == rule]


def set_first(**kw):
    """rows[0]의 값을 바꾸는 edits 함수."""
    return lambda rows: rows[0].update(kw)


class RowRules(unittest.TestCase):
    def test_base_region_has_no_errors(self):
        self.assertEqual(rules_of(run(), "error"), [])

    def test_e101_required_value_missing_quarantines_the_row(self):
        res = run(edits={"projects.csv": set_first(project_name="")})
        [issue] = issues(res, "E101")
        self.assertEqual((issue.file, issue.row), ("projects.csv", 1))
        self.assertIn("project_name", issue.message)
        self.assertTrue(res.is_quarantined("projects.csv", 1))
        self.assertEqual(res.active_rows("projects.csv"), [])

    def test_e102_bad_formats(self):
        cases = [
            ("projects.csv", "pnu_list", "123"), ("projects.csv", "observed_at", "2026-13-40"),
            ("projects.csv", "units", "-5"), ("projects.csv", "source_id", "Bad ID"),
            ("dongs.csv", "floors_above", "abc"), ("dongs.csv", "floors_below", "99"),
            ("dongs.csv", "height_m", "1e3"), ("sources.csv", "url", "example.org"),
            ("region_codes.csv", "code", "123"), ("events.csv", "event_date", "2026/02/02"),
            ("events.csv", "value", "1_000"), ("regions.csv", "center_lon", "140"),
        ]
        for file, col, bad in cases:
            with self.subTest(file=file, col=col, bad=bad):
                res = run(edits={file: set_first(**{col: bad})})
                self.assertIn("E102", rules_of(res, "error"))

    def test_e103_value_not_in_enum(self):
        cases = [("projects.csv", "sponsor_type", "gov"), ("zones.csv", "zone_type", "공원"),
                 ("events.csv", "event_type", "started"), ("sources.csv", "redistributable", "maybe")]
        for file, col, bad in cases:
            with self.subTest(file=file, col=col, bad=bad):
                res = run(edits={file: set_first(**{col: bad})})
                self.assertIn("E103", rules_of(res, "error"))

    def test_e104_duplicate_primary_key_quarantines_the_later_row(self):
        res = run(edits={"projects.csv": lambda rows: rows.append(dict(rows[0]))})
        [issue] = issues(res, "E104")
        self.assertEqual((issue.file, issue.row), ("projects.csv", 2))
        self.assertFalse(res.is_quarantined("projects.csv", 1))

    def test_e104_duplicate_event(self):
        res = run(edits={"events.csv": lambda rows: rows.append(dict(rows[0]))})
        [issue] = issues(res, "E104")
        self.assertEqual((issue.file, issue.row), ("events.csv", 4))

    def test_e105_event_for_unknown_project(self):
        res = run(edits={"events.csv": set_first(project_id="nope")})
        [issue] = issues(res, "E105")
        self.assertEqual((issue.file, issue.row), ("events.csv", 1))

    def test_e105_unknown_zone_source_or_region(self):
        cases = [("projects.csv", "zone_id", "nozone"), ("events.csv", "source_id", "missing-src"),
                 ("zones.csv", "source_id", "missing-src"), ("projects.csv", "region_slug", "other")]
        for file, col, bad in cases:
            with self.subTest(file=file, col=col):
                res = run(edits={file: set_first(**{col: bad})})
                self.assertIn("E105", rules_of(res, "error"))

    def test_blank_zone_id_is_allowed(self):
        res = run(edits={"projects.csv": set_first(zone_id="")})
        self.assertEqual(rules_of(res, "error"), [])

    def test_reference_to_a_quarantined_parent_is_an_error(self):
        res = run(edits={"projects.csv": set_first(project_name="")})
        got = sorted((i.file, i.row) for i in issues(res, "E105"))
        self.assertEqual(got, [("dongs.csv", 1), ("events.csv", 1), ("events.csv", 2), ("events.csv", 3)])


if __name__ == "__main__":
    unittest.main()
