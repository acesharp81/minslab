from backend.schedule_period import schedule_period
from backend.seoul_cleanup import matches,parse_history,address_key
from backend.sequence_audit import sequence_checks
from backend.roadmap import source_events
from datetime import date
import pytest

@pytest.mark.parametrize('raw,expected',[('2027년 3분기','2027-09'),('2027년 하반기','2027-12'),('2027년 상반기','2027-06'),('2027년 3~5월','2027-05'),('2027-11~2028-02','2028-02'),('2027~2028년','2028-12'),('2027년','2027-12'),('2027.3','2027-03')])
def test_end_month(raw,expected):
    p=schedule_period(raw);assert p['month']==expected;assert p['original']==raw
@pytest.mark.parametrize('raw',['미정','2027년 이후','2027년 5분기','2027-13','2027-02-30','2028~2027','하반기'])
def test_unknown_not_dates(raw):assert schedule_period(raw) is None

def test_address_range_matches_representative_only():
    p=dict(region='서울특별시',municipality='영등포구',name='양평14',address='서울특별시 영등포구 양평동2가 29-6번지 일대')
    r=dict(municipality='영등포구',name='양평제14구역',address='서울특별시 영등포구 양평동2가 29-6')
    assert matches(p,r)
    assert not matches(p,dict(r,address='양평동2가 29-60'))
    assert not matches(p,dict(r,municipality='동작구'))

def test_history_application_not_approval():
    body='<li class="foldings-li"><div class="foldings-in-wrap"><span>사업시행인가</span></div><ul class="check-list01"><li><h3 class="tit">2025- 05- 29</h3>[(변경)인가신청]</li><li><h3 class="tit">2025-11-24</h3>[(변경)인가]</li></ul></li>'
    f=parse_history(body,'2026-10-13');assert len(f)==1;assert f[0]['date']=='2025-11-24';assert f[0]['stage']=='APPROVAL'

def test_future_movein_does_not_create_preceding_actuals():
    cells={'MOVE_IN':dict(sources=[dict(kind='PLAN',date='2028-01')])}
    checks=sequence_checks(cells);assert checks;assert all(c['priority']=='NORMAL' for c in checks)
    assert cells['MOVE_IN']['sources'][0]['kind']=='PLAN'

def test_gh_range_reaches_graph_without_recollect():
    r=dict(source_id='gh_supply_plan',source_supply_label='2027년 하반기',source_move_in_label='2028년 3분기',planned_units=100)
    e=source_events(r,date(2026,10,13));assert {x['month'] for x in e}=={'2027-12','2028-09'}
    assert all(x['date_conversion']=='PERIOD_END' for x in e)

def test_gh_first_notice_range_retains_original_and_end_month():
    raw='2026년 5~6월 중(최초)'
    p=schedule_period(raw)
    assert p['due_date']=='2026-06-30' and p['precision']=='MONTH_RANGE'
    assert p['original']==raw and p['conversion']=='PERIOD_END'
    events=source_events(dict(source_id='gh_supply_plan',planned_units=518,source_supply_label=raw),date(2026,10,19))
    assert len(events)==1 and events[0]['units']==518 and events[0]['stage']=='SUPPLY'
    assert schedule_period('2026년 5~6월 중(취소)') is None

def test_sh_split_columns_allow_quarter():
    from backend.sh_apis import scheduled_month
    assert scheduled_month({'공급시기 예정 년도':2027,'공급시기 예정월':'3분기'})=='2027-09'

def test_lh_raw_range_preserved_in_source_events():
    row=dict(source_id='lh_rent',rows=[dict(units=10,supply_month=None,supply_raw='2027년 하반기')])
    event=source_events(row,date(2026,10,13))[0]
    assert event['month']=='2027-12' and event['source_date_label']=='2027년 하반기'
    assert event['date_conversion']=='PERIOD_END'

def test_stored_supply_does_not_sum_partial_or_share_document():
    from backend.evidence_bridge import supply_notices
    class Service:
        def rows(self,kind,reference):
            if kind!='evidence_bridge':return []
            base=dict(source_entity_id='doc',source_name='SH 모집',evidence_source_id='official_document',status='REVIEW',evidence_url='https://example.gov',facts=[dict(stage='SUPPLY',kind='ACTUAL',date='2026-02-27',units=381)])
            return [dict(base,project_id='one'),dict(base,project_id='two')]
    assert supply_notices(Service(),date(2026,10,13))=={}

def test_seoul_refresh_preserves_officer_decision():
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool
    from backend.db import Base,upsert_revision
    from backend.service import HomeService
    from backend.seoul_cleanup import reconcile
    from backend.evidence_bridge import review
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine);service=HomeService(engine)
    try:
        p=dict(name='서울 테스트',region='서울특별시',municipality='노원구',base_date='2026-01-01',warnings=[],evidence_url='https://cleanup.seoul.go.kr/',planned_units=100)
        with service.sessions.begin() as db:r,_=upsert_revision(db,'project','sh_inventory','one',p,'test');pid=r.entity_id
        def document(day):
            payload=dict(p,matched_project_ids=[pid],matching_basis='주소 일치',facts=[dict(stage='BUSINESS',kind='ACTUAL',date=day,basis='공식 추진경과')])
            with service.sessions.begin() as db:upsert_revision(db,'document_evidence','seoul_cleanup','one',payload,'test')
        document('2025-01-01');assert reconcile(service)['added']==1
        document('2025-02-01');assert reconcile(service)['refreshed']==1
        link=service.rows('evidence_bridge')[0];assert link['source_revision_no']==2
        review(service,link['id'],link['revision_no'],'CONFIRMED','담당자 원문 대조 완료')
        document('2025-03-01');assert reconcile(service)['preserved']==1
        link=service.rows('evidence_bridge')[0];assert link['source_revision_no']==2 and link['status']=='CONFIRMED'
    finally:engine.dispose()
