import unittest

from helpers import ROOT, SPEC, TODAY, rules_of
from datacheck.validate import validate_region

EXAMPLES = ROOT / "docs" / "data-interface" / "examples"


class Examples(unittest.TestCase):
    def test_both_examples_exist(self):
        names = sorted(p.name for p in EXAMPLES.iterdir() if p.is_dir())
        self.assertEqual(names, ["gwangju-gwangsan", "incheon-gyeyang"])

    def test_each_example_validates_without_errors_or_warnings(self):
        for d in sorted(p for p in EXAMPLES.iterdir() if p.is_dir()):
            with self.subTest(d.name):
                res = validate_region(d, SPEC, TODAY)
                self.assertFalse(res.rejected)
                self.assertEqual(rules_of(res, "error"), [])
                self.assertEqual(rules_of(res, "warn"), [])

    def test_example_content(self):
        g = validate_region(EXAMPLES / "incheon-gyeyang", SPEC, TODAY)
        s = validate_region(EXAMPLES / "gwangju-gwangsan", SPEC, TODAY)
        self.assertEqual(g.scope["public"], 2)
        self.assertEqual(s.scope["public"], 1)
        self.assertEqual(len(g.tables["dongs.csv"].rows), 12 + 9)
        a9_progress = [r for r in g.tables["events.csv"].rows
                       if r.get("project_id") == "techno-A9" and r.get("event_type") == "progress"]
        self.assertEqual(len(a9_progress), 7)
        permits = [r for r in s.tables["events.csv"].rows if r.get("event_type") == "permit_approved"]
        self.assertEqual(sorted(r.get("event_date") for r in permits), ["2022-03-04", "2022-03-11"])
        self.assertEqual(s.tables["projects.csv"].rows[0].get("pnu_list"), "1233010600105190000")


if __name__ == "__main__":
    unittest.main()
