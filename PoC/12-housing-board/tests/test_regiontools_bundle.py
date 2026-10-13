import json
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT  # noqa: F401  (tools/ 를 sys.path 에 넣는다)

from regiontools import bundle

try:
    import jsonschema  # noqa: F401
    HAVE_JSONSCHEMA = True
except ImportError:
    HAVE_JSONSCHEMA = False

RING = [[126.78123456789, 35.15], [126.79, 35.15], [126.79, 35.16], [126.78, 35.16]]
SOURCES = [{"id": "myhome-notice", "label": "마이홈포털 공공주택 모집공고", "publisher": "국토교통부",
            "url": "https://www.data.go.kr/data/15108420/openapi.do", "asOf": "2026-10-04", "redistributable": "unknown"}]


def sample_region():
    return bundle.region_doc(
        slug="test-region", name="테스트구", title="주택파동 · 테스트구", description=None,
        center=[126.785123456, 35.155], zoom=15, pitch=52, codes=[{"code": "12330", "type": "sigungu", "name": "광산구"}],
        zones=[{"id": "z1", "name": "테스트 공공주택지구", "type": "공공주택지구", "publicLand": True, "poly": RING}],
        sources=SOURCES, updated="2026-10-04")


def sample_project():
    return {"id": "z1-A1", "label": "A-1", "name": "테스트 A-1", "sponsor": {"name": "LH", "type": "public"},
            "sponsorClass": "public", "kind": "신혼희망타운", "status": "입주 단계", "units": None, "dongCount": 6,
            "progress": None, "outline": {"tier": "official", "poly": RING, "how": "V-World 공식 블록(LT_C_LHBLPN)"},
            "dongs": [{"no": "101", "tier": "building", "floorsAbove": 25, "heightM": None, "poly": [RING]}],
            "events": [{"type": "notice", "date": "2026-07-06", "value": 39, "source": "myhome-notice", "ref": "0000061131"}],
            "sources": ["myhome-notice"], "zoneId": "z1"}


class Docs(unittest.TestCase):
    def test_dumps_is_compact_utf8(self):
        s = bundle.dumps({"a": [1, 2], "이름": "광산"})
        self.assertEqual(s, '{"a":[1,2],"이름":"광산"}')

    def test_round_coords(self):
        self.assertEqual(bundle.round_coords([[126.12345678, 35.98765432]]), [[126.123457, 35.987654]])
        self.assertEqual(bundle.round_coords([126.12345678, 35.98765432]), [126.123457, 35.987654])

    def test_region_doc(self):
        r = sample_region()
        self.assertEqual(r["schema_version"], "1.1.0")
        self.assertEqual(r["statusOrder"], ["계획", "분양중", "건설 단계", "준공 임박", "입주 단계"])
        self.assertNotIn("description", r)
        self.assertEqual(r["view"], {"center": [126.785123, 35.155], "zoom": 15, "pitch": 52, "bearing": 0})
        self.assertEqual(r["zones"][0]["poly"][0], [126.781235, 35.15])

    def test_projects_doc_strips_none(self):
        p = bundle.projects_doc([sample_project()], other_blocks=[])
        proj = p["projects"][0]
        self.assertNotIn("units", proj)
        self.assertNotIn("progress", proj)
        self.assertNotIn("heightM", proj["dongs"][0])
        self.assertNotIn("otherBlocks", p)
        self.assertEqual(proj["outline"]["poly"][0], [126.781235, 35.15])

    def test_write_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "test-region"
            bld = bundle.buildings_doc([{"type": "Feature", "properties": {"eh": 3.0, "src": "정보없음"},
                                         "geometry": {"type": "Polygon", "coordinates": [RING + [RING[0]]]}}],
                                       {"basis": "20261004"})
            ctx = bundle.context_doc([{"name": "테스트역", "lon": 126.781234567, "lat": 35.15}], [], "2026-10-04",
                                     "© OpenStreetMap contributors (ODbL)")
            written = bundle.write_bundle(out, sample_region(), bundle.projects_doc([sample_project()], [RING]), bld, ctx)
            self.assertEqual(sorted(p.name for p in written),
                             ["buildings.json", "context.json", "projects.json", "region.json"])
            for p in written:
                raw = p.read_bytes()
                self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
                doc = json.loads(raw.decode("utf-8"))
                self.assertEqual(doc["schema_version"], "1.1.0")
                self.assertNotIn(b", ", raw)
            self.assertEqual(json.loads((out / "context.json").read_text("utf-8"))["stations"][0]["lon"], 126.781235)
            if HAVE_JSONSCHEMA:
                from regiontools.check_bundle import check_region_dir
                self.assertEqual(check_region_dir(out), [])

    def test_write_bundle_without_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "test-region"
            bld = bundle.buildings_doc([], {"basis": "20261004"})
            written = bundle.write_bundle(out, sample_region(), bundle.projects_doc([], []), bld, None)
            self.assertEqual(len(written), 3)
            self.assertFalse((out / "context.json").exists())


if __name__ == "__main__":
    unittest.main()
