from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.pool import StaticPool
from backend.db import Base, Revision, CollectionJob, IntegrityRound, Mapping, ProgramMapping, Audit, upsert_revision, now
from backend.service import HomeService
from backend.evidence_bridge import contained_facts, reconcile, match_key, review
from backend.independent_metrics import freeze, get_snapshot, source_role
from backend.data_integrity import classification_metrics, save_round, get_round
from backend.collection_jobs import enqueue, run_next


@pytest.fixture
def service():
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    yield HomeService(engine)
    engine.dispose()


def put(service,kind,source,key,payload):
    with service.sessions.begin() as db:
        r,_=upsert_revision(db,kind,source,key,payload,'test')
        return r.entity_id


def project(**extra):
    return dict(name='마곡지구 17단지',region='서울특별시',program='토지임대부',tenure='유형 확인 필요',
                planned_units=381,base_date='2026-01-01',evidence_url='https://example.org/plan',**extra)


def document():
    return dict(name='마곡17단지 본청약 모집공고',region='서울특별시',planned_units=577,
                base_date='2026-01-01',verification_status='SOURCE_CONTENT_CHECKED',evidence_url='https://example.org/notice',
                facts=[dict(stage='SUPPLY',kind='ACTUAL',date='2026-02-27',units=381,basis='전체 중 해당 분양 381호'),
                       dict(stage='MOVE_IN',kind='PLAN',date='2026-08-28',units=381)])


def test_sh_exact_event_scope_does_not_extrapolate_residual(service):
    p=put(service,'project','sh_inventory','p',project())
    d=put(service,'document_evidence','official_document','d',document())
    assert reconcile(service,apply=True,actor='김민',reason='공식 발표 후 도출된 보완 사항 적용')['added_links']==1
    b=service.rows('evidence_bridge')[0]
    assert b['relation_type']=='CONTAINED_SCOPE'
    assert len(b['facts'])==1 and b['facts'][0]['units']==381
    assert b['facts'][0]['source_total_units']==577
    assert not b['facts'][0]['scope_partial']
    review(service,b['id'],1,'RELEASED','다른 범위 검토')
    assert reconcile(service,apply=True)['added_links']==0
    assert service.rows('evidence_bridge')[0]['status']=='RELEASED'


def test_numeric_complex_requires_region_and_exact_number():
    a=match_key(project());b=match_key(dict(document(),name='마곡 17단지'))
    assert a==b
    assert a!=match_key(dict(document(),name='마곡 16단지'))
    assert a!=match_key(dict(document(),region='경기도'))
    assert match_key(dict(document(),name='마곡17단지 및 마곡18단지')) is None


def test_exact_event_requires_checked_source_and_main_round():
    d=dict(document(),id='doc')
    assert contained_facts(project(),d,[d],now().date())
    assert contained_facts(project(),dict(d,verification_status='UNVERIFIED'),[d],now().date()) is None
    assert contained_facts(project(),dict(d,notice_round='ADDITIONAL'),[d],now().date()) is None


def test_snapshot_uses_original_revision_and_never_official_aggregate(service):
    p=put(service,'project','sh_inventory','p',project())
    d=put(service,'document_evidence','official_document','d',document())
    put(service,'statistic','molit_statistics','s',dict(name='집계 통계',region='서울특별시',base_date='2026-01-01',units=999999))
    reconcile(service,apply=True)
    snapshot=freeze(service,'김민','공식 발표 후 도출된 보완 사항 적용')
    result=snapshot['result']
    m=next(m for m in result['metrics'] if m['metric_code']=='RECRUITMENT_PUBLISHED')
    assert m['value']==381 and not m['publishable']
    event=result['selected_events'][0]
    with service.sessions() as db:
        original=db.scalar(select(Revision).where(Revision.entity_id==d))
        assert event['source_revision_id']==original.id
        assert event['source_payload_hash']==original.payload_hash
    original_result=get_snapshot(service,snapshot['id'])
    put(service,'document_evidence','official_document','d',dict(document(),planned_units=999))
    assert get_snapshot(service,snapshot['id'])==original_result
    assert next(m for m in result['metrics'] if m['metric_code']=='OCCUPIED_UNITS')['value'] is None
    assert all(e['evidence_origin'] in ('PRIMARY_OPERATION','PRIMARY_NOTICE') for e in result['events'])


def test_confirmed_state_does_not_invent_annual_occurrence_date(service):
    from backend.independent_metrics import build
    pid=put(service,'project','lh_construction','p',project())
    fact=dict(stage='APPROVAL',kind='ACTUAL',date='2026-07-14',units=381,
        date_basis='OBSERVED_BY',observed_on='2026-07-14',source_event_date=None)
    did=put(service,'document_evidence','official_document','d',dict(document(),facts=[fact]))
    payload=dict(project_id=pid,source_entity_id=did,source_revision_no=1,facts=[fact],status='CONFIRMED',
        base_date='2026-07-14',evidence_url='https://example.org/amendment')
    put(service,'evidence_bridge','cross_source','b',payload)
    result=build(service,now())
    events=[e for e in result['events'] if e['event_type']=='APPROVAL_GRANTED']
    assert events and all('OBSERVATION_IS_NOT_NEW_EVENT_DATE' in e['validation_reasons'] for e in events)
    assert not [e for e in result['selected_events'] if e['event_type']=='APPROVAL_GRANTED']
    # An official statement that the event happened within this year can support
    # the full year's interval, but cannot locate it within a narrower month.
    started=dict(fact,stage='CONSTRUCTION',event_period_start='2026-01-01')
    put(service,'evidence_bridge','cross_source','b',dict(payload,facts=[started]))
    annual=build(service,now());monthly=build(service,now(),period_start='2026-07-01')
    assert len([e for e in annual['selected_events'] if e['event_type']=='CONSTRUCTION_STARTED'])==1
    assert not [e for e in monthly['selected_events'] if e['event_type']=='CONSTRUCTION_STARTED']


@pytest.mark.parametrize('reverse', [False, True])
@pytest.mark.parametrize('notice_tenure,expected', [('공공분양', 'SALE'), ('행복주택', 'RENT'), ('6년 분양전환공공임대주택', 'RENT')])
def test_offering_classification_survives_duplicate_project_anchors(service, reverse, notice_tenure, expected):
    from backend.independent_metrics import build
    payloads = [dict(name='남양주왕숙2 A01', tenure='공공분양'),
                dict(name='남양주왕숙2 A-1BL 아파트 건설공사', tenure='유형 확인 필요')]
    if reverse:
        payloads.reverse()
    pids = [put(service, 'project', 'lh_construction', str(i), dict(p,
                region='경기도', district='남양주왕숙2', block='A1', planned_units=812,
                program='3기 신도시', base_date='2026-01-01', evidence_url='https://example.org/work'))
            for i, p in enumerate(payloads)]
    fact = dict(stage='SUPPLY', kind='ACTUAL', date='2026-04-30', units=381,
                scope_partial=True, scope_units=381, milestone='NOTICE')
    did = put(service, 'document_evidence', 'lh_notice_detail', 'notice', dict(
        name='남양주왕숙2 A-1BL '+notice_tenure+' 입주자모집공고', tenure=notice_tenure,
        region='경기도', district='남양주왕숙2', block='A1', base_date='2026-04-30',
        evidence_url='https://example.org/notice', facts=[fact]))
    for pid in pids:
        put(service, 'evidence_bridge', 'cross_source', pid, dict(project_id=pid,
            source_entity_id=did, source_revision_no=1, facts=[fact], status='CONFIRMED',
            relation_type='SAME_SCOPE', base_date='2026-04-30', evidence_url='https://example.org/notice'))
    result = build(service, now())
    offered = [e for e in result['selected_events'] if e['event_type']=='RECRUITMENT_PUBLISHED']
    assert len(offered)==1 and offered[0]['quantity']==381
    assert offered[0]['quantity_scope']=='PART'
    assert offered[0]['taxonomy']['supply_mode']==expected
    assert offered[0]['classification_evidence']['source_revision_id']==offered[0]['source_revision_id']
    assert offered[0]['classification_evidence']['value']==expected
    # A legacy source edition with no notice_round still excludes re-offerings.
    for title in ('잔여세대 추가입주자 모집공고', '예비입주자 모집공고'):
        with service.sessions.begin() as db:
            row=db.scalar(select(Revision).where(Revision.entity_id==did))
            row.payload=dict(row.payload, name='남양주왕숙2 A-1BL '+notice_tenure+' '+title)
        result=build(service, now())
        assert not result['selected_events']
        assert any('REISSUE_NOT_NET_NEW' in e['validation_reasons'] for e in result['exclusions'])


def test_known_at_same_day_excludes_later_source_and_decision(service):
    p=put(service,'project','sh_inventory','p',project())
    boundary=now()-timedelta(minutes=30)
    with service.sessions.begin() as db:
        db.scalar(select(Revision).where(Revision.entity_id==p)).recorded_at=boundary-timedelta(minutes=1)
    put(service,'project','sh_inventory','p',dict(project(),planned_units=400))
    assert service.rows('project',known_at=boundary)[0]['planned_units']==381
    assert service.rows('project')[0]['planned_units']==400
    frozen=freeze(service,'김민','과거 인지시각 고정',known_at=boundary)
    assert frozen['result']['project_records']==1
    with pytest.raises(ValueError):freeze(service,'김민','시간대 누락',known_at=datetime(2026,1,1))


def test_capacity_and_officer_input_do_not_replace_primary_event_quantity(service):
    pid=put(service,'project','lh_construction','p',project(start_actual_date='2026-04-01'))
    put(service,'project_profile','officer','manual',dict(project_id=pid,name='입력',region='서울특별시',base_date='2026-01-01',
        evidence_url='https://example.org/evidence',progress=dict(SUPPLY=dict(event_date='2026-02-01',units=381,inferred=False))))
    result=freeze(service,'김민','직접 근거 확인')['result']
    assert not result['selected_events']
    assert any('QUANTITY_UNCONFIRMED' in e['validation_reasons'] for e in result['exclusions'])
    assert any('NOT_PRIMARY_EVENT' in e['validation_reasons'] for e in result['exclusions'])


def test_known_at_rewinds_mapping_decisions_only(service):
    pid=put(service,'project','sh_inventory','p',project(proposed_policy='UNASSIGNED'))
    boundary=now()-timedelta(minutes=30)
    with service.sessions.begin() as db:
        db.scalar(select(Revision).where(Revision.entity_id==pid)).recorded_at=boundary-timedelta(minutes=1)
        db.add(Mapping(project_id=pid,policy_id='POL_NEW',status='CONFIRMED',basis='현재',evidence_url='https://example.org/now',revision_no=2))
        db.add(Audit(entity_id=pid,action='MAPPING_REVIEW',before=dict(policy_id='UNASSIGNED',status='REVIEW',revision_no=1),after={}))
        db.add(Audit(entity_id=pid,action='PROJECT_PROFILE_UPDATED',before=dict(overrides={'name':'이전 이름'}),after={}))
    historical=service.rows('project',known_at=boundary)[0]
    assert historical['mapping']['policy_id']=='UNASSIGNED'
    assert historical['mapping']['status']=='REVIEW'
    assert 'overrides' not in historical['mapping']


def test_reference_candidate_idempotent_and_never_creates_actual(service):
    from backend.reference_registry import reconcile as refs
    put(service,'renewal_inventory','molit_renewal_inventory','one',dict(name='흑석11재정비촉진구역',region='서울특별시',
        units=1515,base_date='2026-05-18',evidence_url='https://example.org/list',start_actual_date='2025-01-01'))
    first=refs(service,'김민','공식 발표 후 도출된 보완 사항 적용',promote=True)
    assert first['candidates_added']==1 and len(first['promoted'])==1
    p=service.rows('project')[0]
    assert 'start_actual_date' not in p and p['mapping']['status']=='REVIEW'
    assert p['mapping']['policy_id']=='UNASSIGNED'
    second=refs(service,'김민','공식 발표 후 도출된 보완 사항 적용',promote=True)
    assert second['candidates_added']==0 and second['promoted'][0]['outcome']=='unchanged'


def test_unassigned_reference_does_not_inherit_programme_policy_before_review(service):
    pid=put(service,'project','ih_notice','candidate',project(proposed_policy='UNASSIGNED',policy_candidate_only=True))
    with service.sessions.begin() as db:
        db.add(ProgramMapping(id='PRG_candidate',name='일반 프로그램',seed_policy_id='UNASSIGNED',policy_id='POL_2025_0907',
                             status='CONFIRMED',basis='프로그램 전체 판단',evidence_url='https://example.org/program'))
        db.add(Mapping(project_id=pid,program_id='PRG_candidate',policy_id='UNASSIGNED',status='REVIEW',basis='후보',evidence_url='https://example.org/source'))
    row=service.rows('project')[0]
    assert row['mapping']['policy_id']=='UNASSIGNED' and row['mapping']['reference_policy_pending']
    assert not service.projects(policy_id='POL_2025_0907')


def test_ih_collection_dispatches_once_without_falling_through_to_generic_parser(service):
    from backend.sources import SOURCES
    source=next(s for s in SOURCES if s['id']=='ih_notice')
    records=[('project','land:test',project(proposed_policy='UNASSIGNED',policy_candidate_only=True))]
    with patch('backend.ih_public.collect',return_value=(records,dict(complete_query=False))) as collected,patch('backend.service.collect',side_effect=AssertionError('generic parser must not run')):
        result=service.collect_one(source)
    assert result['status']=='SUCCESS'
    assert collected.call_count==1
    assert service.rows('project')[0]['mapping']['policy_id']=='UNASSIGNED'


def test_queue_retries_link_without_recollecting(service):
    identity=enqueue(service,'lh_notice',force=True)
    assert enqueue(service,'lh_notice',force=True) is None
    with patch.object(service,'collect_one',return_value=dict(status='SUCCESS')) as collected:
        assert run_next(service)['next_stage']=='LINK'
        with patch('backend.stage_evidence.refresh',side_effect=ValueError('fail')):
            assert run_next(service)['status']=='RETRY'
        with service.sessions.begin() as db:
            row=db.get(CollectionJob,identity);assert row.stage=='LINK'
            row.run_after=now()-timedelta(seconds=1)
        with patch('backend.stage_evidence.refresh',return_value={}),patch('backend.project_collection.refresh_links',return_value={}),patch('backend.evidence_bridge.reconcile',return_value={}):
            assert run_next(service)['next_stage']=='SNAPSHOT'
        assert collected.call_count==1
        assert run_next(service)['status']=='SUCCESS'


def test_old_worker_cannot_overwrite_recovered_job(service):
    identity=enqueue(service,'sh_inventory',force=True)
    def recovered(_):
        with service.sessions.begin() as db:
            row=db.get(CollectionJob,identity);row.lease_token='new-owner';row.stage='LINK'
        return dict(status='SUCCESS')
    with patch.object(service,'collect_one',side_effect=recovered):
        assert run_next(service)['status']=='STALE_WORKER'
    with service.sessions() as db:
        row=db.get(CollectionJob,identity)
        assert row.lease_token=='new-owner' and row.stage=='LINK' and row.status=='RUNNING'


def test_manual_source_lock_does_not_exhaust_collection_retries(service):
    identity=enqueue(service,'building_register',force=True)
    with patch.object(service,'collect_one',return_value=dict(status='BUSY')):
        for _ in range(6):
            assert run_next(service)['status']=='BUSY'
            with service.sessions.begin() as db:
                row=db.get(CollectionJob,identity)
                assert row.status=='QUEUED' and row.stage=='COLLECT' and row.attempts==0
                assert row.error is None and row.lease_until is None
                row.run_after=now()-timedelta(seconds=1)
    with patch.object(service,'collect_one',return_value=dict(status='SUCCESS')):
        assert run_next(service)['next_stage']=='LINK'


def test_busy_worker_cannot_requeue_a_recovered_job(service):
    identity=enqueue(service,'building_register',force=True)
    def recovered(_):
        with service.sessions.begin() as db:
            row=db.get(CollectionJob,identity);row.lease_token='replacement';row.stage='LINK'
        return dict(status='BUSY')
    with patch.object(service,'collect_one',side_effect=recovered):
        assert run_next(service)['status']=='STALE_WORKER'
    with service.sessions() as db:
        row=db.get(CollectionJob,identity)
        assert row.lease_token=='replacement' and row.stage=='LINK' and row.status=='RUNNING'


def test_metrics_confusion_denominators_and_missing_not_zero():
    cases=[dict(label=a,prediction=b) for a,b in [(True,True),(False,True),(True,False),(False,False)]]
    m=classification_metrics(cases)
    assert (m['tp'],m['fp'],m['fn'],m['tn'])==(1,1,1,1)
    assert [m[k] for k in ('accuracy','precision','recall','f1')]==[50]*4
    assert classification_metrics([])['accuracy'] is None
    assert classification_metrics([dict(label=False,prediction=False)])['precision'] is None


def test_round_immutable_and_followup_comments_required(service):
    result=dict(display_score=50,categories=[dict(items=[dict(id=str(i),weight=2.5,score=1.25) for i in range(40)])])
    save_round(service,'R00',0,result,'<!doctype html><html></html>','김민','기준 보존')
    assert get_round(service,'R00')['result']==result
    with pytest.raises(ValueError):save_round(service,'R00',0,dict(result,display_score=100),'<!doctype html><html></html>','김민','기준 보존')
    with pytest.raises(ValueError):save_round(service,'R01',1,result,'<!doctype html><html></html>','김민','보완',parent_id='R00')
    with service.sessions.begin() as db:db.get(IntegrityRound,'R00').score='changed'
    with pytest.raises(ValueError):get_round(service,'R00')


def test_explicit_same_round_amendment_archives_and_rolls_back_invalid_input(service,tmp_path):
    from copy import deepcopy
    from backend.data_integrity import amend_round,rounds
    service.data_dir=tmp_path
    baseline=dict(display_score=50,total_score=50,categories=[dict(items=[dict(id=str(i),weight=2.5,score=1.25) for i in range(40)])])
    html='<!doctype html><html></html>'
    save_round(service,'R00',0,baseline,html,'김민','기준')
    first=deepcopy(baseline)
    for i in first['categories'][0]['items']:i.update(previous_score=1.25,change_comment='최초 대비')
    save_round(service,'R01',1,first,html,'김민','보완',parent_id='R00')
    old=get_round(service,'R01');base_digest=get_round(service,'R00')['digest']
    invalid=deepcopy(first);invalid['categories'][0]['items'][0]['previous_score']=0
    with pytest.raises(ValueError):amend_round(service,'R01',old['digest'],invalid,html,'김민','갱신')
    assert get_round(service,'R01')['digest']==old['digest']
    with pytest.raises(ValueError):amend_round(service,'R00',base_digest,first,html,'김민','갱신')
    amended=deepcopy(first);amended['categories'][0]['items'][0].update(score=1.5,change_comment='API 누락 보완')
    amended.update(total_score=50.25,display_score=50.3)
    amend_round(service,'R01',old['digest'],amended,html,'김민','기존 보완1 갱신')
    assert len(rounds(service)['items'])==2
    assert get_round(service,'R00')['digest']==base_digest
    assert get_round(service,'R01')['result']['total_score']==50.25
    assert (tmp_path/'remediation/round-amendments'/(old['digest']+'.json')).exists()
    with pytest.raises(ValueError):amend_round(service,'R01',old['digest'],amended,html,'김민','갱신')


def test_completed_district_revisit_does_not_starve_backfill(service,monkeypatch):
    from backend.building_scope import next_districts
    rows=[dict(source_object_id=str(i),address='서울특별시 동'+str(i),region='서울특별시',sigungu_code='11110',bjdong_code=str(i)) for i in range(8)]
    monkeypatch.setenv('POC10_BUILDING_DONGS_PER_BATCH','4')
    with patch.object(service,'rows',return_value=rows),patch.object(service,'projects',return_value=[]),patch.object(service,'latest_collection_stats',return_value=dict(district_counts={'0':dict(legal_dong_code='0',complete_query=True)})):
        districts,counts,total=next_districts(service,'building_hub')
    assert len(districts)==4 and total==8
    assert any(d[2]=='0' for d in districts)
    assert sum(d[2]!='0' for d in districts)==3
