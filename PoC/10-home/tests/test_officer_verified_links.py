from copy import deepcopy
import pytest
from sqlalchemy import create_engine,select,func
from backend.db import Base,Revision,Mapping,ProgramMapping,Audit,upsert_revision
from backend.service import HomeService
from scripts.apply_officer_verified_links_20261020 import apply_reviews,LINKS,CASES,POLICY,BRIEF_SHA,YEON_DOC,YEON_ID

@pytest.fixture
def service(tmp_path):
    e=create_engine('sqlite://');Base.metadata.create_all(e);s=HomeService(e,tmp_path)
    with s.sessions.begin() as db:
        db.add(ProgramMapping(id='RENT',name='건설형 공공임대',seed_policy_id=POLICY,policy_id=POLICY,status='CONFIRMED',basis='test',evidence_url='https://test'))
        # Named cases are existing management members, never new quantities.
        names={pid:name for name,pid,_ in LINKS.values()}
        for n,_,_ in CASES:
            if not any(n.replace(' ','') in name.replace(' ','') for name in names.values()):names['named-'+n]=n
        for pid,name in names.items():
            row,_=upsert_revision(db,'project','test',name,dict(name=name,planned_units=309 if 'A17' in name else 100,base_date='2026-10-20'),'test')
            # Referenced production IDs are preserved in this fixture.
            db.flush();row.entity_id=pid
            db.add(Mapping(project_id=pid,policy_id=POLICY,program_id='RENT',status='CONFIRMED',revision_no=1,basis='test',evidence_url='https://test'))
        p=dict(source_object_id='external-match-review-20261020:Q4:32',name='연남8호 검토',official_units=8,
            official_source_sha256=BRIEF_SHA,official_stage='SUPPLY',official_kind='PLAN',base_date='2026-10-20')
        r,_=upsert_revision(db,'document_evidence','official_document',p['source_object_id'],p,'test');assert r.entity_id==YEON_DOC
        for eid,(name,pid,relation) in LINKS.items():
            src,_=upsert_revision(db,'document_evidence','test',name,dict(name=name,base_date='2026-10-20'),'test')
            db.flush();src.entity_id={'인천계양 A17':'PRO_fe4aa9d7d9211312f996dec5','흑석11':'DOC_3e6f87c1932e254aa123776b','신림2':'DOC_5c59006430033b9e10c30b79'}[name]
            fact=dict(stage='CONSTRUCTION',kind='PLAN',date='2027-01',units=309)
            if 'A17' in name:fact.update(scope_units=309,source_total_units=463)
            payload=dict(project_id=pid,source_entity_id=src.entity_id,source_revision_no=1,relation_type=relation,
                facts=[fact],status='REVIEW',reviewed=False,name=name)
            b,_=upsert_revision(db,'evidence_bridge','cross_source',pid+':'+src.entity_id,payload,'test');db.flush();assert b.entity_id==eid
    return s


def test_plan_only_admission_confirms_sources_and_does_not_invent_starts(service):
    preview=apply_reviews(service,verify_files=False)
    assert preview['added_project_units']==0
    result=apply_reviews(service,True,verify_files=False)
    assert result['added_project_units']==8 and result['construction_added_units']==0
    assert result['old_business_records_unchanged']
    with service.sessions() as db:
        p=db.scalar(select(Revision).where(Revision.entity_id==YEON_ID,Revision.superseded_at.is_(None)))
        assert p.payload['planned_units']==8 and p.payload['start_actual_date'] is None
        bridges=list(db.scalars(select(Revision).where(Revision.kind=='evidence_bridge',Revision.superseded_at.is_(None))))
        new=next(r for r in bridges if r.payload['project_id']==YEON_ID)
        assert new.payload['facts']==[dict(stage='SUPPLY',kind='PLAN',date='2026년4분기',date_label='2026년4분기',units=8,precision='QUARTER',basis='공식4분기 임대 공급계획 · 실제 모집·착공·입주 실적 아님')]
        assert all(r.payload['status']=='CONFIRMED' for r in bridges)
        assert db.scalar(select(func.count()).select_from(Revision).where(Revision.kind=='execution_schedule'))==0
        count=db.scalar(select(func.count()).select_from(Audit))
    repeated=apply_reviews(service,True,verify_files=False)
    assert repeated['added_project_units']==0
    with service.sessions() as db:assert db.scalar(select(func.count()).select_from(Audit))==count


def test_duplicate_plan_identity_aborts_before_source_review(service):
    with service.sessions.begin() as db:
        upsert_revision(db,'project','other','collision',dict(name='연남동 공공임대주택',base_date='2026-10-20'),'test')
    with pytest.raises(ValueError,match='중복'):apply_reviews(service,True,verify_files=False)
    with service.sessions() as db:
        assert db.scalar(select(func.count()).select_from(Audit))==0
        assert not db.scalar(select(Revision).where(Revision.entity_id==YEON_ID))


def test_incompatible_scope_or_released_link_is_not_overridden(service):
    with service.sessions.begin() as db:
        old=db.scalar(select(Revision).where(Revision.entity_id==next(iter(LINKS))))
        payload=deepcopy(old.payload);payload['status']='RELEASED';old.payload=payload
    with pytest.raises(ValueError,match='해제'):apply_reviews(service,True,verify_files=False)
    with service.sessions() as db:assert db.scalar(select(func.count()).select_from(Audit))==0
