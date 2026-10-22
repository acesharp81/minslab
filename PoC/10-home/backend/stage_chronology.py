"""Field-specific provenance and prerequisite timing; preserve source observations."""
from .collection_tags import tag

SOURCE_RULES={'SOURCE_ACCEPTED','BEST_SOURCE_SELECTED','MEASUREMENT_TO_TARGET'}
EDGES=(('BUSINESS','APPROVAL'),('APPROVAL','CONSTRUCTION'),('CONSTRUCTION','COMPLETION'),('APPROVAL','SUPPLY'),('COMPLETION','MOVE_IN'))


def estimated_field(value,field):
    proof=value.get('field_provenance',{})
    own=proof.get(field) or (proof.get('event_date') or proof.get('due_date') if field=='date' else None)
    if own:
        if '추정일' in own.get('basis','') or '관리 추정' in own.get('basis',''):return True
        return bool(own.get('rule') and own['rule'] not in SOURCE_RULES)
    if proof and value.get('input_rule') in SOURCE_RULES:return False
    if proof and set(proof).issubset({'units'}) and field=='date':return False
    return bool(value.get('inferred'))


def field_tag(value,source,field,missing=False,upcoming=False):
    merged=dict(source,**value)
    inferred=estimated_field(value,field) or (not value.get('manual') and estimated_field(source,field))
    merged['field_provenance']={};merged['inferred']=inferred
    # Management quantity assumptions must not hide the actual date's source.
    if source.get('evidence_url'):merged['evidence_url']=source['evidence_url']
    result=tag(merged,missing=missing,upcoming=upcoming)
    result['reason']=('일자' if field=='date' else '수량')+' · '+result['reason']
    return result


def propagate_upcoming(cells,reference):
    rows={kind:{r['milestone']:r for c in cells.values() for r in c['management'][kind]} for kind in ('target','measurement')}
    actual=rows['measurement'];targets=rows['target'];future={}
    def has_actual(s):return bool(actual.get(s,{}).get('date') or actual.get(s,{}).get('units') is not None)
    for s,r in actual.items():
        due=targets.get(s,{}).get('date') or ''
        if due>reference and not has_actual(s):future[s]=s
    for before,after in EDGES:
        if before not in future or has_actual(after):continue
        due=targets.get(after,{}).get('date') or ''
        # A dated, overdue downstream plan is a conflict, not automatically upcoming.
        if due and due<=reference:continue
        future[after]=future[before]
    for c in cells.values():
        m=c['management']
        for r in m['measurement']:
            s=r['milestone']
            if s not in future:continue
            root=future[s];label={'BUSINESS':'사업화','APPROVAL':'인허가','CONSTRUCTION':'착공','COMPLETION':'준공','SUPPLY':'공급','MOVE_IN':'입주'}.get(root,root);reason=f'{label} 선행 단계의 예정일({targets.get(root,{}).get("date")})이 기준일 이후입니다.'
            for field in ('date','units'):
                if r.get(field) in (None,''):
                    r.setdefault('field_tags',{})[field]=dict(tag(missing=True,upcoming=True),reason=reason)
            if not has_actual(s):r['collection_tag']=dict(tag(missing=True,upcoming=True),reason=reason)
            for gap in m['remaining']:
                if gap['milestone']==s and gap['field'].startswith('measurement.'):
                    gap.update(code='UPCOMING',label='시기 미도래·미진행',predecessor=root)


def constrain_estimated_dates(rows,date_key):
    """Clamp only estimated dates to neighbouring dates; retain observations and audit changes."""
    changes=[]
    for _ in range(len(EDGES)+1):
        changed=False
        for before,after in EDGES:
            a,b=rows.get(before,{}),rows.get(after,{})
            if not a.get(date_key) or not b.get(date_key) or a[date_key]<=b[date_key]:continue
            def movable(r):
                proof=r.get('field_provenance',{}).get(date_key,{})
                return estimated_field(r,'date') and not (date_key=='event_date' and (r.get('input_rule') in ('TARGET_EQUALS_MISSING_MEASUREMENT','SEQUENCE_VALIDATED_TARGET_ESTIMATE') or proof.get('rule') in ('TARGET_EQUALS_MISSING_MEASUREMENT','SEQUENCE_VALIDATED_TARGET_ESTIMATE')))
            if movable(a):stage,record,new=before,a,b[date_key]
            elif movable(b):stage,record,new=after,b,a[date_key]
            else:continue
            old=record[date_key];record[date_key]=new;record['inferred']=True
            record.setdefault('field_provenance',{})[date_key]=dict(rule='SEQUENCE_DATE_CONSTRAINT',previous_value=old,value=new,
                basis='선행 단계 ≤ 후행 단계 규칙으로 추정일 경계 보정 · 실제 사건일 확정 아님',anchor_stage=after if stage==before else before)
            changes.append(dict(stage=stage,field=date_key,before=old,after=new,anchor_stage=after if stage==before else before));changed=True
        if not changed:break
    return changes
