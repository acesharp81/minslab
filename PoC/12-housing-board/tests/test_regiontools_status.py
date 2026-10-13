import unittest
from datetime import date

from helpers import ROOT  # noqa: F401  (tools/ 를 sys.path 에 넣는다)

from regiontools import status as S

TODAY = date(2026, 10, 4)


def E(t, d, **kw):
    return dict(type=t, date=d, **kw)


class Status(unittest.TestCase):
    def st(self, *events):
        return S.compute_status(list(events), TODAY)

    def test_actual_completion_is_move_in_stage(self):
        self.assertEqual(self.st(E("completion_inspection", "2026-07-06")), "입주 단계")

    def test_planned_completion_alone_is_plan(self):
        self.assertEqual(self.st(E("completion_inspection", "2027-07-06", planned=True)), "계획")

    def test_actual_move_in_month(self):
        self.assertEqual(self.st(E("move_in", "2026-05")), "입주 단계")

    def test_structure_with_notice_is_move_in_even_if_notice_recent(self):
        self.assertEqual(self.st(E("notice", "2026-07-06"), E("structure_observed", "2026-10-04", value=6)), "입주 단계")

    def test_structure_with_permit(self):
        self.assertEqual(self.st(E("permit_approved", "2021-12-29"), E("structure_observed", "2026-10-04")), "입주 단계")

    def test_structure_alone_is_plan(self):
        self.assertEqual(self.st(E("structure_observed", "2026-10-04")), "계획")

    def test_construction_start_beats_structure_path(self):
        self.assertEqual(self.st(E("permit_approved", "2023-01-01"), E("construction_start", "2023-09-08"),
                                 E("structure_observed", "2026-10-04")), "건설 단계")

    def test_near_completion(self):
        self.assertEqual(self.st(E("construction_start", "2024-01-01"), E("progress", "2026-09-30", value=95),
                                 E("move_in", "2026-12", planned=True)), "준공 임박")
        self.assertEqual(self.st(E("construction_start", "2024-01-01"), E("progress", "2026-09-30", value=95),
                                 E("move_in", "2027-03", planned=True)), "건설 단계")

    def test_progress_zero_is_not_construction(self):
        self.assertEqual(self.st(E("progress", "2026-09-30", value=0)), "계획")

    def test_notice_within_12_months(self):
        self.assertEqual(self.st(E("notice", "2025-11-01")), "분양중")
        self.assertEqual(self.st(E("notice", "2025-09-01")), "계획")

    def test_permit_only_is_plan(self):
        self.assertEqual(self.st(E("permit_approved", "2023-12-21", value=494)), "계획")

    def test_suspect_events_ignored(self):
        self.assertEqual(self.st(E("completion_inspection", "2026-01-20", suspect=True)), "계획")


class Suspects(unittest.TestCase):
    def test_future_actual_dates_flagged(self):
        out = S.flag_future([E("construction_start", "2026-12-23"), E("move_in", "2027-03", planned=True),
                             E("permit_approved", "2025-11-07")], TODAY)
        self.assertEqual([e.get("suspect", False) for e in out], [True, False, False])

    def test_parse_day(self):
        self.assertEqual(S.parse_day("2026-05"), date(2026, 5, 1))
        self.assertEqual(S.parse_day("2026-05-31"), date(2026, 5, 31))
        self.assertEqual(S.add_months(date(2026, 11, 30), 3), date(2027, 2, 28))


if __name__ == "__main__":
    unittest.main()
