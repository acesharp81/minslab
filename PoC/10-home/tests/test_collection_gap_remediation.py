from datetime import date,timedelta
from pathlib import Path
from unittest.mock import patch
import pytest
from sqlalchemy import create_engine,select
from sqlalchemy.pool import StaticPool
from backend.db import Base,upsert_revision,IdentityAlias,Mapping,Batch,Audit,now
from backend.service import HomeService
from backend.monthly_release import discover,parse_pdf
from backend.annual_supply import annual_supply
from backend.construction_candidates import reconcile
from backend.sources import SOURCES


@pytest.fixture
def service(tmp_path):
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    yield HomeService(engine,tmp_path)
    engine.dispose()


def test_official_pdf_and_cumulative_periods_never_double_count(service):
    root=Path(__file__).resolve().parents[1]/'docs/evidence/HOME_COLLECTION_GAP_REVIEW_20261019'
    period,(_,url)=discover((root/'index_permits.html').read_bytes())
    source=next(s for s in SOURCES if s['id']=='molit_monthly_release')
    body=(root/'official_august.pdf').read_bytes()
    records=parse_pdf(body,period,source,url)
    assert len(records)==6
    with pytest.raises(ValueError,match='연월'):parse_pdf(body,'202607',source,url)
    with service.sessions.begin() as db:
        for kind,key,p in records:upsert_revision(db,kind,source['id'],key,p,'test')
        earlier=dict(records[1][2],statistic_period='202607',units=28634)
        upsert_revision(db,'statistic_reference',source['id'],'earlier',earlier,'test')
    cell=annual_supply(service,'서울특별시')['rows'][0]['metrics']['인허가']
    assert cell['units']==39940 and cell['through_period']=='202608'
    assert cell['complete'] is False and cell['change_yoy_units'] is None
    assert cell['aggregation']=='OFFICIAL_YTD'
    with service.sessions.begin() as db:
        upsert_revision(db,'statistic','molit_statistics','annual',dict(name='인허가',region='서울특별시',
            statistic_metric='인허가',statistic_frequency='YEAR',statistic_period='2026',units=50000),'test')
    cell=annual_supply(service,'서울특별시')['rows'][0]['metrics']['인허가']
    assert cell['units']==50000 and cell['complete'] is True


def test_construction_candidate_idempotence_and_approved_alias_preservation(service):
    def payload(**kw):
        return dict(name='신축주택',region='서울특별시',address='서울특별시 구의동 1',
            construction_type='신축',main_purpose='공동주택',units=29,
            dates={'실제착공일 (realStcnsDay)':'2026-02-01'},**kw)
    with service.sessions.begin() as db:
        r,_=upsert_revision(db,'general_permit','building_general_permit','one',payload(),'test');eid=r.entity_id
        bad=dict(payload(),construction_type='발코니구조변경')
        upsert_revision(db,'general_permit','building_general_permit','balcony',bad,'test')
        future=dict(payload(),dates={'실제착공일 (realStcnsDay)':'2027-02-01'})
        upsert_revision(db,'general_permit','building_general_permit','future',future,'test')
    first=reconcile(service,date(2026,10,19));assert first['candidate_rows']==1 and first['candidates_added']==1
    with service.sessions.begin() as db:
        alias=db.scalar(select(IdentityAlias).where(IdentityAlias.source_entity_id==eid))
        alias.relation_status='CONFIRMED';alias.basis='담당자 확정'
    second=reconcile(service,date(2026,10,19));assert second['candidates_added']==0 and second['evidence_added']==0
    with service.sessions() as db:
        a=db.scalar(select(IdentityAlias));assert a.relation_status=='CONFIRMED' and a.basis=='담당자 확정'
        assert db.scalar(select(Mapping)) is None
        assert all(len(a.action)<=Audit.__table__.c.action.type.length for a in db.scalars(select(Audit)))
    assert service.rows('project')==[] and first['actual_events_created']==0


def test_partial_backfill_interval_and_complete_daily_interval(service):
    from backend.collection_jobs import enqueue
    with service.sessions.begin() as db:
        b=Batch(source_id='building_general_permit',status='SUCCESS',finished_at=now()-timedelta(minutes=70),
            stats={'scope_remaining_dongs':1});db.add(b)
    with patch('backend.collection_jobs.backfill_window_open',return_value=True):
        assert enqueue(service,'building_general_permit')
    # Different source with completed scope retains the normal daily schedule.
    with service.sessions.begin() as db:
        db.add(Batch(source_id='building_hub_incheon',status='SUCCESS',finished_at=now()-timedelta(minutes=20),
            stats={'scope_remaining_dongs':0}))
    assert enqueue(service,'building_hub_incheon') is None


def test_one_district_override_alternates_revisit_and_new(service,monkeypatch):
    from backend.building_scope import next_districts
    monkeypatch.setenv('POC10_GENERAL_PERMIT_DONGS_PER_BATCH','1')
    codes=[dict(address='서울특별시 가동',source_object_id='1111010100',region='서울특별시',sigungu_code='11110',bjdong_code='10100'),
           dict(address='서울특별시 나동',source_object_id='1111010200',region='서울특별시',sigungu_code='11110',bjdong_code='10200')]
    meta=dict(district_counts={'1111010100':dict(legal_dong_code='1111010100',complete_query=True,checked_at='2020-01-01T00:00:00+00:00')})
    with patch.object(service,'rows',side_effect=lambda k:codes if k=='legal_dong' else []),patch.object(service,'projects',return_value=[]),patch.object(service,'latest_collection_stats',return_value=meta):
        a,_,_=next_districts(service,'building_general_permit');assert a[0][2]=='10100'
        meta['single_revisit_batch']=True
        b,_,_=next_districts(service,'building_general_permit');assert b[0][2]=='10200'


def test_partial_overview_preserves_blank_instead_of_zero():
    from backend.seoul_cleanup import parse_overview
    body='<table><caption>주택공급계획 임대</caption><tr>'+''.join('<td>'+v+'</td>' for v in ['', '', '', '', '', '57', '', '126', ''])+'</tr></table>'
    p=parse_overview(body)
    assert p['housing_plan_partial_components']['임대']['area_band_units']==[57,None,126]
    assert p['housing_plan_total'] is None and '임대' not in p['housing_plan_components']


def test_backfill_balances_regions_and_prioritizes_under_collected_region():
    from backend.building_scope import balanced_pending
    codes=[dict(source_object_id=p+str(i).zfill(8)) for p in ('11','28','41') for i in range(4)]
    counts={r['source_object_id']:dict(complete_query=True) for r in codes if r['source_object_id'].startswith('11') and r['source_object_id'].endswith(('0','1'))}
    pending=[r for r in codes if r['source_object_id'] not in counts]
    ordered=balanced_pending(codes,counts,pending)
    assert [r['source_object_id'][:2] for r in ordered[:3]]==['28','41','11']
    assert len(ordered)==len(pending) and len({r['source_object_id'] for r in ordered})==len(pending)


def test_source_candidates_do_not_inherit_an_existing_program_policy(service):
    from backend.db import ProgramMapping
    from backend.program_hierarchy import program_id
    pid=program_id('공공주택 건설','UNASSIGNED')
    with service.sessions.begin() as db:
        db.add(ProgramMapping(id=pid,name='공공주택 건설',seed_policy_id='UNASSIGNED',policy_id='POL_2025_0907',status='CONFIRMED',revision_no=1,basis='승인',evidence_url='https://example.org'))
        m=Mapping(project_id='candidate',policy_id='UNASSIGNED',status='REVIEW',basis='신규 후보',evidence_url='https://example.org')
        db.add(m);db.flush()
        service._attach_program(db,m,dict(program='공공주택 건설',policy_candidate_only=True),{})
        assert m.program_id=='UNASSIGNED' and m.policy_id=='UNASSIGNED'
        approved=db.get(ProgramMapping,pid)
        assert approved.status=='CONFIRMED' and approved.policy_id=='POL_2025_0907'
