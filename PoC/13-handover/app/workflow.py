"""Read-only views over a revision; never change its confirmed facts."""
from datetime import date

from .engine import FIELDS


def readiness(payload):
    keys = ['status', 'completed_work', 'remaining_work', 'next_action', 'issues', 'owner', 'due_date']
    if any(i['fields'].get('overview',{}).get('value') for i in payload['items']):
        keys += ['overview','objectives','implementation_plan','future_plan','operating_steps','completion_criteria','budget','contacts']
    gaps = []
    for item in payload['items']:
        fields = item['fields']
        missing = [k for k in keys if not fields.get(k, {}).get('value', '').strip()]
        if item.get('business_status') == 'COMPLETED':
            missing = [k for k in missing if k not in {'remaining_work', 'next_action'}]
        if missing:
            gaps.append({'item_id': item['id'], 'title': fields['title']['value'],
                         'missing': [{'key': k, 'label': FIELDS[k]} for k in missing]})
    return {'items': gaps, 'missing_fields': sum(len(i['missing']) for i in gaps),
            'note': '미기재는 완료·현안 없음이라는 뜻이 아닙니다. 확인한 내용이나 미확인 사유를 보완하세요.'}


def briefing(revision, today):
    groups = {k: [] for k in ['기한 경과 확인', '7일 이내', '이후 일정', '정기 업무', '일정 확인 필요', '완료 업무']}
    contacts = []
    for item in revision['payload']['items']:
        fields = item['fields']
        def value(key):
            return fields.get(key, {}).get('value', '')
        due = fields.get('due_date', {})
        normalized = due.get('normalized_date')
        group = '일정 확인 필요'
        if item.get('business_status') == 'COMPLETED':
            group = '완료 업무'
        elif due.get('review_status') not in {'CONFLICT', 'NEEDS_CONFIRMATION'}:
            if due.get('precision') == 'RECURRING':
                group = '정기 업무'
            elif normalized:
                delta = (date.fromisoformat(normalized) - today).days
                group = '기한 경과 확인' if delta < 0 else '7일 이내' if delta <= 7 else '이후 일정'
        row = {'item_id': item['id'], 'title': value('title'), 'status': value('status'),
               'due_date': value('due_date'), 'normalized_date': normalized, 'owner': value('owner'),
               'next_action': value('next_action'), 'issues': value('issues')}
        groups[group].append(row)
        contacts.append({'item_id': item['id'], 'title': value('title'), 'owner': value('owner'),
                         'collaborators': value('collaborators'), 'contacts': value('contacts'),
                         'evidence': {k: fields.get(k, {}).get('evidence', []) for k in ['owner', 'collaborators', 'contacts']},
                         'provenance': {k: fields.get(k, {}).get('provenance') for k in ['owner', 'collaborators', 'contacts']}})
    for rows in groups.values():
        rows.sort(key=lambda r: (r['normalized_date'] or '9999', r['title']))
    return {'revision_id': revision['id'], 'hash': revision['hash'], 'as_of': today.isoformat(),
            'groups': groups, 'contacts': contacts,
            'note': '현재 날짜 기준 일정 조회입니다. 확정 보고서의 기준일·내용은 바뀌지 않습니다. 정기 일정의 다음 날짜나 미확정 기한을 추측하지 않습니다.'}
