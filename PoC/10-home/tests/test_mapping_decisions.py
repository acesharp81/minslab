import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.pool import StaticPool
from backend.db import Base, Mapping, ProgramMapping, Revision, Audit, upsert_revision
from backend.service import HomeService
from backend.mapping_decisions import save, ACTIVE
from backend.mapping_workbench import build

@pytest.fixture
def data():
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool);Base.metadata.create_all(engine);s=HomeService(engine)
    with s.sessions.begin() as db:
        db.add(ProgramMapping(id='p',name='후보 프로그램',seed_policy_id='UNASSIGNED',policy_id='UNASSIGNED',status='REVIEW',basis='후보',evidence_url='https://www.korea.kr/'))
        db.add(ProgramMapping(id='active',name='연결 프로그램',seed_policy_id=ACTIVE,policy_id=ACTIVE,status='CONFIRMED',basis='근거',evidence_url='https://www.korea.kr/'))
        row,_=upsert_revision(db,'project','test','candidate',dict(name='후보 사업',region='경기도',program='후보 프로그램',planned_units=100,base_date='2026-01-01',stage='PLANNING',stage_label='계획',warnings=[],evidence_url='https://www.korea.kr/'),'test')
        pid=row.entity_id
        db.add(Mapping(project_id=pid,program_id='p',policy_id='UNASSIGNED',status='REVIEW',basis='후보',evidence_url='https://www.korea.kr/'))
    yield s,pid
    engine.dispose()

def decision(s,pid,action='EXCLUDE',revision_no=0,kind='project',**kw):
    return save(s,kind,pid,action=action,revision_no=revision_no,actor='담당자',reason='정책 대상 아님을 확인',**kw)

def test_exclusion_is_durable_separate_from_source_and_reversible(data):
    s,pid=data;before=s.projects()[0]
    r=decision(s,pid);assert r['status']=='EXCLUDED' and r['actor']=='담당자'
    view=build(s);assert view['counts']['EXCLUDED']['projects']==1 and view['counts']['UNLINKED']['projects']==0
    assert s.projects(policy_id=ACTIVE)==[]
    with s.sessions() as db:
        raw=db.scalar(select(Revision).where(Revision.entity_id==pid, Revision.superseded_at.is_(None)))
        assert raw.revision_no==1 and raw.payload['planned_units']==100
        m=db.scalar(select(Mapping).where(Mapping.project_id==pid));assert m.status=='REVIEW' and m.program_id=='p'
    assert decision(s,pid,action='RESTORE',revision_no=0)['conflict']
    decision(s,pid,action='RESTORE',revision_no=1)
    assert build(s)['counts']['UNLINKED']['projects']==1
    assert s.projects()[0]['mapping']==before['mapping']
    with s.sessions() as db:
        assert len(db.scalars(select(Audit).where(Audit.action=='CANDIDATE_DECISION')).all())==2

def test_excluded_candidates_cannot_be_silently_linked(data):
    s,pid=data;decision(s,pid)
    with pytest.raises(ValueError,match='후보로 복원'):
        s.confirm_project_program(pid,'active',1,'CONFIRMED','근거','https://www.korea.kr/')
    decision(s,pid,action='RESTORE',revision_no=1)
    s.confirm_project_program(pid,'active',1,'CONFIRMED','근거','https://www.korea.kr/')
    with pytest.raises(ValueError,match='연결을 해제'):
        decision(s,pid,revision_no=2)

def test_program_exclusion_and_input_validation(data):
    s,pid=data;decision(s,'p',kind='program')
    assert build(s)['counts']['EXCLUDED']['programs']==1
    with s.sessions.begin() as db:
        db.add(ProgramMapping(id='zero',name='zero',seed_policy_id=ACTIVE,policy_id=ACTIVE,status='REVIEW',basis='x',evidence_url='https://www.korea.kr/'))
    with pytest.raises(ValueError,match='연결을 해제'):decision(s,'active',kind='program')
    with pytest.raises(ValueError,match='담당자'):save(s,'project',pid,action='EXCLUDE',revision_no=0,actor=' ',reason='확인')
    with pytest.raises(ValueError,match='지원하지'):decision(s,pid,action='ADD_LINK')

def test_source_update_does_not_reintroduce_excluded_candidate(data):
    s,pid=data;decision(s,pid)
    with s.sessions.begin() as db:
        m=db.scalar(select(Mapping).where(Mapping.project_id==pid));m.program_id='active';m.policy_id=ACTIVE
    assert s.projects(policy_id=ACTIVE)==[]
    assert build(s)['counts']['EXCLUDED']['projects']==1


def test_api_auth_conflict_and_persistent_reload(data):
    from fastapi.testclient import TestClient
    from unittest.mock import patch
    from backend.app import create_app
    s,pid=data
    payload=dict(action='EXCLUDE',revision_no=0,actor='담당자',reason='공식 대상 범위 밖')
    path=f'/poc/home/api/admin/mapping-decisions/project/{pid}'
    with TestClient(create_app(s.engine,auto_collect=False)) as client:
        assert client.post(path,json=payload).status_code==401
        with patch('backend.app.authenticated',return_value=True):
            assert client.post(path,json=payload).status_code==200
            assert client.post(path,json=payload).status_code==409
            assert client.get('/poc/home/api/mapping-workbench').json()['counts']['EXCLUDED']['projects']==1
            assert client.post(path,json=dict(payload,action='ADD_LINK')).status_code==422
            assert client.post(path,json=dict(payload,action='RESTORE',revision_no=1)).status_code==200
            assert client.get('/poc/home/api/mapping-workbench').json()['counts']['UNLINKED']['projects']==1


def reference_payload(s,pid):
    p=s.rows('project')[0]
    return dict(project_id=pid,policy_id=ACTIVE,category='A',relation_type='POLICY_REFERENCE',relation_level='DISTRICT',relation_status='CANDIDATE',report_sha256='a'*64,project_sha256=p['source_payload_hash'],mapping_revision_no=p['mapping']['revision_no'],reason='지구만 명시 · 블록 대상 미확인',actor='검토자',base_date='2026-01-01',inclusion_in_97_supply_target=False,credited_housing_units=None,credited_start_date=None,approved_by=None,approved_at=None)


def test_district_reference_never_changes_mapping_or_statistics_and_is_idempotent(data,monkeypatch):
    from backend.project_policy_relations import save_reference
    s,pid=data;monkeypatch.setattr(s,'mapping_policies',lambda *a:[dict(policy_id=ACTIVE,name='9.7')])
    before=s.projects()[0];payload=reference_payload(s,pid)
    assert save_reference(s,payload)['change']=='new'
    assert save_reference(s,payload)['change']=='unchanged'
    view=build(s);row=view['items'][0]
    assert row['review']['group']=='UNLINKED' and len(row['policy_relations'])==1
    assert row['policy_relations'][0]['inclusion_in_97_supply_target'] is False
    assert row['policy_relations'][0]['needs_recheck'] is False
    assert s.projects()[0]['mapping']==before['mapping'] and s.projects(policy_id=ACTIVE)==[]
    with s.sessions() as db:
        assert len(list(db.scalars(select(Audit).where(Audit.action=='POLICY_REFERENCE_REVIEW'))))==1


def test_reference_rejects_fake_approval_unknown_policy_and_stale_revision(data,monkeypatch):
    from backend.project_policy_relations import save_reference
    s,pid=data;monkeypatch.setattr(s,'mapping_policies',lambda:[dict(policy_id=ACTIVE)])
    p=reference_payload(s,pid)
    for change in [dict(inclusion_in_97_supply_target=True),dict(credited_housing_units=4022),dict(approved_by='AI'),dict(relation_status='VERIFIED'),dict(relation_type='POLICY_TARGET'),dict(policy_id='invented'),dict(mapping_revision_no=999),dict(project_sha256='b'*64)]:
        with pytest.raises(ValueError):save_reference(s,dict(p,**change))
    assert s.rows('project_policy_relation')==[]


def test_api_intro_is_not_project_evidence_but_native_identifier_is_preserved():
    from backend.project_policy_relations import evidence_context
    r=evidence_context(dict(evidence_url='https://www.data.go.kr/data/15136267/openapi.do',source_object_id='1000000000000000848411',address='자양동 217-23'))
    assert r['evidence_status']=='PER_PROJECT_EVIDENCE_MISSING'
    assert r['source_object_id']=='1000000000000000848411' and r['address']=='자양동 217-23'
