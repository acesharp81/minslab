import csv
import io
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from backend.collection_exports import export, HEADERS, STAGES
from backend.collection_schema import build
from backend.source_authority import authority, public_url

class ExportTests(unittest.TestCase):
    def fixture(self):
        p=dict(id='p',name='=FORMULA()',planned_units=8,region='서울특별시',municipality='마포구',
               tenure='국민임대',source_id='lh_sale',evidence_url='https://lh.or.kr/a',mapping={'program_id':'prg'},
               metadata={'secret':'must-remove','public':'보존'})
        cells={k:dict(sources=[],management={'target':[],'measurement':[]},status='ACQUIRED') for k in STAGES if k!='COMPLETION'}
        cells['CONSTRUCTION']['sources']=[dict(kind='ACTUAL',date='2024-01-01',units=0,milestone='CONSTRUCTION',
            source_id='press',source_entity_id='doc',evidence_url='https://news.example/a?serviceKey=secret&id=1',review_status='CONFIRMED'),
            dict(kind='ACTUAL',date='2026-01-01',units=8,milestone='COMPLETION',source_id='lh_sale',source_entity_id='doc2',evidence_url='https://lh.or.kr/a')]
        matrix={'as_of_date':'2026-10-22','items':[dict(id='p',name=p['name'],region=p['region'],policy_id='pol',policy_name='정책',program='프로그램',cells=cells)]}
        service=SimpleNamespace(projects=lambda **_: [p],policy_rows=lambda _:[],rows=lambda kind,*args:[p] if kind=='project' else [])
        return service,matrix
    def test_dataset_preserves_all_stages_null_zero_supply_type_and_provenance(self):
        service,matrix=self.fixture();text=export(service,matrix)
        raw=list(csv.reader(io.StringIO(text.lstrip('\ufeff'))))
        self.assertTrue(all(len(row)==len(HEADERS) for row in raw))
        rows=list(csv.DictReader(io.StringIO(text.lstrip('\ufeff'))))
        self.assertEqual({r['세부단계'] for r in rows},set(STAGES))
        start=next(r for r in rows if r['세부단계']=='CONSTRUCTION');complete=next(r for r in rows if r['세부단계']=='COMPLETION')
        self.assertEqual(start['호수'],'0');self.assertEqual(complete['호수'],'8')
        self.assertEqual(start['출처구분'],'비공식 출처');self.assertEqual(start['연결확인상태'],'CONFIRMED')
        self.assertEqual(sum(bool(r['사업메타정보JSON']) for r in rows),1)
        self.assertEqual(start['공급형태'],'국민임대');self.assertEqual(start['사업명'],"'=FORMULA()")
        self.assertNotIn('must-remove',text);self.assertNotIn('serviceKey',text)
        self.assertEqual(next(r for r in rows if r['세부단계']=='MOVE_IN')['호수'],'')
    def test_schema_counts_unique_source_records_and_excludes_officer_estimates(self):
        service,matrix=self.fixture();source=matrix['items'][0]['cells']['CONSTRUCTION']['sources'][0]
        matrix['items'][0]['cells']['CONSTRUCTION']['sources'] += [dict(source),dict(source,source_id='officer',units=999,inferred=True)]
        with patch('backend.collection_schema.document_sources',return_value=[]):data=build(service,matrix)
        stage=next(r for r in data['stages'] if r['id']=='CONSTRUCTION')
        units=next(f for f in stage['fields'] if f['field']=='units')
        self.assertEqual(units['sources'][0]['count'],1)
        self.assertTrue(all(s['source_id']!='officer' for f in stage['fields'] for s in f['sources']))
    def test_external_source_names_use_publisher_not_internal_review_code(self):
        from backend.source_authority import publisher_name
        service,matrix=self.fixture()
        row=matrix['items'][0]['cells']['CONSTRUCTION']['sources'][0]
        row.update(source_id='external_officer',name='external_officer',evidence_url='https://nwww.newsis.com/view/a')
        with patch('backend.collection_schema.document_sources',return_value=[]):data=build(service,matrix)
        actual=[s for stage in data['stages'] for field in stage['fields'] for s in field['sources'] if s['source_id']=='external_officer']
        self.assertTrue(actual)
        self.assertEqual({s['name'] for s in actual},{'뉴시스'})
        self.assertEqual({s['authority'] for s in actual},{'NONOFFICIAL'})
        self.assertEqual(publisher_name('https://newsis.com.evil.test/a'),'newsis.com.evil.test')
        self.assertEqual(publisher_name('https://xn--3-3u6ey6lv7rsa.kr/a'),'3기신도시.kr')
        self.assertEqual(publisher_name('', 'external_official'),'출처 확인 필요')

    def test_authority_follows_publisher_not_confirmation_or_deceptive_hostname(self):
        self.assertEqual(authority('https://www.lh.or.kr/a'),'OFFICIAL')
        self.assertEqual(authority('https://mas.smc.seoul.kr/a.pdf'),'OFFICIAL')
        self.assertEqual(authority('https://mas.smc.seoul.kr.evil.test/a'),'NONOFFICIAL')
        self.assertEqual(authority('https://lh.or.kr.evil.test/a'),'NONOFFICIAL')
        self.assertEqual(authority('https://news.test/a','officer'),'NONOFFICIAL')
        self.assertEqual(authority('https://lh.or.kr/a','officer',True),'INTERNAL')
        self.assertEqual(public_url('javascript:alert(1)'),'')

if __name__=='__main__':unittest.main()

class EndpointTests(unittest.TestCase):
    def test_download_filters_scope_and_preserves_empty_scope(self):
        from fastapi.testclient import TestClient
        from sqlalchemy import create_engine
        from sqlalchemy.pool import StaticPool
        from backend.db import Base
        from backend.app import create_app
        from backend.service import HomeService
        from datetime import date
        engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
        Base.metadata.create_all(engine)
        service,matrix=ExportTests().fixture()
        client=TestClient(create_app(engine,auto_collect=False))
        try:
            with patch('backend.project_collection.collection_matrix',return_value=matrix) as builder, patch.object(HomeService,'projects',return_value=service.projects()):
                response=client.get('/poc/home/api/project-collection/dataset.csv?policy_id=pol&region=서울특別시&q=test&as_of_date=2024-01-01')
                self.assertEqual(response.status_code,400)
                response=client.get('/poc/home/api/project-collection/dataset.csv?policy_id=pol&region=서울특별시&q=test&as_of_date=2024-01-01')
                self.assertEqual(response.status_code,200)
                self.assertIn('attachment',response.headers['content-disposition'])
                self.assertEqual(builder.call_args.kwargs['as_of'],date(2024,1,1))
                self.assertEqual(builder.call_args.kwargs['region'],'서울특별시')
                self.assertEqual(builder.call_args.kwargs['q'],'test')
                rows=list(csv.DictReader(io.StringIO(response.text.lstrip('\ufeff'))))
                self.assertEqual({r['사업ID'] for r in rows},{'p'})
                response=client.get('/poc/home/api/project-collection/dataset.csv?collection_status=LINK_REQUIRED')
                self.assertEqual(len(list(csv.reader(io.StringIO(response.text.lstrip('\ufeff'))))),1)
        finally:
            client.close();engine.dispose()

    def test_document_publisher_grouping_is_independent_of_policy_link(self):
        from sqlalchemy import create_engine
        from sqlalchemy.pool import StaticPool
        from backend.db import Base,upsert_revision
        from backend.service import HomeService
        from backend.collection_schema import document_sources
        engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
        Base.metadata.create_all(engine);service=HomeService(engine)
        try:
            with service.sessions.begin() as db:
                upsert_revision(db,'document_evidence','official_document','a',{'evidence_url':'https://www.lh.or.kr/a'},'test')
                upsert_revision(db,'document_evidence','official_document','b',{'evidence_url':'https://news.example/b','status':'REVIEW'},'test')
                upsert_revision(db,'document_evidence','official_document','c',{'evidence_url':'https://news.example/c','status':'CONFIRMED'},'test')
            groups=document_sources(service)
            self.assertEqual([g['authority'] for g in groups],['OFFICIAL','NONOFFICIAL'])
            self.assertEqual([g['record_count'] for g in groups],[1,2])
        finally:engine.dispose()
