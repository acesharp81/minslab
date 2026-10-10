import hashlib
import hmac
import io
import os
import tempfile
import time
import unittest
import zipfile
import httpx
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.pool import StaticPool

from backend.app import create_app
from backend.collectors import Fetcher, collect_lh_plan, parse_construction, parse_lh_plan, parse_policy
from backend.db import Audit, Base, Batch, Mapping, Revision, factory, upsert_revision
from backend.service import HomeService, today


def lh_html(rows, total=None):
    return '<h3>2026년 공급계획</h3><p class="bbs_total">전체 '+str(total or len(rows))+'건</p><div class="bbs_apply"><table><thead><tr><th>공급호수</th></tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+str(v)+'</td>' for v in row)+'</tr>' for row in rows)+'</tbody></table></div>'


def docx(rows):
    stream = io.BytesIO()
    xml = '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:tbl>'
    xml += ''.join('<w:tr>'+''.join('<w:tc><w:p><w:r><w:t>'+str(v)+'</w:t></w:r></w:p></w:tc>' for v in row)+'</w:tr>' for row in rows)
    xml += '</w:tbl></w:body></w:document>'
    with zipfile.ZipFile(stream, 'w') as archive:
        archive.writestr('word/document.xml', xml)
    return stream.getvalue()


class CollectorTests(unittest.TestCase):
    def test_fetch_preserves_source_type_and_lh_second_page(self):
        requests = []
        def respond(request):
            requests.append(request)
            params = request.url.params
            self.assertEqual(params['sUppAisTpCd'], '06')
            page = int(params['currPage']) if params['listCo'] == params.get('prevListCo') else 1
            rows = [['경기도','행복주택',f'사업{i}','36','10','2026년05월','2027년07월','경기','']
                    for i in range(100 if page == 1 else 28)]
            if page == 2:
                for row in rows:
                    row[2] += '-두번째'
            return httpx.Response(200, text=lh_html(rows,128))
        with tempfile.TemporaryDirectory() as raw:
            fetcher = Fetcher('lh_rent',raw)
            fetcher.client.close()
            fetcher.client = httpx.Client(transport=httpx.MockTransport(respond))
            try:
                records, stats = collect_lh_plan({'id':'lh_rent','url':'https://apply.lh.or.kr/lhapply/apply/noti/sp/list.do?sUppAisTpCd=06'},fetcher)
            finally:
                fetcher.close()
        self.assertEqual(len(requests),2)
        self.assertEqual(len(records),128)
        self.assertEqual(stats['raw_rows'],128)

    def test_lh_repeated_total_and_explicit_region(self):
        year, count, rows = parse_lh_plan(lh_html([
            ['공공분양','경기도','고양창릉 S01','494','59','371','2026년04월','경기북부',''],
            ['공공분양','경기도','고양창릉 S01','494','84','123','2026년04월','경기북부',''],
            ['공공분양','인천광역시','인천계양 A9','317','55','317','2026년04월','인천','']]))
        self.assertEqual((year,count),(2026,3))
        from backend.collectors import collect_lh_plan
        class Fetch:
            def get(self,*args,**kwargs):
                return lh_html([
                    ['공공분양','경기도','고양창릉 S01','494','59','371','2026년04월','경기북부',''],
                    ['공공분양','경기도','고양창릉 S01','494','84','123','2026년04월','경기북부',''],
                    ['공공분양','인천광역시','인천계양 A9','317','55','317','2026년04월','인천','']])
        records, stats = collect_lh_plan({'id':'lh_sale','url':'https://apply.lh.or.kr/'},Fetch())
        self.assertEqual(len(records),1)
        self.assertEqual(records[0][2]['planned_units'],494)
        self.assertEqual(records[0][2]['supply_units'],494)
        self.assertEqual(stats['excluded_rows'],1)
        self.assertEqual(records[0][2]['stage'],'PLANNED_SUPPLY')

    def test_corrupt_schema_does_not_parse_as_empty_success(self):
        with self.assertRaises(ValueError):
            parse_lh_plan('<h1>접근 차단</h1>')

    def test_hq_is_not_region_and_contract_end_is_not_actual_completion(self):
        sample = [
            ['서울지역본부','성남','건축','A1','성남복정','성남복정 A1 건설','회사','100','500','호','26-02-01','28-12-31','10'],
            ['서울지역본부','위례','건축','A2','위례','위례 A2 건설','회사','100','100','호','26-02-01','28-12-31','20']]
        records, stats = parse_construction(docx(sample),'2026-07-01')
        self.assertEqual(len(records),1)
        self.assertEqual(records[0][2]['region'],'경기도')
        self.assertEqual(stats['excluded_ambiguous_region'],1)
        self.assertEqual(records[0][2]['stage'],'CONSTRUCTION')
        self.assertNotIn('completion_actual_date',records[0][2])

    def test_policy_quantities_are_extracted_without_guessed_dates(self):
        content = '<div class="view_cont">도심 주택공급 확대 및 신속화 방안 총 6만호. '+('공식 설명 '*30)+' 광명경찰서 부지 550호, 남양주 군부지 4,180호.</div>'
        rows, stats = parse_policy('policy_129',content)
        projects = [r[2] for r in rows if r[0]=='project']
        self.assertEqual([p['planned_units'] for p in projects],[550,4180])
        self.assertTrue(all(p['schedule_month'] is None for p in projects))


class StorageApiTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.directory = tempfile.TemporaryDirectory()
        self.service = HomeService(self.engine,self.directory.name)
        with self.service.sessions.begin() as session:
            p,_=upsert_revision(session,'policy','policy_129','POL_2026_0129',{'id':'POL_2026_0129','name':'정책','base_date':today().isoformat()},'batch')
            self.payload={'name':'서울 사업','region':'서울특별시','municipality':'용산구','program':'공공주택','planned_units':100,
                'stage':'PLANNING','stage_label':'계획','base_date':today().isoformat(),'warnings':[], 'proposed_policy':'POL_2026_0129',
                'mapping_basis':'공식 원문','evidence_url':'https://www.korea.kr/','availability':'PUBLIC'}
            r,_=upsert_revision(session,'project','policy_129','project',self.payload,'batch')
            self.project_id=r.entity_id
            session.add(Mapping(project_id=r.entity_id,policy_id='POL_2026_0129',status='REVIEW',basis='공식 원문',evidence_url='https://www.korea.kr/'))
        self.app=create_app(self.engine,auto_collect=False)
        self.client=TestClient(self.app)

    def tearDown(self):
        self.client.close()
        self.engine.dispose()
        self.directory.cleanup()

    def test_recollection_is_idempotent_and_revision_keeps_history(self):
        with self.service.sessions.begin() as session:
            row,outcome=upsert_revision(session,'project','policy_129','project',self.payload,'second')
            self.assertEqual(outcome,'unchanged')
            row,outcome=upsert_revision(session,'project','policy_129','project',dict(self.payload,planned_units=120),'third')
            self.assertEqual(outcome,'changed')
        with self.service.sessions() as session:
            rows=session.scalars(select(Revision).where(Revision.entity_id==self.project_id).order_by(Revision.revision_no)).all()
            self.assertEqual([r.payload['planned_units'] for r in rows],[100,120])
            self.assertIsNotNone(rows[0].superseded_at)

    def test_failed_collector_preserves_last_success(self):
        source={'id':'policy_129','url':'https://www.korea.kr/'}
        with patch('backend.service.collect',side_effect=ValueError('schema 변경')):
            result=self.service.collect_one(source)
        self.assertEqual(result['status'],'FAILED')
        self.assertEqual(self.service.projects()[0]['planned_units'],100)

    def test_api_filter_scope_and_unknown_fields(self):
        response=self.client.get('/poc/home/api/projects?region=경기도')
        self.assertEqual(response.json()['total'],0)
        self.assertEqual(self.client.get('/poc/home/api/projects?region=인천광역시').status_code,400)
        self.assertEqual(self.client.get('/poc/home/api/projects?q=서울').json()['total'],1)
        self.assertEqual(self.client.get('/poc/home/api/projects?as_of_date=2099-01-01').status_code,400)

    def test_review_records_not_in_official_supply_total(self):
        data=self.client.get('/poc/home/api/overview').json()
        self.assertEqual(data['review_count'],1)
        self.assertIsNone(data['official_total_units'])
        self.assertEqual(data['baseline_status'],'DRAFT')

    def test_mapping_optimistic_lock_and_audit(self):
        result=self.service.confirm_mapping(self.project_id,'POL_2026_0129',1,'CONFIRMED','공식 공개 근거','https://www.korea.kr/')
        self.assertEqual(result['revision_no'],2)
        self.assertTrue(self.service.confirm_mapping(self.project_id,'POL_2026_0129',1,'REVIEW','근거','https://www.korea.kr/')['conflict'])
        with self.service.sessions() as session:
            self.assertEqual(len(session.scalars(select(Audit)).all()),1)

    def test_public_write_and_forged_auth_rejected(self):
        self.assertEqual(self.client.post('/poc/home/api/admin/refresh').status_code,401)
        self.assertEqual(self.client.post('/poc/home/api/admin/refresh',headers={'x-home-admin':'forged'}).status_code,401)
        self.assertEqual(self.client.post('/poc/home/api/projects').status_code,405)

    def test_real_signature_and_replay_window(self):
        payload={'policy_id':'POL_2026_0129','revision_no':1,'status':'CONFIRMED','basis':'공식 공개 근거','evidence_url':'https://www.korea.kr/'}
        path='/poc/home/api/admin/mappings/'+self.project_id
        with patch.dict(os.environ,{'POC10_INTERNAL_SECRET':'test-home-secret'}):
            stamp=str(int(time.time()))
            signature=hmac.new(b'test-home-secret',f'{stamp}:POST:{path}'.encode(),hashlib.sha256).hexdigest()
            response=self.client.post(path,json=payload,headers={'x-home-admin':stamp+':'+signature})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['status'],'CONFIRMED')

    def test_historical_record_is_not_invented_before_collection(self):
        old=(today()-timedelta(days=1)).isoformat()
        data=self.client.get('/poc/home/api/projects?as_of_date='+old).json()
        self.assertEqual(data['total'],0)

    def test_historical_detail_hides_later_data_and_mapping_changes(self):
        old = today()-timedelta(days=1)
        recorded = datetime.combine(old, datetime.min.time(), timezone.utc)
        old_payload = dict(self.payload,base_date=old.isoformat())
        with self.service.sessions.begin() as session:
            original = session.scalar(select(Revision).where(Revision.entity_id==self.project_id))
            original.recorded_at = recorded
            original.payload = old_payload
            upsert_revision(session,'project','policy_129','project',dict(old_payload,planned_units=120),'new')
        self.service.confirm_mapping(self.project_id,'POL_2026_0129',1,'CONFIRMED','수정 근거','https://www.korea.kr/')
        past = self.client.get('/poc/home/api/projects/'+self.project_id+'?as_of_date='+old.isoformat()).json()
        self.assertEqual(past['planned_units'],100)
        self.assertEqual(past['mapping']['status'],'REVIEW')
        self.assertEqual(len(past['history']),1)
        self.assertIsNone(past['history'][0]['superseded_at'])
        self.assertEqual(self.client.get('/poc/home/api/projects/'+self.project_id).json()['planned_units'],120)

    def test_unknown_supply_units_are_not_zero(self):
        class Fetch:
            def get(self,*args,**kwargs):
                return lh_html([['경기도','행복주택','미정 사업','36','미정','2026년05월','2027년07월','경기','']])
        records, _ = collect_lh_plan({'id':'lh_rent','url':'https://apply.lh.or.kr/'},Fetch())
        self.assertIsNone(records[0][2]['supply_units'])
        self.assertIsNone(records[0][2]['planned_units'])

    def test_csv_and_provenance_and_no_secret_exposure(self):
        response=self.client.get('/poc/home/api/export.csv')
        self.assertIn('서울 사업',response.text)
        data=self.client.get('/poc/home/api/projects/'+self.project_id).json()
        self.assertEqual(data['history'][0]['revision_no'],1)
        with patch.dict(os.environ,{'POC10_BUILDING_HUB_SERVICE_KEY':'sensitive-test-value'}):
            response=self.client.get('/poc/home/api/sources')
        self.assertNotIn('sensitive-test-value',response.text)
        self.assertEqual(self.client.get('/poc/home/.env').status_code,404)
        self.assertEqual(self.client.get('/poc/home/data/raw/anything').status_code,404)
