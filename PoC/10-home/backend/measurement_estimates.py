"""Infer missing fields from their own goals only when observed events support them.

Collected zero/partial quantities and exact event dates always take precedence.
No predecessor copying, no inferred event is promoted to a collected fact.
"""
from copy import deepcopy
from datetime import date
from calendar import monthrange
import hashlib
import json
from .stage_chronology import estimated_field

RULE = 'SEQUENCE_VALIDATED_TARGET_ESTIMATE'
REVIEWED_RULE = 'REVIEWED_MANAGEMENT_ESTIMATE'
BASIS = '수집 측정값 우선 보존 · 확인된 사건의 선후관계·물량에 합당한 미확보 항목만 같은 단계 목표값으로 추정'
STAGES = ('BUSINESS', 'APPROVAL', 'CONSTRUCTION', 'COMPLETION', 'SUPPLY', 'MOVE_IN')


def reviewed_estimate(prior, stage, reference, scope_limit):
    """A pinned, individually reviewed decision is not a fresh goal fallback."""
    review = prior.get('restoration_review', {})
    values = {f: prior.get(f) for f in ('event_date', 'units')}
    signature = hashlib.sha256(json.dumps(values, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return bool(stage in ('BUSINESS', 'APPROVAL')
                and review.get('status') == 'RESTORED_REVIEWED_ESTIMATE'
                and review.get('original_revision_id') and review.get('reason')
                and review.get('values_digest') == signature
                and day(values['event_date']) and day(values['event_date']) <= reference
                and type(values['units']) is int and values['units'] > 0
                and (scope_limit is None or values['units'] <= scope_limit))


def day(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        if len(value) == 4:
            value += '-12-31'
        elif len(value) == 7:
            value += '-%02d' % monthrange(int(value[:4]), int(value[5:7]))[1]
        return date.fromisoformat(value).isoformat()
    except (ValueError, TypeError):
        return None


def matches(row, stage):
    milestone = row.get('milestone')
    if stage == 'COMPLETION':
        return milestone == 'COMPLETION'
    if stage == 'CONSTRUCTION':
        return milestone != 'COMPLETION'
    return milestone in (None, stage) or (stage == 'SUPPLY' and milestone == 'NOTICE')


def goals_from_cells(cells):
    return {r['milestone']: dict(r, due_date=r.get('date'))
            for c in cells.values() for r in c.get('management', {}).get('target', [])
            if r.get('milestone') in STAGES}


def source_values(cell, stage, field, reference):
    result = []
    for r in cell.get('sources', []):
        if (r.get('kind') != 'ACTUAL' or r.get('pct') is not None or r.get('scope_partial')
                or r.get('estimation_anchor') or not matches(r, stage)
                or r.get('review_status') in ('REVIEW', 'REJECTED', 'RELEASED')):
            continue
        if field == 'event_date':
            if r.get('date_basis') == 'OBSERVED_BY' or estimated_field(r, 'date'):
                continue
            value = day(r.get('date'))
            if not value or value > reference:
                continue
        else:
            if estimated_field(r, 'units'):
                continue
            value = r.get('units')
            if type(value) not in (int, float) or value < 0:
                continue
        result.append((value, r))
    return sorted(result, key=lambda v: (v[1].get('source_id') == 'officer', v[1].get('source_id') or '', v[1].get('source_entity_id') or ''))


# Supply may precede construction. Neither approvals nor presales prove a start.
EDGES = (('BUSINESS', 'APPROVAL'), ('APPROVAL', 'CONSTRUCTION'),
         ('CONSTRUCTION', 'COMPLETION'), ('COMPLETION', 'MOVE_IN'),
         ('APPROVAL', 'SUPPLY'), ('SUPPLY', 'MOVE_IN'))


def precedes(before, after):
    reachable = {before}
    for _ in STAGES:
        reachable.update(b for a, b in EDGES if a in reachable)
    return before != after and after in reachable


def identity(row, field):
    proof = row.get('field_provenance', {}).get(field, {})
    if field == 'date':
        proof = proof or row.get('field_provenance', {}).get('event_date', {})
    if proof.get('rule') != 'SOURCE_ACCEPTED':
        proof = {}
    return {k: proof.get(k) or row.get(k) for k in
            ('source_id', 'source_entity_id', 'source_revision_no')}


def event_evidence(cells, reference, scope_limit, progress):
    """Independent observations only: estimates and plans cannot witness estimates."""
    evidence = []
    for stage in STAGES:
        cell = cells.get('CONSTRUCTION' if stage == 'COMPLETION' else stage, {})
        rows = list(cell.get('sources', []))
        prior = progress.get(stage, {})
        if not rows and prior:
            rows.append(dict(prior, kind='ACTUAL', milestone=stage, date=prior.get('event_date'), source_id='officer'))
        for row in rows:
            if (row.get('kind') not in ('ACTUAL', 'STATE') or not matches(row, stage)
                    or row.get('scope_partial') or row.get('estimation_anchor')
                    or row.get('review_status') in ('REVIEW', 'REJECTED', 'RELEASED')
                    or (row.get('original_method') or row.get('method')) in
                       ('PREREQUISITE', 'STAGE_INFERENCE', 'SIMILAR')):
                continue
            if row.get('kind') == 'STATE' and row.get('date_basis') != 'OBSERVED_BY':
                continue
            stamp = day(row.get('date')) if not estimated_field(row, 'date') else None
            if stamp and stamp > reference:
                continue
            units = row.get('units') if not estimated_field(row, 'units') else None
            units = units if type(units) in (int, float) and units >= 0 else None
            if scope_limit is not None and units is not None and units > scope_limit:
                continue
            pct = row.get('pct') if not estimated_field(row, 'pct') else None
            if pct is not None and (type(pct) not in (int, float) or pct <= 0):
                continue
            if row.get('pct') is not None and pct is None:
                continue
            if units == 0 or not (stamp or units or pct):
                continue
            evidence.append(dict(stage=stage, date=stamp, units=units, pct=pct,
                exact=bool(stamp and pct is None and row.get('kind') == 'ACTUAL'
                           and row.get('date_basis') != 'OBSERVED_BY'),
                **identity(row, 'date' if stamp else 'units')))
    # Prefer the original record over the adopted officer wrapper; make rechecks stable.
    evidence.sort(key=lambda r: (r.get('source_id') == 'officer', r.get('date') is None, r.get('date') or '',
                                r.get('source_id') or '', r.get('source_entity_id') or ''))
    return [r for i, r in enumerate(evidence) if r not in evidence[:i]]


def inference_evidence(stage, when, units, field, facts, reference, scope_limit):
    if not when or when > reference:
        return None
    if field == 'units' and (type(units) not in (int, float) or units <= 0
                            or (scope_limit is not None and units > scope_limit)):
        return None
    predecessors = [r for r in facts if precedes(r['stage'], stage)]
    successors = [r for r in facts if precedes(stage, r['stage'])]
    own = [r for r in facts if r['stage'] == stage]
    # Exact earlier events provide a lower date bound; observations are upper bounds.
    lower = max((r['date'] for r in predecessors if r['exact']), default=None)
    upper = min((r['date'] for r in own + successors if r['date']), default=None)
    if (lower and when < lower) or (upper and when > upper):
        return None
    # An earlier event alone never establishes that the requested stage happened.
    witnesses = own + successors
    if field == 'units':
        # A partial downstream count cannot establish full target delivery upstream.
        witnesses = [r for r in witnesses if r['units'] is None or r['units'] >= units]
        # Respect any known predecessor capacity for the same project scope.
        if any(r['units'] is not None and r['units'] < units and
               (not r['date'] or r['date'] >= when) for r in predecessors):
            return None
    if not witnesses:
        return None
    return dict(witness=witnesses[0], lower_date=lower, upper_date=upper,
                basis='같은 단계 또는 후행 단계의 확인 사건으로 도달 여부·날짜 경계·물량 검증')


def reconcile(progress, goals, cells, reference, scope_limit=None):
    """Return new values and derivations without mutating input dictionaries."""
    reference = reference.isoformat() if isinstance(reference, date) else reference
    output, changes, conflicts = {}, [], []
    facts = event_evidence(cells, reference, scope_limit, progress)
    for stage in STAGES:
        prior = deepcopy(progress.get(stage, {}))
        cell = cells.get('CONSTRUCTION' if stage == 'COMPLETION' else stage, {})
        goal = goals.get(stage, {})
        target_day = day(goal.get('due_date') or goal.get('date'))
        blocked = cell.get('progress', {}).get('code') in ('NOT_REACHED_REPORTED', 'SCHEDULE_PENDING')
        reviewed = reviewed_estimate(prior, stage, reference, scope_limit) and not blocked
        chosen, proofs = {}, {}
        for field, target_key in (('event_date', 'due_date'), ('units', 'units')):
            sources = source_values(cell, stage, field, reference)
            if field == 'units' and type(scope_limit) in (int,float):
                outside=[v for v,_ in sources if v>scope_limit]
                sources=[(v,r) for v,r in sources if v<=scope_limit]
                if outside and not sources:
                    chosen[field]=None
                    proofs[field]=dict(rule='SOURCE_SCOPE_CONFLICT',values=outside,scope_limit=scope_limit)
                    conflicts.append(dict(stage=stage,field=field,values=outside,scope_limit=scope_limit))
                    continue
            values = {v for v, _ in sources}
            old = prior.get(field)
            old_day = day(old) if field == 'event_date' else old
            # A saved source selection can resolve multiple collected versions.
            selected = next(((v, r) for v, r in sources if v == old_day), None)
            if selected is None and len(values) == 1:
                selected = sources[0]
            if selected is not None:
                value, r = selected
                chosen[field] = value
                anchor=r.get('field_provenance',{}).get(field,{})
                if field=='event_date':anchor=anchor or r.get('field_provenance',{}).get('date',{})
                if anchor.get('rule')!='SOURCE_ACCEPTED':anchor={}
                proofs[field] = dict(rule='SOURCE_ACCEPTED', value=value,
                    source_id=anchor.get('source_id') or r.get('source_id'),
                    source_entity_id=anchor.get('source_entity_id') or r.get('source_entity_id'),
                    source_revision_no=anchor.get('source_revision_no') or r.get('source_revision_no'),
                    basis='같은 사업·단계의 수집 측정값 우선 보존')
                continue
            if len(values) > 1:
                chosen[field] = '' if field == 'event_date' else None
                proofs[field] = dict(rule='SOURCE_CONFLICT', values=sorted(values), basis='수집값 상충: 목표값으로 대체하지 않고 확인 대기')
                conflicts.append(dict(stage=stage, field=field, values=sorted(values)))
                continue
            # Source observations above still win, including zero and partial counts.
            # The historical adoption reason must not disappear merely because a
            # stricter automatic inference rule has no independent witness.
            if reviewed:
                chosen[field] = old_day
                proofs[field] = deepcopy(prior.get('field_provenance', {}).get(field, {}))
                proofs[field].update(rule=REVIEWED_RULE, value=old_day)
                continue
            # Keep independently entered, non-estimated measurements when no source wrapper exists.
            if not cell.get('sources') and old not in (None, '') and not estimated_field(prior, 'date' if field == 'event_date' else field):
                if field != 'event_date' or (old_day and old_day <= reference):
                    chosen[field] = old_day
                    proofs[field] = dict(rule='SOURCE_ACCEPTED', value=old_day, basis='기존 비추정 측정값 보존')
                    continue
            target = target_day if field == 'event_date' else goal.get(target_key)
            # Elapsed deadlines alone do not establish an event.
            when = target_day if field == 'event_date' else chosen.get('event_date') or target_day
            evidence = inference_evidence(stage, when, target if field == 'units' else None,
                                          field, facts, reference, scope_limit)
            eligible = bool(target_day and target_day <= reference and not blocked and evidence)
            if eligible and target not in (None, ''):
                chosen[field] = target
                proofs[field] = dict(rule=RULE, value=target, target_stage=stage,
                    target_field=target_key, target_date=target_day, target_units=goal.get('units'),
                    target_revision_id=goal.get('source_revision_id'), sequence_evidence=evidence, basis=BASIS)
            else:
                chosen[field] = '' if field == 'event_date' else None
        if chosen.get('event_date') or chosen.get('units') is not None:
            r = dict(prior, **chosen)
            r['field_provenance'] = proofs
            has_review = any(p.get('rule') == REVIEWED_RULE for p in proofs.values())
            r['inferred'] = has_review or any(p.get('rule') == RULE for p in proofs.values())
            r['input_rule'] = REVIEWED_RULE if has_review else RULE if r['inferred'] else 'SOURCE_ACCEPTED'
            r['input_basis'] = prior.get('input_basis') if has_review else BASIS if r['inferred'] else '수집 측정값 보존 · 목표 대체 추정 미적용'
            output[stage] = r
    # Individually plausible target dates must also form a consistent displayed sequence.
    invalid = set()
    for before in STAGES:
        for after in STAGES:
            a, b = output.get(before, {}), output.get(after, {})
            if (not precedes(before, after) or not a.get('event_date') or not b.get('event_date')
                    or a['event_date'] <= b['event_date']):
                continue
            for stage in (before, after):
                if output[stage]['field_provenance'].get('event_date', {}).get('rule') == RULE:
                    invalid.add(stage)
    for stage in invalid:
        record = output[stage]
        record['event_date'] = ''
        record['field_provenance'].pop('event_date', None)
        if record['field_provenance'].get('units', {}).get('rule') == RULE:
            record['units'] = None
            record['field_provenance'].pop('units', None)
        if record.get('units') is None:
            output.pop(stage)
        else:
            record.update(inferred=False, input_rule='SOURCE_ACCEPTED',
                          input_basis='수집 측정값 보존 · 사건 순서와 상충하는 추정일 미적용')
    for stage in STAGES:
        prior, record = progress.get(stage, {}), output.get(stage, {})
        old_values = {k: prior.get(k) for k in ('event_date', 'units')}
        new_values = {k: record.get(k) for k in ('event_date', 'units')}
        proofs = record.get('field_provenance', {})
        if old_values != new_values or prior.get('field_provenance', {}) != proofs or prior.get('input_rule') != record.get('input_rule'):
            if prior or record:
                changes.append(dict(stage=stage, before=old_values, after=new_values,
                                    field_provenance=proofs))
    return dict(progress=output, changes=changes, conflicts=conflicts)
