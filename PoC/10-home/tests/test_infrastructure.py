import json
import unittest
from unittest.mock import patch

from backend.infrastructure import normalize_place, parse_places, nearby_gtx_stations, GTX_RADIUS_METRES


def document(items, total=None):
    return json.dumps({"response": {"status": "OK", "record": {"total": len(items) if total is None else total},
                                    "result": {"items": items}}}).encode()


def place(name, category, lat=37.6222, lon=126.8709):
    return {"id": name, "title": name, "category": category,
            "point": {"x": str(lon), "y": str(lat)}, "address": {"road": "공식 주소"}}


class InfrastructureTests(unittest.TestCase):
    def test_only_requested_facilities_with_verified_points_are_included(self):
        origin = (37.6222, 126.8709)
        station = normalize_place(place("화전역", "철도시설 > 철도/지하철 > 지하철역"), "subway", *origin)
        school = normalize_place(place("창릉초등학교", "중앙행정기관 > 교육부 > 초등학교"), "school", *origin)
        hospital = normalize_place(place("고양병원", "병원 > 일반병원 > 병원"), "hospital", *origin)
        self.assertEqual([station["kind"], school["kind"], hospital["kind"]], ["subway", "school", "hospital"])
        self.assertIsNone(normalize_place(place("동물병원", "수의업"), "hospital", *origin))
        self.assertIsNone(normalize_place(place("학교급식실", "중앙행정기관 > 교육부"), "school", *origin))
        self.assertIsNone(normalize_place(place("역앞상가", "시설구역경계"), "subway", *origin))
        self.assertIsNone(normalize_place(place("멀리병원", "병원",37.7,127.0), "hospital", *origin))

    def test_gtx_stations_require_verified_poi_and_separate_radius(self):
        nearby = nearby_gtx_stations(37.6222373, 126.8708709)
        self.assertEqual([row["name"] for row in nearby[:2]], ["연신내역", "대곡역"])
        self.assertTrue(all(row["kind"] == "gtx" and row["service_status"] == "OPERATING"
                            and row["location_basis"] in ("VWORLD_EXISTING_STATION_POI", "VWORLD_STATION_EXIT_BUS_STOP_PROXY")
                            and row["distance_m"] <= GTX_RADIUS_METRES for row in nearby))
        self.assertNotIn("창릉역", [row["name"] for row in nearby])
        self.assertIn("킨텍스역", [row["name"] for row in nearby])
        self.assertEqual(next(row for row in nearby if row["name"] == "킨텍스역")["location_basis"],
                         "VWORLD_STATION_EXIT_BUS_STOP_PROXY")
        self.assertEqual(nearby_gtx_stations(34.0, 128.0), [])

    def test_place_search_pagination_is_complete(self):
        with patch("backend.infrastructure.PAGE_SIZE", 2):
            first,total=parse_places(document([place("A역","철도시설 > 철도/지하철"),place("B역","철도시설 > 철도/지하철")],3),1)
            last,last_total=parse_places(document([place("C역","철도시설 > 철도/지하철")],3),2)
            self.assertEqual((len(first),len(last),total,last_total),(2,1,3,3))
            with self.assertRaises(ValueError):parse_places(document([place("C역","철도시설 > 철도/지하철")],3),1)
