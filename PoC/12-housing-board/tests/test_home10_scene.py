import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("home_scene", Path(__file__).resolve().parents[1] / "scripts/build-home10-3d.py")
scene = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scene)


class HomeSceneTests(unittest.TestCase):
    def test_existing_apartment_inside_new_site_is_not_candidate_geometry(self):
        center = [127.1, 37.4]
        boundary = scene.rectangle(center, 200, 200)
        shape = {"type": "Polygon", "coordinates": [boundary + [boundary[0]]]}
        ring = scene.footprint(center, 32, 18)
        building = {"properties": {"n": "통보8차공원아파트 A동", "f": 6, "u": "공동주택", "eh": 17.2},
                    "geometry": {"type": "Polygon", "coordinates": [ring + [ring[0]]]}}
        rows = [{"district": "성남복정2", "block": "A1"}]
        self.assertEqual(scene.observed_dongs([building], shape, rows), [])
        building["properties"]["n"] = "성남복정2 A1 101동"
        self.assertEqual(len(scene.observed_dongs([building], shape, rows)), 1)
        self.assertEqual(scene.observed_dongs([building], None, rows), [])
        building["properties"]["n"] = "성남복정2 A10 101동"
        self.assertEqual(scene.observed_dongs([building], shape, rows), [])

    def test_illustrations_stay_in_land_and_remain_explicit_assumptions(self):
        center = [127.1, 37.4]
        boundary = scene.rectangle(center, 200, 180)
        shape = {"type": "Polygon", "coordinates": [boundary + [boundary[0]]]}
        _, dongs = scene.synthetic_dongs(center, 960, shape)
        self.assertEqual(len(dongs), 10)
        for dong in dongs:
            self.assertEqual(dong["tier"], "schematic")
            self.assertEqual(dong["heightBasis"], "ILLUSTRATIVE_ASSUMPTION")
            for ring in dong["poly"]:
                self.assertTrue(all(scene.geo.point_in_geometry(point, shape) for point in ring))


if __name__ == "__main__":
    unittest.main()
