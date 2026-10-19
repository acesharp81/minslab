from copy import deepcopy
from datetime import timedelta
import io
import zipfile
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.pool import StaticPool
from backend.db import Base, Revision, Audit, upsert_revision, now
from backend.service import HomeService
from backend.matching_corrections import propose, apply, REASON
from backend.ih_public import hwpx_text, scan_pages, notice_fingerprint, parse_inventory
from backend.independent_metrics import freeze, get_snapshot


@pytest.fixture
def service():
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    yield HomeService(engine)
    engine.dispose()


def put(s,kind,source,key,payload):
    with s.sessions.begin() as db:
        r,_=upsert_revision(db,kind,source,key,payload,'test')
        return r.entity_id


def test_reviewed_whole_permit_quantity_withdrawn_without_fabricated_allocation(service):
    p=put(service,'project','lh_rent','p',dict(name='성남금토 A2',region='경기도',planned_units=438,base_date='2026-01-01',evidence_url='https://example.org/p'))
    source=put(service,'permit','building_hub','s',dict(name='성남금토 A2',region='경기도',units=633,base_date='2026-01-01',evidence_url='https://example.org/s'))
    put(service,'stage_evidence','stage_match',p+':APPROVAL',dict(project_id=p,name='성남금토 A2',region='경기도',base_date='2026-01-01',stage='APPROVAL',status='CONFIRMED',reviewed=True,
        selected=dict(source_entity_id=source,source_revision_no=1,source_id='building_hub',source_name='성남금토 A2',event_date='2026-01-01',units=633,method='OFFICER_CONFIRMATION',basis='자동매칭 확인 완료',evidence_url='https://example.org/s')))
    sources={r['id']:r for r in service.rows('permit')}
    changes=propose(service.rows('project'),[],service.rows('stage_evidence'),sources)
    assert len(changes)==1
    before=freeze(service,'김민','정정 전')
    result=apply(service,changes)
    assert result['count']==1 and result['items'][0]['reason']==REASON
    link=service.rows('stage_evidence')[0]
    assert link['status']=='CONFIRMED' and link['selected']['source_entity_id']==source
    assert link['selected']['units'] is None and link['selected']['source_units']==633
    after=freeze(service,'김민',REASON)
    assert not after['result']['selected_events']
    assert get_snapshot(service,before['id'])['result']['selected_events'][0]['quantity']==633
    assert not propose(service.rows('project'),[],service.rows('stage_evidence'),sources)
    with pytest.raises(ValueError):apply(service,changes)
    with service.sessions() as db:
        audit=db.scalar(select(Audit).where(Audit.action=='STAGE_EVIDENCE_REVIEW'))
        assert audit.before['selected']['units']==633 and audit.after['reason']==REASON


def test_full_and_contained_scope_correction_retains_direct_fact(service):
    p=dict(id='p',planned_units=381)
    source=dict(id='s',planned_units=577,verification_status='SOURCE_CONTENT_CHECKED')
    b=dict(id='b',revision_no=2,project_id='p',source_entity_id='s',status='CONFIRMED',relation_type='SAME_SCOPE',facts=[dict(stage='SUPPLY',kind='ACTUAL',units=381)])
    changes=propose([p],[b],[],{'s':source})
    assert changes[0]['payload']['relation_type']=='CONTAINED_SCOPE'
    assert changes[0]['payload']['facts'][0]['units']==381
    assert changes[0]['payload']['facts'][0]['source_total_units']==577
    assert b['relation_type']=='SAME_SCOPE'
    assert not propose([p],[dict(b,status='RELEASED')],[],{'s':source})
    assert not propose([p],[dict(b,facts=[dict(units=577)])],[],{'s':source})


def test_amended_approval_stage_link_keeps_event_semantics(service):
    p=put(service,'project','lh_sale','p',dict(name='계양 A17',district='인천계양',block='A17',region='인천광역시',planned_units=309,base_date='2026-01-01',evidence_url='https://example.org/p'))
    source=put(service,'document_evidence','official_document','s',dict(name='계양 A17 변경승인',region='인천광역시',base_date='2026-01-01',evidence_url='https://example.org/s'))
    put(service,'stage_evidence','stage_match',p+':APPROVAL',dict(project_id=p,base_date='2026-01-01',stage='APPROVAL',status='CONFIRMED',selected=dict(source_entity_id=source,source_revision_no=1,source_id='official_document',event_type='AMENDED_APPROVAL',units=309,source_units=463,scope_partial=True,event_date='2026-06-30',evidence_url='https://example.org/s')))
    events=freeze(service,'김민',REASON)['result']['selected_events']
    assert events[0]['event_type']=='APPROVAL_AMENDED'
    assert events[0]['quantity_scope']=='PART' and events[0]['source_total_units']==463


def test_archive_scan_continues_after_backfill_and_overlaps_boundaries():
    pages,cursor=scan_pages(dict(next_page=10,complete_window=False))
    assert 9 in pages and 10 in pages and pages[:2]==[1,2]
    pages,_=scan_pages(dict(next_page=94,complete_window=True,revisit_next_page=43))
    assert pages==[1,2,43,44]


def test_hwpx_paragraphs_keep_explicit_quantity_and_reject_external_definitions():
    def archive(body):
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w') as z:z.writestr('Contents/section0.xml',body)
        return out.getvalue()
    assert '금회 공급 381호' in hwpx_text(archive('<section><p><t>금회 공급 </t><t>381호</t></p></section>'))
    with pytest.raises(ValueError):hwpx_text(archive('<!DOCTYPE x><section/>'))
    p=dict(name='공고',source_date='2026-01-01',content_text='본문',attachments=[dict(name='공고.hwpx',url='https://www.ih.co.kr/f')])
    assert notice_fingerprint(p)==notice_fingerprint(dict(p,views=100,original_sha256='new'))
    assert notice_fingerprint(p)!=notice_fingerprint(dict(p,attachments=[]))


def test_new_inventory_path_separates_program_stock_and_actual_events():
    body='''<table class="list"><thead><tr><th>입주년월</th></tr></thead><tbody>
    <tr><td>공공임대</td><td>운영중</td><td><a href="/main/lease/leaseAptDetail.do?apt_seq=39">구월 1단지</a></td><td>남동구</td><td>511</td><td>2013년 3월</td><td>2015년 6월</td></tr>
    <tr><td>맞춤형임대</td><td>운영중</td><td><a href="/main/lease/leaseAptDetail.do?apt_seq=51">기존주택 매입임대사업</a></td><td>인천 전역</td><td></td><td>2016년 ~</td><td></td></tr>
    </tbody></table>'''
    rows=parse_inventory(body.encode())
    assert rows[0]['stock_units']==511 and rows[0]['facts']==[]
    assert rows[1]['record_scope']=='PROGRAM' and rows[1]['stock_units'] is None
    assert all('start_actual_date' not in r for r in rows)


def test_overview_household_columns_never_count_buildings_or_tenants():
    from backend.seoul_cleanup import parse_overview
    tables=''.join(f'<table><caption>주택공급계획 {kind}</caption><tr>'+''.join(f'<td>{v}</td>' for v in ['', '', '', '30', '', *parts, ''])+'</tr></table>'
        for kind,parts in [('분양',['530','659','60']),('임대',['141','92','33'])])
    r=parse_overview((tables+'<p>세입자 3,177명</p>').encode())
    assert r['housing_plan_total']==1515 and r['housing_plan_components']=={'분양':1249,'임대':266}
    assert r['overview_date_status']=='UNDATED_PLAN'


def test_benchmark_requires_period_and_primary_actuals_not_matching_sum():
    from backend.integrity_diagnostics import evaluate
    snap=dict(id='s',context=dict(known_at='2026-10-17T00:00:00+09:00'),result=dict(selected_events=[],exclusions=[],conflicts=[],metrics=[]))
    delivery=dict(plan=dict(target_units=1350000,annual=[]),portfolio_cohorts=[dict(id='p',name='고양창릉 S03',events=[dict(stage='CONSTRUCTION',status='ACTUAL',event_date='2026-04-01',units=2306,inferred=True)])])
    annual=dict(rows=[dict(year=2026,region='서울특별시',metrics={'착공':dict(units=20679,periods=8,through_period='202608')})])
    r=evaluate(snap,[],delivery,annual,[],{})
    assert len(r['agreement']['rows'])==53 and r['agreement']['numeric_rows']==47
    assert r['agreement']['confirmed_matches']==2
    assert r['agreement']['independent_actual_matches']==0
    s01=next(x for x in r['agreement']['rows'] if x['id']=='S01')
    assert s01['state']=='pending' and '추정' in s01['explanation']
    annual['rows'][0]['metrics']['착공']['through_period']='202609'
    assert evaluate(snap,[],delivery,annual,[],{})['agreement']['confirmed_matches']==1


def test_round_replacement_rolls_back_failed_registration_and_preserves_baseline(service,tmp_path):
    from backend.data_integrity import save_round,replace_consolidated_round,rounds
    service.data_dir=tmp_path
    report=dict(display_score=50,total_score=50,categories=[dict(items=[dict(id=str(i),weight=2.5,score=1.25) for i in range(40)])])
    html='<!doctype html><html></html>'
    save_round(service,'HOME-INTEGRITY-R00',0,report,html,'김민','최초')
    current=deepcopy(report)
    for i in current['categories'][0]['items']:i.update(previous_score=i['score'],change_comment='유지')
    save_round(service,'HOME-INTEGRITY-R01',1,current,html,'김민','이전',parent_id='HOME-INTEGRITY-R00')
    save_round(service,'HOME-INTEGRITY-R02',2,current,html,'김민','이전',parent_id='HOME-INTEGRITY-R01')
    invalid=deepcopy(current);invalid['categories'][0]['items'][0]['previous_score']=0
    with pytest.raises(ValueError):replace_consolidated_round(service,'new',invalid,html,'김민','통합')
    assert len(rounds(service)['items'])==3
    replace_consolidated_round(service,'new',current,html,'김민','통합')
    assert [r['id'] for r in rounds(service)['items']]==['new','HOME-INTEGRITY-R00']
    assert len(list((tmp_path/'remediation/retired-rounds-20261017').glob('*.json')))==2
