"""Screen projections of the same ledger; calculate only visible comparisons."""
from datetime import date
from .policy_delivery_comparison import comparison_index, REGIONS


def screen_view(model, group='policy', selected=None):
    if model.get('status')!='READY':return model
    portfolio=model['portfolio_cohorts'];selected=selected or group
    if group=='policy':
        members=portfolio;keys={'policy',*('region:'+r for r in REGIONS)}
        keys.update('city:'+c['municipality_id'] for c in members if c.get('municipality_id'))
    elif group.startswith('program:'):
        pid=group.removeprefix('program:')
        if pid not in model['plan'].get('program_profiles',{}) and not any(c.get('program_id')==pid for c in portfolio):
            raise ValueError('프로그램 범위를 찾을 수 없습니다')
        members=[c for c in portfolio if c.get('program_id')==pid]
        keys={'policy',group}
        keys.update(group+'|region:'+c['region'] for c in members)
        keys.update(group+'|city:'+c['municipality_id'] for c in members if c.get('municipality_id'))
    else:raise ValueError('조회 그룹을 확인하세요')
    # Program screens use the same project ledger as policy screens. The old
    # all-scope response had no program|project entry; provide an explicit alias.
    project_key=None;extra={}
    if selected not in keys:
        sub=selected.removeprefix(group+'|') if group!='policy' else selected
        places={p['id']:p for p in model['geometry']['shapes']}
        if sub.startswith('city:') and sub[5:] in places:
            cid=sub[5:];extra[selected]=dict(name=places[cid]['name'],kind='program_city' if group!='policy' else 'city',id=cid,cohorts=[])
        elif group!='policy' and sub.startswith('region:') and sub[7:] in REGIONS:
            rid=sub[7:];extra[selected]=dict(name=rid,kind='program_region',id=rid,cohorts=[])
        elif sub.startswith('project:') and any('project:'+c['id']==sub for c in members):project_key=sub
        else:raise ValueError('선택 사업이 조회 그룹에 포함되지 않습니다')
        if extra and group!='policy':extra[selected]['program_id']=group.removeprefix('program:')
        keys.add(project_key or selected)
    # The map reads cohort events directly. Build comparison tables only for
    # the selected area/project and its parent; render() requests another scope
    # when selected. Precomputing every city multiplied cold CPU and payload.
    keys={'policy',group,project_key or selected}
    inputs=model['_comparison_inputs'];day=date.fromisoformat(model['as_of_date']);plan=model['plan']
    yearly=comparison_index(plan,model['cohorts'],inputs['config'],inputs['statistics'],day,
        program_cohorts=portfolio,scope_keys=keys,extra_scopes=extra)
    cumulative=comparison_index(dict(plan,period_start='1900-01-01',portfolio=True),portfolio,
        inputs['config'],[],day,scope_keys=keys,extra_scopes=extra)
    if project_key and selected!=project_key:
        for index in (yearly,cumulative):
            if project_key in index:index[selected]=index[project_key]
    # The full report/export endpoint retains all scopes and diagnostics.
    # This endpoint keeps all ledger events/quantities and only visible matrices.
    return dict({k:v for k,v in model.items() if k not in ('_comparison_inputs','goal_comparisons','sources')},
        plan={k:v for k,v in plan.items() if k!='program_profiles'},
        program_assessments={k:v for k,v in model['program_assessments'].items() if group=='program:'+k},
        yearly_comparisons=yearly,portfolio_comparisons=cumulative,view_group=group,view_scope=selected)
