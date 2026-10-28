from copy import deepcopy
import hashlib,hmac,time
from unittest.mock import patch
import pytest
from sqlalchemy import create_engine,select,func
from sqlalchemy.pool import StaticPool
from backend.db import Base,Revision,Mapping,Audit,upsert_revision
from backend.service import HomeService
from backend import publication_reviews as reviews

POLICIES=[dict(policy_id='POL_TEST',name='검토 정책',monitor_kind='POLICY')]

@pytest.fixture
def env(tmp_path):
 e=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool);Base.metadata.create_all(e)
 s=HomeService(e,tmp_path)
 with s.sessions.begin() as db:
  doc,_=upsert_revision(db,'document_evidence','seoul_press_watch','case',dict(name='서울시, 면목·사당 모아주택 2,121세대 2027년 착공 추진',source_date='2026-10-23',evidence_url='https://www.seoul.go.kr/example',facts=[],units=None),'seed')
  project,_=upsert_revision(db,'project','test','p',dict(name='면목 후보',planned_units=100,region='서울특별시'),'seed')
  db.add(Mapping(project_id=project.entity_id,policy_id='POL_TEST',status='REVIEW',basis='이전 검토 사유',evidence_url='https://seoul.go.kr/a'))
 with patch.object(HomeService,'mapping_policies',return_value=POLICIES):yield s,doc.entity_id,project.entity_id
 e.dispose()

def approve(s,doc,pid,**kwargs):
 payload=dict(document_id=doc,source_revision_no=1,review_revision_no=0,status='APPROVED',policy_id='POL_TEST',project_ids=[pid],new_project_names=[],actor='시험 담당자',reason='원문과 동일 구역을 확인했습니다.',source_checked=True)
 payload.update(kwargs);return reviews.save(s,**payload)


def test_discovery_is_visible_without_prior_mutation_and_candidate_not_preapproved(env):
 s,doc,pid=env
 with s.sessions() as db:before=db.scalar(select(func.count()).select_from(Revision))
 q=reviews.queue(s);r=q['items'][0]
 assert q['pending']==1 and r['status']=='REVIEW' and r['priority']==1
 assert r['review_revision_no']==0 and r['candidates'][0]['id']==pid
 assert r['candidates'][0]['mapping_basis']=='이전 검토 사유'
 assert r['decision'] is None
 with s.sessions() as db:assert before==db.scalar(select(func.count()).select_from(Revision))


def test_manual_collection_preserves_decision_and_exports_revision_scope(env):
 from backend.publication_supplements import save as collect_text
 from backend.publication_review_export import export_csv
 s,doc,pid=env
 approve(s,doc,pid)
 with s.sessions() as db:
  before=[(r.entity_id,r.payload_hash) for r in db.scalars(select(Revision).where(Revision.kind.in_(['project','publication_review','evidence_bridge']),Revision.superseded_at.is_(None)).order_by(Revision.entity_id))]
 collect_text(s,doc,1,'공식 본문 12호','재모집12호 · 신규 건설 아님',
   [{'name':'공고문.pdf','url':'https://www.seoul.go.kr/notice.pdf','sha256':'b'*64}], '수집 점검','a'*64)
 item=reviews.queue(s)['items'][0]
 assert item['status']=='APPROVED' and not item['supplement']['stale']
 assert 'body_text' not in item['supplement']
 row,=csv_rows(export_csv(s))
 assert row['수동수집본문']=='공식 본문 12호' and row['수동수집상태']=='현재 판본 원문·첨부 수집'
 with s.sessions() as db:
  after=[(r.entity_id,r.payload_hash) for r in db.scalars(select(Revision).where(Revision.kind.in_(['project','publication_review','evidence_bridge']),Revision.superseded_at.is_(None)).order_by(Revision.entity_id))]
 assert before==after
 with s.sessions.begin() as db:
  old=db.scalar(select(Revision).where(Revision.entity_id==doc,Revision.superseded_at.is_(None)))
  upsert_revision(db,'document_evidence','seoul_press_watch','case',dict(old.payload,name='변경된 주택 공고'),'next')
 assert reviews.queue(s)['items'][0]['supplement']['stale']
 row,=csv_rows(export_csv(s));assert row['수동수집상태']=='이전 판본 수집 · 재확인 필요'
 with pytest.raises(ValueError,match='판본'):
  collect_text(s,doc,1,'old','old',[],'수집 점검','a'*64)


def test_sh_notices_are_visible_with_correction_and_followup_review_questions(env):
 s,doc,pid=env
 with s.sessions.begin() as db:
  for key,title in [('sh1','[정정공고] 고덕강일지구 3단지 토지임대부 분양주택'),('sh2','제50차 장기전세주택 당첨자 발표')]:
   upsert_revision(db,'document_evidence','sh_notice_watch',key,dict(name=title,source_date='2026-10-27',evidence_url='https://www.i-sh.co.kr/main/',facts=[],units=None),'seed')
 q=reviews.queue(s)
 assert q['pending']==3
 from backend.publication_review_guidance import guidance
 correction=guidance('[정정공고] 고덕강일지구 3단지 토지임대부 분양주택',[],2)
 followup=guidance('제50차 장기전세주택 당첨자 발표',[],3)
 assert '무엇이 바뀌었나요' in correction['decision']
 assert '후속 안내' in followup['decision']


def test_approval_pins_document_creates_empty_fact_bridge_and_keeps_mapping(env):
 s,doc,pid=env
 with s.sessions() as db:
  before=db.scalar(select(Revision).where(Revision.entity_id==pid)).payload_hash
 approve(s,doc,pid)
 q=reviews.queue(s);assert q['pending']==0 and q['counts']['APPROVED']==1
 with s.sessions() as db:
  bridge=db.scalar(select(Revision).where(Revision.kind=='evidence_bridge',Revision.superseded_at.is_(None)))
  assert bridge.payload['status']=='CONFIRMED' and bridge.payload['facts']==[] and bridge.payload['units'] is None
  assert bridge.payload['source_revision_no']==1 and bridge.payload['source_entity_id']==doc
  assert db.scalar(select(Mapping)).status=='REVIEW'
  assert db.scalar(select(Revision).where(Revision.entity_id==pid)).payload_hash==before
  assert db.scalar(select(func.count()).select_from(Audit))==1
 assert reviews.history(s,doc)[0]['actor']=='시험 담당자'


def test_new_project_approval_remains_in_incomplete_queue_and_no_fake_project(env):
 s,doc,pid=env
 approve(s,doc,pid,status='REGISTRATION_REQUIRED',project_ids=[],new_project_names=['면목 실제 구역','사당 실제 구역'])
 q=reviews.queue(s);assert q['pending']==1 and q['counts']['REGISTRATION_REQUIRED']==1
 with s.sessions() as db:
  assert db.scalar(select(func.count()).select_from(Revision).where(Revision.kind=='project'))==1
  assert db.scalar(select(func.count()).select_from(Revision).where(Revision.kind=='evidence_bridge'))==0


def test_document_can_be_linked_without_assigning_a_policy(env):
 s,doc,pid=env
 result=approve(s,doc,pid,policy_id='UNASSIGNED')
 assert result['status']=='APPROVED' and result['policy_id']=='UNASSIGNED'
 assert reviews.queue(s)['pending']==0
 with s.sessions() as db:
  mapping=db.scalar(select(Mapping))
  assert mapping.policy_id=='POL_TEST' and mapping.status=='REVIEW'
  bridge=db.scalar(select(Revision).where(Revision.kind=='evidence_bridge',Revision.superseded_at.is_(None)))
  assert bridge.payload['status']=='CONFIRMED' and bridge.payload['facts']==[]
 result=approve(s,doc,pid,status='REGISTRATION_REQUIRED',policy_id='UNASSIGNED',project_ids=[],new_project_names=['신규 사업'],review_revision_no=1)
 assert result['status']=='REGISTRATION_REQUIRED' and result['policy_id']=='UNASSIGNED'
 with s.sessions() as db:
  assert db.scalar(select(func.count()).select_from(Revision).where(Revision.kind=='project'))==1
  assert db.scalar(select(Mapping)).policy_id=='POL_TEST'
  bridge=db.scalar(select(Revision).where(Revision.kind=='evidence_bridge',Revision.superseded_at.is_(None)))
  assert bridge.payload['status']=='RELEASED' and bridge.payload['facts']==[]


@pytest.mark.parametrize('changes',[
 dict(source_checked=False),dict(policy_id=None),dict(policy_id='FAKE'),dict(project_ids=[]),dict(project_ids=['missing']),
 dict(new_project_names=['new']),dict(actor=' '),dict(reason=' '),dict(status='REGISTRATION_REQUIRED',new_project_names=[]),dict(status='UNKNOWN')])
def test_invalid_approval_does_not_write(env,changes):
 s,doc,pid=env
 with pytest.raises(ValueError):approve(s,doc,pid,**changes)
 assert reviews.history(s,doc)==[]


def test_repeat_click_and_stale_source_conflict_and_new_source_reopens_queue(env):
 s,doc,pid=env
 approve(s,doc,pid)
 assert approve(s,doc,pid)['conflict']
 with s.sessions.begin() as db:
  row=db.scalar(select(Revision).where(Revision.entity_id==doc,Revision.superseded_at.is_(None)))
  upsert_revision(db,'document_evidence','seoul_press_watch','case',dict(row.payload,name='원문 정정 · 면목·사당'), 'update')
 assert approve(s,doc,pid,review_revision_no=1)['conflict']
 q=reviews.queue(s);assert q['items'][0]['source_changed'] and q['items'][0]['status']=='REVIEW' and q['pending']==1
 assert reviews.history(s,doc)[0]['status']=='APPROVED'


def test_withdrawal_releases_only_this_review_owned_bridge_and_keeps_history(env):
 s,doc,pid=env
 approve(s,doc,pid)
 approve(s,doc,pid,review_revision_no=1,status='HOLD',reason='범위를 추가로 확인해야 합니다.')
 with s.sessions() as db:
  r=db.scalar(select(Revision).where(Revision.kind=='evidence_bridge',Revision.superseded_at.is_(None)))
  assert r.payload['status']=='RELEASED'
 assert len(reviews.history(s,doc))==2 and reviews.queue(s)['pending']==1


def test_preexisting_bridge_facts_are_not_overwritten(env):
 s,doc,pid=env
 with s.sessions.begin() as db:
  upsert_revision(db,'evidence_bridge','cross_source',pid+':'+doc,dict(project_id=pid,source_entity_id=doc,status='CONFIRMED',facts=[{'units':100}]),'existing')
 approve(s,doc,pid)
 approve(s,doc,pid,review_revision_no=1,status='EXCLUDED',reason='다른 범위 자료로 검토 제외')
 with s.sessions() as db:
  r=db.scalar(select(Revision).where(Revision.kind=='evidence_bridge',Revision.superseded_at.is_(None)))
  assert r.payload['facts']==[{'units':100}] and r.revision_no==1


def test_api_guest_read_admin_save_and_409(env,monkeypatch):
 from fastapi.testclient import TestClient
 from backend.app import create_app
 s,doc,pid=env;monkeypatch.setenv('POC10_INTERNAL_SECRET','review-test');monkeypatch.setenv('POC10_DATA_DIR',str(s.data_dir))
 path='/poc/home/api/admin/publication-reviews/'+doc
 payload=dict(source_revision_no=1,review_revision_no=0,status='HOLD',policy_id=None,project_ids=[],new_project_names=[],actor='시험 담당자',reason='추가 공식 자료 확인이 필요합니다.',source_checked=False)
 with TestClient(create_app(s.engine,auto_collect=False)) as client:
  assert client.get('/poc/home/api/publication-reviews').status_code==200
  assert client.get('/poc/home/api/publication-reviews/summary').json()['pending']==1
  assert client.post(path,json=payload).status_code==401
  stamp=str(int(time.time()));signature=hmac.new(b'review-test',f'{stamp}:POST:{path}'.encode(),hashlib.sha256).hexdigest();headers={'x-home-admin':stamp+':'+signature}
  assert client.post(path,json=payload,headers=headers).status_code==200
  assert client.post(path,json=payload,headers=headers).status_code==409
  assert client.get('/poc/home/api/publication-reviews/'+doc+'/history').json()['items'][0]['status']=='HOLD'


def test_general_articles_do_not_get_business_priority():
 assert reviews.triage('주거복지 교육 성료')['priority']==4
 assert reviews.triage('전력망 준공 지연')['priority']==4


def test_link_released_in_other_screen_reopens_review(env):
 from backend.evidence_bridge import review
 s,doc,pid=env;approve(s,doc,pid)
 with s.sessions() as db:
  b=db.scalar(select(Revision).where(Revision.kind=='evidence_bridge',Revision.superseded_at.is_(None)))
 review(s,b.entity_id,b.revision_no,'RELEASED','다른 화면에서 범위 불일치 확인')
 q=reviews.queue(s)
 assert q['items'][0]['link_changed'] and q['items'][0]['status']=='REVIEW' and q['pending']==1


def test_review_instructions_explain_pending_decision_without_claiming_verified_facts(env):
 s,doc,pid=env
 row=reviews.queue(s)['items'][0]
 assert row['guidance']['decision']=='면목·사당의 해당 구역은 기존 사업인가요, 새로 등록을 검토할 사업인가요?'
 assert '담당자 확인 전' in row['guidance']['basis']
 assert row['guidance']['comparison_status']=='NAME_CANDIDATES_ONLY'
 assert len(row['guidance']['checks'])==3
 assert row['candidates'][0]['policy_name']=='검토 정책'
 assert '실제 착공' in row['guidance']['event']
 assert reviews.queue(s,include_options=False)['items'][0]['guidance'] is None


def test_seongbuk_notice_does_not_suggest_unrelated_suseo_projects(env):
 s,doc,pid=env
 with s.sessions.begin() as db:
  upsert_revision(db,'document_evidence','seoul_press_watch','case',dict(name='성북동 3-38일대 신속통합기획 확정',source_date='2026-10-23',evidence_url='https://www.seoul.go.kr/example'),'changed')
  upsert_revision(db,'project','test','suseo',dict(name='수서 노후 임대 재건축',planned_units=3899),'seed')
 row=reviews.queue(s)['items'][0]
 assert not row['candidates']
 assert row['guidance']['comparison_status']=='NO_NAME_CANDIDATE'
 assert '성북동' in row['guidance']['decision']
 assert '주소·별칭' in row['guidance']['dataset_summary']


@pytest.mark.parametrize('title,question,event',[
 ('제물포역 북측 이주율 90.8% 연내 착공 청신호','같은 구역','이주'),
 ('인천구월2 보상 본격 착수','개별 블록','보상'),
 ('신길4·녹번동근린공원·송중동 본궤도','이전 보류','도심복합'),
 ('수서택지 4개단지 재건축 자문','대상 단지','자문'),
 ('시흥거모 S-1 공공분양 300호 공급','같은 공고','공급'),
 ('주거복지 교육 성료','특정 주택사업','관련성'),
 ('새로운 일반 공고','특정 주택사업','확인 필요'),
])
def test_review_guide_asks_source_specific_questions(title,question,event):
 from backend.publication_review_guidance import guidance
 g=guidance(title,[],reviews.triage(title)['priority'])
 assert question in g['decision']
 assert event in g['event']
 assert len(g['checks'])==3 and g['reason_hint'] and g['next_step']
 assert '본문' in g['basis']


def csv_rows(content):
 import csv,io
 assert content.startswith('\ufeff')
 return list(csv.DictReader(io.StringIO(content.lstrip('\ufeff'))))


@pytest.mark.parametrize('status', ['REVIEW','HOLD','REGISTRATION_REQUIRED','APPROVED','EXCLUDED'])
def test_csv_each_status_has_evidence_and_preserves_decisions(env,status):
 import json
 from backend.publication_review_export import export_csv
 s,doc,pid=env
 if status!='REVIEW':
  approve(s,doc,pid,status=status,new_project_names=['면목 실제 구역'] if status=='REGISTRATION_REQUIRED' else [])
 with s.sessions() as db:
  before=[(r.id,r.payload_hash) for r in db.scalars(select(Revision).order_by(Revision.id))]
  audits=db.scalar(select(func.count()).select_from(Audit))
 row,=csv_rows(export_csv(s,status=status))
 assert row['현재상태코드']==status and row['자료ID']==doc
 assert row['원문URL']=='https://www.seoul.go.kr/example' and row['원문해시']
 assert row['본문보유여부'].startswith('미보유') and row['수집본문']==''
 assert json.loads(row['이름유사후보_동일사업미확정_JSON'])[0]['mapping_basis']=='이전 검토 사유'
 assert row['외부검증결과']==row['외부검증사유']==row['추가확인사항']==''
 if status!='REVIEW':
  assert row['검토사유']=='원문과 동일 구역을 확인했습니다.'
  assert json.loads(row['검토이력_JSON'])[0]['status']==status
  assert json.loads(row['선택사업_현재등록정보_JSON'])[0]['id']==pid
 else: assert json.loads(row['검토이력_JSON'])==[]
 assert len(csv_rows(export_csv(s,status='OPEN')))==int(status in ('REVIEW','HOLD','REGISTRATION_REQUIRED'))
 assert csv_rows(export_csv(s,status='APPROVED' if status!='APPROVED' else 'HOLD'))==[]
 assert len(csv_rows(export_csv(s,priority=1,search='면목')))==1
 assert not csv_rows(export_csv(s,priority=4)) and not csv_rows(export_csv(s,search='없는 자료'))
 with s.sessions() as db:
  assert before==[(r.id,r.payload_hash) for r in db.scalars(select(Revision).order_by(Revision.id))]
  assert audits==db.scalar(select(func.count()).select_from(Audit))


def test_csv_separates_reopened_status_and_prior_decision_and_escapes_formulas(env):
 import json
 from backend.publication_review_export import export_csv
 s,doc,pid=env
 reason='=검토식, "인용"\n둘째 줄 근거'
 approve(s,doc,pid,reason=reason)
 with s.sessions.begin() as db:
  old=db.scalar(select(Revision).where(Revision.entity_id==doc,Revision.superseded_at.is_(None)))
  upsert_revision(db,'document_evidence','seoul_press_watch','case',dict(old.payload,text='본문, "근거"\n확인',name='면목 정정'),'update')
 row,=csv_rows(export_csv(s,status='REVIEW'))
 assert row['현재상태코드']=='REVIEW' and row['최근저장판단코드']=='APPROVED'
 assert row['원문변경_재검토필요']=='예' and row['원문판본']=='2' and row['검토당시원문판본']=='1'
 assert row['검토사유']=="'"+reason
 assert row['수집본문']=='본문, "근거"\n확인'
 assert json.loads(row['검토이력_JSON'])[0]['reason']==reason
 assert not csv_rows(export_csv(s,status='APPROVED'))


def test_csv_api_download_empty_headers_and_validation(env,monkeypatch):
 from fastapi.testclient import TestClient
 from backend.app import create_app
 s,doc,pid=env;monkeypatch.setenv('POC10_DATA_DIR',str(s.data_dir))
 with TestClient(create_app(s.engine,auto_collect=False)) as client:
  base='/poc/home/api/publication-reviews/export.csv'
  response=client.get(base,params={'status':'REVIEW'})
  assert response.status_code==200 and response.content.startswith(b'\xef\xbb\xbf')
  assert response.headers['content-type'].startswith('text/csv')
  assert 'attachment;' in response.headers['content-disposition'] and '-REVIEW-' in response.headers['content-disposition']
  assert response.headers['cache-control']=='no-store'
  assert len(csv_rows(response.text))==1
  response=client.get(base,params={'status':'EXCLUDED'})
  assert response.status_code==200 and csv_rows(response.text)==[] and '현재상태코드' in response.text
  for params in ({'status':'invalid'},{'priority':0},{'priority':5},{'search':'x'*501}):
   assert client.get(base,params=params).status_code==422
