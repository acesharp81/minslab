from backend.stage_chronology import field_tag,propagate_upcoming,estimated_field


def test_quantity_assumption_does_not_make_lh_source_date_estimated():
    value={'inferred':True,'manual':True,'field_provenance':{'units':{'rule':'PROJECT_CAPACITY_ASSUMPTION'}}}
    source={'date':'2025-12-31','evidence_url':'https://www.lh.or.kr/a'}
    assert field_tag(value,source,'date')['code']=='OFFICIAL'
    assert field_tag(value,source,'units')['code']=='ESTIMATED'
    assert estimated_field({'field_provenance':{'event_date':{'rule':'BEST_SOURCE_SELECTED','basis':'관리 추정일'}}},'date')


def cells():
    return {s:{'management':{'target':[dict(milestone=s,date='2026-12-31' if s=='APPROVAL' else None,units=None)],'measurement':[dict(milestone=s,date=None,units=None)],'remaining':[dict(milestone=s,field=k,code='UNRESOLVED',label='추가 확인 필요') for k in ('target.date','measurement.date','measurement.units')]}} for s in ('APPROVAL','CONSTRUCTION','COMPLETION','SUPPLY','MOVE_IN')}


def test_future_approval_propagates_through_absent_actuals_but_not_targets():
    c=cells();propagate_upcoming(c,'2026-10-22')
    for v in c.values():
        assert v['management']['measurement'][0]['field_tags']['date']['code']=='UPCOMING'
        assert v['management']['remaining'][0]['code']=='UNRESOLVED'


def test_actual_supply_and_overdue_targets_survive_upcoming_propagation():
    c=cells();c['SUPPLY']['management']['measurement'][0].update(date='2026-09-01',units=300)
    c['CONSTRUCTION']['management']['target'][0]['date']='2026-09-30'
    propagate_upcoming(c,'2026-10-22')
    assert c['SUPPLY']['management']['measurement'][0]['units']==300
    assert c['CONSTRUCTION']['management']['remaining'][1]['code']=='UNRESOLVED'


def test_estimate_correction_is_idempotent_and_never_changes_source_dates():
    from backend.stage_chronology import constrain_estimated_dates
    rows={'APPROVAL':dict(event_date='2026-04-30',inferred=True), 'CONSTRUCTION':dict(event_date='2026-02-06',inferred=False)}
    assert len(constrain_estimated_dates(rows,'event_date'))==1
    assert rows['APPROVAL']['event_date']=='2026-02-06'
    assert rows['APPROVAL']['inferred']
    assert constrain_estimated_dates(rows,'event_date')==[]
    source={'APPROVAL':dict(event_date='2026-01-15'), 'CONSTRUCTION':dict(event_date='2025-12-31',inferred=True,field_provenance={'units':{'rule':'PROJECT_CAPACITY_ASSUMPTION'}})}
    assert constrain_estimated_dates(source,'event_date')==[]
