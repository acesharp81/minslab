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
