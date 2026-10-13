import copy
import json
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT  # noqa: F401  (tools/ 를 sys.path 에 넣는다)

try:
    import jsonschema  # noqa: F401
    HAVE = True
except ImportError:
    HAVE = False

RING = [[126.78, 35.15], [126.79, 35.15], [126.79, 35.16], [126.78, 35.16]]

REGION = {
    "schema_version": "1.1.0", "slug": "test-region", "name": "테스트구", "title": "주택파동 · 테스트구",
    "updatedAt": "2026-10-04", "view": {"center": [126.785, 35.155], "zoom": 15},
    "codes": [{"code": "12330", "type": "sigungu", "name": "테스트구"}],
    "zones": [{"id": "z1", "name": "테스트 지구", "type": "공공주택지구", "publicLand": True, "poly": RING}],
    "sources": [{"id": "src-a", "label": "출처 A", "redistributable": "unknown"}],
    "statusOrder": ["계획", "분양중", "건설 단계", "준공 임박", "입주 단계"],
}
PROJECT = {
    "id": "z1-A1", "label": "A-1", "name": "테스트 A-1", "sponsor": {"name": "LH", "type": "public"},
    "sponsorClass": "public", "kind": "공공분양", "status": "입주 단계", "units": 100, "dongCount": 1,
    "outline": {"tier": "official", "poly": RING},
    "dongs": [{"no": "101", "tier": "building", "floorsAbove": 15, "poly": [RING]}],
    "sources": ["src-a"],
}
BUILDINGS = {"type": "FeatureCollection", "meta": {"basis": "20261004"},
             "features": [{"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [RING + [RING[0]]]},
                           "properties": {"eh": 12.0, "src": "정보없음"}}]}
CONTEXT = {"stations": [{"name": "테스트역", "lon": 126.78, "lat": 35.15}], "schools": [], "asOf": "2026-10-04", "source": "OSM"}
INFRA = {
    "schema_version": "1.3.0", "asOf": "2026-10-04",
    "sources": [{"id": "i-src", "label": "교육재정알리미", "redistributable": "unknown"}],
    "schools": [{"id": "s1", "name": "(가칭)테스트초", "level": "초등학교", "status": "신설예정", "openYm": "2029-03",
                 "lon": 126.785, "lat": 35.155, "poly": RING, "sources": ["i-src"]}],
    "zones": [{"id": "z-a", "name": "테스트초통학구역", "school": "테스트초등학교", "poly": RING, "asOf": "2026-09-20", "sources": ["i-src"]}],
    "attendance": [{"projectId": "z1-A1", "zoneId": "z-a"}],
    "stops": [{"id": "S1", "name": "정류장", "no": "101", "lon": 126.785, "lat": 35.155, "routes": ["R1"]}],
    "busRoutes": [{"id": "R1", "no": "87", "type": "간선버스", "from": "기점", "to": "종점", "live": True, "path": [[126.78, 35.15], [126.79, 35.16]]},
                  {"id": "R2", "no": "9"}],
    "busCityCode": 23,
    "sites": [{"id": "e1", "category": "전기", "name": "전기공급설비", "poly": RING, "sources": ["i-src"]}],
    "permits": [{"id": "p1", "name": "누리센터", "use": "노유자시설", "permitDate": "2025-12-04", "startDate": None, "sources": ["i-src"]}],
    "measures": [{"id": "m1", "category": "교통", "title": "버스 신설", "when": "2026-10", "status": "예정", "sources": ["i-src"]}],
}
INDEX = {"schema_version": "1.1.0", "regions": [
    {"slug": "test-region", "name": "테스트구", "default": True, "visibility": "public",
     "updatedAt": "2026-10-04", "schema_version": "1.1.0"}]}


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def make(tmp, region=None, projects=None, buildings=None, context="default", index=None, infra=None):
    root = Path(tmp) / "regions"
    d = root / "test-region"
    write_json(root / "index.json", index if index is not None else INDEX)
    write_json(d / "region.json", region if region is not None else REGION)
    write_json(d / "projects.json", projects if projects is not None else {"schema_version": "1.1.0", "projects": [PROJECT]})
    write_json(d / "buildings.json", buildings if buildings is not None else BUILDINGS)
    if context == "default":
        write_json(d / "context.json", CONTEXT)
    elif context is not None:
        write_json(d / "context.json", context)
    if infra is not None:
        write_json(d / "infra.json", infra)
    return root


def variant(base, **changes):
    d = copy.deepcopy(base)
    for k, v in changes.items():
        d[k] = v
    return d


@unittest.skipUnless(HAVE, "jsonschema 패키지가 필요함 (.venv/bin/python 으로 실행)")
class CheckBundle(unittest.TestCase):
    def setUp(self):
        import regiontools.check_bundle as cb
        self.cb = cb

    def errors(self, **kw):
        with tempfile.TemporaryDirectory() as tmp:
            root = make(tmp, **kw)
            return self.cb.check_region_dir(root / "test-region") + self.cb.check_index(root / "index.json")

    def test_valid_bundle_has_no_errors(self):
        self.assertEqual(self.errors(), [])

    def test_context_is_optional(self):
        self.assertEqual(self.errors(context=None), [])

    def test_a_1_0_0_bundle_without_new_fields_is_still_valid(self):
        self.assertEqual(self.errors(), [])  # PROJECT 에는 1.1.0 추가 필드가 하나도 없다

    def test_1_1_0_fields_are_accepted(self):
        project = copy.deepcopy(PROJECT)
        project.update(note="메모", builder="시공사", contractAmountM=1000.5)
        project["progress"] = {"rate": 12.5, "asOf": "2026-10-04", "start": "2026-01-01", "end": "2028-01-01", "source": "src-a"}
        region = variant(REGION, projectOrder=["z1-A1"])
        self.assertEqual(self.errors(projects={"schema_version": "1.1.0", "projects": [project]}, region=region), [])

    def test_schema_violation_names_the_missing_field(self):
        bad = {k: v for k, v in PROJECT.items() if k != "label"}
        errs = self.errors(projects={"schema_version": "1.1.0", "projects": [bad]})
        self.assertTrue(any("label" in e and "projects.json" in e for e in errs), errs)

    def test_unknown_status_is_a_schema_error(self):
        errs = self.errors(projects={"schema_version": "1.1.0", "projects": [dict(PROJECT, status="공사중")]})
        self.assertTrue(any("status" in e for e in errs), errs)

    def test_project_source_must_exist_in_region_sources(self):
        errs = self.errors(projects={"schema_version": "1.1.0", "projects": [dict(PROJECT, sources=["nope"])]})
        self.assertTrue(any("nope" in e for e in errs), errs)

    def test_progress_source_must_exist(self):
        p = dict(PROJECT, progress={"rate": 1, "asOf": "2026-10-04", "source": "nope"})
        errs = self.errors(projects={"schema_version": "1.1.0", "projects": [p]})
        self.assertTrue(any("nope" in e for e in errs), errs)

    def test_duplicate_project_ids(self):
        errs = self.errors(projects={"schema_version": "1.1.0", "projects": [PROJECT, copy.deepcopy(PROJECT)]})
        self.assertTrue(any("중복" in e and "z1-A1" in e for e in errs), errs)

    def test_project_order_must_reference_existing_projects(self):
        errs = self.errors(region=variant(REGION, projectOrder=["z1-A1", "ghost"]))
        self.assertTrue(any("ghost" in e for e in errs), errs)

    def test_region_slug_must_match_folder(self):
        errs = self.errors(region=variant(REGION, slug="other"))
        self.assertTrue(any("폴더" in e for e in errs), errs)

    def test_index_needs_exactly_one_default(self):
        two = copy.deepcopy(INDEX)
        two["regions"].append(dict(two["regions"][0], slug="other", name="다른구"))
        none = copy.deepcopy(INDEX)
        none["regions"][0].pop("default")
        for label, idx in (("둘", two), ("없음", none)):
            with self.subTest(label):
                with tempfile.TemporaryDirectory() as tmp:
                    root = make(tmp, index=idx)
                    errs = self.cb.check_index(root / "index.json")
                    self.assertTrue(any("default" in e for e in errs), errs)

    def test_index_region_folder_must_exist(self):
        idx = copy.deepcopy(INDEX)
        idx["regions"].append(dict(idx["regions"][0], slug="ghost-region", name="유령", default=False))
        with tempfile.TemporaryDirectory() as tmp:
            root = make(tmp, index=idx)
            errs = self.cb.check_index(root / "index.json")
            self.assertTrue(any("ghost-region" in e for e in errs), errs)

    def test_infra_is_optional_and_a_valid_one_passes(self):
        self.assertEqual(self.errors(infra=INFRA), [])

    def test_infra_schema_violation_names_the_field(self):
        bad = copy.deepcopy(INFRA)
        bad["schools"][0]["status"] = "개교"
        errs = self.errors(infra=bad)
        self.assertTrue(any("infra.json" in e and "status" in e for e in errs), errs)

    def test_infra_unknown_top_level_key_is_rejected(self):
        errs = self.errors(infra=variant(INFRA, extra=1))
        self.assertTrue(any("infra.json" in e for e in errs), errs)

    def test_infra_source_ids_must_exist(self):
        for where, key in (("schools", "sources"), ("zones", "sources"), ("sites", "sources"), ("permits", "sources"), ("measures", "sources")):
            with self.subTest(where):
                bad = copy.deepcopy(INFRA)
                bad[where][0][key] = ["ghost-src"]
                errs = self.errors(infra=bad)
                self.assertTrue(any("ghost-src" in e for e in errs), errs)

    def test_infra_attendance_must_reference_project_and_zone(self):
        bad = copy.deepcopy(INFRA)
        bad["attendance"] = [{"projectId": "nope-A", "zoneId": "z-a"}, {"projectId": "z1-A1", "zoneId": "nope-z"}]
        errs = self.errors(infra=bad)
        self.assertTrue(any("nope-A" in e for e in errs), errs)
        self.assertTrue(any("nope-z" in e for e in errs), errs)

    def test_infra_ids_must_be_unique_within_a_list(self):
        bad = copy.deepcopy(INFRA)
        bad["schools"].append(copy.deepcopy(bad["schools"][0]))
        errs = self.errors(infra=bad)
        self.assertTrue(any("중복" in e and "s1" in e for e in errs), errs)

    def test_infra_bus_routes_are_cross_checked(self):
        cases = {
            "duplicate route id": (lambda d: d["busRoutes"].append({"id": "R2", "no": "10"}), "중복"),
            "stop points at an unknown route": (lambda d: d["stops"][0].update(routes=["R1", "ghost-route"]), "ghost-route"),
            "duplicate stop id": (lambda d: d["stops"].append(copy.deepcopy(d["stops"][0])), "중복"),
            "live route without a path": (lambda d: d["busRoutes"][0].pop("path"), "path"),
            "path on a route that is not live": (lambda d: d["busRoutes"][1].update(path=[[126.7, 35.1], [126.8, 35.2]]), "live가 아닌데"),
            "live route without a city code": (lambda d: d.pop("busCityCode"), "busCityCode"),
        }
        for name, (mutate, needle) in cases.items():
            with self.subTest(name):
                bad = copy.deepcopy(INFRA)
                mutate(bad)
                errs = self.errors(infra=bad)
                self.assertTrue(any("infra.json" in e and needle in e for e in errs), errs)

    def test_infra_open_ym_only_makes_sense_for_scheduled_schools(self):
        bad = copy.deepcopy(INFRA)
        bad["schools"][0]["status"] = "부지만"
        errs = self.errors(infra=bad)
        self.assertTrue(any("openYm" in e for e in errs), errs)

    def test_infra_measure_may_carry_a_short_label_for_the_timeline(self):
        ok = copy.deepcopy(INFRA)
        ok["measures"][0]["short"] = "7701번"
        self.assertEqual(self.errors(infra=ok), [])
        bad = copy.deepcopy(INFRA)
        bad["measures"][0]["short"] = "가" * 15
        errs = self.errors(infra=bad)
        self.assertTrue(any("infra.json" in e and "short" in e for e in errs), errs)

    def test_infra_scheduled_school_needs_open_ym(self):
        bad = copy.deepcopy(INFRA)
        del bad["schools"][0]["openYm"]
        errs = self.errors(infra=bad)
        self.assertTrue(any("openYm" in e for e in errs), errs)

    def test_cli_exit_codes(self):
        import contextlib, io
        with tempfile.TemporaryDirectory() as tmp:
            root = make(tmp)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(self.cb.main([str(root)]), 0)
                self.assertEqual(self.cb.main([str(Path(tmp) / "nope")]), 2)
            bad = make(tempfile.mkdtemp(), projects={"schema_version": "1.1.0", "projects": [dict(PROJECT, status="x")]})
            with contextlib.redirect_stdout(out):
                self.assertEqual(self.cb.main([str(bad)]), 1)


if __name__ == "__main__":
    unittest.main()
