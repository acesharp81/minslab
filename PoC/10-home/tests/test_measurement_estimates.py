from copy import deepcopy
import pytest
from backend.measurement_estimates import reconcile, RULE
from backend.stage_chronology import constrain_estimated_dates
REF='2026-10-22'
def cell(*sources):return {'BUSINESS':dict(sources=list(sources),progress={})}
def goal(day='2025-01-01',units=100):return {'BUSINESS':dict(due_date=day,units=units,source_revision_id='goal-v3')}
def fact(day='2024-01-01',units=40,**kwargs):return dict(kind='ACTUAL',date=day,units=units,source_id='official',**kwargs)
def test_collected_partial_and_zero_values_are_preserved_without_input_mutation():
    for units in (0,40):
        c=cell(fact(units=units));original=deepcopy(c);r=reconcile({},goal(),c,REF)['progress']['BUSINESS']
        assert c==original and r['event_date']=='2024-01-01' and r['units']==units and not r['inferred']
def test_missing_values_equal_own_goal_instead_of_successor_date():
    prior={'BUSINESS':dict(event_date='2025-05-01',units=200,inferred=True,input_rule='PREDECESSOR_ASSUMPTION')}
    c=cell();c['APPROVAL']=dict(sources=[fact('2025-05-01',100,milestone='APPROVAL')])
    r=reconcile(prior,goal(),c,REF)['progress']['BUSINESS']
    assert r['event_date']=='2025-01-01' and r['units']==100 and r['inferred']
    assert all(p['rule']==RULE and p['target_revision_id']=='goal-v3' for p in r['field_provenance'].values())
def test_fields_fall_back_independently_and_collected_date_does_not_move():
    r=reconcile({},goal(),cell(fact(units=None)),REF)['progress']['BUSINESS']
    assert r['event_date']=='2024-01-01' and r['units']==100
    assert r['field_provenance']['event_date']['rule']=='SOURCE_ACCEPTED' and r['field_provenance']['units']['rule']==RULE
    r=reconcile({},goal(),cell(fact(day=None,units=40)),REF)['progress']['BUSINESS']
    assert r['event_date']=='2025-01-01' and r['units']==40
@pytest.mark.parametrize('g,c',[(goal('2027-01-01'),cell()),(goal(),{'BUSINESS':dict(sources=[],progress={'code':'NOT_REACHED_REPORTED'})}),({},cell())])
def test_future_unperformed_or_missing_goals_do_not_create_current_values(g,c):
    assert reconcile({},g,c,REF)['progress']=={}
def test_observation_dates_and_estimated_sources_are_not_collected_event_dates():
    r=reconcile({},goal(),cell(fact(date_basis='OBSERVED_BY')),REF)['progress']['BUSINESS']
    assert r['event_date']=='' and r['units']==40 # target is after the observed upper bound
    r=reconcile({},goal('2023-01-01'),cell(fact(date_basis='OBSERVED_BY')),REF)['progress']['BUSINESS']
    assert r['event_date']=='2023-01-01' and r['units']==40
    assert reconcile({},goal(),cell(fact(inferred=True,input_rule='PREDECESSOR_ASSUMPTION')),REF)['progress']=={}
def test_conflicting_measurements_are_not_replaced_with_goals():
    r=reconcile({},goal(),cell(fact('2024-01-01',20),fact('2024-02-01',40)),REF)
    assert r['conflicts'] and r['progress']=={}
def test_sequence_repair_cannot_move_goal_fallback_to_successor_date():
    rows={'BUSINESS':dict(event_date='2025-01-01',input_rule=RULE,inferred=True),'APPROVAL':dict(event_date='2024-01-01',input_rule='SOURCE_ACCEPTED',inferred=False)}
    before=deepcopy(rows);assert constrain_estimated_dates(rows,'event_date')==[] and rows==before
def test_same_input_versions_produce_no_further_changes():
    g=goal();c=cell(fact(units=None));first=reconcile({},g,c,REF)['progress']
    assert reconcile(first,g,c,REF)['changes']==[]

def test_data_application_appends_revisions_preserves_goals_and_rejects_stale_plan():
    from sqlalchemy import create_engine,select,func
    from backend.db import Base,Revision,Audit,upsert_revision
    from backend.service import HomeService
    from scripts.reconcile_measurement_targets_20261022 import apply,STAGES
    e=create_engine('sqlite://');Base.metadata.create_all(e);s=HomeService(e)
    with s.sessions.begin() as db:
        old,_=upsert_revision(db,'project_profile','manual_project','p',dict(project_id='p',progress={'BUSINESS':dict(event_date='2025-05-01',units=100,inferred=True)}),'old')
        goalrow,_=upsert_revision(db,'execution_schedule','officer','p:BUSINESS',dict(due_date='2025-01-01',units=100),'old')
        prior=deepcopy(old.payload);rid=old.id;goalrid=goalrow.id
    after=deepcopy(prior);after['progress']['BUSINESS']['event_date']='2025-01-01'
    refs={stage:goalrid if stage=='BUSINESS' else None for stage in STAGES}
    plan=dict(summary={},updates=[dict(project_id='p',name='P',expected_revision_id=rid,expected_goal_revisions=refs,before=prior,after=after,changes=[])])
    apply(s,plan)
    with s.sessions() as db:
        assert db.get(Revision,rid).payload==prior
        assert db.get(Revision,goalrid).superseded_at is None
        assert db.scalar(select(func.count()).select_from(Audit))==1
        assert len(db.scalar(select(Audit)).action)<=30
    with pytest.raises(ValueError,match='입력 변경'):apply(s,plan)

def test_source_identity_survives_adopted_officer_wrapper_on_recheck():
    raw=fact(units=40,source_entity_id='DOC-1',source_revision_no=3)
    first=reconcile({},goal(),cell(raw),REF)['progress']
    adopted=dict(kind='ACTUAL',date=first['BUSINESS']['event_date'],source_id='officer',**first['BUSINESS'])
    second=reconcile(first,goal(),cell(adopted),REF)
    assert second['changes']==[]
    assert second['progress']['BUSINESS']['field_provenance']['units']['source_entity_id']=='DOC-1'


def stage_cells(**facts):
    return {stage: dict(sources=rows, progress={}) for stage, rows in facts.items()}


def start_goal(when='2025-01-01', units=100):
    return {'CONSTRUCTION': dict(due_date=when, units=units)}


def test_elapsed_goal_and_inferred_predecessor_never_establish_construction():
    prior={'CONSTRUCTION':dict(event_date='2025-01-01', units=100, inferred=True, input_rule='TARGET_EQUALS_MISSING_MEASUREMENT')}
    c=stage_cells(APPROVAL=[fact('2024-01-01',100)], SUPPLY=[fact('2024-05-01',100)])
    assert 'CONSTRUCTION' not in reconcile(prior,start_goal(),c,REF)['progress']
    assert reconcile({},start_goal(),{},REF)['progress']=={}


def test_confirmed_completion_supports_prior_start_at_goal_date_with_witness():
    c=stage_cells(APPROVAL=[fact('2024-01-01',100)],CONSTRUCTION=[fact('2026-01-01',100,milestone='COMPLETION')])
    r=reconcile({},start_goal(),c,REF)['progress']['CONSTRUCTION']
    assert r['event_date']=='2025-01-01' and r['units']==100
    witness=r['field_provenance']['event_date']['sequence_evidence']
    assert witness['witness']['stage']=='COMPLETION' and witness['lower_date']=='2024-01-01' and witness['upper_date']=='2026-01-01'
    first=reconcile({},start_goal(),c,REF)['progress']
    assert reconcile(first,start_goal(),c,REF)['changes']==[]


@pytest.mark.parametrize('when',['2023-12-31','2026-01-02'])
def test_target_outside_confirmed_event_sequence_does_not_become_an_actual(when):
    c=stage_cells(APPROVAL=[fact('2024-01-01',100)],CONSTRUCTION=[fact('2026-01-01',100,milestone='COMPLETION')])
    assert 'CONSTRUCTION' not in reconcile({},start_goal(when),c,REF)['progress']


def test_real_positive_progress_is_an_upper_bound_but_estimated_or_zero_progress_is_not_evidence():
    for pct,inferred,expected in [(20,False,True),(0,False,False),(20,True,False)]:
        c=stage_cells(CONSTRUCTION=[fact('2025-06-01',None,pct=pct,inferred=inferred)])
        r=reconcile({},start_goal(),c,REF)['progress']
        assert ('CONSTRUCTION' in r)==expected
    c=stage_cells(CONSTRUCTION=[fact('2025-06-01',None,pct=20)])
    assert 'CONSTRUCTION' not in reconcile({},start_goal('2025-07-01'),c,REF)['progress']


def test_partial_later_delivery_does_not_expand_missing_predecessor_quantity_to_full_goal():
    c=stage_cells(MOVE_IN=[fact('2026-01-01',30)])
    r=reconcile({},start_goal(),c,REF)['progress']['CONSTRUCTION']
    assert r['event_date']=='2025-01-01' and r['units'] is None
    assert reconcile({},start_goal(units=30),c,REF)['progress']['CONSTRUCTION']['units']==30


def test_inferred_measurements_cannot_be_used_as_evidence_for_more_estimates():
    c=stage_cells(MOVE_IN=[fact('2026-01-01',100,inferred=True,input_rule=RULE)])
    assert reconcile({},start_goal(),c,REF)['progress']=={}


def test_future_collected_date_does_not_support_earlier_estimate():
    c=stage_cells(MOVE_IN=[fact('2027-01-01',100)])
    assert 'CONSTRUCTION' not in reconcile({},start_goal(),c,REF)['progress']


def test_inconsistent_target_dates_are_withdrawn_instead_of_clamped_to_each_other():
    goals={'BUSINESS':dict(due_date='2025-01-01',units=100), 'APPROVAL':dict(due_date='2024-01-01',units=100)}
    c=stage_cells(CONSTRUCTION=[fact('2026-01-01',100)])
    result=reconcile({},goals,c,REF)['progress']
    assert 'BUSINESS' not in result and 'APPROVAL' not in result
    assert result['CONSTRUCTION']['event_date']=='2026-01-01'


def test_earlier_partial_predecessor_is_not_a_permanent_cap_on_later_delivery():
    c=stage_cells(APPROVAL=[fact('2024-01-01',30)], CONSTRUCTION=[fact('2026-01-01',100,milestone='COMPLETION')])
    assert reconcile({},start_goal(),c,REF)['progress']['CONSTRUCTION']['units']==100


def test_independent_manual_event_without_source_wrapper_supports_missing_quantity():
    prior={'BUSINESS':dict(event_date='2024-01-01', units=None, inferred=False)}
    r=reconcile(prior,goal(),{},REF)['progress']['BUSINESS']
    assert r['event_date']=='2024-01-01' and r['units']==100


def test_observed_date_witness_stays_stable_after_adopting_quantity_only_wrapper():
    raw=fact('2024-01-01',40,date_basis='OBSERVED_BY',source_entity_id='DOC-1')
    first=reconcile({},goal('2023-01-01'),cell(raw),REF)['progress']
    wrapper=dict(kind='ACTUAL',date=first['BUSINESS']['event_date'],source_id='officer',**first['BUSINESS'])
    assert reconcile(first,goal('2023-01-01'),cell(raw,wrapper),REF)['changes']==[]


def restored_record():
    import hashlib,json
    from backend.measurement_estimates import REVIEWED_RULE
    values=dict(event_date='2025-01-01',units=100)
    review=dict(status='RESTORED_REVIEWED_ESTIMATE',original_revision_id='original-reviewed-revision',reason='원 채택사유·범위 재검토',
                values_digest=hashlib.sha256(json.dumps(values,sort_keys=True,ensure_ascii=False).encode()).hexdigest())
    return dict(**values,inferred=True,input_rule=REVIEWED_RULE,input_basis='기존 관리 추정 채택',restoration_review=review,
                field_provenance={f:dict(rule=REVIEWED_RULE,value=v) for f,v in values.items()})


def test_reviewed_management_estimate_survives_generic_reconciliation_and_stays_estimated():
    r=restored_record();prior={'BUSINESS':r}
    result=reconcile(prior,goal(),cell(),REF,scope_limit=100)
    assert result['progress']==prior and result['changes']==[]
    c={'CONSTRUCTION':dict(sources=[dict(r,kind='ACTUAL',date=r['event_date'])])}
    assert reconcile({},goal(),c,REF)['progress']=={} # never use management decisions as observed events


def test_reviewed_estimates_do_not_override_new_source_zero_partial_or_conflict():
    for n in (0,40):
        r=reconcile({'BUSINESS':restored_record()},goal(),cell(fact(units=n)),REF)['progress']['BUSINESS']
        assert r['units']==n and r['event_date']=='2024-01-01' and not r['inferred']
    r=reconcile({'BUSINESS':restored_record()},goal(),cell(fact(units=20),fact(units=40)),REF)
    assert r['conflicts'] and r['progress']['BUSINESS']['units'] is None


def test_reviewed_marker_cannot_authorize_changed_values_future_dates_or_other_stages():
    r=restored_record();r['units']=101
    assert reconcile({'BUSINESS':r},goal(),cell(),REF)['progress']=={}
    r=restored_record()
    assert reconcile({'BUSINESS':r},goal(),cell(),REF,scope_limit=99)['progress']=={}
    assert reconcile({'CONSTRUCTION':r},{}, {},REF)['progress']=={}
    assert reconcile({'BUSINESS':r},goal(),{'BUSINESS':dict(sources=[],progress={'code':'NOT_REACHED_REPORTED'})},REF)['progress']=={}
