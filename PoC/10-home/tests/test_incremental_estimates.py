from copy import deepcopy
from datetime import date
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select, func
from backend.db import Base, Audit, Mapping, ProgramMapping, Revision, upsert_revision
from backend.incremental_estimates import values, apply, ih_inputs
from backend.project_profile import STAGES
from backend.service import HomeService


def model():
    return {k:dict(mean_days=n,sample_count=10,origin='COLLECTED_INTERVAL_MEAN',
        **(dict(days_per_unit=1.5,typical_units=750) if k=='CONSTRUCTION_COMPLETION' else {}))
        for k,n in [('BUSINESS_APPROVAL',300),('APPROVAL_CONSTRUCTION',200),
                    ('CONSTRUCTION_COMPLETION',1125),('COMPLETION_MOVE_IN',60),('CONSTRUCTION_SUPPLY',180)]}


def compute(p,anchors=()):
    cells={s:dict(sources=[],targets=[],progress={},assessment=None) for s in ('POLICY','BUSINESS','APPROVAL','CONSTRUCTION','SUPPLY','MOVE_IN')}
    with patch('backend.officer_completion.today',return_value=date(2026,10,18)):
        return values(p,cells,model(),'2026-10-18T12:00:00+00:00','김민','공식 자료 확인 및 IH 추가 연결',date(2026,10,18),anchors,[500,900])


def test_past_schedule_alone_does_not_create_measurements():
    p=dict(id='p',name='중계본동',region='서울특별시',planned_units=3178,source_id='molit_renewal_inventory',
           source_revision_id='raw',start_actual_date=None)
    original=deepcopy(p)
    r=compute(p,[dict(stage='CONSTRUCTION',due_date='2026-08-15',precision='DAY'),
                 dict(stage='COMPLETION',due_date='2029-10-31',precision='DAY')])
    assert p==original
    assert r['targets']['CONSTRUCTION']['due_date']=='2026-08-15'
    assert not r['progress']
    assert 'progress_pct' not in r['overrides']


def test_ih_explicit_fields_precede_capacity_model_and_preserve_half_year():
    p=dict(id='p',name='검단 AA10',region='인천광역시',planned_units=None,source_id='ih_notice',
           source_revision_id='raw',source_fields={'공급규모':'1,458세대(전용면적 59㎡ 583세대, 84㎡ 583세대, 101㎡ 292세대)',
                                                '사업일정':'착공 23년 11월, 준공 26년 6월'})
    r=compute(p)
    assert r['planned_units']==1458 and p['planned_units'] is None
    assert not r['overrides']['planned_units']['inferred']
    from backend.input_status import input_status
    assert input_status(r['overrides']['planned_units'])=='CONFIRMED'
    assert not r['progress'] # source schedule alone is not a completed event
    assert r['targets']['CONSTRUCTION']['due_date']=='2023-11-30'
    assert 'COMPLETION' not in r['progress']
    p['planned_units']=749;p['source_fields']={'사업일정':'착공(예정) 27년 상반기, 준공(예정) 30년 하반기'}
    r=compute(p)
    assert r['targets']['CONSTRUCTION']['due_date']=='2027-06-30'
    assert r['targets']['CONSTRUCTION']['date_precision']=='HALF_YEAR'
    assert 'CONSTRUCTION' not in r['progress']
    assert 'COMPLETION' not in r['progress']


def test_missing_construction_uses_observed_approval_before_generic_deadline():
    p=dict(id='p',name='정비',region='서울특별시',planned_units=1430,source_id='test',source_revision_id='raw')
    r=compute(p,[dict(stage='APPROVAL',due_date='2025-07-03')])
    assert r['targets']['CONSTRUCTION']['due_date']=='2026-01-19'
    assert 'CONSTRUCTION' not in r['progress']


@pytest.fixture
def db_plan():
    e=create_engine('sqlite://');Base.metadata.create_all(e);s=HomeService(e)
    with s.sessions.begin() as db:
        db.add(ProgramMapping(id='pr',name='추가 사업',seed_policy_id='POL_2025_0907',policy_id='POL_2025_0907',status='CONFIRMED',revision_no=1,basis='연결',evidence_url='https://example.org'))
        source,_=upsert_revision(db,'project','test','new',dict(name='추가',base_date='2026-01-01',region='서울특별시',planned_units=3178),'test')
        pid,rid=source.entity_id,source.id
        db.add(Mapping(project_id=pid,program_id='pr',policy_id='POL_2025_0907',status='CONFIRMED',revision_no=2,basis='연결',evidence_url='https://example.org'))
        upsert_revision(db,'project_profile','manual_project','existing',dict(project_id='existing',overrides={'planned_units':{'value':9}},base_date='2026-01-01'),'old')
    p=dict(id=pid,name='추가',region='서울특별시',planned_units=3178,source_id='test',source_revision_id=rid)
    r=compute(p,[dict(stage='CONSTRUCTION',due_date='2026-08-15'),dict(stage='COMPLETION',due_date='2029-10-31')])
    r.update(mapping_revision_no=2,evidence_url='https://example.org',pinned_inputs=[dict(entity_id=pid,revision_id=rid)])
    yield s,dict(reference_date='2026-10-18',projects=[r],summary={'projects':1}),pid
    e.dispose()


def test_incremental_apply_preserves_old_inputs_source_mapping_and_is_idempotent(db_plan):
    s,plan,pid=db_plan
    old=s.rows('project_profile')[0]['source_revision_id']
    result=apply(s,plan,'incremental1','김민','공식 자료 확인 및 IH 추가 연결')
    assert result['counts']=={'project_profile':1,'execution_schedule':6}
    assert next(p for p in s.rows('project_profile') if p['project_id']=='existing')['source_revision_id']==old
    assert len(s.rows('execution_schedule'))==6
    assert s.rows('project')[0]['source_revision_id']==plan['projects'][0]['pinned_inputs'][0]['revision_id']
    with s.sessions() as db:
        assert db.scalar(select(Mapping).where(Mapping.project_id==pid)).revision_no==2
        count=db.scalar(select(func.count()).select_from(Audit))
    assert apply(s,plan,'incremental1','김민','공식 자료 확인 및 IH 추가 연결')['unchanged']
    with s.sessions() as db:assert db.scalar(select(func.count()).select_from(Audit))==count


@pytest.mark.parametrize('bad',['revision','existing','source'])
def test_changed_or_preexisting_inputs_reject_all_writes(db_plan,bad):
    s,plan,pid=db_plan
    if bad=='revision':plan['projects'][0]['mapping_revision_no']=1
    elif bad=='source':plan['projects'][0]['pinned_inputs'][0]['revision_id']='stale'
    else:
        with s.sessions.begin() as db:
            upsert_revision(db,'execution_schedule','officer',pid+':SUPPLY',dict(project_id=pid,base_date='2026-01-01'),'old')
    with pytest.raises(ValueError):apply(s,plan,'incremental1','김민','공식 자료 확인 및 IH 추가 연결')
    with s.sessions() as db:assert db.scalar(select(func.count()).select_from(Audit))==0
    assert len(s.rows('project_profile'))==1


def test_explicit_unassigned_scope_does_not_create_policy_schedules(db_plan):
    s,plan,pid=db_plan
    with s.sessions.begin() as db:
        db.scalar(select(Mapping).where(Mapping.project_id==pid)).policy_id='UNASSIGNED'
    plan['projects'][0]['policy_id']='UNASSIGNED'
    apply(s,plan,'unassigned-start','사용자','동일 규칙 적용')
    assert all(r['policy_id']=='UNASSIGNED' for r in s.rows('execution_schedule'))
