"""Officer-owned policy fields overlay immutable collected evidence; no read-time writes."""
from copy import deepcopy
from datetime import date
import re
from sqlalchemy import select, text
from .api_samples import today
from .db import Revision, Audit, ProgramMapping, entity_id, upsert_revision, now

POLICY_ID = 'POL_2025_0907'
REGIONS = ('서울특별시', '경기도', '인천광역시')
STAGES = ('BUSINESS', 'APPROVAL', 'CONSTRUCTION', 'SUPPLY', 'MOVE_IN')
LABELS = dict(POLICY='정책', BUSINESS='사업화', APPROVAL='인허가', CONSTRUCTION='건설', SUPPLY='공급', MOVE_IN='입주')


def cumulative_progress(totals, target):
    """Presentation only: later stages imply prior reach; source partitions remain exclusive."""
    progress = {'POLICY': target}
    for i, stage in enumerate(STAGES):
        progress[stage] = sum(totals.get(later, 0) for later in STAGES[i:])
    return progress


def profile(service, as_of=None):
    return next((r for r in service.rows('policy_profile', as_of) if r.get('policy_id') == POLICY_ID),
                dict(policy_id=POLICY_ID, revision_no=0, overrides={}))


def source_fields(plan):
    fields = dict(name='9·7 주택공급 확대방안', overview='수도권 주택시장 안정을 위한 2026~2030년 신규 착공 135만 호 추진',
                  period_start=plan['period_start'], period_end=plan.get('period_end', '2030-12-31'),
                  target_units=plan['target_units'], advice=None)
    for region in REGIONS:
        fields['region:' + region] = plan.get('region_allocations', {}).get(region)
    for row in plan.get('annual', []):
        fields['annual:전체:' + str(row['year'])] = row['units']
        fields['annual:서울특별시:' + str(row['year'])] = row.get('seoul_units')
    from .policy_field_evidence import evidence_for
    evidence=evidence_for(plan,'overview',fields['overview'])
    if evidence.get('excerpt_type') == 'QUOTE': fields['overview']=evidence['excerpt']
    return fields


def apply_profile(plan, stored):
    result = deepcopy(plan)
    fields = source_fields(plan)
    fields.update({key: item['value'] for key, item in stored.get('overrides', {}).items()})
    result.update({key: fields[key] for key in ('name', 'overview', 'period_start', 'period_end', 'target_units')})
    result['region_allocations'] = {r: fields.get('region:' + r) for r in REGIONS}
    years = range(int(fields['period_start'][:4]), int(fields['period_end'][:4]) + 1)
    result['annual'] = [dict(year=y, units=fields.get(f'annual:전체:{y}'),
                           seoul_units=fields.get(f'annual:서울특별시:{y}')) for y in years]
    result['profile_overrides'] = stored.get('overrides', {})
    result['profile_revision_no'] = stored.get('revision_no', 0)
    return result


def validate(plan, overrides):
    values = source_fields(plan)
    values.update({k: v['value'] for k, v in overrides.items()})
    for key, item in overrides.items():
        value = item['value']
        if key in ('name', 'overview', 'advice'):
            if not isinstance(value, str) or not value.strip() or len(value) > (150 if key == 'name' else 4000):
                raise ValueError('정책명·개요·조언은 빈칸 없이 허용 길이 내로 입력하세요')
        elif key in ('period_start', 'period_end'):
            try:
                if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value: raise ValueError()
            except (TypeError, ValueError): raise ValueError('추진기간은 YYYY-MM-DD 형식입니다') from None
        elif key == 'target_units' or key in ['region:' + r for r in REGIONS] or re.fullmatch(r'annual:(전체|서울특별시|경기도|인천광역시):\d{4}', key):
            if type(value) is not int or not 0 <= value <= 100000000:
                raise ValueError('목표량은 0~1억 호 사이의 정수입니다. 미배분은 원천값 사용을 선택하세요')
        else: raise ValueError('편집할 수 없는 정책 항목입니다')
    start, end = date.fromisoformat(values['period_start']), date.fromisoformat(values['period_end'])
    if start > end or end.year - start.year > 30 or start.year < 1900 or end.year > 2100:
        raise ValueError('추진기간의 시작·종료일을 확인하세요 (최대 31개 연도)')
    total = values['target_units']
    if total <= 0: raise ValueError('정책 전체 목표는 1호 이상이어야 합니다')
    if sum(values.get('region:' + r) or 0 for r in REGIONS) > total:
        raise ValueError('지역별 목표 합계가 정책 전체 목표를 초과합니다')
    for key in overrides:
        if key.startswith('annual:') and not start.year <= int(key.rsplit(':', 1)[1]) <= end.year:
            raise ValueError('추진기간 밖의 사용자 연간 목표를 먼저 원천값으로 되돌려 주세요')
    for scope in ('전체', *REGIONS):
        cap = total if scope == '전체' else values.get('region:' + scope)
        annual = [values.get(f'annual:{scope}:{y}') for y in range(start.year, end.year + 1)]
        if cap is not None and sum(v or 0 for v in annual) > cap:
            raise ValueError(scope + ' 연간 목표 합계가 해당 총목표를 초과합니다')
    for y in range(start.year, end.year + 1):
        cap = values.get(f'annual:전체:{y}')
        if cap is not None and sum(values.get(f'annual:{r}:{y}') or 0 for r in REGIONS) > cap:
            raise ValueError(str(y) + '년 지역 목표 합계가 전체 연간 목표를 초과합니다')
    return values


def save(service, revision_no, changes, actor, reason, program_changes=None):
    program_changes = program_changes or {}
    if not changes and not program_changes or len(changes) > 140: raise ValueError('변경 항목을 입력하세요 (최대 140개)')
    if not actor.strip() or not reason.strip(): raise ValueError('변경자와 변경 사유가 필요합니다')
    plans = service.rows('policy_delivery_plan')
    plan = next((r for r in plans if r.get('policy_id') == POLICY_ID), None)
    if not plan: raise ValueError('정책 원문 수집 후 입력할 수 있습니다')
    eid = entity_id('policy_profile', 'manual_policy', POLICY_ID)
    with service.sessions.begin() as session:
        if session.bind.dialect.name == 'postgresql':
            session.execute(text('SELECT pg_advisory_xact_lock(9072026)'))
        old = session.scalar(select(Revision).where(Revision.entity_id == eid, Revision.superseded_at.is_(None)).with_for_update())
        version = old.revision_no if old else 0
        if version != revision_no: return dict(conflict=True, revision_no=version)
        program_updates = []
        for pid, change in sorted(program_changes.items()):
            row = session.scalar(select(ProgramMapping).where(ProgramMapping.id == pid).with_for_update())
            if row is None: raise ValueError('등록된 프로그램을 선택하세요')
            if type(change.get('selected')) is not bool or type(change.get('revision_no')) is not int:
                raise ValueError('프로그램 선택값과 버전을 확인하세요')
            if row.revision_no != change['revision_no']: return dict(conflict=True, revision_no=version)
            if not change['selected'] and row.policy_id != POLICY_ID:
                raise ValueError('다른 정책의 연결은 이 화면에서 해제할 수 없습니다')
            before = {k:getattr(row,k) for k in ('policy_id','status','basis','evidence_url','revision_no')}
            after = dict(policy_id=POLICY_ID if change['selected'] else 'UNASSIGNED',
                         status='CONFIRMED' if change['selected'] else 'RELEASED',
                         basis='사용자 입력 · '+actor.strip()+' · '+reason.strip(),
                         evidence_url='https://www.minslab.kr/poc/home/#policy-progress', revision_no=row.revision_no+1)
            program_updates.append((row, before, after))
        overrides = deepcopy(old.payload.get('overrides', {})) if old else {}
        stamp = now().isoformat()
        for key, value in changes.items():
            # Null releases only this override; collected evidence remains immutable.
            if value is None:
                if key not in source_fields(plan) and not re.fullmatch(r'annual:(전체|서울특별시|경기도|인천광역시):\d{4}', key):
                    raise ValueError('편집할 수 없는 정책 항목입니다')
                overrides.pop(key, None)
            else: overrides[key] = dict(value=value, actor=actor.strip(), changed_at=stamp, reason=reason.strip(), origin='MANUAL', authentication='ADMIN', actor_basis='담당자 입력 이름')
        validate(plan, overrides)
        # Rebuild against the proposed fields before commit: reject an impossible ledger.
        from .policy_delivery import build_delivery
        class CandidateService:
            def __getattr__(self, key): return getattr(service, key)
            def projects(self, **kwargs):
                target = kwargs.pop('policy_id', None)
                rows = deepcopy(service.projects(**kwargs))
                for item in rows:
                    for row, before, after in program_updates:
                        if item.get('mapping',{}).get('program_id') == row.id:
                            item['mapping'].update(policy_id=after['policy_id'], policy_status=after['status'])
                return [r for r in rows if not target or r.get('mapping',{}).get('policy_id') == target]
            def rows(self, kind, as_of=None, **kwargs):
                if kind == 'policy_profile': return [dict(policy_id=POLICY_ID, overrides=overrides)]
                return service.rows(kind, as_of, **kwargs)
        build_delivery(CandidateService(), today(), include_portfolio_comparisons=False)
        for row, before, after in program_updates:
            for key, value in after.items(): setattr(row, key, value)
            row.reviewed_at = now()
            session.add(Audit(entity_id=row.id, action='PROGRAM_POLICY_REVIEW', before=before, after=dict(after, actor=actor.strip(), changed_at=stamp)))
        payload = dict(program_changes=[dict(id=row.id,name=row.name,before=before,after=after) for row,before,after in program_updates], policy_id=POLICY_ID, overrides=overrides, base_date=today().isoformat(), actor=actor.strip(), changed_at=stamp, reason=reason.strip())
        record, outcome = upsert_revision(session, 'policy_profile', 'manual_policy', POLICY_ID, payload, 'manual')
        session.add(Audit(entity_id=POLICY_ID, action='POLICY_PROFILE_UPDATED', before=old.payload if old else {}, after=payload))
        return dict(revision_no=record.revision_no, outcome=outcome)


def view(service, model):
    stored = profile(service)
    plan = next(r for r in service.rows('policy_delivery_plan') if r.get('policy_id') == POLICY_ID)
    original = source_fields(plan)
    overrides = stored.get('overrides', {})
    fields = {}
    from .policy_field_evidence import evidence_for
    annual_keys={f'annual:{scope}:{y}' for scope in ('전체',*REGIONS) for y in range(int(model['plan']['period_start'][:4]),int(model['plan']['period_end'][:4])+1)}
    for key in original.keys() | overrides.keys() | annual_keys:
        source = dict(value=original.get(key), origin='SOURCE', basis='9·7 정책 원문 수집값' if key not in ('name','overview','advice') else '9·7 정책명·목표 요약' if key != 'advice' else '정책조언은 담당자 판단을 입력합니다', evidence_url=plan.get('evidence_url'), source_date=plan.get('base_date'))
        source.update(evidence_for(plan,key,original.get(key)))
        if key == 'advice': source['evidence_url'] = None
        manual = overrides.get(key)
        fields[key] = dict(value=manual['value'] if manual else source['value'], evidence=([manual] if manual else []) + [source], manual=bool(manual))
    cohorts = model.get('cohorts', [])
    end = model['as_of_date']
    start = model['plan']['period_start']
    years = list(range(int(start[:4]), int(model['plan']['period_end'][:4]) + 1))
    # Same-policy linked starts, never substitute region-wide macro statistics.
    actual = {}
    for scope in ('전체', *REGIONS):
        records = []
        for c in cohorts:
            if scope != '전체' and c['region'] != scope: continue
            events = [e for e in c['events'] if e['stage'] == 'CONSTRUCTION' and e.get('status','ACTUAL') == 'ACTUAL' and start <= e['event_date'] <= min(end, model['plan']['period_end'])]
            if events:
                event = min(events, key=lambda e:e['event_date'])
                records.append(dict(project_id=c['id'], name=c['name'], value=c['units'], date=event['event_date'], evidence_url=event.get('evidence_url') or c.get('evidence_url'), mapping_status=c.get('mapping_status')))
        annual = {str(y): sum(r['value'] for r in records if r['date'].startswith(str(y))) if any(r['date'].startswith(str(y)) for r in records) else None for y in years}
        actual[scope] = dict(value=sum(r['value'] for r in records) if records else None, annual=annual, evidence=records,
                             basis='정책기간 내 연결 사업의 착공 확인량 · 정책 귀속 검토 중 포함 · 미확보는 0이 아님')
    totals = model['current']['totals']
    progress = cumulative_progress(totals, model['target_units'])
    aliases={r['alias_id'] for r in service.rows('program_alias')}
    with service.sessions() as session:
        programs = [dict(id=r.id, name=r.name, policy_id=r.policy_id, status=r.status, revision_no=r.revision_no, basis=r.basis, evidence_url=r.evidence_url, selected=r.policy_id == POLICY_ID and r.status != 'RELEASED') for r in session.scalars(select(ProgramMapping).order_by(ProgramMapping.name,ProgramMapping.id)) if r.id not in aliases]
        program_audits = session.scalars(select(Audit).where(Audit.entity_id.in_([p['id'] for p in programs]), Audit.action.in_(['PROGRAM_POLICY_REVIEW','PROGRAM_POLICY_AUTO'])).order_by(Audit.recorded_at)).all()
        for p in programs:
            changes = [a for a in program_audits if a.entity_id == p['id']]
            manual = [a for a in changes if a.action == 'PROGRAM_POLICY_REVIEW']
            original_link = next((a.before for a in changes if a.before), p)
            p['evidence'] = [dict(origin='MANUAL', value=a.after.get('policy_id'), actor=a.after.get('actor','관리자 (이전 기록 이름 미수록)'), changed_at=a.after.get('changed_at') or a.recorded_at.isoformat(), reason=a.after.get('basis'), status=a.after.get('status'), evidence_url=a.after.get('evidence_url')) for a in reversed(manual)]
            p['evidence'].append(dict(origin='SOURCE', value=original_link.get('policy_id'), basis=original_link.get('basis'), evidence_url=original_link.get('evidence_url'), status=original_link.get('status')))
        history = [dict(program_changes=r.after.get('program_changes',[]), recorded_at=r.recorded_at.isoformat(), actor=r.after.get('actor'), reason=r.after.get('reason'), changes=[dict(field=k, before=r.before.get('overrides',{}).get(k), after=r.after.get('overrides',{}).get(k)) for k in r.before.get('overrides',{}).keys() | r.after.get('overrides',{}).keys() if r.before.get('overrides',{}).get(k) != r.after.get('overrides',{}).get(k)]) for r in session.scalars(select(Audit).where(Audit.entity_id == POLICY_ID, Audit.action == 'POLICY_PROFILE_UPDATED').order_by(Audit.recorded_at.desc()).limit(50))]
    from .program_profile import profiles
    names=profiles(service)
    availability={r['id']:r for r in service.program_links()}
    for p in programs:
        p.update({k:availability.get(p['id'],{}).get(k) for k in ('selection_enabled','inactive_reason')})
        if names.get(p['id'],{}).get('values',{}).get('name'):p['name']=names[p['id']]['values']['name']
    return dict(policy_id=POLICY_ID, programs=programs, revision_no=stored.get('revision_no',0), fields=fields, years=years, regions=REGIONS, actual=actual,
                progress=progress, stages=LABELS, as_of_date=end, unknown_units=totals.get('UNKNOWN',0),
                progress_evidence=[dict(name=c['name'], parts=c.get('parts',{}), evidence_url=c.get('evidence_url'), events=c['events']) for c in cohorts],
                advice='정책 목표의 지역·연도별 배분을 확인하고, 계획 대비 부족량은 실적 누락 여부를 검증한 뒤 지연으로 판단하세요. 경기·인천 공동 목표의 개별 배분과 담당기관 확인이 필요합니다.', history=history)
