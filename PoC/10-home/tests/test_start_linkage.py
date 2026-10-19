from copy import deepcopy
from datetime import date
from unittest.mock import patch
from sqlalchemy import create_engine,select
from backend.db import Base,Revision,Mapping,upsert_revision
from backend.service import HomeService
from backend.start_linkage import prepare,category,quantity,apply_links,apply_identities,GENERAL,SMALL,RENEWAL


def source(**kw):
    return dict(id='g',source_id='building_general_permit',source_revision_id='r',revision_no=1,
        sample_kind='general_permit',region='서울특별시',name='주택',address='서울특별시 광진구 자양동 601-4번지',
        units=29,main_purpose='공동주택',construction_type='신축',evidence_url='https://example.org/raw',
        dates={'건축허가일 (archPmsDay)':'2026-01-27','실제착공일 (realStcnsDay)':'2026-02-10'},**kw)


def test_classification_uses_business_type_and_does_not_call_private_houses_public():
    assert category(source())==(GENERAL,'UNASSIGNED')
    assert category(dict(business_type='가로주택정비'))==(SMALL,'UNASSIGNED')
    assert category(dict(business_type='재개발(주택정비형)'))==(RENEWAL,'UNASSIGNED')


def test_partial_components_and_family_count_do_not_become_verified_units():
    row=dict(sample_kind='document_evidence',id='d',name='번동3',housing_plan_partial_components={
        '분양':dict(reported_total=None,area_band_units=[103,30,None]),'임대':dict(reported_total=None,area_band_units=[34,None,None])})
    original=deepcopy(row);units,proof=quantity(row,[])
    assert units==167 and proof['inferred'] and row==original
    row=source();row.update(units=0,main_purpose='단독주택',family_count=5)
    units,proof=quantity(row,[])
    assert units==1 and proof['inferred'] and row['family_count']==5 and row['units']==0


def test_exact_scope_duplicate_reuses_existing_project_and_prior_approval():
    raw=source();raw['dates']['건축허가일 (archPmsDay)']='2026-03-01'
    projects=[dict(id='old',region=raw['region'],address=raw['address'],planned_units=29)]
    with patch('backend.start_linkage.today',return_value=date(2026,10,19)):
        plan=prepare(projects,[raw,dict(raw,id='duplicate')],[],[])
    assert len(plan['items'])==1 and plan['items'][0]['project_id']=='old'
    assert plan['items'][0]['approval_date'] is None  # amendment after start
    assert len(plan['held'])==1


def test_link_application_is_idempotent_and_raw_revisions_are_preserved():
    engine=create_engine('sqlite://');Base.metadata.create_all(engine);s=HomeService(engine)
    raw=source()
    with s.sessions.begin() as db:
        r,_=upsert_revision(db,'general_permit',raw['source_id'],'native',raw,'test')
        raw.update(id=r.entity_id,source_revision_id=r.id)
    with patch('backend.start_linkage.today',return_value=date(2026,10,19)):
        plan=prepare([], [raw],[],[])
        assert apply_links(s,plan,'사용자','선후관계 보완')['projects_added']==1
        assert apply_identities(s,plan,'사용자','선후관계 보완')['linked']==1
        assert apply_links(s,plan,'사용자','선후관계 보완')=={'links_preserved':1}
        assert apply_identities(s,plan,'사용자','선후관계 보완')=={'preserved':1}
    with s.sessions() as db:
        assert db.scalar(select(Mapping)).policy_id=='UNASSIGNED'
        assert db.scalar(select(Revision).where(Revision.kind=='general_permit')).id==raw['source_revision_id']
    engine.dispose()


def test_scope_correction_only_withdraws_batch_policy_claims_and_is_idempotent():
    from backend.start_linkage import BATCH
    from backend.policy_scope_correction import correct
    from backend.db import ProgramMapping, Audit
    from backend.program_hierarchy import program_id
    engine=create_engine('sqlite://');Base.metadata.create_all(engine);s=HomeService(engine)
    raw=source(business_type='가로주택정비')
    with s.sessions.begin() as db:
        r,_=upsert_revision(db,'general_permit',raw['source_id'],'native',raw,'test')
        raw.update(id=r.entity_id,source_revision_id=r.id)
    with patch('backend.start_linkage.today',return_value=date(2026,10,19)):
        plan=prepare([], [raw],[],[])
        # Reproduce only the original type-only assertion, not a staff decision.
        plan['items'][0].update(policy_id='POL_2025_0907',program='소규모주택정비사업 활성화')
        apply_links(s,plan,'작업 배치','선후관계 보완')
    pid=plan['items'][0]['project_id']
    with s.sessions.begin() as db:
        profile,_=upsert_revision(db,'project_profile','manual_project',pid,dict(project_id=pid,overrides={'planned_units':{'value':29}}),BATCH+'-estimates')
        profile_hash=profile.payload_hash
        upsert_revision(db,'execution_schedule','officer',pid+':CONSTRUCTION',dict(project_id=pid,policy_id='POL_2025_0907',stage='CONSTRUCTION',units=29,due_date='2026-02-10',batch_id=BATCH+'-estimates'),BATCH+'-estimates')
        db.add(Mapping(project_id='staff',policy_id='POL_2025_0907',status='CONFIRMED',revision_no=3,basis='담당자',evidence_url='https://example.org'))
    assert correct(s,plan)=={'policy_assertions_withdrawn':1,'schedule_scope_corrected':1}
    assert correct(s,plan)=={'already_corrected':1}
    with s.sessions() as db:
        m=db.scalar(select(Mapping).where(Mapping.project_id==pid))
        assert m.policy_id=='UNASSIGNED' and m.status=='REVIEW'
        assert db.get(ProgramMapping,m.program_id).policy_id=='UNASSIGNED'
        assert db.scalar(select(Mapping).where(Mapping.project_id=='staff')).revision_no==3
        assert db.scalar(select(Revision).where(Revision.kind=='project_profile')).payload_hash==profile_hash
        assert db.scalar(select(Revision).where(Revision.kind=='general_permit')).id==raw['source_revision_id']
    engine.dispose()
