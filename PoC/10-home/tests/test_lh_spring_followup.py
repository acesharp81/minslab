from copy import deepcopy
from datetime import date
import pytest
from sqlalchemy import create_engine, select, func
from backend.db import Base, Mapping, ProgramMapping, Revision, upsert_revision
from backend.service import HomeService
from backend.lh_spring_followup import parse_plans, admit_reviewed, REVIEWED
from backend.lh_policy_followup import POLICY
from backend.roadmap import source_events

EXTRA=[('서울도봉01','1',2100),('평택고덕','A72',773),('평택고덕','A73',522),('평택고덕','A69',1162),('평택고덕','A71',833),('평택고덕','A70',1225),('인천검단','AA30',444),('안산장상','A10',320),('성남복정1','B2',735),('고양창릉','B1',1594),('양주고읍','A12',138),('화성동탄','A1',464),('수원당수','C5',490),('수원당수2','B5',364),('수원당수2','B7',880)]
def fixture_pages():
    return ['2026. 5. 29. 민간사업자 선정을 마쳤다. 연내 착공', '\n'.join(f'{d} {b} 60-85 {n:,}' for d,b,n in REVIEWED+EXTRA)+'\n소계 21개 블록 14,913호']
POLICY_PAGES=['9.7대책 직접시행으로 전환 총 4개 지구 6개 블록 연내 착공']

def test_only_documented_round_is_policy_eligible_and_no_actual_is_generated():
    rows=parse_plans(fixture_pages(),POLICY_PAGES)
    assert len(rows)==21 and sum(r['units'] for r in rows)==14913
    assert sum(r['units'] for r in rows if r['proposed_policy']==POLICY)==2869
    assert all(not r['facts'] for r in rows[6:])
    assert all(f['kind']=='PLAN' for r in rows for f in r['facts'])
    with pytest.raises(ValueError):parse_plans(fixture_pages(),['민간참여 공공주택'])
    with pytest.raises(ValueError):parse_plans([fixture_pages()[0],fixture_pages()[1].replace('766','767')],POLICY_PAGES)
    with pytest.raises(ValueError):parse_plans([fixture_pages()[0],fixture_pages()[1].replace('AA31','AA32')],POLICY_PAGES)

@pytest.fixture
def service(tmp_path):
    engine=create_engine('sqlite://');Base.metadata.create_all(engine);s=HomeService(engine,tmp_path)
    with s.sessions.begin() as db:
        db.add(ProgramMapping(id='pg',name='LH 직접시행 전환·토지이용 효율화',seed_policy_id=POLICY,policy_id=POLICY,status='CONFIRMED',basis='test',evidence_url='https://www.lh.or.kr'))
        for p in parse_plans(fixture_pages(),POLICY_PAGES):
            p['original_sha256']='a'*64
            upsert_revision(db,'agency_plan','lh_policy_followup',p['source_object_id'],p,'test')
    return s

def test_admission_is_plan_only_idempotent_and_keeps_unrelated_candidates_unassigned(service):
    before=admit_reviewed(service)
    assert len(before['projects'])==6 and all(x['result']=='proposed' for x in before['projects'])
    with service.sessions() as db:assert db.scalar(select(func.count()).select_from(Mapping))==0
    result=admit_reviewed(service,True)
    assert all(x['result']=='added' for x in result['projects'])
    assert all(x['result']=='existing_preserved' for x in admit_reviewed(service,True)['projects'])
    with service.sessions() as db:
        assert db.scalar(select(func.count()).select_from(Mapping))==6
        for r in db.scalars(select(Revision).where(Revision.kind=='project')):
            assert not r.payload.get('start_actual_date')
            events=source_events(dict(r.payload,source_id='lh_policy_followup'),date(2026,10,19))
            assert len(events)==1 and events[0]['precision']=='YEAR' and events[0]['due_date']=='2026-12-31'

def test_last_block_collision_rolls_back_entire_admission(service):
    with service.sessions.begin() as db:
        upsert_revision(db,'project','other','duplicate',dict(name='양주회천 A23',district='양주회천',block='A23',region='경기도',planned_units=636),'test')
    with pytest.raises(ValueError):admit_reviewed(service,True)
    with service.sessions() as db:assert db.scalar(select(func.count()).select_from(Mapping))==0
