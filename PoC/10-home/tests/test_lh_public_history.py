import csv
import io
import unittest
import zipfile
from backend.lh_public_history import parse_supply, parse_movein, parse_stock
from backend.sources import SOURCES
from tests.test_missing_sources import stock_xlsx

S={s['id']:s for s in SOURCES}

class LhPublicHistoryTests(unittest.TestCase):
    def test_supply_uses_offered_units_instead_of_total_and_does_not_claim_occupancy(self):
        h=['공급년도','사업지구','블록','시도','주소','공급유형','세대수','모집공고일','최초입주시기','공급유형별 호수']
        r=['2020','평택고덕','A1','경기도','경기도 평택시 고덕동','공공분양','100','20200102','202212','80']
        data=stock_xlsx([['기준일: 25.11.13'],h,r]);rows,meta=parse_supply(data,S['lh_supply_history'],'https://www.lh.or.kr/')
        p=rows[0][2];self.assertEqual(p['units'],80);self.assertEqual(p['total_units'],100)
        self.assertEqual(p['source_date'],'2020-01-02');self.assertEqual(p['move_in_plan_month'],'2022-12')
        self.assertIn('ANNOUNCEMENT_NOT_OCCUPANCY',p['warnings']);self.assertNotIn('proposed_policy',p)
        with self.assertRaisesRegex(ValueError,'중복'):parse_supply(stock_xlsx([['기준일: 25.11.13'],h,r,r]),S['lh_supply_history'],'https://www.lh.or.kr/')

    def hwpx(self,year,total,rows):
        stream=io.BytesIO()
        from xml.sax.saxutils import escape
        table='<hp:tbl>'+''.join('<hp:tr>'+''.join('<hp:tc><hp:t>'+escape(c)+'</hp:t></hp:tc>' for c in row)+'</hp:tr>' for row in rows)+'</hp:tbl>'
        with zipfile.ZipFile(stream,'w') as z:z.writestr('Contents/section0.xml',f'<root xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph"><hp:t>{year}년 주택입주계획 {total}</hp:t>{table}</root>')
        return stream.getvalue()

    def test_movein_uses_actual_city_instead_of_headquarters_and_flags_mismatched_total(self):
        data=self.hwpx(2026,1000,[['성남복정1','A1','60이하','공공분양','100','2026- 12'],['인천검단','A2','60이하','공공분양','200','2026-01'],['위례','A3','60이하','행복','300','2026-01']])
        rows,meta=parse_movein(data,S['lh_movein_history'],2026,'https://www.lh.or.kr/')
        self.assertEqual(len(rows),2);self.assertEqual(rows[0][2]['region'],'경기도')
        self.assertEqual(rows[1][2]['region'],'인천광역시')
        self.assertEqual(meta['region_counts'],{'경기도':1,'인천광역시':1})
        self.assertEqual(rows[0][2]['source_date'],'2026-12');self.assertIn('PLAN_NOT_ACTUAL',rows[0][2]['warnings'])
        self.assertIn('SOURCE_TOTAL_MISMATCH',rows[0][2]['warnings']);self.assertEqual(meta['national_detail_units'],600)
        self.assertFalse(meta['summary_matches_details'])

    def test_stock_preserves_historical_date_and_rejects_outside_address_despite_name(self):
        header=['지역본부','단지코드','단지명','세대수','동수','임대유형','주택유형','주소','준공일','입주지정시작일','입주지정종료일']
        stream=io.StringIO();w=csv.writer(stream);w.writerow(header)
        w.writerow(['인천지역본부','A1','부천원종','10','1','건설임대','행복주택','경기도 부천시 도로 1','2018-01-01','2018-02-01','2018-03-01'])
        w.writerow(['부산지역본부','A2','강서단지','20','1','건설임대','행복주택','부산광역시 강서구 도로 1','','',''])
        w.writerow(['서울지역본부','A3','공공리모델링(서울)','0','0','매입임대','기존주택매입임대','서울특별시 중구 서울시청 본관동','','',''])
        rows,meta=parse_stock(stream.getvalue().encode('cp949'),S['lh_stock'],'https://www.data.go.kr/','2026-08-10')
        self.assertEqual(len(rows),1);self.assertEqual(rows[0][2]['source_date'],'2018-02-01')
        self.assertEqual(rows[0][2]['dataset_version'],'2026-08-10');self.assertEqual(meta['historic_2018_2024_records'],1)
        self.assertIn('AGENCY_STOCK_NOT_SUPPLY',rows[0][2]['warnings'])

    def test_xlsx_with_inline_strings_needs_no_shared_strings_file(self):
        from backend.public_files import xlsx_rows
        b=io.BytesIO()
        with zipfile.ZipFile(b,'w') as z:z.writestr('xl/worksheets/sheet1.xml','<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row><c r="A1" t="inlineStr"><is><t>단지</t></is></c></row></sheetData></worksheet>')
        self.assertEqual(xlsx_rows(b.getvalue()),[{'A':'단지'}])

    def test_db_annual_counts_keep_permit_event_date_and_unknown_rows_without_loading_payloads(self):
        from datetime import date
        from sqlalchemy import create_engine
        from backend.db import Base,upsert_revision
        from backend.service import HomeService,today
        engine=create_engine('sqlite://');Base.metadata.create_all(engine);service=HomeService(engine)
        rows=[('P1','2020-01-01','2018-02-01'),('P2','2020-02-01',''),('P3',None,None),('P4','2026-12-01',None)]
        with service.sessions.begin() as session:
            for key,source,event in rows:
                upsert_revision(session,'permit','building_hub',key,dict(name=key,region='경기도',base_date=today().isoformat(),source_date=source,dates={'원천 허가일 (apprvDay)':event}),'fixture')
        counts=service.observation_year_counts('permit')
        self.assertEqual(dict(counts),{'2018':1,'2020':1,'':1,'2026':1})
        self.assertEqual(dict(service.observation_year_counts('permit',through=date(2026,10,3))),{'2018':1,'2020':1})
        self.assertEqual(dict(service.observation_year_counts('permit',q='P2')),{'2020':1})
        self.assertEqual(dict(service.observation_year_counts('permit',region='서울특별시')),{})
