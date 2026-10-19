"""The source construction row, not plan capacity, attests event quantity."""
import io
import zipfile
from datetime import date, timedelta
from xml.sax.saxutils import escape
from sqlalchemy import create_engine, select
from sqlalchemy.pool import StaticPool
import pytest
from backend.collectors import parse_construction
from backend.evidence_bridge import facts
from backend.db import Base, Revision, upsert_revision, now
from backend.service import HomeService
from backend.independent_metrics import freeze


def source_row(name='고양창릉 S-3BL 아파트 건설공사', units='1282', start='26-04-15'):
    values=['경기북부지역본부','고양','건축','S-03','고양창릉',name,'시공사','100',units,'호',start,'29-10-31','0']
    xml='<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:tbl><w:tr>'
    xml+=''.join('<w:tc><w:p><w:r><w:t>'+escape(v)+'</w:t></w:r></w:p></w:tc>' for v in values)
    xml+='</w:tr></w:tbl></w:body></w:document>'
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w') as z:z.writestr('word/document.xml',xml)
    return dict(parse_construction(stream.getvalue(),'2026-07-01')[0][0][2],evidence_url='https://www.lh.or.kr/source.docx')


def starts(row):
    return [f for f in facts(row,date(2026,10,17)) if f['kind']=='ACTUAL' and f.get('milestone')=='CONSTRUCTION']


def test_construction_row_retains_quantity_even_when_plan_capacity_differs():
    row=source_row()
    row['planned_units']=9999
    assert starts(row)[0]['units']==1282
    assert starts(row)[0]['date']=='2026-04-15'
    assert row['construction_start_evidence']['source_row'][8:11]==['1282','호','26-04-15']


@pytest.mark.parametrize('change',[
    {'construction_start_evidence':{}},
    {'warnings':['MULTI_SITE_CONTRACT']},
    {'start_actual_date':'2026-05-01'},
    {'construction_start_evidence':dict(event_date='2026-04-15',units=1282,unit='건',work_type='토목',scope='SINGLE_BLOCK')},
])
def test_ordinary_capacity_or_ambiguous_proof_never_fills_quantity(change):
    assert starts(dict(source_row(),**change))[0].get('units') is None


def test_multisite_zero_and_future_rows_are_not_verified_starts():
    assert starts(source_row(name='고양창릉 S-3BL 및 S-4BL 건설공사'))[0].get('units') is None
    assert starts(source_row(units='0'))[0].get('units') is None
    assert starts(source_row(start='26-08-01'))==[]


def test_reparsed_source_restores_actual_once_and_keeps_historical_snapshot():
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine);s=HomeService(engine)
    row=source_row();old=dict(row);old.pop('construction_start_evidence')
    with s.sessions.begin() as db:
        r,_=upsert_revision(db,'project','lh_construction','s3',old,'old')
        r.recorded_at=now()-timedelta(minutes=10)
    before=freeze(s,'김민','수정 전',known_at=now()-timedelta(minutes=5))
    with s.sessions.begin() as db:
        upsert_revision(db,'project','lh_construction','s3',row,'new')
        upsert_revision(db,'project','duplicate_source','s3',row,'new')
    after=freeze(s,'김민','공식 발표 후 도출된 보완 사항 적용')
    metric=lambda snap:next(m for m in snap['result']['metrics'] if m['metric_code']=='CONSTRUCTION_STARTED')
    assert metric(before)['value'] is None
    assert metric(after)['value']==1282
    assert len(metric(after)['event_ids'])==1
    assert not metric(after)['publishable']
    with s.sessions() as db:
        revisions=db.scalars(select(Revision).where(Revision.source_id=='lh_construction').order_by(Revision.revision_no)).all()
        assert 'construction_start_evidence' not in revisions[0].payload
        assert revisions[1].previous_id==revisions[0].id
    engine.dispose()


def test_permit_audit_reports_zero_as_unresolved_and_respects_knowledge_time():
    from backend.construction_audit import permit_candidates
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine);s=HomeService(engine);boundary=now()-timedelta(minutes=5)
    row=dict(name='허가 행',region='경기도',units=0,base_date='2026-01-01',
             dates={'원천 착공일 (stcnsDay)':'2026-04-15'})
    with s.sessions.begin() as db:
        old,_=upsert_revision(db,'permit','building_hub','one',row,'old')
        old.recorded_at=boundary-timedelta(minutes=1)
    with s.sessions.begin() as db:
        upsert_revision(db,'permit','building_hub','one',dict(row,units=100),'new')
        upsert_revision(db,'permit','building_hub','outside',dict(row,dates={'원천 착공일 (stcnsDay)':'2025-04-15'}),'new')
    past=permit_candidates(s,boundary,'2026-01-01','2026-10-17')
    assert past['candidate_rows']==1
    assert past['quantity_states']=={'ZERO_QUANTITY_UNRESOLVED':1}
    assert not past['counted_as_actual']
    current=permit_candidates(s,now(),'2026-01-01','2026-10-17')
    assert current['quantity_states']=={'POSITIVE_UNVERIFIED':1}
    assert current['candidate_rows']==1 and not current['counted_as_actual']
    engine.dispose()
