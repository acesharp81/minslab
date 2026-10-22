from copy import deepcopy
from datetime import date
import hashlib
import json
import pytest
from sqlalchemy import create_engine,select,func
from backend.db import Base,Mapping,Audit,Revision,upsert_revision
from backend.service import HomeService
from scripts.review_external_stage_events_20261020 import apply,repair_waitlist,BATCH
from backend.lh_notice_detail import parse_detail
from tests.test_lh_notice_detail import HTML,NOTICE,KEY
from tests.test_policy_delivery import FakeService
from backend.policy_delivery import build_delivery


def fixture(tmp_path):
    e=create_engine('sqlite://');Base.metadata.create_all(e);s=HomeService(e,tmp_path)
    folder=tmp_path/BATCH;folder.mkdir()
    body=b'checked project 1305';(folder/'source.html').write_bytes(body);(folder/'source.txt').write_text(body.decode())
    with s.sessions.begin() as db:
        row,_=upsert_revision(db,'project','test','p',dict(name='고덕강일 3단지',planned_units=1305,base_date='2026-10-20'),'test');pid=row.entity_id
        db.add(Mapping(project_id=pid,policy_id='POL_2025_0907',status='CONFIRMED',revision_no=1,basis='approved',evidence_url='https://test'))
        upsert_revision(db,'project_profile','manual_project',pid,dict(project_id=pid,base_date='2026-10-20',overrides={'address':{'value':'preserve'}},progress={'SUPPLY':dict(event_date='2026-08-31',units=1305,inferred=True,actor='old')}),'test')
    manifest=[dict(key='S1',status=200,file='source.html',text_file='source.txt',sha256=hashlib.sha256(body).hexdigest(),url='https://news.example/original')]
    spec=dict(key='E05:S1:'+pid,case_id='E05',source_key='S1',project_id=pid,source_name='뉴시스',official=False,published_at='2026-10-16',checks=['checked','1305'],facts=[dict(stage='SUPPLY',kind='ACTUAL',date='2026-10-16',units=1305,basis='checked')],adopt_progress=dict(stage='SUPPLY',event_date='2026-10-16',units=1305))
    return s,pid,dict(decisions=[dict(case_id='E05',result='checked actual recruitment')],specs=[spec]),manifest


def test_nonofficial_confirmation_replaces_estimate_preserves_history_and_replays_once(tmp_path):
    s,pid,plan,manifest=fixture(tmp_path);result=apply(s,plan,manifest)
    assert result['new_projects']==0 and result['project_and_mapping_preserved']
    p=s.rows('project_profile')[0];value=p['progress']['SUPPLY']
    assert value['event_date']=='2026-10-16' and value['units']==1305 and not value['inferred']
    assert value['previous_estimate']['event_date']=='2026-08-31'
    assert value['review_label'].startswith('담당자 확인 완료 - 비공식 자료: 뉴시스')
    assert p['overrides']['address']['value']=='preserve'
    with s.sessions() as db:audits=db.scalar(select(func.count()).select_from(Audit))
    again=apply(s,plan,manifest)
    with s.sessions() as db:assert db.scalar(select(func.count()).select_from(Audit))==audits
    assert len(s.rows('evidence_bridge'))==1 and again['results'][0]['bridge_outcome']=='unchanged'
    assert s.rows('document_evidence')[0]['official_actual_verified'] is False


def test_changed_source_or_unconfirmed_claim_causes_no_partial_write(tmp_path):
    s,pid,plan,manifest=fixture(tmp_path);bad=deepcopy(plan);bad['specs'][0]['checks']=['absent']
    with pytest.raises(ValueError,match='확인 항목'):apply(s,bad,manifest)
    assert s.rows('evidence_bridge')==[]
    bad=deepcopy(plan);bad['specs'][0]['facts'][0].update(stage='MOVE_IN')
    with pytest.raises(ValueError,match='실제 준공'):apply(s,bad,manifest)
    assert s.rows('document_evidence')==[]
    assert s.rows('project_profile')[0]['progress']['SUPPLY']['event_date']=='2026-08-31'


def test_waiting_list_is_not_actual_supply_in_future_collections_or_old_repairs():
    n=dict(NOTICE,name=NOTICE['name'].replace('입주자 모집공고','예비입주자 모집공고'))
    p=parse_detail(HTML.encode(),n,KEY)
    assert p['notice_round']=='WAITLIST'
    assert p['facts'][0]['kind']=='STATE' and p['facts'][0]['units'] is None
    assert p['facts'][0]['recruitment_persons']==219
    old=dict(evidence_url='https://apply.lh.or.kr/?panId=2015122300020531',facts=[dict(stage='SUPPLY',kind='ACTUAL',date='2026-08-13',units=300)])
    new=repair_waitlist(old)
    assert new['facts'][0]['kind']=='STATE' and new['facts'][0]['recruitment_persons']==300
    assert repair_waitlist(new) is None
    assert old['facts'][0]['kind']=='ACTUAL'


def test_historical_reference_plan_does_not_enter_current_policy_schedules():
    s=FakeService();rows=s.rows
    bridge=dict(id='link',project_id='new',source_entity_id='doc',source_id='external_officer',source_name='old plan',status='CONFIRMED',evidence_url='https://test',facts=[dict(stage='MOVE_IN',kind='PLAN',date='2028-01',units=1000,reference_only=True,basis='historical')])
    s.rows=lambda kind,as_of=None: [bridge] if kind=='evidence_bridge' else rows(kind,as_of)
    model=build_delivery(s,date(2026,10,20),include_portfolio_comparisons=False)
    assert not any(t['stage']=='MOVE_IN' for c in model['portfolio_cohorts'] for t in c['schedules'])
    bridge['facts'][0]['reference_only']=False
    model=build_delivery(s,date(2026,10,20),include_portfolio_comparisons=False)
    assert any(t['stage']=='MOVE_IN' for c in model['portfolio_cohorts'] for t in c['schedules'])


def test_verified_rental_offering_supersedes_sibling_whole_contract_estimate():
    from backend.policy_delivery_comparison import _events
    s=FakeService();base=dict(s.project_rows[0],start_actual_date=None,district='부천대장',block='A5')
    s.project_rows=[dict(base,id='rental',name='부천대장 A5',source_id='lh_rent',tenure='행복주택',planned_units=314),dict(base,id='contract',name='부천대장 A5BL 공사',source_id='lh_construction',planned_units=952)]
    profiles=[dict(project_id='contract',progress={'SUPPLY':dict(event_date='2025-09-20',units=952,inferred=True,reason='whole-contract estimate')}),dict(project_id='rental',progress={'SUPPLY':dict(event_date='2026-07-23',units=312,inferred=False,input_rule='OFFICER_VERIFIED_SOURCE',reason='exact offered cohort')})]
    rows=s.rows;s.rows=lambda kind,as_of=None:profiles if kind=='project_profile' else rows(kind,as_of)
    model=build_delivery(s,date(2026,10,20),include_portfolio_comparisons=False)
    points=_events(model['portfolio_cohorts'],'SUPPLY',date(2026,10,20),'1900-01-01',cumulative=True)
    assert points[-1]['units']==312
    assert len(model['portfolio_cohorts'])==1
