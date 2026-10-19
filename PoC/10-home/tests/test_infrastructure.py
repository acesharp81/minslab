import json
import unittest
from unittest.mock import patch

from backend.infrastructure import normalize_place, parse_places, nearby_gtx_stations, GTX_RADIUS_METRES, deduplicate_places, merge_rail_stations


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

    def test_childcare_excludes_play_cafes_closed_and_unlocated_facilities(self):
        origin = (37.6222, 126.8709)
        result = normalize_place(place("시립하늘어린이집", "교육 > 유아교육 > 어린이집"), "childcare", *origin)
        self.assertEqual(result["kind"], "childcare")
        for name, category in [("하늘키즈카페", "유아놀이시설"), ("폐원하늘어린이집", "어린이집"), ("개원예정어린이집", "어린이집")]:
            self.assertIsNone(normalize_place(place(name, category), "childcare", *origin))
        self.assertIsNone(normalize_place(place("먼어린이집", "어린이집", 35, 128), "childcare", *origin))

    def test_large_mart_store_names_and_categories_exclude_tenants_and_small_stores(self):
        origin = (37.6222, 126.8709)
        for name, category in [('이마트 수서점', '음ㆍ식료품위주종합소매업 > 슈퍼마켓'),
                ('홈플러스(주)가양점', '기타식품제조업 > 기타식사용가공처리조리식품제조업'),
                ('롯데마트 김포공항점', '기타정보서비스업 > 재해구호물자구매업체'),
                ('트레이더스홀세일클럽마곡점', '음ㆍ식료품위주종합소매업 > 슈퍼마켓'),
                ('코스트코 양평점', '대형종합소매업 > 대형마트'),
                ('메가마트', '대형종합소매업 > 대형마트')]:
            with self.subTest(name=name):
                self.assertEqual(normalize_place(place(name,category),'mart',*origin)['kind'],'mart')
        for name, category in [('이마트24수서점','슈퍼마켓'), ('이마트에브리데이마곡점','슈퍼마켓'),
                ('홈플러스익스프레스가양점','대형마트'), ('동네마트','슈퍼마켓'),
                ('이마트,증미역','도로시설 > 버스터미널/정류장'), ('이마트가양점입구','진출입시설'),
                ('이마트문화센터가양점','교육'), ('이마트가양점','버스정류장'),
                ('공차트레이더스마곡점','음식점업 > 카페'), ('홈플러스아모레잠실점','화장품소매업'),
                ('롯데마트문화비송파점','슈퍼마켓'), ('홈플러스도서문화비잠실점','슈퍼마켓'),
                ('NC백화점강서점','대형종합소매업 > 대형마트'), ('제이에스엠케이','대형마트'),
                ('폐점이마트가양점','대형마트'), ('롯데하이마트화곡점','슈퍼마켓')]:
            with self.subTest(name=name):
                self.assertIsNone(normalize_place(place(name,category),'mart',*origin))
        self.assertIsNone(normalize_place(place('코스트코양평점','대형마트',35,128),'mart',*origin))
        self.assertIsNone(normalize_place({'title':'이마트가양점','category':'슈퍼마켓'},'mart',*origin))

    def test_large_marts_are_searched_deduplicated_counted_and_cached(self):
        from backend.infrastructure import InfrastructureContext
        from unittest.mock import MagicMock
        from pathlib import Path
        fetcher=MagicMock();fetcher.manifest=[]
        items=[place('홈플러스(주)가양점','슈퍼마켓'),place('홈플러스가양점','슈퍼마켓'),
               place('홈플러스익스프레스가양점','슈퍼마켓')]
        fetcher.get.side_effect=lambda *a,params,**kw:document(items) if params['query'] in ('대형마트','홈플러스') else document([])
        anchor=dict(latitude=37.6222,longitude=126.8709,coordinate_basis='APPROXIMATE_ADDRESS',label='대표 위치',approximate=True)
        with patch('backend.infrastructure.Fetcher',return_value=fetcher),patch('backend.infrastructure.key_for',return_value='test'):
            context=InfrastructureContext();result=context.get('mart-block',MagicMock(data_dir=Path('/tmp')),anchor)
            calls=fetcher.get.call_count
            self.assertEqual(context.get('mart-block',MagicMock(),anchor),result)
            self.assertEqual(fetcher.get.call_count,calls)
        self.assertEqual(result['counts']['mart'],1)
        self.assertEqual(len([p for p in result['items'] if p['kind']=='mart']),1)
        self.assertIn('영업',result['mart_note'])
        self.assertIn('롯데마트',{c.kwargs['params']['query'] for c in fetcher.get.call_args_list})

    def test_opening_plans_preserve_month_precision_and_unlocated_status(self):
        from backend.facility_plans import nearby_plans
        from backend.infrastructure import distance_metres
        rows, note = nearby_plans(37.407, 127.0818, distance_metres)
        self.assertEqual(rows[0]['name'], '금토초등학교')
        self.assertEqual(rows[0]['opening_date'], '2027-03')
        self.assertEqual(rows[0]['service_status'], 'PLANNED')
        self.assertEqual(rows[0]['opening_date_precision'], 'MONTH')
        rows, _ = nearby_plans(37.5561, 126.7547, distance_metres, district_key='인천계양')
        self.assertEqual(len(rows), 2)
        unlocated = next(r for r in rows if r['id'].endswith('a3-childcare'))
        self.assertIsNone(unlocated['distance_m'])
        self.assertIsNone(unlocated['latitude'])
        self.assertEqual(nearby_plans(34, 128, distance_metres)[0], [])

    def test_gtx_stations_require_verified_poi_and_separate_radius(self):
        nearby = nearby_gtx_stations(37.6222373, 126.8708709)
        self.assertEqual([row["name"] for row in nearby[:2]], ["연신내역", "대곡역"])
        self.assertTrue(all(row["kind"] == "subway" and row["line"] == "GTX-A" and row["service_status"] == "OPERATING"
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


    def test_bus_stop_categories_nonstopping_and_opposite_directions(self):
        origin=(37.6222,126.8709)
        category='도로시설 > 버스터미널/정류장 > 버스정류장'
        first=normalize_place(dict(place('창릉역(버스정류장)',category),id='stop-1'),'bus',*origin)
        opposite=normalize_place(dict(place('창릉역(버스정류장)',category,lat=37.6223),id='stop-2'),'bus',*origin)
        self.assertEqual(first['kind'],'bus')
        self.assertEqual(len(deduplicate_places([first,dict(first),opposite])),2)
        for name,cat in [('일산IC(미정차)(버스정류장)',category),('폐쇄 정류장',category),('버스정류장카페','음식점'),('터미널','도로시설 > 버스터미널')]:
            self.assertIsNone(normalize_place(place(name,cat),'bus',*origin))

    def test_gtx_same_station_is_merged_into_subway_without_losing_source(self):
        gtx=nearby_gtx_stations(37.61896,126.92116)[0]
        existing=dict(gtx,category='철도시설 > 철도/지하철 > 지하철역')
        existing.pop('line');existing.pop('service_status_source_url')
        result=merge_rail_stations([existing],[gtx])
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['kind'],'subway')
        self.assertEqual(result[0]['line'],'GTX-A')
        self.assertEqual(result[0]['service_status_source_url'],gtx['service_status_source_url'])
        self.assertNotIn('line',existing)

    def test_representative_location_query_keeps_coordinate_basis_and_cache_scope(self):
        from backend.infrastructure import InfrastructureContext,QUERIES
        from unittest.mock import MagicMock
        from pathlib import Path
        service=MagicMock(data_dir=Path('/tmp'))
        fetcher=MagicMock();fetcher.manifest=[];fetcher.get.return_value=json.dumps({'response':{'status':'NOT_FOUND'}}).encode()
        anchor=dict(latitude=37.5,longitude=127.1,coordinate_basis='APPROXIMATE_ADDRESS',label='대표 지번 근사 위치',approximate=True)
        with patch('backend.infrastructure.Fetcher',return_value=fetcher),patch('backend.infrastructure.key_for',return_value='test'):
            context=InfrastructureContext();result=context.get('project-test',service,anchor)
            self.assertEqual(result['origin'],anchor)
            self.assertIn('대표 지번 근사 위치',result['distance_basis'])
            self.assertEqual(fetcher.get.call_count,len(QUERIES))
            context.get('project-test',service,anchor)
            self.assertEqual(fetcher.get.call_count,len(QUERIES))
            context.get('project-test',service,dict(anchor,longitude=127.11))
            self.assertEqual(fetcher.get.call_count,len(QUERIES)*2)

    def test_nearest_rail_search_expands_beyond_facility_radius(self):
        from backend.infrastructure import InfrastructureContext
        from unittest.mock import MagicMock
        from pathlib import Path
        fetcher=MagicMock();fetcher.manifest=[]
        station=place('외곽역','철도시설 > 철도/지하철',37.60,127.1)
        def response(*args,params,**kwargs):
            if params['query']=='지하철역':return document([station])
            return document([])
        fetcher.get.side_effect=response
        anchor=dict(latitude=37.5,longitude=127.1,coordinate_basis='APPROXIMATE_ADDRESS',label='대표 위치',approximate=True)
        with patch('backend.infrastructure.Fetcher',return_value=fetcher),patch('backend.infrastructure.key_for',return_value='test'),patch('backend.infrastructure.nearby_gtx_stations',return_value=[]):
            result=InfrastructureContext().get('far-rail',MagicMock(data_dir=Path('/tmp')),anchor)
        self.assertEqual(result['subway_search_radius_metres'],12000)
        self.assertEqual(result['items'][0]['name'],'외곽역')
        self.assertGreater(result['items'][0]['distance_m'],3500)
        self.assertEqual(sum(call.kwargs['params']['query']=='지하철역' for call in fetcher.get.call_args_list),2)
        self.assertIsNone(normalize_place(place('먼병원','병원',37.60,127.1),'hospital',37.5,127.1))

    def test_map_editor_and_infrastructure_share_anchor_priority(self):
        from backend.project_locations import resolve_anchor
        project=dict(id='p',latitude=37.5,longitude=127.1,coordinate_basis='APPROXIMATE_ADDRESS')
        block=dict(id='b',project_ids=['p'],latitude=37.51,longitude=127.11,coordinate_basis='LH_PUBLIC_BLOCK_LABEL_POINT')
        anchor=resolve_anchor(project,dict(blocks=[block]));self.assertEqual(anchor['block_id'],'b');self.assertFalse(anchor['approximate'])
        anchor=resolve_anchor(project,{},dict(address_original='서울특별시 강남구 일원동 711',evidence_url='https://example.org'))
        self.assertEqual(anchor['latitude'],project['latitude']);self.assertTrue(anchor['approximate']);self.assertIn('711',anchor['address'])
        anchor=resolve_anchor(dict(id='p'),dict(municipalities=[dict(block,coordinate_basis=None)]))
        self.assertIn('시군구 대표점',anchor['label']);self.assertTrue(anchor['approximate'])
        self.assertIsNone(resolve_anchor(dict(id='p',latitude=float('nan'),longitude=127)))
