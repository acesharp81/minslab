import io
import json
import tempfile
import unittest
import zipfile
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from xml.sax.saxutils import escape
from sqlalchemy import create_engine
from backend.db import Base, upsert_revision
from backend.service import HomeService, today
from backend.sources import SOURCES
from backend.public_files import parse_sh_stock, parse_gh_stock, excel_day
from backend.building_scope import next_districts, expansion_stats
from backend.policy_attachments import collect_urban930_attachment

SOURCES={s['id']:s for s in SOURCES}


def stock_xlsx(rows):
    stream=io.BytesIO()
    def xmlrow(row,index):
        return '<row>'+''.join(f'<c r="{chr(65+i)}{index}" t="inlineStr"><is><t>{escape(v)}</t></is></c>' for i,v in enumerate(row))+'</row>'
    with zipfile.ZipFile(stream,'w') as z:
        z.writestr('xl/sharedStrings.xml','<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"/>')
        z.writestr('xl/worksheets/sheet1.xml','<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'+''.join(xmlrow(row,i+1) for i,row in enumerate(rows))+'</sheetData></worksheet>')
    return stream.getvalue()


class MissingSourcesTests(unittest.TestCase):
    def test_sh_stock_preserves_inventory_metric_and_actual_first_move_in_date(self):
        header=['자치구명','단지명','주택유형','임대세대수','입주개시일','주소','우편번호']
        row=['강남구','단지1','공공임대','10','33618','개포로 1','00000']
        records,stats=parse_sh_stock(stock_xlsx([header,row]),SOURCES['sh_files'],2026,'2026-02-20','https://data.seoul.go.kr/')
        self.assertEqual(records[0][2]['dates']['단지 입주개시일'],'1992-01-15')
        self.assertEqual(records[0][2]['units'],10);self.assertEqual(stats['stock_basis'],'임대세대수')
        self.assertNotIn('proposed_policy',records[0][2]);self.assertIn('AGENCY_STOCK_NOT_SUPPLY',records[0][2]['warnings'])
        with self.assertRaisesRegex(ValueError,'중복'):parse_sh_stock(stock_xlsx([header,row,row]),SOURCES['sh_files'],2026,'2026-02-20','https://data.seoul.go.kr/')

    def test_sh_dataset_year_is_part_of_identity(self):
        header=['자치구명','단지명','주택유형','세대수','입주개시일','주소','우편번호'];row=['강남구','단지1','공공임대','10','','개포로 1','00000']
        data=stock_xlsx([header,row]);a,_=parse_sh_stock(data,SOURCES['sh_files'],2024,'2024-01-01','https://data.seoul.go.kr/');b,_=parse_sh_stock(data,SOURCES['sh_files'],2025,'2025-01-01','https://data.seoul.go.kr/')
        self.assertNotEqual(a[0][1],b[0][1]);self.assertIsNone(a[0][2]['dates']['단지 입주개시일'])

    def test_gh_stock_cp949_and_verified_coordinates(self):
        text='매입임대주택명,공급물량(세대),소재지도로명주소,위도,경도,비고,데이터확인일\n단지1,12,경기도 안양시 도로 1,37.4,126.9,재건축,2026-08-21\n'
        rows,stats=parse_gh_stock(text.encode('cp949'),SOURCES['gh_files'],'https://www.data.go.kr/')
        self.assertEqual(stats['stock_units'],12);self.assertEqual(rows[0][2]['municipality'],'안양시');self.assertFalse(stats['complete_population'])
        with self.assertRaisesRegex(ValueError,'좌표'):parse_gh_stock(text.replace('37.4','35.1').encode('cp949'),SOURCES['gh_files'],'https://www.data.go.kr/')

    def test_scope_resumes_completed_legacy_dongs_and_prioritizes_policy(self):
        def dong(code,address):return dict(source_object_id=code,address=address,region='서울특별시',sigungu_code=code[:5],bjdong_code=code[5:])
        codes=[dong('1168010300','서울특별시 강남구 개포동'),dong('1111010100','서울특별시 종로구 청운동'),dong('1117011900','서울특별시 용산구 효창동')]
        service=SimpleNamespace(rows=lambda k:codes,projects=lambda:[dict(address='서울특별시 용산구 효창동')],latest_collection_stats=lambda s:dict(district_counts={'강남구 개포동':dict(complete_query=True,matching_records=2,fetched=2)}))
        with patch.dict('os.environ',{'POC10_BUILDING_DONGS_PER_BATCH':'1'}):
            districts,counts,total=next_districts(service,'building_hub')
        self.assertEqual(districts[0][1:3],('11170','11900'));self.assertEqual(total,3)
        self.assertIn('1168010300',counts);self.assertFalse(expansion_stats(counts,total,1)['complete_scope'])
        self.assertEqual(expansion_stats(counts,total,1)['scope_remaining_dongs'],2)

    def test_curated_image_identity_and_scope(self):
        data=json.loads((Path(__file__).parents[1]/'backend/data/urban930_progress.json').read_text())
        self.assertEqual(len(data['records']),47)
        self.assertEqual(sum(r['region'] in ('서울특별시','경기도') for r in data['records']),40)
        self.assertEqual(sum(r['status']=='UNKNOWN' for r in data['records']),8)
        class Fetch:
            def get(self,*args):return b'changed PDF'
        # PDF parse occurs first; a valid changed PDF must still fail the evidence hash.
        with patch('backend.policy_attachments.PdfReader',return_value=SimpleNamespace(pages=[])),patch('backend.policy_attachments.parse_urban930_attachment',return_value=([],{})):
            with self.assertRaisesRegex(ValueError,'판본 변경'):collect_urban930_attachment(Fetch())

    def test_database_pagination_matches_filters_without_wildcard_expansion(self):
        engine=create_engine('sqlite://');Base.metadata.create_all(engine);service=HomeService(engine)
        with service.sessions.begin() as session:
            for i,name in enumerate(['100% 실제','1000 사업','다른사업']):
                upsert_revision(session,'agency_stock','sh_files',str(i),dict(name=name,address='서울 주소',region='서울특별시',sample_kind='agency_stock',base_date=today().isoformat(),source_date='2024-02-01' if i<2 else '2025-02-01'),'fixture')
        result=service.sample_page(kind='agency_stock',source_year=2024,page_size=1)
        self.assertEqual(result['total'],2);self.assertEqual(len(result['items']),1);self.assertEqual(result['source_years'],[2025,2024])
        self.assertEqual(service.sample_count(kind='agency_stock',q='100%'),1)
        self.assertEqual(service.sample_count(as_of=today()-timedelta(days=1)),0)
        self.assertEqual(service.sample_page(kind='agency_stock',source_id='not_present')['total'],0)
