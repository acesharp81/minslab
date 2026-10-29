"""Original checklist projection; never creates or upgrades model verdicts."""
from collections import Counter
from .rules import PACK


def build(run):
    pack=run.get('rule_pack',PACK);selected=set(run.get('selected',[]))
    overrides={r['finding_id']:r['status'] for r in run.get('reviews',[])}
    items=[]
    for parent in pack['parents']:
        steps=[s for s in pack['steps'] if s['parent_id']==parent['id']]
        ids={s['rule_id'] for s in steps}
        raw=[r for r in run['results'] if r['rule_id'] in ids]
        # Old special-purpose results remain in their historical report, but
        # cannot be presented as a completed original-checklist AI assessment.
        rows=[r for r in raw if not r.get('model','').startswith('local/')]
        completed={r['rule_id'] for r in rows if r['status'] not in ('NOT_RUN','ERROR')}
        missing=ids-completed
        groups={}
        for row in rows:
            status=overrides.get(row.get('id'),row['status'])
            key=(status,row.get('observation',''),row.get('reason',''),row.get('recommended_action',''),row.get('model',''))
            g=groups.setdefault(key,{'status':status,'observation':row.get('observation',''),'reason':row.get('reason',''),
                'action':row.get('recommended_action',''),'model':row.get('model',''),'rule_ids':[],'finding_ids':[],
                'reference_ids':[],'evidence_ids':[]})
            for field,values in [('rule_ids',[row['rule_id']]),('finding_ids',[row.get('id')]),('reference_ids',row.get('reference_ids',[])),('evidence_ids',row.get('evidence_ids',[]))]:
                g[field]=list(dict.fromkeys(g[field]+[x for x in values if x]))
        ordered=sorted(groups.values(),key=lambda g:pack['status_priority'].index(g['status']))
        states=[g['status'] for g in ordered]
        status=next((s for s in pack['status_priority'] if s in states),'NOT_RUN')
        if missing and status in ('PASS','NOT_APPLICABLE'):status='NOT_RUN'
        items.append({**parent,'status':status,'evaluations':ordered,'step_count':len(ids),'assessed_count':len(completed),
            'requested_count':len(ids&selected),'missing_rule_ids':sorted(missing),'complete':not missing,
            'technical_evidence':run.get('structural_checks') if parent['id']=='H-04' else None})
    return {'version':pack['version'],'items':items,'total':len(items),'complete_count':sum(i['complete'] for i in items),
        'step_total':len(pack['steps']),'assessed_steps':sum(i['assessed_count'] for i in items),
        'requested_steps':len(selected),'counts':dict(Counter(i['status'] for i in items))}
