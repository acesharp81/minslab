from backend.input_status import input_status,input_label
from backend.stage_display import annotate
from tests.test_officer_completion import cells
from datetime import date

def test_confirmed_sources_and_adopted_values_are_separate_from_estimates():
    assert input_label(dict(origin='MANUAL',input_rule='SOURCE_ACCEPTED'))=='확인 완료'
    assert input_label(dict(source_id='LH',officer_confirmed=True))=='확인 완료'
    assert input_label(dict(source_id='LH'))=='수집완료'
    assert input_label(dict(origin='MANUAL',inferred=True,officer_confirmed=True))=='추정 입력(미수집)'

def test_unavailability_requires_explicit_decision_not_missing_or_future_data():
    v=dict(inferred=True)
    assert input_label(v,dict(status='METHOD_UNKNOWN'))=='추정 입력(미수집)'
    assert input_label(v,dict(status='UPCOMING'))=='추정 입력(미수집)'
    assert input_label(v,dict(status='COLLECTION_UNAVAILABLE'))=='추정 입력(수집 불가)'
    assert input_status(dict(inferred=False,origin='MANUAL'),dict(status='COLLECTION_UNAVAILABLE'))=='CONFIRMED'
    assert input_label(dict(inferred=True,input_rule='UNAVAILABLE_POLICY_ESTIMATE'))=='추정 입력(수집 불가)'

def test_partial_field_estimate_cannot_be_presented_as_confirmed():
    v=dict(origin='MANUAL',input_rule='SOURCE_ACCEPTED',field_provenance={'units':{'rule':'PROJECT_CAPACITY_TARGET'}})
    assert input_label(v)=='추정 입력(미수집)'

def test_stage_management_and_source_expansion_share_status():
    c=cells();v=dict(origin='MANUAL',actor='김민',inferred=True,due_date='2027-01-01',units=952)
    c['BUSINESS']['assessment']={'status':'COLLECTION_UNAVAILABLE'}
    c['BUSINESS']['sources']=[dict(source_id='officer',kind='PLAN',**v)]
    annotate(c,dict(planned_units=952),{},dict(BUSINESS=v),date(2026,10,14))
    assert c['BUSINESS']['management']['target'][0]['input_status']=='ESTIMATED_UNAVAILABLE'
    assert c['BUSINESS']['sources'][0]['input_status']=='ESTIMATED_UNAVAILABLE'
    assert all(r['code']=='UPCOMING' for r in c['BUSINESS']['management']['remaining'])

def test_past_goal_with_no_observation_is_not_claimed_as_future_or_completed():
    c=cells();v=dict(origin='MANUAL',actor='김민',inferred=True,due_date='2026-01-01',units=952)
    annotate(c,dict(planned_units=952),{'stage_states':{'BUSINESS':{'status':'NOT_OBSERVED'}}},dict(BUSINESS=v),date(2026,10,14))
    missing=c['BUSINESS']['management']['remaining']
    assert all(r['code']=='NOT_OBSERVED' and r['label']=='미측정 · 실적 근거 없음' for r in missing)
