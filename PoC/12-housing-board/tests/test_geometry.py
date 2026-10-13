import json
import tempfile
import unittest

from helpers import SPEC, TODAY, make_region, rules_of
from datacheck.validate import validate_region

GEO = "geometry_overrides.geojson"


def square(lon=126.78, lat=35.15, size=0.001):
    return [[lon, lat], [lon + size, lat], [lon + size, lat + size], [lon, lat + size], [lon, lat]]


def feature(ring=None, geometry=None, **props):
    p = dict(project_id="z1-A1", dong_no="", tier="schematic", basis="LH 팸플릿 단지배치도",
             source_id="src-a", observed_at="2026-10-04")
    p.update(props)
    return {"type": "Feature", "properties": p,
            "geometry": geometry or {"type": "Polygon", "coordinates": [ring or square()]}}


def run(features=None, raw=None):
    with tempfile.TemporaryDirectory() as tmp:
        d = make_region(tmp)
        if raw is not None:
            (d / GEO).write_bytes(raw)
        elif features is not None:
            (d / GEO).write_text(json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8")
        return validate_region(d, SPEC, TODAY)


class GeometryRules(unittest.TestCase):
    def test_valid_polygon_and_multipolygon(self):
        multi = {"type": "MultiPolygon", "coordinates": [[square()], [square(126.79)]]}
        res = run([feature(), feature(geometry=multi, dong_no="101")])
        self.assertEqual(rules_of(res, "error"), [])
        self.assertEqual(len(res.features), 2)

    def test_empty_feature_collection_is_fine(self):
        res = run([])
        self.assertEqual(rules_of(res, "error"), [])
        self.assertEqual(res.tables[GEO].rows, [])

    def test_e108_bad_geometry(self):
        p0, p1, p2 = square()[:3]
        cases = {
            "닫히지 않은 링": feature(ring=square()[:4]),
            "점 4개 미만": feature(ring=[p0, p1, p0]),
            "한국 범위 밖": feature(ring=square(lon=140.0)),
            "점 타입": feature(geometry={"type": "Point", "coordinates": [126.78, 35.15]}),
            "구조 이상": feature(geometry={"type": "Polygon", "coordinates": [[["x", "y"], p1, p2, ["x", "y"]]]}),
        }
        for label, f in cases.items():
            with self.subTest(label):
                res = run([f])
                self.assertIn("E108", rules_of(res, "error"))
                self.assertTrue(res.is_quarantined(GEO, 1))

    def test_bad_feature_is_quarantined_but_good_one_stays(self):
        res = run([feature(ring=square(lon=140.0)), feature(dong_no="102")])
        self.assertTrue(res.is_quarantined(GEO, 1))
        self.assertFalse(res.is_quarantined(GEO, 2))

    def test_property_errors_use_the_generic_rules(self):
        cases = [("E101", dict(basis="")), ("E103", dict(tier="exact")),
                 ("E105", dict(project_id="nope")), ("E102", dict(observed_at="2026-13-40"))]
        for rule, props in cases:
            with self.subTest(rule):
                self.assertIn(rule, rules_of(run([feature(**props)]), "error"))

    def test_e104_same_project_and_dong_twice(self):
        res = run([feature(), feature()])
        [issue] = [i for i in res.issues if i.rule == "E104"]
        self.assertEqual((issue.file, issue.row), (GEO, 2))

    def test_w001_unknown_property(self):
        res = run([feature(memo="메모")])
        self.assertIn("W001", rules_of(res, "warn"))

    def test_e002_when_file_is_not_valid_json_or_not_a_feature_collection(self):
        for label, raw in (("깨진 JSON", b"{not json"), ("다른 GeoJSON", b'{"type": "Feature"}')):
            with self.subTest(label):
                res = run(raw=raw)
                self.assertIn("E002", rules_of(res, "error"))
                self.assertIn(GEO, res.rejected_files)


if __name__ == "__main__":
    unittest.main()
