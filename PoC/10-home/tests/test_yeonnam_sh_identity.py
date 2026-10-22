from copy import deepcopy
from pathlib import Path
import pytest
from sqlalchemy import select,func
from backend.db import Revision,Mapping,Audit,upsert_revision
from scripts.confirm_yeonnam_sh_identity_20261020 import (
    apply_identity,verify_pdf,historical_facts,SHA,YEON_ID,YEONHUI_ID,OTHER_YEONNAM,
    DOC_ID,RESOLVED,PLAN_BRIDGE,DESIGNER,CIS,BASIS,current)
from scripts.apply_officer_verified_links_20261020 import apply_reviews
from test_officer_verified_links import service as admission_service


@pytest.fixture
def service(admission_service):
    s=admission_service;apply_reviews(s,True,verify_files=False)
    with s.sessions.begin() as db:
        r,_=upsert_revision(db,'agency_plan','reb_movein_plan_file','e1462ceea3417321abdf03327cd5a47e5479ea94bf4189a7c072802f7cf18ac3',
            dict(name='연희96호',units=96,facts=[dict(kind='PLAN',stage='MOVE_IN',date='2027-09-30',units=96)]),'test')
        assert r.entity_id==YEONHUI_ID
        r,_=upsert_revision(db,'project','test','other-yeonnam',dict(name='연남동244-16 가로주택',planned_units=167),'test')
        db.flush();r.entity_id=OTHER_YEONNAM
        for source,key,eid in [('officer','prior-nonofficial-20261020:yeonnam-designer',DESIGNER),('official_document','closure-review-20261019:yeonhui-yeonnam-cis',CIS)]:
            r,_=upsert_revision(db,'document_evidence',source,key,dict(name='기존 참고자료',source_object_id=key,facts=[],unverified_fields=['합본96호 포함 여부']),'test')
            assert r.entity_id==eid
    return s


def proof():return dict(sha256=SHA,yeonnam=dict(total_units=8))


def test_reuses_existing_id_preserves_other_records_and_actuals(service):
    with service.sessions() as db:
        before={r.entity_id:r.payload_hash for r in db.scalars(select(Revision).where(Revision.kind=='project',Revision.superseded_at.is_(None)))}
        old_plan=deepcopy(current(db,PLAN_BRIDGE).payload['facts'])
        old_h=current(db,YEONHUI_ID).payload_hash
    result=apply_identity(service,proof(),True)
    assert result['added_projects']==result['added_actual_facts']==result['added_units']==0
    assert result['protected_before_hash']==result['protected_after_hash']
    assert result['all_existing_agency_plans_unchanged']
    with service.sessions() as db:
        after={r.entity_id:r.payload_hash for r in db.scalars(select(Revision).where(Revision.kind=='project',Revision.superseded_at.is_(None)))}
        assert before.keys()==after.keys()
        assert {k:v for k,v in before.items() if k!=YEON_ID}=={k:v for k,v in after.items() if k!=YEON_ID}
        p=current(db,YEON_ID).payload
        assert p['planned_units']==8 and p['start_actual_date'] is None
        assert p['land_area_sqm']==277 and p['building_count']==1 and p['floors_above']==5
        assert p['identity_resolution_status']==RESOLVED
        assert {x['entity_id'] for x in p['identity_exclusions']}=={YEONHUI_ID,OTHER_YEONNAM}
        assert all(x['relation']=='NOT_SAME_PROJECT' for x in p['identity_exclusions'])
        assert current(db,YEONHUI_ID).payload_hash==old_h
        assert current(db,PLAN_BRIDGE).payload['facts']==old_plan
        assert current(db,DOC_ID).payload['matched_project_ids']==[YEON_ID]
        assert db.scalar(select(Mapping).where(Mapping.project_id==YEON_ID)).basis==BASIS


def test_month_plans_are_historical_references_never_actuals():
    fs=historical_facts()
    assert [f['date'] for f in fs]==['2025-11','2026-10']
    assert all(f['kind']=='PLAN' and f['precision']=='MONTH' and f['reference_only'] and f['units']==8 for f in fs)


def test_explicit_exclusion_wins_over_similar_or_equal_name():
    from backend.stage_evidence import similarity
    p=dict(id=YEON_ID,name='연남동 공공임대주택',region='서울특별시',identity_exclusions=[dict(relation='NOT_SAME_PROJECT',entity_id=OTHER_YEONNAM)])
    s=dict(id=OTHER_YEONNAM,name=p['name'],region=p['region'])
    assert similarity(p,s)[0]==0
    assert similarity(s,p)[0]==0


def test_replay_and_earlier_batch_cannot_restore_old_hypothesis(service):
    apply_identity(service,proof(),True)
    with service.sessions() as db:
        first={r.entity_id:r.payload_hash for r in db.scalars(select(Revision).where(Revision.superseded_at.is_(None)))}
        audits=db.scalar(select(func.count()).select_from(Audit))
    repeat=apply_identity(service,proof(),True)
    assert all(c['result']=='unchanged' for c in repeat['changes'])
    apply_reviews(service,True,verify_files=False)
    with service.sessions() as db:
        after={r.entity_id:r.payload_hash for r in db.scalars(select(Revision).where(Revision.superseded_at.is_(None)))}
        assert first==after
        assert db.scalar(select(func.count()).select_from(Audit))==audits


def test_incompatible_approval_aborts_without_writes(service):
    with service.sessions.begin() as db:
        m=db.scalar(select(Mapping).where(Mapping.project_id==YEON_ID));m.status='REVIEW'
    with service.sessions() as db:before=db.scalar(select(func.count()).select_from(Audit))
    with pytest.raises(ValueError,match='승인값'):apply_identity(service,proof(),True)
    with service.sessions() as db:
        assert not current(db,DOC_ID)
        assert db.scalar(select(func.count()).select_from(Audit))==before


def test_original_pdf_separate_rows_and_tampered_bytes(tmp_path):
    path=Path(__file__).resolve().parents[1]/'data/yeonnam-sh-20261020/A0069855.pdf'
    if not path.exists():pytest.skip('operational pinned PDF not packaged with unit tests')
    p=verify_pdf(path)
    assert p['page']==79 and p['yeonnam']['total_units']==8 and p['yeonhui']['total_units']==96
    changed=tmp_path/'changed.pdf';changed.write_bytes(path.read_bytes()+b'changed')
    with pytest.raises(ValueError,match='해시'):verify_pdf(changed)
