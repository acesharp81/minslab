"""Conserved map slices and cumulative stage attainment, bounded by evidence date."""
from collections import defaultdict

STAGES = ('POLICY', 'BUSINESS', 'APPROVAL', 'CONSTRUCTION', 'SUPPLY', 'MOVE_IN')


def evidence_events(service, reference):
    from .stage_evidence import linked_events
    from .evidence_bridge import by_project
    events = defaultdict(list)
    for pid, rows in linked_events(service, reference).items():
        events[pid].extend(rows)
    for pid, bridges in by_project(service, reference).items():
        for bridge in bridges:
            if bridge.get('status') not in ('REVIEW', 'CONFIRMED'):
                continue
            for fact in bridge.get('facts', []):
                if fact.get('kind') != 'ACTUAL' or fact.get('scope_partial'):
                    continue
                events[pid].append(dict(stage=fact.get('stage'), event_date=fact.get('date'),
                                        units=fact.get('units'), status='ACTUAL'))
    for config in service.rows('delivery_setting', reference):
        for event in config.get('events', []):
            events[event['project_id']].append(event)
    return events


def cohort_parts(selected, rows, links, events, reference, key_for):
    """One partition per inventory owner; plans cannot advance observed stages."""
    peers = defaultdict(list)
    for row in rows:
        peers[key_for(row) or ('ID', row['id'])].append(row)
    result = {}
    cutoff = reference.isoformat()
    for owner in selected:
        cap = owner.get('planned_units')
        if cap is None or cap <= 0:
            continue
        reached = defaultdict(int)
        for row in peers[key_for(owner) or ('ID', owner['id'])]:
            if 'MULTI_SITE_CONTRACT' in row.get('warnings', []):
                continue
            facts = list(events.get(row['id'], []))
            if row.get('start_actual_date'):
                facts.append(dict(stage='CONSTRUCTION', event_date=row['start_actual_date']))
            report_date = row.get('progress_date') or row.get('base_date')
            if (row.get('progress_pct') or 0) > 0 or row.get('stage') == 'COMPLETED':
                facts.append(dict(stage='CONSTRUCTION', event_date=report_date))
            notice = links.get(row['id'])
            if notice:
                facts.append(dict(stage='SUPPLY', event_date=notice.get('source_date'), units=notice.get('units')))
            for fact in facts:
                stamp = fact.get('event_date')
                if fact.get('status', 'ACTUAL') != 'ACTUAL' or not stamp or len(stamp) != 10 or stamp > cutoff:
                    continue
                stage = 'CONSTRUCTION' if fact.get('stage') == 'COMPLETION' else fact.get('stage')
                if stage not in STAGES[1:]:
                    continue
                units = fact.get('units')
                # A same-block construction contract may include other tenures.
                # Reuse only the portion proven to fit this inventory cohort.
                if units is None:
                    peer_cap = row.get('planned_units')
                    if row['id'] != owner['id'] and peer_cap not in (None, cap):
                        continue
                    units = cap
                if 0 <= units <= cap:
                    reached[stage] = max(reached[stage], units)
        parts = {stage: 0 for stage in (*STAGES, 'UNKNOWN')}
        assigned = 0
        for stage in reversed(STAGES[1:]):
            parts[stage] = max(0, reached[stage] - assigned)
            assigned += parts[stage]
        # A policy announcement establishes the policy pool, not implementation.
        rest = 'POLICY' if owner.get('source_id') == 'policy_907' else 'UNKNOWN'
        parts[rest] = cap - assigned
        result[owner['id']] = parts
    return result


def aggregate(selected, parts):
    totals = {stage: 0 for stage in (*STAGES, 'UNKNOWN')}
    missing = 0
    for row in selected:
        values = parts.get(row['id'])
        if values is None:
            missing += 1
            continue
        for stage, value in values.items():
            totals[stage] += value
    total = sum(totals.values())
    cumulative = {stage: sum(totals[s] for s in STAGES[index:]) for index, stage in enumerate(STAGES) if index}
    return dict(total_units=total or None, parts=totals, cumulative=cumulative,
                advanced_units=sum(totals[s] for s in STAGES[1:]), missing_quantity_projects=missing,
                basis='중복 제거 계획물량 대비 확인된 단계 도달 비율 · 이후 단계 포함 · 입주는 입주 시작 확인 사업물량')
