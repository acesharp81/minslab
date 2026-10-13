import importlib.util
import unittest

from helpers import ROOT  # noqa: F401  (tools/ 를 sys.path 에 넣는다)

from regiontools import proj

LEGACY = ROOT / "data" / "tools" / "vworld_buildings" / "tm.py"


class KoreaTm(unittest.TestCase):
    def test_origin_maps_to_false_easting_northing(self):
        x, y = proj.to_tm(127.0, 38.0)
        self.assertAlmostEqual(x, 200000.0, places=3)
        self.assertAlmostEqual(y, 600000.0, places=3)

    def test_round_trip_is_sub_millimetre_across_korea(self):
        for lon, lat in [(126.7573, 37.5553), (126.8, 35.2), (126.7, 35.0), (129.0, 35.1), (126.2, 33.5), (128.9, 37.8)]:
            with self.subTest((lon, lat)):
                x, y = proj.to_tm(lon, lat)
                lo, la = proj.from_tm(x, y)
                self.assertAlmostEqual(lo, lon, places=8)
                self.assertAlmostEqual(la, lat, places=8)

    def test_seoul_city_hall_is_where_epsg5186_puts_it(self):
        x, y = proj.to_tm(126.9780, 37.5665)
        self.assertTrue(197000 < x < 199500, x)    # 중부원점 서쪽 약 2 km
        self.assertTrue(550500 < y < 552500, y)    # 위도 38도보다 약 48 km 남쪽

    def test_east_is_larger_x_and_north_is_larger_y(self):
        x0, y0 = proj.to_tm(126.75, 37.55)
        x1, y1 = proj.to_tm(126.76, 37.56)
        self.assertGreater(x1, x0)
        self.assertGreater(y1, y0)
        self.assertAlmostEqual(x1 - x0, 0.01 * 88200, delta=300)   # 경도 0.01도 ≈ 880 m (위도 37.5도)
        self.assertAlmostEqual(y1 - y0, 0.01 * 111200, delta=300)  # 위도 0.01도 ≈ 1.11 km

    @unittest.skipUnless(LEGACY.exists(), "옛 도구(tm.py)가 없음")
    def test_matches_the_legacy_tool_used_for_the_old_buildings(self):
        spec = importlib.util.spec_from_file_location("legacy_tm", LEGACY)
        legacy = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(legacy)
        for lon, lat in [(126.7378, 37.5375), (126.7146, 37.5531), (126.978, 37.5665)]:
            with self.subTest((lon, lat)):
                self.assertAlmostEqual(proj.to_tm(lon, lat)[0], legacy.forward(lon, lat)[0], places=4)
                self.assertAlmostEqual(proj.to_tm(lon, lat)[1], legacy.forward(lon, lat)[1], places=4)
                self.assertAlmostEqual(proj.from_tm(*legacy.forward(lon, lat))[0], lon, places=8)


if __name__ == "__main__":
    unittest.main()
