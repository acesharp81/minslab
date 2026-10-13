import csv
import io
import json
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT  # noqa: F401  (tools/ 를 sys.path 에 넣는다)
from test_regiontools_shp import write_dbf, write_shp

from regiontools import geo, infra, proj

AREA = [[126.75, 37.54], [126.77, 37.54], [126.77, 37.56], [126.75, 37.56]]      # 지구
OUT = [126.70, 37.50]                                                          # 지구 밖


def sq(lon, lat, m=100):
    dl = m / 2 / 111320
    dn = m / 2 / (111320 * 0.7934)
    return [[lon - dn, lat - dl], [lon + dn, lat - dl], [lon + dn, lat + dl], [lon - dn, lat + dl]]


def edu_row(**kw):
    row = {"schlSeq": 51, "ditcNm": "초", "eduOffcNm": "북부교육지원청", "schlNm": "(가칭)계양1초", "openYear": "2029",
           "stdtCnt": "1113", "schlGradCd": "E", "realAddr": "인천광역시 계양구 동양동 416-2 일원",
           "pointX": "37.5553787", "pointY": "126.7573199", "sggNm": "계양구", "classCnt": "44", "openSchdYm": "202903"}
    row.update(kw)
    return row


def site_feature(lcl, mls, lon, lat, m=100, area="14000", name=None, new_style=False):
    """new_style: 3기 신도시처럼 대분류가 '미분류', 중분류가 '학교', 세분류(scl_nam)·속성(atr_nam)에 학교급이 오는 기록."""
    ring = sq(lon, lat, m)
    props = {"lcl_nam": lcl, "mls_nam": mls, "dgm_nm": name or mls, "dgm_ar": area, "exc_nam": "집행완료"}
    if new_style:
        props.update(lcl_nam="미분류", mls_nam=lcl, scl_nam=mls, atr_nam=mls, dgm_nm=name or mls)
    return {"type": "Feature", "properties": props, "geometry": {"type": "MultiPolygon", "coordinates": [[ring + [ring[0]]]]}}


class ScheduledSchools(unittest.TestCase):
    def test_maps_official_fields(self):
        [s] = infra.scheduled_schools([edu_row()], "인천광역시 계양구")
        self.assertEqual((s["id"], s["name"], s["level"], s["status"]), ("edu-51", "(가칭)계양1초", "초등학교", "신설예정"))
        self.assertEqual((s["openYm"], s["classes"], s["students"]), ("2029-03", 44, 1113))
        self.assertAlmostEqual(s["lon"], 126.7573199)       # pointX 가 위도, pointY 가 경도로 온다
        self.assertAlmostEqual(s["lat"], 37.5553787)
        self.assertEqual(s["address"], "인천광역시 계양구 동양동 416-2 일원")
        self.assertEqual(s["sources"], ["edu-newschool"])

    def test_filters_by_address_and_sorts_by_open_month(self):
        rows = [edu_row(schlSeq=2, schlNm="(가칭)나", openSchdYm="202909"), edu_row(schlSeq=3, schlNm="(가칭)다", realAddr="전남광주통합특별시 광산구 하남동 395 일원"),
                edu_row(schlSeq=1, schlNm="(가칭)가", openSchdYm="202703")]
        out = infra.scheduled_schools(rows, "인천광역시 계양구")
        self.assertEqual([s["name"] for s in out], ["(가칭)가", "(가칭)나"])

    def test_all_school_levels_are_mapped(self):
        levels = [infra.scheduled_schools([edu_row(ditcNm=k)], "인천")[0]["level"] for k in ("초", "중", "고", "특수")]
        self.assertEqual(levels, ["초등학교", "중학교", "고등학교", "특수학교"])

    def test_unknown_level_or_bad_month_is_an_error_not_a_silent_drop(self):
        with self.assertRaises(ValueError):
            infra.scheduled_schools([edu_row(ditcNm="대학")], "인천")
        with self.assertRaises(ValueError):
            infra.scheduled_schools([edu_row(openSchdYm="2029")], "인천")

    def test_implausible_coordinates_are_an_error(self):
        with self.assertRaises(ValueError):
            infra.scheduled_schools([edu_row(pointX="126.7", pointY="37.5")], "인천")      # 위·경도가 바뀜


class SchoolSites(unittest.TestCase):
    def feats(self):
        return [site_feature("학교", "초등학교", 126.7573, 37.5553), site_feature("학교", "초등학교", 126.7628, 37.5558),
                site_feature("학교", "유치원", 126.7556, 37.5467, 77, "6000"), site_feature("학교", "중학교", 126.7586, 37.5553, 120, "15000"),
                site_feature("공공문화체육시설", "공공체육시설", 126.76, 37.55), site_feature("학교", "초등학교", *OUT)]

    def test_picks_school_sites_inside_the_area_only(self):
        sites = infra.school_sites(self.feats(), [AREA])
        self.assertEqual(sorted(s["level"] for s in sites), ["유치원", "중학교", "초등학교", "초등학교"])
        self.assertTrue(all(len(s["poly"]) >= 3 and s["poly"][0] != s["poly"][-1] for s in sites))
        self.assertEqual([s["areaM2"] for s in sites if s["level"] == "유치원"], [6000.0])

    def test_new_town_records_put_the_school_level_in_other_columns(self):
        feats = [site_feature("학교", "초등학교", 126.7573, 37.5553, new_style=True), site_feature("학교", "유치원", 126.7556, 37.5467, 77, "6000", new_style=True),
                 site_feature("체육시설", "공공체육시설", 126.76, 37.55, new_style=True)]
        sites = infra.school_sites(feats, [AREA])
        self.assertEqual(sorted(s["level"] for s in sites), ["유치원", "초등학교"])

    def test_scheduled_school_takes_the_site_that_contains_it_and_the_rest_become_site_only(self):
        scheduled = infra.scheduled_schools([edu_row()], "인천광역시 계양구")
        out = infra.merge_schools(scheduled, infra.school_sites(self.feats(), [AREA]))
        by = {s["id"]: s for s in out}
        new = by["edu-51"]
        self.assertEqual(new["status"], "신설예정")
        self.assertIn("poly", new)
        self.assertEqual(new["areaM2"], 14000.0)
        self.assertEqual(new["sources"], ["edu-newschool", "vworld-upis"])
        rest = [s for s in out if s["status"] == "부지만"]
        self.assertEqual(sorted(s["level"] for s in rest), ["유치원", "중학교", "초등학교"])    # 짝 지은 초등 부지는 빠진다
        for s in rest:
            self.assertNotIn("openYm", s)
            self.assertEqual(s["sources"], ["vworld-upis"])
            self.assertIn("공시", s["note"])
        self.assertEqual(len({s["id"] for s in out}), len(out))

    def test_scheduled_school_without_a_site_stays_a_point(self):
        sp = infra.scheduled_schools([edu_row(ditcNm="특수", schlSeq=49, schlNm="(가칭)계양학교", pointX="37.55", pointY="126.75")], "인천")
        out = infra.merge_schools(sp, infra.school_sites(self.feats(), [AREA]))
        special = [s for s in out if s["id"] == "edu-49"][0]
        self.assertNotIn("poly", special)
        self.assertEqual(special["sources"], ["edu-newschool"])

    def test_site_ids_are_stable_across_input_order(self):
        a = infra.merge_schools([], infra.school_sites(self.feats(), [AREA]))
        b = infra.merge_schools([], infra.school_sites(list(reversed(self.feats())), [AREA]))
        self.assertEqual([s["id"] for s in a], [s["id"] for s in b])

    def test_a_nearby_same_level_site_is_taken_when_the_official_point_is_just_outside(self):
        site = infra.school_sites([site_feature("학교", "초등학교", 126.7573, 37.5553, 20)], [AREA])    # 한 변 20 m
        sch = infra.scheduled_schools([edu_row(pointX="37.55545", pointY="126.75732")], "인천")        # 부지 중심에서 북쪽 약 17 m = 가장자리 바깥
        self.assertFalse(geo.point_in_ring((sch[0]["lon"], sch[0]["lat"]), site[0]["poly"]))
        self.assertIn("poly", infra.merge_schools(sch, site)[0])

    def test_a_far_same_level_site_is_not_taken(self):
        site = infra.school_sites([site_feature("학교", "초등학교", 126.7600, 37.5553, 20)], [AREA])       # 약 240 m 떨어짐
        sch = infra.scheduled_schools([edu_row()], "인천")
        self.assertNotIn("poly", infra.merge_schools(sch, site)[0])

    def test_a_site_of_another_level_is_never_taken(self):
        site = infra.school_sites([site_feature("학교", "중학교", 126.7573, 37.5553)], [AREA])
        out = infra.merge_schools(infra.scheduled_schools([edu_row()], "인천"), site)
        self.assertNotIn("poly", out[0])
        self.assertEqual([s["status"] for s in out], ["신설예정", "부지만"])


class FacilitySites(unittest.TestCase):
    def test_power_and_transit_sites_inside_the_area(self):
        power = [site_feature("전기공급설비", "기타전기공급설비", 126.7607, 37.5419, 50, "2400", "전기공급설비"), site_feature("전기공급설비", "기타전기공급설비", *OUT)]
        transit = [site_feature("교통시설", "자동차정류장", 126.7659, 37.5568, 100, "12000", "공영차고지"), site_feature("교통시설", "노외주차장", 126.76, 37.55)]
        out = infra.facility_sites(power, transit, [AREA])
        self.assertEqual([(s["category"], s["name"], s["areaM2"]) for s in out], [("전기", "전기공급설비", 2400.0), ("교통", "공영차고지", 12000.0)])
        self.assertEqual([s["id"] for s in out], ["site-power-1", "site-transit-1"])
        self.assertTrue(all(s["sources"] == ["vworld-upis"] for s in out))


    def test_new_town_power_record_is_recognised_too(self):
        power = [site_feature("전기공급설비", "기타전기공급설비", 126.7607, 37.5419, 50, "2400", "전기공급설비", new_style=True)]
        out = infra.facility_sites(power, [], [AREA])
        self.assertEqual([(s["category"], s["areaM2"]) for s in out], [("전기", 2400.0)])


class Attendance(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        # 학구 A: (126.75~126.76, 37.55~37.56) 시계 방향 바깥 고리 / 학구 B: 그 동쪽
        def ring_tm(lon0, lat0, lon1, lat1):
            pts = [(lon0, lat0), (lon0, lat1), (lon1, lat1), (lon1, lat0), (lon0, lat0)]     # 시계 방향
            return [proj.to_tm(*p) for p in pts]
        self.shp = d / "zone.shp"
        write_shp(self.shp, [[ring_tm(126.75, 37.55, 126.76, 37.56)], [ring_tm(126.76, 37.55, 126.77, 37.56)]])
        write_dbf(d / "zone.dbf", [{"HAKGUDO_ID": "ZA", "HAKGUDO_NM": "가초통학구역", "HAKGUDO_GB": "0", "BASE_DT": "2026-09-20"},
                                   {"HAKGUDO_ID": "ZB", "HAKGUDO_NM": "나초통학구역", "HAKGUDO_GB": "0", "BASE_DT": "2026-09-20"}])
        self.link = [{"학구ID": "ZA", "학교ID": "B1", "학교명": "가초등학교", "학교급구분": "초등학교"},
                     {"학구ID": "ZB", "학교ID": "B2", "학교명": "나초등학교", "학교급구분": "초등학교"}]
        self.loc = [{"학교ID": "B1", "학교명": "가초등학교", "위도": "37.555", "경도": "126.755"},
                    {"학교ID": "B2", "학교명": "나초등학교", "위도": "37.556", "경도": "126.765"}]

    def tearDown(self):
        self.tmp.cleanup()

    def projects(self):
        return [{"id": "p1", "outline": {"poly": sq(126.752, 37.552)}}, {"id": "p2", "outline": {"poly": sq(126.768, 37.557)}},
                {"id": "p3", "outline": {"poly": sq(126.753, 37.558)}}, {"id": "far", "outline": {"poly": sq(127.5, 36.0)}}]

    def test_each_project_gets_the_zone_that_contains_its_centre(self):
        zones, att = infra.attendance(self.projects(), self.shp, self.shp.with_suffix(".dbf"), self.link, self.loc, "2026-09-20")
        self.assertEqual({a["projectId"]: a["zoneId"] for a in att}, {"p1": "ZA", "p2": "ZB", "p3": "ZA"})   # 지구 밖 단지는 빠진다
        self.assertEqual([z["id"] for z in zones], ["ZA", "ZB"])

    def test_zone_carries_school_name_location_ring_and_date(self):
        zones, _ = infra.attendance(self.projects(), self.shp, self.shp.with_suffix(".dbf"), self.link, self.loc, "2026-09-20")
        z = zones[0]
        self.assertEqual((z["name"], z["school"], z["asOf"], z["sources"]), ("가초통학구역", "가초등학교", "2026-09-20", ["edu-zone"]))
        self.assertAlmostEqual(z["schoolLon"], 126.755)
        self.assertAlmostEqual(z["schoolLat"], 37.555)
        lons = [p[0] for p in z["poly"]]
        lats = [p[1] for p in z["poly"]]
        self.assertAlmostEqual(min(lons), 126.75, places=5)
        self.assertAlmostEqual(max(lats), 37.56, places=5)
        self.assertNotEqual(z["poly"][0], z["poly"][-1])

    def test_a_zone_without_a_linked_school_is_an_error(self):
        with self.assertRaises(ValueError):
            infra.attendance(self.projects(), self.shp, self.shp.with_suffix(".dbf"), self.link[1:], self.loc, "2026-09-20")

    def test_prefers_the_single_school_zone_over_a_joint_zone(self):
        d = Path(self.tmp.name)
        ring = [proj.to_tm(*p) for p in [(126.74, 37.54), (126.74, 37.57), (126.78, 37.57), (126.78, 37.54), (126.74, 37.54)]]
        write_shp(d / "z2.shp", [[ring], [[proj.to_tm(*p) for p in [(126.75, 37.55), (126.75, 37.56), (126.76, 37.56), (126.76, 37.55), (126.75, 37.55)]]]])
        write_dbf(d / "z2.dbf", [{"HAKGUDO_ID": "ZJ", "HAKGUDO_NM": "공동통학구역", "HAKGUDO_GB": "1", "BASE_DT": "2026-09-20"},
                                 {"HAKGUDO_ID": "ZA", "HAKGUDO_NM": "가초통학구역", "HAKGUDO_GB": "0", "BASE_DT": "2026-09-20"}])
        _, att = infra.attendance([self.projects()[0]], d / "z2.shp", d / "z2.dbf", self.link, self.loc, "2026-09-20")
        self.assertEqual(att[0]["zoneId"], "ZA")


def bus_row(nid, name, lat, lon, no="1"):
    return {"nodeid": nid, "nodenm": name, "nodeno": no, "gpslati": lat, "gpslong": lon, "citycode": 23}


def route_row(rid, no, tp="간선버스", a="기점", b="종점"):
    return {"routeid": rid, "routeno": no, "routetp": tp, "startnodenm": a, "endnodenm": b}


class BusStops(unittest.TestCase):
    def test_grid_cells_are_small_enough_that_a_500m_search_covers_the_whole_box(self):
        pts = infra.bus_grid([AREA], margin_m=400)
        x0, y0, x1, y1 = infra._expanded_bbox([AREA], 400)
        self.assertGreater(len(pts), 4)
        self.assertTrue(all(y0 <= la <= y1 and x0 <= lo <= x1 for la, lo in pts))
        samples = [(x0, y0), (x1, y0), (x0, y1), (x1, y1), ((x0 + x1) / 2, (y0 + y1) / 2), (x0 + (x1 - x0) * 0.37, y0 + (y1 - y0) * 0.81)]
        for lon, lat in samples:
            self.assertLessEqual(min(infra._dist_m((lon, lat), (lo, la)) for la, lo in pts), 500, (lon, lat))

    def test_a_tiny_area_still_gets_one_point(self):
        self.assertEqual(len(infra.bus_grid([[[126.75, 37.55], [126.7501, 37.55], [126.7501, 37.5501]]], margin_m=10)), 1)

    def test_merge_keeps_one_per_id_inside_the_box_and_reads_string_coordinates(self):
        rows = [bus_row("S1", "가", "37.55", 126.76, "101"), bus_row("S1", "가", 37.55, 126.76), bus_row("S2", "나", 37.5605, 126.76, no=""),
                bus_row("S3", "멀리", 37.6, 126.9), bus_row("S4", "빈", "", 126.76), {"nodenm": "id 없음", "gpslati": 37.55, "gpslong": 126.76}]
        out = infra.merge_bus_stops(rows, [AREA], margin_m=1000)
        self.assertEqual([s["id"] for s in out], ["S1", "S2"])
        self.assertEqual(out[0], {"id": "S1", "name": "가", "lon": 126.76, "lat": 37.55, "no": "101"})
        self.assertNotIn("no", out[1])                                   # 정류소 번호가 없으면 키를 뺀다

    def test_catalog_attach_and_live(self):
        sr = {"S1": [route_row("R584", 584, "지선버스"), route_row("R87", 87)], "S2": [route_row("R87", 87)], "S3": [route_row("R9", "9")], "S4": []}
        cat = infra.route_catalog(sr)
        self.assertEqual(sorted(cat), ["R584", "R87", "R9"])
        self.assertEqual(cat["R87"], {"id": "R87", "no": "87", "type": "간선버스", "from": "기점", "to": "종점"})
        stops = [{"id": "S1", "name": "가", "lon": 126.760, "lat": 37.55}, {"id": "S2", "name": "나", "lon": 126.80, "lat": 37.55},
                 {"id": "S3", "name": "다", "lon": 126.82, "lat": 37.55}, {"id": "S4", "name": "라", "lon": 126.76, "lat": 37.55}]
        out = infra.attach_routes(stops, sr, cat)
        self.assertEqual(out[0]["routes"], ["R87", "R584"])             # 노선 번호 순(숫자로)
        self.assertNotIn("routes", out[3])                              # 지나는 노선이 없으면 키를 뺀다
        self.assertEqual(infra.live_route_ids(out, [(126.755, 37.55)], 500), {"R87", "R584"})   # S1 은 440 m, S2·S3 는 멀다
        self.assertEqual(infra.live_route_ids(out, [(126.755, 37.55)], 100), set())

    def test_route_path_is_indexed_by_stop_order_and_fills_missing_coordinates(self):
        rows = [{"nodeord": 2, "gpslati": "37.2", "gpslong": "126.2"}, {"nodeord": 1, "gpslati": 37.1, "gpslong": 126.1},
                {"nodeord": 4, "gpslati": 37.4, "gpslong": 126.4}, {"nodeord": 3, "gpslati": "", "gpslong": ""}, {"nodeord": "x", "gpslati": 1, "gpslong": 1}]
        self.assertEqual(infra.route_path(rows), [[126.1, 37.1], [126.2, 37.2], [126.2, 37.2], [126.4, 37.4]])
        self.assertEqual(infra.route_path([]), [])
        self.assertEqual(infra.route_path([{"nodeord": 3, "gpslati": 37.3, "gpslong": 126.3}]), [[126.3, 37.3]] * 3)   # 앞쪽이 비면 첫 좌표로

    def test_routes_doc_puts_live_first_and_only_live_routes_carry_a_path(self):
        cat = infra.route_catalog({"S": [route_row("R9", "9"), route_row("R87", 87), route_row("R584", 584, "지선버스"), route_row("RM", "M6405", "광역버스")]})
        doc = infra.bus_routes_doc(cat, {"R584"}, {"R584": [[1, 2], [3, 4]], "R87": [[9, 9], [8, 8]]})
        self.assertEqual([r["no"] for r in doc], ["584", "9", "87", "M6405"])
        self.assertEqual(doc[0], {"id": "R584", "no": "584", "type": "지선버스", "from": "기점", "to": "종점", "live": True, "path": [[1, 2], [3, 4]]})
        self.assertTrue(all("path" not in r and "live" not in r for r in doc[1:]))


def permit(**kw):
    """건축HUB 기본개요 한 건. 3기 신도시 지구 안 건물은 블록 표기가 block·lot 칸에 나뉘어 온다(예: block '공공주택지구', lot '커뮤니티3')."""
    p = {"mgmPmsrgstPk": "100", "bldNm": "", "mainPurpsCdNm": "노유자시설", "platPlc": "인천광역시 계양구 동양동 블록",
         "block": "공공주택지구", "lot": "커뮤니티3", "splotNm": "인천계양 테크노밸리", "archPmsDay": "20251204", "realStcnsDay": "20260407", "useAprDay": ""}
    p.update(kw)
    return p


class Permits(unittest.TestCase):
    def test_keeps_recent_block_notation_permits_that_are_not_housing(self):
        items = [permit(bldNm="계양구립종합누리센터"), permit(mgmPmsrgstPk="101", mainPurpsCdNm="공동주택"),
                 permit(mgmPmsrgstPk="102", platPlc="인천광역시 계양구 박촌동 70-11번지", block="", lot="", splotNm=""),
                 permit(mgmPmsrgstPk="103", archPmsDay="20150101"), permit(mgmPmsrgstPk="104", bldNm="", block="종교시설1", lot="", mainPurpsCdNm="종교시설")]
        out = infra.nonhousing_permits(items, since="2019-01-01")
        self.assertEqual([p["id"] for p in out], ["permit-100", "permit-104"])
        self.assertEqual(out[0], {"id": "permit-100", "name": "계양구립종합누리센터", "use": "노유자시설", "permitDate": "2025-12-04",
                                  "startDate": "2026-04-07", "approvalDate": None, "sources": ["hub-arch"]})
        self.assertEqual(out[1]["name"], "종교시설1")           # 건물 이름이 비면 블록 표기를 이름으로

    def test_a_building_name_that_is_only_the_dong_name_is_replaced_by_the_block_label(self):
        [p] = infra.nonhousing_permits([permit(bldNm="동양동", block="종교시설1", lot="", mainPurpsCdNm="종교시설")], "2019-01-01")
        self.assertEqual(p["name"], "종교시설1")

    def test_block_and_lot_labels_are_joined_when_there_is_no_building_name(self):
        [p] = infra.nonhousing_permits([permit()], "2019-01-01")
        self.assertEqual(p["name"], "공공주택지구 커뮤니티3")

    def test_sorted_by_permit_date(self):
        out = infra.nonhousing_permits([permit(mgmPmsrgstPk="2", archPmsDay="20260101"), permit(mgmPmsrgstPk="1", archPmsDay="20250101")], "2019-01-01")
        self.assertEqual([p["id"] for p in out], ["permit-1", "permit-2"])


class Assemble(unittest.TestCase):
    def test_document_lists_only_the_sources_it_uses_and_validates(self):
        scheduled = infra.scheduled_schools([edu_row()], "인천")
        doc = infra.assemble(today="2026-10-04", schools=infra.merge_schools(scheduled, []), zones=[], attendance=[], stops=[], sites=[], permits=[],
                             curated={"sources": [{"id": "news-a", "label": "기사 A", "redistributable": "unknown"}],
                                      "measures": [{"id": "m1", "category": "교통", "title": "버스", "sources": ["news-a"]}]},
                             source_dates={"edu-newschool": "2026-03-31"})
        self.assertEqual(doc["schema_version"], "1.3.0")
        self.assertEqual(doc["asOf"], "2026-10-04")
        self.assertEqual([s["id"] for s in doc["sources"]], ["edu-newschool", "news-a"])
        self.assertEqual(doc["sources"][0]["asOf"], "2026-03-31")
        self.assertNotIn("zones", doc)            # 비어 있는 목록은 키를 뺀다
        self.assertEqual(doc["measures"][0]["id"], "m1")

    def test_unknown_source_reference_is_an_error(self):
        sch = [{"id": "s", "name": "x", "level": "초등학교", "status": "부지만", "lon": 126.7, "lat": 37.5, "sources": ["nope"]}]
        with self.assertRaises(ValueError):
            infra.assemble(today="2026-10-04", schools=sch, zones=[], attendance=[], stops=[], sites=[], permits=[], curated={}, source_dates={})

    def test_coordinates_are_rounded_to_six_places(self):
        sch = [{"id": "s", "name": "x", "level": "초등학교", "status": "부지만", "lon": 126.757319912345, "lat": 37.555378712345,
                "poly": [[126.7573199123, 37.5553787123], [126.7574, 37.5553], [126.7573, 37.5552]], "sources": ["vworld-upis"]}]
        doc = infra.assemble(today="2026-10-04", schools=sch, zones=[], attendance=[], stops=[], sites=[], permits=[], curated={}, source_dates={})
        self.assertEqual(doc["schools"][0]["lon"], 126.757320)
        self.assertEqual(doc["schools"][0]["poly"][0], [126.75732, 37.555379])

    def test_bus_stops_and_routes_cite_the_tago_source_and_keep_the_city_code(self):
        stops = [{"id": "S1", "name": "가", "lon": 126.76, "lat": 37.55, "routes": ["R87"]}]
        routes = [{"id": "R87", "no": "87", "type": "간선버스", "from": "기", "to": "종", "live": True, "path": [[126.7600001, 37.55], [126.77, 37.56]]}]
        doc = infra.assemble(today="2026-10-05", schools=[], zones=[], attendance=[], stops=stops, sites=[], permits=[], curated={},
                             source_dates={"tago-bus": "2026-10-05"}, bus_routes=routes, bus_city=23)
        self.assertEqual([s["id"] for s in doc["sources"]], ["tago-bus"])
        self.assertEqual(doc["sources"][0]["asOf"], "2026-10-05")
        self.assertEqual(doc["busCityCode"], 23)
        self.assertEqual(doc["busRoutes"][0]["path"][0], [126.76, 37.55])           # 경로 좌표도 6자리
        self.assertNotIn("molit-busstop", [s["id"] for s in doc["sources"]])

    def test_live_routes_need_a_city_code_and_no_live_route_means_no_city_code(self):
        live = [{"id": "R", "no": "1", "live": True, "path": [[126.7, 37.5], [126.8, 37.6]]}]
        with self.assertRaises(ValueError):
            infra.assemble(today="2026-10-05", schools=[], zones=[], attendance=[], stops=[], sites=[], permits=[], curated={}, source_dates={}, bus_routes=live)
        doc = infra.assemble(today="2026-10-05", schools=[], zones=[], attendance=[], stops=[], sites=[], permits=[], curated={}, source_dates={},
                             bus_routes=[{"id": "R", "no": "1"}], bus_city=23)
        self.assertNotIn("busCityCode", doc)


if __name__ == "__main__":
    unittest.main()
