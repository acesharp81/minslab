"""Deterministic role coverage within the existing call/region budget."""
from collections import deque

ROLES = ('institution', 'heading', 'body', 'notice')
LABELS = dict(institution='기관명', heading='제목', body='본문', notice='작은 안내')


def role(obj):
    label = obj.get('label', '')
    if any(t in label for t in ('기관명', '부처명', '기관 간판')):
        return 'institution'
    if any(t in label for t in ('제목', '헤드라인', '슬로건', '표제', '강조 문구')):
        return 'heading'
    if any(t in label for t in ('각주', '작은', '안내', '표지', '라벨', '명찰', '간판', '표찰', '지명', '행선판')):
        return 'notice'
    return 'body'


def prominence(obj):
    """Layout hints only; never consume an expected spelling or evaluation ROI."""
    label = obj.get('label', '')
    return (180 if any(t in label for t in ('강조', '큰 제목', '메인 제목')) else 0) - (120 if any(t in label for t in ('번호', '페이지', '시험 표기', '테스트 표기', '소제목', '부제')) else 0)


def balanced(items, get_role):
    """Keep risk order within a role, but reserve a turn for every present role."""
    buckets = {r: deque() for r in ROLES}
    for item in items:
        buckets[get_role(item)].append(item)
    result = []
    while any(buckets.values()):
        for r in ROLES:
            if buckets[r]:
                result.append(buckets[r].popleft())
    return result
