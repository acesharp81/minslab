"""Dated display geography for Incheon; retain the unmodified source labels."""
from datetime import date
import re
from urllib.parse import parse_qs, urlsplit
from .api_samples import today

INCHON_ADMIN_URL = 'https://www.incheon.go.kr/IC040102'
INCHON_REFORM_URL = 'https://www.incheon.go.kr/IC01070101'
REFORM = date(2026, 7, 1)
CURRENT = {'제물포구','영종구','미추홀구','연수구','남동구','부평구','계양구','서해구','검단구','강화군','옹진군'}


def incheon_municipality(row, reference=None):
    if row.get('region') != '인천광역시':
        return None
    reference = reference or today()
    if isinstance(reference, str):
        reference = date.fromisoformat(reference)
    municipality = row.get('municipality') or ''
    # A valid, explicit municipality wins over a station/project nickname:
    # 제물포역 도심복합사업 is in 미추홀구, not necessarily 제물포구.
    valid = CURRENT if reference >= REFORM else (CURRENT - {'제물포구','영종구','서해구','검단구'}) | {'중구','동구','서구'}
    if municipality in valid:
        return municipality
    query = parse_qs(urlsplit(row.get('evidence_url') or '').query)
    text = ' '.join(str(row.get(k) or '') for k in ('district','name','address')) + ' ' + ' '.join(query.get('seBzdtNm', []))
    matches = {m for m in valid if re.search(r'인천(?:광역시|시)?\s*' + re.escape(m) + r'(?=\s|$)', text)}
    if len(matches) == 1:
        return matches.pop()
    # Each token is an identified Incheon development/neighbourhood, not a
    # general mapping of the legacy 서구 or 중구 into one successor district.
    rules = [
        (r'검단', '검단구', '서구'),
        (r'인천계양|계양(?:구|지구)', '계양구', '계양구'),
        (r'영종', '영종구', '중구'),
        (r'인천부평|부평(?:구|\(도시재생)', '부평구', '부평구'),
        (r'인천송림|송림\d|송림동', '제물포구', '동구'),
        (r'석남|거북이기지|가정2|검암|청라', '서해구', '서구'),
        (r'도화(?:동|\s|도시)|인천도화', '미추홀구', '미추홀구'),
        (r'연수구|송도(?:동|\s|지구)', '연수구', '연수구'),
    ]
    found = {current if reference >= REFORM else old for pattern, current, old in rules if re.search(pattern, text)}
    return found.pop() if len(found) == 1 else None


def normalize_project_region(row, reference):
    if row.get('region') != '인천광역시':
        return row
    original = row.get('municipality')
    resolved = incheon_municipality(row, reference)
    row['source_municipality'] = original
    row['municipality'] = resolved or '시군구 미확인'
    row['municipality_provenance'] = dict(
        source_value=original, display_value=row['municipality'], as_of_date=reference.isoformat(),
        rule='INCHON_DATED_ADMINISTRATIVE_NAME' if resolved else 'UNRESOLVED_NO_GUESS',
        evidence_url=INCHON_ADMIN_URL, reform_evidence_url=INCHON_REFORM_URL,
        basis='원천의 명시 시군구 또는 식별된 지구·동과 조회일의 행정구역 대조. 원천 주소·좌표·사업 식별자 보존')
    return row
