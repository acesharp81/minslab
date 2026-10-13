import unittest

from helpers import ROOT  # noqa: F401  (tools/ 를 sys.path 에 넣는다)

from regiontools import api, existence as E

LON, LAT = 126.79, 35.02


def rect(dx, dy, w=0.0003, h=0.0003):
    """(LON+dx, LAT+dy)에서 시작하는 w×h 도 크기 사각형(약 27×33 m) Polygon."""
    x, y = LON + dx, LAT + dy
    return {"type": "Polygon", "coordinates": [[[x, y], [x + w, y], [x + w, y + h], [x, y + h], [x, y]]]}


def bld(geom, **props):
    base = {"eh": 3.0, "src": "공식높이"}
    base.update(props)
    return {"type": "Feature", "properties": base, "geometry": geom}


ZONE = [[[LON - 0.01, LAT - 0.01], [LON + 0.01, LAT - 0.01], [LON + 0.01, LAT + 0.01], [LON - 0.01, LAT + 0.01]]]
FAR_ZONE = [[[LON + 0.5, LAT + 0.5], [LON + 0.6, LAT + 0.5], [LON + 0.6, LAT + 0.6], [LON + 0.5, LAT + 0.6]]]


class Coverage(unittest.TestCase):
    def test_inside_half_and_outside(self):
        idx = E.Index([rect(0, 0)])
        self.assertGreater(E.coverage(rect(0.00005, 0.00005, 0.0002, 0.0002), idx), 0.95)   # 완전히 안
        half = E.coverage(rect(0.00015, 0, 0.0003, 0.0003), idx)                              # 절반만 겹침
        self.assertTrue(0.4 < half < 0.6, half)
        self.assertEqual(E.coverage(rect(0.002, 0), idx), 0.0)                                # 겹치지 않음

    def test_empty_index_is_zero(self):
        self.assertEqual(E.coverage(rect(0, 0), E.Index([])), 0.0)


class Annotate(unittest.TestCase):
    def setUp(self):
        # 도로명주소 건물: 현존 건물 12동(2008년 이후 승인 표본 가늠용)을 가로로 늘어놓는다
        self.live = [rect(0.001 * i, 0.0) for i in range(12)]
        self.newer = [bld(g, a=2012) for g in self.live]

    def run_(self, feats, spbd=None, zone=None, **kw):
        return E.annotate(feats, self.live if spbd is None else spbd, [ZONE[0] if zone is None else zone[0]], **kw)

    def test_flags_only_unmatched_old_buildings_in_zone(self):
        stale = bld(rect(0.0, 0.002), a=1996, u="동.식물 관련시설")      # 지구 안, 안 겹침, 오래됨 → 표시
        kept = bld(rect(0.001, 0.0), a=1996)                             # 도로명주소 건물과 겹침 → 현존
        feats = self.newer + [stale, kept]
        st = self.run_(feats)
        self.assertEqual(stale["properties"].get("g"), 1)
        self.assertNotIn("g", kept["properties"])
        self.assertEqual(st["flagged"], 1)
        self.assertNotIn("skipped", st)

    def test_outside_zone_never_flagged(self):
        far = bld(rect(0.0, 0.002), a=1996)
        st = E.annotate(self.newer + [far], self.live, FAR_ZONE)          # 건물은 모두 이 지구 밖
        self.assertNotIn("g", far["properties"])
        self.assertEqual(st["flagged"], 0)

    def test_recent_approval_and_missing_year(self):
        recent = bld(rect(0.0, 0.002), a=2019)    # 도로명주소가 아직 없을 수 있음 → 표시하지 않음
        noyear = bld(rect(0.0, 0.004))            # 연도 없음 → 표시(철거된 옛 건물도 연도를 잃을 수 있음)
        self.run_(self.newer + [recent, noyear])
        self.assertNotIn("g", recent["properties"])
        self.assertEqual(noyear["properties"].get("g"), 1)

    def test_no_info_building_is_counted_separately(self):
        ghost = bld(rect(0.0, 0.002), src="정보없음", eh=3)
        st = self.run_(self.newer + [ghost])
        self.assertEqual(ghost["properties"].get("g"), 1)
        self.assertEqual((st["flagged"], st["flaggedNoInfo"]), (1, 1))

    def test_nothing_flagged_without_spbd(self):
        stale = bld(rect(0.0, 0.002), a=1996)
        st = E.annotate([stale], [], [ZONE[0]])
        self.assertNotIn("g", stale["properties"])
        self.assertIn("skipped", st)

    def test_nothing_flagged_when_recent_buildings_do_not_overlap(self):
        # 최근 승인(2008년 이후) 건물 12동이 모두 도로명주소와 안 겹치면 자료가 불완전하다고 보고 아무것도 붙이지 않는다
        elsewhere = [rect(0.005, 0.005 + 0.001 * i) for i in range(12)]
        stale = bld(rect(0.0, 0.002), a=1996)
        st = self.run_(self.newer + [stale], spbd=elsewhere)
        self.assertNotIn("g", stale["properties"])
        self.assertIn("skipped", st)
        self.assertLess(st["sanityRate"], E.SANITY_MIN_RATE)

    def test_rerun_removes_old_flags(self):
        stale = bld(rect(0.0, 0.002), a=1996, g=1)
        gone = bld(rect(0.001, 0.0), a=1996, g=1)    # 이번엔 도로명주소와 겹침 → 이전의 g 를 지운다
        self.run_(self.newer + [stale, gone])
        self.assertEqual(stale["properties"].get("g"), 1)
        self.assertNotIn("g", gone["properties"])


class FakeClient:
    """vworld_features 만 흉내 낸다: 요청한 상자마다 미리 정한 건물을 돌려주고, 부른 상자를 기록한다."""

    def __init__(self, per_tile=None, error=None):
        self.per_tile, self.error, self.boxes = per_tile or [], error, []

    def vworld_features(self, layer, bbox=None, attr_filter=None, size=1000):
        self.boxes.append((layer, bbox))
        if self.error:
            raise self.error
        return [{"properties": {"bd_mgt_sn": sn}, "geometry": g} for sn, g in self.per_tile]


class Tiles(unittest.TestCase):
    def test_tiles_cover_bbox_and_stay_under_limit(self):
        ts = E.tiles((126.76, 35.00, 126.81, 35.04))        # 0.05° × 0.04° → 3 × 2 칸
        self.assertEqual(len(ts), 6)
        self.assertEqual((min(t[0] for t in ts), min(t[1] for t in ts), max(t[2] for t in ts), max(t[3] for t in ts)), (126.76, 35.0, 126.81, 35.04))
        for t in ts:                                          # V-World 상자 요청은 10 km² 이내여야 한다
            area_km2 = (t[2] - t[0]) * 111.32 * 0.819 * (t[3] - t[1]) * 110.54
            self.assertLess(area_km2, 10)

    def test_fetch_spbd_dedupes_buildings_seen_in_two_tiles(self):
        c = FakeClient(per_tile=[("A", rect(0, 0)), ("B", rect(0.001, 0))])   # 모든 칸이 같은 두 건물을 돌려줌(경계에 걸친 경우)
        out = E.fetch_spbd(c, (LON - 0.03, LAT - 0.03, LON + 0.03, LAT + 0.03))
        self.assertGreater(len(c.boxes), 1)
        self.assertEqual(len(out), 2)
        self.assertTrue(all(layer == E.LAYER for layer, _ in c.boxes))


class Apply(unittest.TestCase):
    def feats(self):
        newer = [bld(rect(0.001 * i, 0.0), a=2012) for i in range(12)]
        return newer, bld(rect(0.0, 0.002), a=1996)

    def test_apply_flags_and_records_meta(self):
        newer, stale = self.feats()
        c = FakeClient(per_tile=[(f"S{i}", rect(0.001 * i, 0.0)) for i in range(12)])
        meta = {"basis": "20261004"}
        st = E.apply(c, newer + [stale], [ZONE[0]], (LON - 0.01, LAT - 0.01, LON + 0.01, LAT + 0.01), meta)
        self.assertEqual(stale["properties"].get("g"), 1)
        self.assertEqual(meta["existence"], {"source": "LT_C_SPBD", "minCover": 0.5, "recentYear": 2015, "flagged": 1})
        self.assertIn("1동 표시", E.report(st))

    def test_api_failure_flags_nothing_and_clears_old_flags(self):
        newer, stale = self.feats()
        stale["properties"]["g"] = 1                      # 이전 실행의 표시
        meta = {"basis": "20261004", "existence": {"flagged": 9}}
        st = E.apply(FakeClient(error=api.ApiError("vworld-LT_C_SPBD: 일시 오류")), newer + [stale], [ZONE[0]],
                     (LON - 0.01, LAT - 0.01, LON + 0.01, LAT + 0.01), meta)
        self.assertIn("skipped", st)
        self.assertNotIn("g", stale["properties"])
        self.assertNotIn("existence", meta)
        self.assertIn("표시 안 함", E.report(st))


if __name__ == "__main__":
    unittest.main()
