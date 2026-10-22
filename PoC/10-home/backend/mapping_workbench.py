"""Read-only review projection: evidence authority never replaces staff approval."""
import re
from .input_status import input_status
from .source_authority import authority, public_url, publisher_name, OFFICIAL_DOMAINS


def review_state(link, parent=None):
    url = public_url(link.get('evidence_url'))
    kind = authority(url)
    # Internal application URLs are audit records, not independent news evidence.
    if 'minslab.kr' in url and '/poc/home/' in url:
        kind = 'INTERNAL'
    connected = bool(link.get('policy_id') not in (None, '', 'UNASSIGNED') and link.get('status') not in ('RELEASED', 'REJECTED'))
    if parent is not None:
        connected = connected and bool(parent.get('id')) and parent.get('status') not in ('RELEASED', 'REJECTED') and parent.get('policy_id') not in (None, '', 'UNASSIGNED')
    confirmed = link.get('status') == 'CONFIRMED'
    mixed_officer_basis = bool(re.search(r'담당자\s*(?:확인|검토)\s*[-–:]\s*비공식\s*자료\s*:', link.get('basis') or ''))
    parent_confirmed = parent is None or parent.get('status') == 'CONFIRMED'
    parent_review = parent.get('review') if parent else None
    parent_complete = parent_confirmed and (not parent_review or parent_review['group'] in ('CONNECTED', 'OFFICER'))
    group = 'UNLINKED'
    if connected:
        group = 'REVIEW'
        if confirmed and parent_complete:
            if kind == 'OFFICIAL':
                group = 'OFFICER' if mixed_officer_basis or parent_review and parent_review['group'] == 'OFFICER' else 'CONNECTED'
            elif kind == 'NONOFFICIAL' and url:
                group = 'OFFICER'
    if not connected: reason = '상위 연결이 없거나 해제된 후보입니다.'
    elif not parent_complete: reason = '상위 프로그램의 정책 귀속 확인이 필요합니다.'
    elif mixed_officer_basis and group == 'OFFICER': reason = '공식 근거와 비공식 자료를 함께 대조한 담당자 확인 완료'
    elif kind == 'NONOFFICIAL': reason = '비공식 자료 · ' + ('담당자 확인 완료' if confirmed else '담당자 확인 필요')
    elif not confirmed: reason = '저장된 임시 연결 · 담당자 확인 필요'
    elif kind != 'OFFICIAL': reason = '담당자 저장 연결 · 외부 근거 출처 확인 필요'
    elif group == 'OFFICER': reason = '공식 사업 근거 · 상위 프로그램의 비공식 근거는 담당자 확인 완료'
    else: reason = '공식 자료 근거와 저장된 연결 확인이 있습니다.'
    return dict(group=group, authority=kind, linked=connected, officer_confirmed=confirmed, mixed_officer_basis=mixed_officer_basis,
                reason=reason, evidence_url=url, publisher=publisher_name(url))


def build(service):
    data = service.mappings()
    decisions = {(r['subject_kind'],r['subject_id']):r for r in service.rows('mapping_decision') if r.get('policy_id')=='POL_2025_0907'} if hasattr(service,'rows') else {}
    active='POL_2025_0907'
    allowed={None,'','UNASSIGNED',active}
    data['programs']=[p for p in data['programs'] if p.get('policy_id') in allowed]
    data['items']=[r for r in data['items'] if r['mapping'].get('policy_id') in allowed]
    programs = []
    for p in data['programs']:
        row = {k:p.get(k) for k in ('id','name','policy_id','seed_policy_id','status','revision_no','basis','evidence_url','project_count')}
        row['review'] = review_state(row)
        apply_decision(row, decisions.get(('program',row['id'])))
        programs.append(row)
    parents = {p['id']:p for p in programs}
    items = []
    for r in data['items']:
        row = {k:r.get(k) for k in ('id','name','region','municipality','planned_units','source_id','program','stage_label','base_date','mapping')}
        quantity=r.get('planned_units')
        row['confirmed_units']=quantity if isinstance(quantity,(int,float)) and quantity>=0 and not input_status(r.get('manual_fields',{}).get('planned_units',{})).startswith('ESTIMATED') else None
        row['source_url'] = public_url(r.get('evidence_url'))
        row['source_publisher'] = publisher_name(row['source_url'])
        row['review'] = review_state(r['mapping'], parents.get(r['mapping'].get('program_id'), {}))
        apply_decision(row, decisions.get(('project',row['id'])))
        items.append(row)
    counts = {group:{'programs':sum(p['review']['group']==group for p in programs),
                     'projects':sum(p['review']['group']==group for p in items),
                     'units':sum(p['confirmed_units'] or 0 for p in items if p['review']['group']==group),
                     'unknown_units':sum(p['confirmed_units'] is None for p in items if p['review']['group']==group)} for group in ('CONNECTED','OFFICER','REVIEW','UNLINKED','EXCLUDED')}
    return dict(programs=programs, items=items, policies=[p for p in data['policies'] if p['policy_id']==active], counts=counts,
                official_domains=OFFICIAL_DOMAINS,
                notice='9·7 정책과 정책 미지정 후보만 표시합니다. 호수는 사업 기록별 확인된 계획규모 합계이며 착공·공급 실적이 아닙니다. 공식 출처와 연결 승인 상태를 함께 확인합니다. 공식 근거는 확인 완료(자동), 비공식 근거의 검토 완료는 확인 완료(담당자), 아직 검토가 끝나지 않은 연결은 확인 필요로 구분합니다. 제외 확인된 후보는 일반 검토 목록과 후보 CSV에서 빠지며 별도 필터에서 확인·복원할 수 있습니다.')


def apply_decision(row, decision):
    row['decision'] = decision
    if decision and decision.get('status') == 'EXCLUDED':
        row['review'] = dict(row['review'], group='EXCLUDED', reason=decision.get('reason') or '담당자 제외 확인')
