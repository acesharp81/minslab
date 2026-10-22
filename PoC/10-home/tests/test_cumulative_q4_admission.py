from datetime import date
from copy import deepcopy
import pytest
from sqlalchemy import create_engine, select, func
from backend.db import Base, Revision, Mapping, ProgramMapping, Audit, upsert_revision
from backend.service import HomeService
from backend.policy_delivery_comparison import _events
from scripts.admit_cumulative_q4_20261020 import admit, SPECS, POLICY, PROGRAM, BRIEF_SHA


@pytest.fixture
def service(tmp_path):
    engine=create_engine('sqlite://')
    Base.metadata.create_all(engine)
    s=HomeService(engine,tmp_path)
    with s.sessions.begin() as db:
        db.add(ProgramMapping(id='RENT',name=PROGRAM,seed_policy_id=POLICY,policy_id=POLICY,
                             status='CONFIRMED',basis='test',evidence_url='https://example.test'))
        for spec in SPECS:
            p=dict(name=spec['name'],source_object_id=f"external-match-review-20261020:Q4:{spec['number']}",
                official_units=spec['units'],original_sha256=spec['evidence_sha'],
                official_source_sha256=BRIEF_SHA,review_decision='OFFICIAL_ITEM_SOURCE_MATCH_CONFIRMED',
                review_basis='명칭·기관·호수 대조',evidence_url='https://example.test/source',
                base_date='2026-10-20')
            r,_=upsert_revision(db,'document_evidence','official_document',p['source_object_id'],p,'fixture')
            assert r.entity_id==spec['evidence_id']
    return s


def test_both_old_starts_admitted_once_plans_never_become_supply_actual(service):
    assert all(p['result']=='proposed' for p in admit(service,verify_files=False)['projects'])
    applied=admit(service,True,verify_files=False)
    assert applied['added_units']==95 and applied['existing_approvals_unchanged']
    assert all(p['result']=='existing_preserved' for p in admit(service,True,verify_files=False)['projects'])
    with service.sessions() as db:
        assert db.scalar(select(func.count()).select_from(Mapping))==2
        records=list(db.scalars(select(Revision).where(Revision.superseded_at.is_(None))))
        # SQLite does not enforce the production PostgreSQL VARCHAR limit.
        assert all(len(a.action)<=Audit.__table__.c.action.type.length for a in db.scalars(select(Audit)))
    ps=[r for r in records if r.kind=='project']
    assert len(ps)==2 and sum(r.payload['planned_units'] for r in ps)==95
    assert all(r.payload['developer']=='SH' for r in ps)
    schedules=[r for r in records if r.kind=='execution_schedule']
    assert len(schedules)==6
    assert all(r.payload['input_rule']=='CONFIRMED_REACHED_OPENING_BALANCE' for r in schedules)
    bridges=[r.payload for r in records if r.kind=='evidence_bridge']
    starts=[f for b in bridges for f in b['facts'] if f['kind']=='ACTUAL']
    assert len(starts)==2 and all(f['stage']=='CONSTRUCTION' and f['date']<'2026-01-01' for f in starts)
    partial=next(f for f in starts if f['units']==75)
    assert partial['date_basis']=='OBSERVED_BY' and partial['source_event_date'] is None
    assert partial['source_event_month']=='2025-06'
    plans=[f for b in bridges for f in b['facts'] if f['stage']=='SUPPLY']
    assert len(plans)==2 and all(f['kind']=='PLAN' and f['date']=='2026년4분기' for f in plans)
    cs=[dict(id=str(i),units=f['units'],events=[dict(stage='CONSTRUCTION',event_date=f['date'],units=f['units'])]) for i,f in enumerate(starts)]
    for stage in ('BUSINESS','APPROVAL','CONSTRUCTION'):
        assert _events(cs,stage,date(2026,10,20),'1900-01-01',True)[-1]['units']==95
    assert not _events(cs,'SUPPLY',date(2026,10,20),'1900-01-01',True)


def test_second_site_collision_leaves_first_site_unwritten(service):
    with service.sessions.begin() as db:
        upsert_revision(db,'project','existing','doksan',dict(name='독산동 산업문화어울림센터 건설공사',
            address='서울특별시 금천구 독산동 331-38',base_date='2026-10-01'),'fixture')
    with pytest.raises(ValueError,match='중복'):
        admit(service,True,verify_files=False)
    with service.sessions() as db:
        assert db.scalar(select(func.count()).select_from(Mapping))==0
        assert db.scalar(select(func.count()).select_from(Revision).where(Revision.kind=='execution_schedule'))==0


def test_unverified_source_and_changed_quantity_never_admitted(service):
    with service.sessions.begin() as db:
        old=db.scalar(select(Revision).where(Revision.entity_id==SPECS[1]['evidence_id']))
        p=deepcopy(old.payload);p['official_units']=21
        upsert_revision(db,'document_evidence','official_document',p['source_object_id'],p,'change')
    with pytest.raises(ValueError,match='수량'):
        admit(service,True,verify_files=False)
    with service.sessions() as db:
        assert db.scalar(select(func.count()).select_from(Mapping))==0
