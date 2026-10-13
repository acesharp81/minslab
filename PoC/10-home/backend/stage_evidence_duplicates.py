"""Explain repeated stored evidence references without rematching or deleting links."""
from collections import defaultdict
from copy import deepcopy


def annotate_duplicates(items, projects):
    from .stage_evidence import evidence_key, norm
    rows=deepcopy(items)
    groups=defaultdict(list)
    for row in rows:
        row.update(duplicate_suspected=False,duplicate_reasons=[],duplicate_peers=[])
        p=projects[row['project_id']]
        identity=evidence_key(p) or (p.get('region'),norm(p['name']))
        for c in ([row['selected']] if row.get('selected') else [])+row.get('candidates',[]):
            c.update(duplicate_suspected=False,duplicate_reasons=[],duplicate_peers=[])
            # A common catalogue/PDF URL alone is never evidence of duplicate data.
            if c.get('source_entity_id'):
                groups[(row['stage'],identity,c.get('source_id'),c['source_entity_id'])].append((row,c))
    for entries in groups.values():
        owners={r['project_id']:r for r,c in entries}
        if len(owners)<2:
            continue  # Selected evidence appearing in its own candidate list is normal.
        reason='같은 사업 식별 범위·단계에서 동일 원천 기록을 여러 사업 기록이 참조합니다. 전체·부분 물량 관계 확인 필요'
        for row,c in entries:
            peers=[dict(project_id=pid,name=r['name'],planned_units=r.get('planned_units')) for pid,r in owners.items() if pid!=row['project_id']]
            c.update(duplicate_suspected=True,duplicate_reasons=[reason],duplicate_peers=peers)
            row['duplicate_suspected']=True
            if reason not in row['duplicate_reasons']:row['duplicate_reasons'].append(reason)
            known={p['project_id'] for p in row['duplicate_peers']}
            row['duplicate_peers'].extend(p for p in peers if p['project_id'] not in known)
    return rows
