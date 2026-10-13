import unittest

from helpers import ROOT  # noqa: F401  (tools/ 를 sys.path 에 넣는다)

from regiontools import buildings as B

RING = [[126.0, 35.0], [126.0003, 35.0], [126.0003, 35.0003], [126.0, 35.0003]]


def raw(**kw):
    base = {"bld_nm": "", "dong_nm": "", "usability": "", "grnd_flr": "0", "ugrnd_flr": "0",
            "height": "0", "useapr_day": ""}
    base.update(kw)
    return base


class EffectiveHeight(unittest.TestCase):
    def test_official_height_first(self):
        self.assertEqual(B.effective_height(30.5, 10), (30.5, "공식높이"))

    def test_floors_times_default(self):
        self.assertEqual(B.effective_height(None, 10), (28.5, "층수환산"))

    def test_floors_times_band_factor(self):
        self.assertEqual(B.effective_height(None, 10, "공동주택", {"공동주택_6-10": 2.9}), (29.0, "층수환산"))

    def test_floors_times_use_factor(self):
        self.assertEqual(B.effective_height(None, 2, "공장", {"공장": 4.0}), (8.0, "층수환산"))

    def test_no_information_is_flat_3m(self):
        self.assertEqual(B.effective_height(None, None), (3.0, "정보없음"))

    def test_floor_band_boundaries(self):
        self.assertEqual([B.floor_band(f) for f in (1, 5, 6, 10, 11, 15, 16, 20, 21, 40)],
                         ["1-5", "1-5", "6-10", "6-10", "11-15", "11-15", "16-20", "16-20", "21+", "21+"])


class Mismatch(unittest.TestCase):
    def test_flags(self):
        self.assertIsNone(B.mismatch_flag(60.0, 20))
        self.assertEqual(B.mismatch_flag(10.0, 20), 1)
        self.assertEqual(B.mismatch_flag(100.0, 5), 1)
        self.assertIsNone(B.mismatch_flag(9.0, 1))   # 1층 건물은 판정하지 않음
        self.assertIsNone(B.mismatch_flag(None, 5))


class Props(unittest.TestCase):
    def test_vworld_record(self):
        p = B.building_props(raw(bld_nm="광주선운2 레니체", dong_nm="105동", usability="02000",
                                 grnd_flr="20", ugrnd_flr="2", useapr_day="20250630"), {}, d="운수동")
        self.assertEqual(p, {"eh": 57.0, "src": "층수환산", "f": 20, "b": 2, "u": "공동주택",
                             "n": "광주선운2 레니체 105동", "a": 2025, "d": "운수동"})

    def test_official_height_kept(self):
        p = B.building_props(raw(grnd_flr="5", height="16.4"), {})
        self.assertEqual((p["eh"], p["src"], p["h"], p["f"]), (16.4, "공식높이", 16.4, 5))

    def test_unknown_zero_values_are_omitted(self):
        self.assertEqual(B.building_props(raw(), {}), {"eh": 3.0, "src": "정보없음"})

    def test_unknown_use_code_omitted(self):
        self.assertNotIn("u", B.building_props(raw(usability="Z8000", grnd_flr="1"), {}))

    def test_mismatch_marked(self):
        p = B.building_props(raw(grnd_flr="20", height="12"), {})
        self.assertEqual(p["x"], 1)


class Factor(unittest.TestCase):
    def test_median_per_band_needs_30_samples(self):
        rows = [{"h": 42.0, "f": 15, "u": "공동주택"}] * 30
        self.assertEqual(B.compute_factor(rows), {"공동주택_11-15": 2.8})
        self.assertEqual(B.compute_factor(rows[:29]), {})

    def test_use_factor_and_mismatch_excluded(self):
        rows = [{"h": 8.0, "f": 2, "u": "공장"}] * 30 + [{"h": 40.0, "f": 2, "u": "공장"}] * 5
        self.assertEqual(B.compute_factor(rows), {"공장": 4.0})


class Features(unittest.TestCase):
    def test_feature_rounds_and_closes(self):
        g = {"type": "MultiPolygon", "coordinates": [[[[126.12345678, 35.1], [126.1238, 35.1],
                                                       [126.1238, 35.1004], [126.12345678, 35.1004]]]]}
        f = B.building_feature(g, {"eh": 3.0, "src": "정보없음"})
        ring = f["geometry"]["coordinates"][0][0]
        self.assertEqual(ring[0], [126.123457, 35.1])
        self.assertEqual(ring[0], ring[-1])
        self.assertEqual(f["type"], "Feature")

    def test_degenerate_feature_is_none(self):
        g = {"type": "Polygon", "coordinates": [[[126.0, 35.0], [126.0, 35.0], [126.0, 35.0]]]}
        self.assertIsNone(B.building_feature(g, {"eh": 3.0}))

    def test_meta(self):
        self.assertEqual(B.make_meta("20261004", {}), {"basis": "20261004"})
        self.assertEqual(B.make_meta("20261004", {"공동주택_21+": 2.8})["factor"], {"공동주택_21+": 2.8})


if __name__ == "__main__":
    unittest.main()
