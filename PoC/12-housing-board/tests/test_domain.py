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
    return lambda rows: rows[0].update(kw)


def ev(**kw):
    base = dict(region_slug="test-region", project_id="z1-A1", source_id="src-a")
    base.update(kw)
    return base


def add_events(*events):
    return lambda rows: rows.extend(events)


class EventRules(unittest.TestCase):
    def test_e106_actual_event_in_the_future(self):
        res = run(edits={"events.csv": add_events(ev(event_type="construction_start", event_date="2026-12-23"))})
        [i] = issues(res, "E106")
        self.assertEqual((i.file, i.row), ("events.csv", 4))

    def test_planned_future_event_is_fine(self):
        res = run(edits={"events.csv": add_events(
            ev(event_type="construction_start", event_date="2026-12-23", is_planned="Y"))})
        self.assertEqual(rules_of(res, "error"), [])

    def test_month_precision_is_only_for_move_in(self):
        ok = run(edits={"events.csv": add_events(ev(event_type="move_in", event_date="2029-06", is_planned="Y"))})
        self.assertEqual(rules_of(ok, "error"), [])
        bad = run(edits={"events.csv": add_events(ev(event_type="construction_start", event_date="2026-05"))})
        self.assertIn("E102", rules_of(bad, "error"))

    def test_actual_move_in_this_month_is_not_future(self):
        res = run(edits={"events.csv": add_events(ev(event_type="move_in", event_date="2026-10"))})
        self.assertEqual(rules_of(res, "error"), [])

    def test_e103_planned_not_allowed_for_notice(self):
        res = run(edits={"events.csv": add_events(ev(event_type="notice", event_date="2026-09-01", is_planned="Y"))})
        self.assertIn("E103", rules_of(res, "error"))

    def test_e107_progress_needs_value_between_0_and_100(self):
        for value, expect_error in (("", True), ("120", True), ("50", False)):
            with self.subTest(value=value):
                res = run(edits={"events.csv": add_events(
                    ev(event_type="progress", event_date="2026-09-21", value=value))})
                self.assertEqual("E107" in rules_of(res, "error"), expect_error)

    def test_w101_permit_after_construction_start_flags_both_events(self):
        res = run(edits={"events.csv": add_events(ev(event_type="construction_start", event_date="2021-01-01"))})
        self.assertEqual(sorted(i.row for i in issues(res, "W101")), [1, 4])
        self.assertEqual(rules_of(res, "error"), [])  # warn은 행을 격리하지 않는다

    def test_w101_construction_start_after_completion(self):
        res = run(edits={"events.csv": add_events(
            ev(event_type="construction_start", event_date="2026-06-01"),
            ev(event_type="completion_inspection", event_date="2026-01-20"))})
        self.assertEqual(sorted(i.row for i in issues(res, "W101")), [4, 5])

    def test_w101_progress_must_not_decrease(self):
        res = run(edits={"events.csv": add_events(
            ev(event_type="progress", event_date="2026-08-28", value="5"),
            ev(event_type="progress", event_date="2026-09-21", value="3"))})
        self.assertEqual([i.row for i in issues(res, "W101")], [5])

    def test_a_later_amendment_permit_after_completion_is_not_a_warning(self):
        res = run(edits={"events.csv": add_events(
            ev(event_type="completion_inspection", event_date="2023-01-01"),
            ev(event_type="permit_approved", event_date="2025-05-05", value="828", source_ref="P2"))})
        self.assertEqual(issues(res, "W101"), [])


class DongRules(unittest.TestCase):
    def test_base_dong_has_no_warning(self):
        res = run()
        self.assertEqual(rules_of(res, "warn"), [])

    def test_w102_height_per_floor_out_of_range(self):
        res = run(edits={"dongs.csv": set_first(floors_above="25", height_m="20")})
        self.assertEqual([i.rule for i in res.issues if i.rule.startswith("W10")], ["W102"])

    def test_w103_zero_floors_with_tall_height_suggests_swapped_fields(self):
        # 12층(36 m)짜리를 지상 0·지하 12로 뒤바꿔 적은 경우. floors_below 상한(15) 안이라 E102로 격리되지 않는다
        res = run(edits={"dongs.csv": set_first(floors_above="0", floors_below="12", height_m="36")})
        self.assertEqual([i.rule for i in res.issues if i.rule.startswith("W10")], ["W103"])

    def test_commercial_building_is_not_checked(self):
        res = run(edits={"dongs.csv": set_first(dong_use="상가", floors_above="5", height_m="100")})
        self.assertEqual(rules_of(res, "warn"), [])

    def test_dong_without_height_is_not_checked(self):
        res = run(edits={"dongs.csv": set_first(height_m="")})
        self.assertEqual(rules_of(res, "warn"), [])


class ProjectRules(unittest.TestCase):
    def test_base_has_no_units_warning_even_though_notice_value_differs(self):
        self.assertNotIn("W104", rules_of(run()))  # notice 86세대 ≠ units 828 이지만 비교 대상이 아니다

    def test_w104_units_differ_from_latest_permit(self):
        res = run(edits={"projects.csv": set_first(units="500")})
        [i] = issues(res, "W104")
        self.assertEqual((i.file, i.row), ("projects.csv", 1))

    def test_w105_unknown_sponsor(self):
        res = run(edits={"projects.csv": set_first(sponsor_type="unknown")})
        self.assertIn("W105", rules_of(res, "warn"))
        self.assertEqual(res.scope["unknown"], 1)
        self.assertNotIn("I201", rules_of(res))

    def test_w106_stale_observation(self):
        res = run(edits={"projects.csv": set_first(observed_at="2025-01-01"),
                         "dongs.csv": set_first(observed_at="2025-01-01")})
        self.assertEqual(sorted(i.file for i in issues(res, "W106")), ["dongs.csv", "projects.csv"])

    def test_scope_public_and_joint(self):
        res = run()
        self.assertEqual(res.scope, {"public": 1, "private_on_public_land": 0, "out_of_scope": 0, "unknown": 0})
        res = run(edits={"projects.csv": set_first(sponsor_type="joint")})
        self.assertEqual(res.scope["public"], 1)

    def test_private_on_public_land_zone_is_in_scope(self):
        res = run(edits={"projects.csv": set_first(sponsor_type="private", project_kind="민간분양")})
        self.assertEqual(res.scope["private_on_public_land"], 1)
        self.assertNotIn("I201", rules_of(res))

    def test_private_outside_public_land_is_out_of_scope(self):
        private = set_first(sponsor_type="private", project_kind="민간분양")
        cases = {
            "도시개발 지구": dict(edits={"projects.csv": private, "zones.csv": set_first(zone_type="도시개발")}),
            "지구 없음": dict(edits={"projects.csv": lambda r: r[0].update(
                sponsor_type="private", project_kind="민간분양", zone_id="")}),
            "on_public_land=N이 지구 유형보다 우선": dict(edits={"projects.csv": lambda r: r[0].update(
                sponsor_type="private", project_kind="민간분양", on_public_land="N")}),
        }
        for label, kw in cases.items():
            with self.subTest(label):
                res = run(**kw)
                self.assertEqual(res.scope["out_of_scope"], 1)
                self.assertEqual(len(issues(res, "I201")), 1)

    def test_on_public_land_y_overrides_zone_type(self):
        res = run(edits={"projects.csv": lambda r: r[0].update(
            sponsor_type="private", project_kind="민간분양", on_public_land="Y"),
            "zones.csv": set_first(zone_type="도시개발")})
        self.assertEqual(res.scope["private_on_public_land"], 1)

    def test_i202_summary_counts(self):
        [i] = issues(run(), "I202")
        self.assertIn("projects 1", i.message)
        self.assertIn("events 3", i.message)
        self.assertEqual((i.file, i.row), ("", None))

    def test_zero_row_tables_summarize_as_zero(self):  # Review Focus 3
        clear = lambda rows: rows.clear()
        res = run(edits={"projects.csv": clear, "events.csv": clear, "dongs.csv": clear})
        self.assertEqual(rules_of(res, "error"), [])
        [i] = issues(res, "I202")
        self.assertIn("projects 0", i.message)
        self.assertIn("events 0", i.message)


if __name__ == "__main__":
    unittest.main()
