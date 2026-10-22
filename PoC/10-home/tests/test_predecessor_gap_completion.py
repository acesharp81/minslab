from copy import deepcopy
from datetime import date
import pytest
from sqlalchemy import create_engine, select
from backend.db import Base, Mapping, Revision, upsert_revision
from backend.service import HomeService
from scripts.complete_predecessor_estimates_20261020 import apply, estimate_units, POLICY


def test_existing_partial_scope_bounds_only_unknown_estimated_quantity():
    assert estimate_units(None,510,340)==340
    assert estimate_units(510,510,340)==510
    assert estimate_units(0,510,340)==0
    assert estimate_units(None,510,None)==510


def prepared(tmp_path):
    engine=create_engine('sqlite://');Base.metadata.create_all(engine);service=HomeService(engine,tmp_path)
    with service.sessions.begin() as db:
        raw,_=upsert_revision(db,'project','test','p',dict(name='사업',region='인천광역시',planned_units=10,base_date='2026-10-20'),'test')
        pid=raw.entity_id
        db.add(Mapping(project_id=pid,policy_id=POLICY,status='CONFIRMED',revision_no=1,basis='approved',evidence_url='https://test'))
        profile,_=upsert_revision(db,'project_profile','manual_project',pid,dict(project_id=pid,base_date='2026-10-20',overrides={},progress={'CONSTRUCTION':{'event_date':'2026-01-01','units':10},'APPROVAL':{'event_date':'2025-01-01','units':None}}),'test')
        plan=dict(reference_date='2026-10-20',created_at='2026-10-20T01:00:00+00:00',summary={},projects=[dict(project_id=pid,name='사업',region='인천광역시',source_revision_id=raw.id,mapping_revision_no=1,profile_revision_id=profile.id,schedule_revision_ids={'BUSINESS':None,'APPROVAL':None},changes=dict(targets={},progress={'APPROVAL':dict(event_date='2025-01-01',units=10,inferred=True)}))])
    return service,plan,pid


def test_partial_fill_preserves_existing_values_other_stages_and_replay(tmp_path):
    service,plan,pid=prepared(tmp_path)
    before=service.rows('project')[0]['source_revision_id']
    apply(service,plan)
    profile=service.rows('project_profile')[0]
    assert profile['progress']['CONSTRUCTION']=={'event_date':'2026-01-01','units':10}
    assert profile['progress']['APPROVAL']['units']==10 and profile['progress']['APPROVAL']['inferred']
    assert service.rows('project')[0]['source_revision_id']==before
    revision=profile['source_revision_id']
    assert apply(service,plan)['unchanged']
    assert service.rows('project_profile')[0]['source_revision_id']==revision


def test_rejects_existing_date_change_future_measurement_and_other_stage(tmp_path):
    service,plan,pid=prepared(tmp_path)
    wrong=deepcopy(plan);wrong['projects'][0]['changes']['progress']['APPROVAL']['event_date']='2024-01-01'
    with pytest.raises(ValueError,match='기존 담당자'):apply(service,wrong)
    future=deepcopy(plan);future['projects'][0]['changes']['progress']['APPROVAL']['event_date']='2027-01-01'
    with pytest.raises(ValueError,match='현재 추정'):apply(service,future)
    other=deepcopy(plan);other['projects'][0]['changes']['progress']={'CONSTRUCTION':dict(event_date='2026-01-01',units=10,inferred=True)}
    with pytest.raises(ValueError,match='외 단계'):apply(service,other)
