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

from regiontools import migrate_legacy as M  # noqa: E402

RING = [[126.75, 37.55], [126.76, 37.55], [126.76, 37.56], [126.75, 37.56]]
DONG = {"no": "201", "floors": 15, "poly": [RING]}

LEGACY_PROJECTS = {
    "district": {"source": "OpenStreetMap contributors (ODbL), way 1", "poly": RING},
    "otherBlocks": [RING],
    "meta": {"title": "t", "asOf": "2026-10-03"},
    "blocks": [
        {"id": "A2", "status": "준공 임박", "kind": "공공분양", "units": 747, "dongCount": 1, "moveIn": "2026.12",
         "src": "LH 입주자모집공고(2024-10-09 정정)·팸플릿", "builder": "제일건설 주식회사", "contractM": 136444,
         "note": "메모", "areaM2": 1, "floorsDoc": "12~15층", "builderSrc": "LH", "outlineHow": "V-World 공식 블록(LT_C_LHBLPN), 0.3% 차이",
         "progress": {"rate": 100.0, "asOf": "2026-09-29", "start": "2024-03-29", "end": "2026-10-11", "history": [["2024-08-22", 1.3]],
                      "src": "LH청약플러스 공사현황(공정율)"},
         "poly": RING, "dongs": [DONG]},
        {"id": "A10", "status": "건설 단계", "kind": "통합공공임대", "units": 778, "dongCount": None, "moveIn": "준공 예정 2028-09-30",
         "src": "LH 공공주택 준공예정현황(2026-01 기준), LH 공사현황(공정율)", "outlineHow": "V-World 공식 블록(LT_C_LHBLPN), 공고문이 없어 면적은 비교하지 못함",
         "progress": {"rate": 1.741, "asOf": "2026-09-21", "start": "2026-06-25", "end": "2029-01-08", "history": [], "src": "x"},
         "poly": RING, "dongs": []},
        {"id": "A6", "status": "분양중", "kind": "공공분양", "units": 663, "dongCount": 12, "moveIn": "2029.06",
         "src": "LH 입주자모집공고(2026-09-14 정정)·팸플릿", "outlineHow": "V-World 공식 블록", "poly": RING, "dongs": [DONG]},
    ],
}
LEGACY_BUILDINGS = {"type": "FeatureCollection", "meta": {"basis": "20260906", "factor": {"공동주택_1-5": 3.1}},
                    "features": [{"type": "Feature", "properties": {"eh": 12.0, "src": "정보없음"},
                                  "geometry": {"type": "Polygon", "coordinates": [RING + [RING[0]]]}}]}
LEGACY_CONTEXT = {"stations": [{"name": "계양역", "lon": 126.73, "lat": 37.57}], "schools": [], "asOf": "2026-10-03", "source": "© OpenStreetMap contributors (ODbL)"}


def write_legacy(d: Path, projects=LEGACY_PROJECTS, buildings=LEGACY_BUILDINGS, context=LEGACY_CONTEXT):
    d.mkdir(parents=True, exist_ok=True)
    (d / "gyeyang_projects.js").write_text("/* 자동 생성 */\nwindow.GY_PROJECTS=" + json.dumps(projects, ensure_ascii=False) + ";\n", encoding="utf-8")
    (d / "gyeyang_buildings.js").write_text("/* 자동 생성 */\nwindow.GY_BUILDINGS=" + json.dumps(buildings, ensure_ascii=False) + ";\n", encoding="utf-8")
    (d / "gyeyang_context.js").write_text("/* 자동 생성 */\nwindow.GY_CONTEXT=" + json.dumps(context, ensure_ascii=False) + ";\n", encoding="utf-8")


class ReadLegacyTest(unittest.TestCase):
    def test_window_assignment_is_parsed(self):
        with tempfile.TemporaryDirectory() as t:
            write_legacy(Path(t))
            self.assertEqual(M.read_legacy_js(Path(t) / "gyeyang_context.js", "GY_CONTEXT"), LEGACY_CONTEXT)

    def test_wrong_variable_is_an_error(self):
        with tempfile.TemporaryDirectory() as t:
            write_legacy(Path(t))
            with self.assertRaises(ValueError):
                M.read_legacy_js(Path(t) / "gyeyang_context.js", "GY_NOPE")


class MoveInTest(unittest.TestCase):
    def test_conversions(self):
        self.assertEqual(M.move_in("2026.12"), "2026-12")
        self.assertEqual(M.move_in("준공 예정 2028-09-30"), "2028-09-30")
        self.assertIsNone(M.move_in(None))
        self.assertIsNone(M.move_in(""))

    def test_unknown_format_is_kept_as_text(self):
        self.assertEqual(M.move_in("2026년 하반기"), "2026년 하반기")


class ConvertTest(unittest.TestCase):
    def setUp(self):
        self.out = M.convert(LEGACY_PROJECTS, LEGACY_BUILDINGS, LEGACY_CONTEXT)
        self.projects = {p["label"]: p for p in self.out["projects"]["projects"]}

    def test_project_fields(self):
        p = self.projects["A2"]
        self.assertEqual(p["id"], "techno-A2")
        self.assertEqual(p["zoneId"], "techno-valley")
        self.assertEqual(p["sponsor"], {"name": "한국토지주택공사", "type": "public"})
        self.assertEqual(p["sponsorClass"], "public")
        self.assertEqual((p["kind"], p["status"], p["units"], p["dongCount"]), ("공공분양", "준공 임박", 747, 1))
        self.assertEqual(p["moveIn"], "2026-12")
        self.assertEqual((p["builder"], p["contractAmountM"], p["note"]), ("제일건설 주식회사", 136444, "메모"))
        self.assertEqual(p["outline"]["tier"], "official")
        self.assertEqual(p["outline"]["how"], "V-World 공식 블록(LT_C_LHBLPN), 0.3% 차이")
        self.assertEqual(p["outline"]["poly"], RING)

    def test_progress_gets_source_id(self):
        pr = self.projects["A2"]["progress"]
        self.assertEqual((pr["rate"], pr["asOf"], pr["start"], pr["end"], pr["source"]), (100.0, "2026-09-29", "2024-03-29", "2026-10-11", "lh-cwstt"))
        self.assertEqual(pr["history"], [["2024-08-22", 1.3]])

    def test_project_without_dongs_has_no_dongs_key_and_null_dong_count(self):
        p = self.projects["A10"]
        self.assertNotIn("dongs", p)
        self.assertIsNone(p["dongCount"])
        self.assertEqual(p["moveIn"], "2028-09-30")

    def test_missing_optional_fields_are_omitted(self):
        p = self.projects["A6"]
        for k in ("builder", "contractAmountM", "note", "progress"):
            self.assertNotIn(k, p)

    def test_dongs_use_floors_above_and_schematic_tier(self):
        d = self.projects["A2"]["dongs"][0]
        self.assertEqual((d["no"], d["floorsAbove"], d["tier"], d["poly"]), ("201", 15, "schematic", [RING]))

    def test_each_project_gets_its_own_notice_source_with_legacy_text(self):
        sources = {s["id"]: s for s in self.out["region"]["sources"]}
        sid = self.projects["A2"]["sources"]
        self.assertEqual(sid, ["notice-a2"])
        self.assertEqual(sources["notice-a2"]["label"], "LH 입주자모집공고(2024-10-09 정정)·팸플릿")
        self.assertIn("lh-cwstt", sources)
        for s in sources.values():
            self.assertIn(s["redistributable"], ("Y", "N", "unknown"))

    def test_region_json(self):
        r = self.out["region"]
        self.assertEqual((r["slug"], r["name"], r["schema_version"]), ("incheon-gyeyang", "인천 계양구", "1.1.0"))
        self.assertEqual(r["zones"][0]["id"], "techno-valley")
        self.assertEqual((r["zones"][0]["type"], r["zones"][0]["publicLand"], r["zones"][0]["poly"]), ("공공주택지구", True, RING))
        self.assertEqual(r["projectOrder"], ["techno-A6", "techno-A10", "techno-A2"])   # 옛 ORDER 에서 있는 것만
        self.assertEqual(r["updatedAt"], "2026-10-03")
        self.assertEqual(set(r["statusOrder"]), {"계획", "분양중", "건설 단계", "준공 임박", "입주 단계"})
        self.assertEqual(r["codes"][0]["code"], "28245")

    def test_other_blocks_buildings_context_pass_through(self):
        self.assertEqual(self.out["projects"]["otherBlocks"], [RING])
        self.assertEqual(self.out["buildings"]["features"], LEGACY_BUILDINGS["features"])
        self.assertEqual(self.out["buildings"]["meta"], LEGACY_BUILDINGS["meta"])
        self.assertEqual(self.out["buildings"]["schema_version"], "1.1.0")
        self.assertEqual(self.out["context"], LEGACY_CONTEXT)

    def test_input_is_not_mutated(self):
        before = json.dumps(LEGACY_PROJECTS, sort_keys=True)
        M.convert(LEGACY_PROJECTS, LEGACY_BUILDINGS, LEGACY_CONTEXT)
        self.assertEqual(json.dumps(LEGACY_PROJECTS, sort_keys=True), before)

    def test_non_official_outline_is_schematic(self):
        proj = json.loads(json.dumps(LEGACY_PROJECTS))
        proj["blocks"][0]["outlineHow"] = "팸플릿에서 옮김"
        out = M.convert(proj, LEGACY_BUILDINGS, LEGACY_CONTEXT)
        self.assertEqual(out["projects"]["projects"][0]["outline"]["tier"], "schematic")


@unittest.skipUnless(HAVE, "jsonschema 가 필요합니다(.venv/bin/python)")
class MigrateWritesValidBundleTest(unittest.TestCase):
    def test_written_bundle_passes_check_bundle(self):
        from regiontools.check_bundle import check_region_dir
        with tempfile.TemporaryDirectory() as t:
            src, out = Path(t) / "legacy", Path(t) / "regions" / "incheon-gyeyang"
            write_legacy(src)
            M.migrate(src, out)
            self.assertEqual(sorted(p.name for p in out.iterdir()), ["buildings.json", "context.json", "projects.json", "region.json"])
            self.assertEqual(check_region_dir(out), [])


class IndexTest(unittest.TestCase):
    def test_add_to_index_creates_and_replaces(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "index.json"
            M.add_to_index(p, slug="incheon-gyeyang", name="인천 계양구", updated_at="2026-10-03", default=True)
            M.add_to_index(p, slug="jeonnam-naju", name="전남 나주시", updated_at="2026-10-04")
            M.add_to_index(p, slug="incheon-gyeyang", name="인천 계양구", updated_at="2026-10-05", default=True)
            idx = json.loads(p.read_text(encoding="utf-8"))
            self.assertEqual(idx["schema_version"], "1.1.0")
            self.assertEqual([r["slug"] for r in idx["regions"]], ["incheon-gyeyang", "jeonnam-naju"])
            self.assertEqual(idx["regions"][0]["updatedAt"], "2026-10-05")
            self.assertTrue(idx["regions"][0]["default"])
            self.assertNotIn("default", idx["regions"][1])
            self.assertEqual({r["visibility"] for r in idx["regions"]}, {"public"})


if __name__ == "__main__":
    unittest.main()
