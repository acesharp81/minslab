from copy import deepcopy
from datetime import date
from unittest.mock import patch
import pytest
from sqlalchemy import create_engine, select, func
from backend.db import Base, Mapping, Audit, Revision, upsert_revision
from backend.service import HomeService
from backend.policy_delivery_comparison import _events
from scripts.reconcile_named_starts_deep_20261020 import SPECS, POLICY, reconcile, validate_source


def test_extract_correct_supply_column_and_exact_start_date():
    spec=deepcopy(SPECS[1])
    valid=b'<table><tr><td>4</td><td>2026-02-06</td><td>'+ '동작구'.encode()+b'</td><td>'+ '흑석11'.encode()+b'</td><td>x</td><td>x</td><td>1,829</td><td>1,515</td></tr></table>'
    assert len(validate_source(spec,valid))==64
    with pytest.raises(ValueError,match='행 불일치'):validate_source(spec,valid.replace(b'<td>1,515</td>',b'<td>1,829</td>'))
    with pytest.raises(ValueError,match='행 불일치'):validate_source(spec,valid.replace(b'2026-02-06',b'2026-03-26'))


def test_pin_sources_preserves_officer_inputs_and_is_idempotent(tmp_path):
    engine=create_engine('sqlite://');Base.metadata.create_all(engine);service=HomeService(engine,tmp_path)
    for spec in SPECS:(tmp_path/(spec['key']+'.html')).write_text('pinned')
    with service.sessions.begin() as db:
        for spec in SPECS:
            r,_=upsert_revision(db,'project','test',spec['name'],dict(name=spec['name'],planned_units=spec['units']),'test')
            db.flush();r.entity_id=spec['pid']
            db.add(Mapping(project_id=spec['pid'],policy_id=POLICY,status='CONFIRMED',revision_no=1,basis='approved',evidence_url='https://test'))
        upsert_revision(db,'project_profile','officer','saved',{'base_date':'2026-10-20','progress':{'CONSTRUCTION':{'event_date':'2026-08-15','units':3178,'inferred':True}}},'test')
    with patch('scripts.reconcile_named_starts_deep_20261020.validate_source',return_value='sha'):
        reconcile(service,tmp_path,True)
        with service.sessions() as db:before=db.scalar(select(func.count()).select_from(Audit))
        result=reconcile(service,tmp_path,True)
        with service.sessions() as db:assert before==db.scalar(select(func.count()).select_from(Audit))
    assert result['protected_before']==result['protected_after'] and result['added_projects']==0
    links=service.rows('evidence_bridge')
    assert len(links)==3
    assert sorted(r['facts'][0]['date_basis'] for r in links)==['EVENT','EVENT','OBSERVED_BY']
    assert all(r['status']=='CONFIRMED' for r in links)
    held=[r for r in service.rows('document_evidence') if r.get('review_decision')=='HOLD_OFFICIAL_ACTUAL_SOURCE']
    assert len(held)==4 and all(r['facts']==[] and r['units'] is None and r['exclude_from_project_totals'] for r in held)
    informal=[r for r in held if r['checked_source_type']=='NON_OFFICIAL']
    assert len(informal)==3 and all(r['review_label'].startswith('담당자 확인 - 비공식 자료: 이투데이') for r in informal)
    assert all(r['officer_review_status']=='CONTENT_CHECKED' and not r['official_actual_verified'] for r in informal)
    assert service.rows('project_profile')[0]['progress']['CONSTRUCTION']['event_date']=='2026-08-15'


def test_two_independent_dates_never_double_count_same_project():
    c=dict(id='p',units=1430,mapping_status='CONFIRMED',events=[
        dict(stage='CONSTRUCTION',event_date='2026-05-06',units=1430,origin='LINKED_EVIDENCE',date_basis='EVENT'),
        dict(stage='CONSTRUCTION',event_date='2026-10-16',units=1430,origin='LINKED_EVIDENCE',date_basis='OBSERVED_BY')])
    series=_events([c],'CONSTRUCTION',date(2026,10,20),'1900-01-01',cumulative=True)
    assert [r['units'] for r in series]==[1430,1430]


def test_event_day_and_observation_bound_are_distinct_in_editor_defaults():
    from backend.project_profile import progress_default
    observation=dict(kind='ACTUAL',milestone='CONSTRUCTION',date='2026-10-16',units=1430,date_basis='OBSERVED_BY')
    exact=dict(kind='ACTUAL',milestone='CONSTRUCTION',date='2026-05-06',units=1430,date_basis='EVENT')
    result=progress_default(dict(sources=[observation,exact]),'CONSTRUCTION')
    assert result['event_date']=='2026-05-06' and result['units']==1430
    assert result['display_note']=='수집 실적'
    only_observed=progress_default(dict(sources=[observation]),'CONSTRUCTION')
    assert only_observed['event_date']=='' and only_observed['observed_by']=='2026-10-16'
    conflicting=progress_default(dict(sources=[observation,dict(exact,date='2026-10-20')]),'CONSTRUCTION')
    assert conflicting['event_date']=='' and conflicting['display_note']=='원천 상충 · 근거 확인'
