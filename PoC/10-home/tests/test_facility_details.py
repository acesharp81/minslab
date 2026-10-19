import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import httpx
from backend.facility_details import FacilityDetails, same_address, parse_school, parse_childcare, bus_match, timetable_headways
from backend.collectors import Fetcher


class FacilityDetailsTests(unittest.TestCase):
    def test_names_alone_and_other_buildings_never_match(self):
        self.assertTrue(same_address('서울 강남구 광평로51길 27, 402동 104호','서울특별시 강남구 광평로51길 27'))
        self.assertFalse(same_address('서울 강남구 광평로 280','서울 강남구 광평로 270'))
        self.assertFalse(same_address('경기도 광평로 280','서울 광평로 280'))
        self.assertFalse(same_address('다솜어린이집','다솜어린이집'))
        self.assertFalse(same_address('서울 강서구 중앙로 27','서울 양천구 중앙로 27'))
        self.assertFalse(same_address('경기도 성남시 분당구 중앙로 27','경기도 성남시 수정구 중앙로 27'))

    def test_school_students_are_separate_from_capacity_and_address_is_required(self):
        body='<title>서울수서초등학교 학교정보</title><select id="gsYear"><option value="2026" selected>2026</option></select><p>주소 : 서울특별시 강남구 광평로51길 46 학생수 : 114명 교원수 : 22명</p>'.encode('cp949')
        place=dict(name='서울수서초등학교',address='서울특별시 강남구 광평로51길 46')
        r=parse_school(body,place)
        self.assertEqual(r['fields'],[{'label':'전교생','value':'114명'},{'label':'교원','value':'22명'}])
        self.assertEqual(r['as_of'],'2026학년도 공시')
        self.assertIsNone(parse_school(body,dict(place,address='서울특별시 강남구 광평로 270')))

    def test_childcare_homonyms_use_address_and_keep_capacity_occupancy_separate(self):
        row=lambda address,capacity: '<tr>'+''.join('<td>'+v+'</td>' for v in ['1','다솜어린이집','가정',capacity,'16명','02-445-2982',address,'<a href="?stCode=11680000406">홈</a>'])+'</tr>'
        body='<table><tbody>'+row('서울특별시 강남구 광평로51길 27','20명')+row('서울특별시 강서구 공항대로 123','99명')+'</tbody></table>'
        r=parse_childcare(body,dict(name='다솜어린이집',address='서울특별시 강남구 광평로51길 27'))
        self.assertEqual([f['value'] for f in r['fields']][1:3],['20명','16명'])
        self.assertIsNone(parse_childcare(body,dict(name='다솜어린이집',address='서울특별시 강남구 광평로51길 28')))

    def test_opposite_bus_stops_are_not_joined_on_name(self):
        p=dict(name='수서역(버스정류장)',latitude=37.5,longitude=127)
        row=lambda lat,code:dict(name='수서역',latitude=lat,longitude=127,code=code)
        self.assertEqual(bus_match(p,[row(37.5003,'wrong'),row(37.5,'right')])['code'],'right')
        self.assertIsNone(bus_match(p,[row(37.5002,'a'),row(37.50022,'b')]))
        self.assertIsNone(bus_match(p,[row(38,'far')]))

    def test_headways_do_not_mix_directions_or_overnight_hours(self):
        r=timetable_headways([dict(hh='07',upArrow='00(대화), 05(대화), 10(대화)',dnArrow='00(오금), 20(오금)'),dict(hh='01',upArrow='00(대화),01(대화)',dnArrow='')])
        self.assertEqual([v['value'] for v in r],['5~5분 · 시간표 기준','20~20분 · 시간표 기준'])
        self.assertEqual(timetable_headways([]),[])

    def test_mart_joins_store_id_and_address_and_preserves_actual_holidays(self):
        p=dict(id='mart',kind='mart',name='이마트수서점',address='서울특별시 강남구 광평로 280',latitude=37.5,longitude=127)
        for address,expected in [('서울특별시 강남구 광평로 280','READY'),('서울특별시 강남구 광평로 270','NOT_LINKED')]:
            with self.subTest(address=address),tempfile.TemporaryDirectory() as raw:
                def respond(request):
                    html='<a href="/branch/view.do?id=1029&mallGbn=">수서점</a>' if request.url.path.endswith('list.do') else '<dl><dt>도로명</dt><dd>'+address+'</dd></dl><dl><dt>휴점일</dt><dd>10/25, 11/8, 11/22</dd></dl>'
                    return httpx.Response(200,text=html+' '*150)
                f=Fetcher('facility_details',raw);f.client.close();f.client=httpx.Client(transport=httpx.MockTransport(respond))
                context=FacilityDetails();context._catalog['emart']=(__import__('time').monotonic(),[('이마트수서점','https://emartapp.emart.com/branch/view.do?id=1029')])
                with patch('backend.facility_details.Fetcher',return_value=f):r=context.get(p,SimpleNamespace(data_dir=Path(raw)))
                self.assertEqual(r['status'],expected)
                if expected=='READY':self.assertEqual(r['fields'][0]['value'],'10/25, 11/8, 11/22')
                else:self.assertEqual(r['fields'],[])

    def test_connection_failure_returns_missing_status_instead_of_zero(self):
        p=dict(id='x',kind='school',name='학교',address='서울 강남구 광평로 1',latitude=37.5,longitude=127)
        with tempfile.TemporaryDirectory() as raw,patch.object(FacilityDetails,'_school',side_effect=httpx.ConnectError('unavailable')):
            r=FacilityDetails().get(p,SimpleNamespace(data_dir=Path(raw)))
            self.assertEqual(r['status'],'UNAVAILABLE');self.assertEqual(r['fields'],[])

    def test_endpoint_only_resolves_ids_from_selected_location(self):
        from fastapi.testclient import TestClient
        from sqlalchemy import create_engine
        from sqlalchemy.pool import StaticPool
        from backend.db import Base
        from backend.app import create_app
        engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool);Base.metadata.create_all(engine)
        p=dict(id='official-place',kind='school',name='공식학교',address='서울 강남구 광평로 1',latitude=37.5,longitude=127)
        app=create_app(engine,auto_collect=False)
        with patch('backend.app.InfrastructureContext.get',return_value={'items':[p]}),patch.object(FacilityDetails,'get',return_value={'status':'READY','fields':[]}) as detail:
            client=TestClient(app)
            base='/poc/home/api/map/facility-details'
            self.assertEqual(client.get(base,params=dict(block_id='block',kind='school',place_id='https://evil.invalid')).status_code,404)
            detail.assert_not_called()
            self.assertEqual(client.get(base,params=dict(block_id='block',kind='school',place_id=p['id'])).status_code,200)
            self.assertEqual(detail.call_args.args[0],p)
            self.assertEqual(client.get(base,params=dict(block_id='block',kind='invalid',place_id=p['id'])).status_code,422)
        engine.dispose()
