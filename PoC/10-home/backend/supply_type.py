"""Evidence-based housing supply classification, independent of policy and starts.

UNKNOWN is retained for candidates: source agency and programme membership alone
cannot establish the official five-way allocation of a mixed development.
"""
import re
from urllib.parse import urlsplit

TYPES = {'PUBLIC': '공공주택', 'PURCHASE_NEW': '신축매입',
         'PRIVATE_RENEWAL': '민간정비', 'OTHER_PRIVATE': '기타 일반·민간주택',
         'PUBLIC_SUPPORTED_RENT': '공공지원 민간임대', 'UNKNOWN': '미확인',
         'MIXED': '복합 유형 · 분리 확인 필요'}
PUBLIC_TENURES = ('공공분양', '국민임대', '영구임대', '행복주택', '통합공공임대',
                  '건설형공공임대', '분양전환공공임대', '공공임대', '이익공유형분양', '공공주택')
DIRECT_BUILD = {'lh_construction', 'lh_incheon_construction', 'lh_progress',
                'lh_sale', 'lh_rent', 'lh_incheon_sale', 'lh_incheon_rent'}


def valid_url(value):
    try:
        url = urlsplit(value or '')
        return url.scheme in ('http', 'https') and bool(url.hostname) and not url.username and not url.password
    except (ValueError, TypeError):
        return False


def assess(project, manual=True):
    """Confirm explicit source scope; keep programme/name-only hints as candidates."""
    p = project
    url = p.get('evidence_url') or ''
    name = re.sub(r'\s+', '', p.get('name') or '')
    tenure = re.sub(r'\s+', '', p.get('tenure') or '')
    program = re.sub(r'\s+', '', p.get('source_program') or p.get('program') or '')
    text = name + ' ' + tenure

    def result(code, basis, rule, confirmed=True, evidence_url=url):
        known = confirmed and code not in ('UNKNOWN', 'MIXED') and valid_url(evidence_url)
        return dict(code=code if known or code == 'MIXED' else 'UNKNOWN',
                    label=TYPES[code] if known or code == 'MIXED' else TYPES['UNKNOWN'],
                    status='CONFIRMED' if known else 'UNRESOLVED',
                    candidate_code=None if known or code in ('UNKNOWN', 'MIXED') else code,
                    candidate_label=None if known or code in ('UNKNOWN', 'MIXED') else TYPES[code],
                    basis=basis, rule=rule, evidence_url=evidence_url,
                    verification_scope='공급유형 분류만 확인 · 정책 귀속·착공기간·실적 산입은 별도')

    overrides = p.get('manual_fields') or {}
    if manual and 'supply_type' in overrides:
        code = p.get('supply_type', 'UNKNOWN')
        if code not in TYPES:
            code = 'UNKNOWN'
        basis = p.get('supply_type_basis') or overrides['supply_type'].get('reason') or '담당자 분류'
        evidence = p.get('supply_type_evidence_url') or ''
        return result(code, basis, 'OFFICER_REVIEW', evidence_url=evidence,
                      confirmed=bool(basis.strip()) and valid_url(evidence))

    if '공공지원민간임대' in text:
        return result('PUBLIC_SUPPORTED_RENT', '원천 사업명·주택유형에 공공지원 민간임대 명시', 'EXPLICIT_SUPPORTED_RENT')
    if any(word in text for word in ('신축매입', '매입약정')):
        return result('PURCHASE_NEW', '원천 사업명·주택유형에 신축매입·매입약정 명시', 'EXPLICIT_NEW_PURCHASE')
    if '매입' in text or '전세임대' in text:
        return result('UNKNOWN', '기존주택 매입·전세와 신축매입의 범위 구분 필요', 'PURCHASE_SCOPE_UNKNOWN')
    if '민영' in text and '공공분양' in text:
        return result('MIXED', '공공분양과 민영주택이 같은 관리사업에 혼합되어 유형별 물량 분리 필요', 'EXPLICIT_MIXED_HOUSING')
    if any(word in tenure for word in PUBLIC_TENURES) or '노후공공임대재건축' in program:
        return result('PUBLIC', '원천 주택유형에 건설형 공공주택·공공임대 명시', 'EXPLICIT_PUBLIC_TENURE')
    if '민간참여공공주택' in name:
        return result('PUBLIC', '원천 개별 사업명에 민간참여 공공주택 명시', 'EXPLICIT_PUBLIC_PROJECT')
    if p.get('source_id')=='sh_inventory' and program=='토지임대부' and p.get('developer') in ('SH','서울주택도시공사','서울주택도시개발공사'):
        return result('PUBLIC', 'SH 공식 사업 현황의 토지임대부 분양주택', 'SH_LAND_LEASE_HOUSING')
    if any(word in program for word in ('공공재개발', '공공재건축')):
        return result('PRIVATE_RENEWAL', '공공참여 정비의 전체 사업과 공공기여분 분리·공식 부문 배정 확인 필요', 'PUBLIC_RENEWAL_ALLOCATION', False)
    if any(word in name + program for word in ('가로주택', '소규모')):
        return result('PRIVATE_RENEWAL', '소규모 정비와 공공기여분의 공식 부문 배정 확인 필요', 'SMALL_RENEWAL_ALLOCATION', False)
    if p.get('source_id') in ('seoul_cleanup', 'molit_renewal_inventory') and (
            any(word in name for word in ('재개발', '재건축', '재정비', '도시환경정비'))
            or program == '민간정비후보'):
        return result('PRIVATE_RENEWAL', '공식 정비사업 명부의 재개발·재건축 사업명 및 사업 유형', 'OFFICIAL_RENEWAL_ROSTER')
    if '지역주택조합' in name + program:
        return result('OTHER_PRIVATE', '원천에 지역주택조합 사업으로 명시', 'EXPLICIT_LOCAL_HOUSING_ASSOCIATION')
    if p.get('source_id') in DIRECT_BUILD and p.get('developer') == 'LH':
        return result('PUBLIC', 'LH 직접 건설·공정·건설형 분양/임대 원천의 주택 사업', 'LH_DIRECT_HOUSING_SOURCE')
    if '도심공공주택복합사업' in program:
        return result('PUBLIC', '정책 원문의 도심 공공주택 복합사업 유형 명시', 'URBAN_PUBLIC_COMPLEX')
    if any(word in program + name for word in ('공공', '3기신도시', '직접시행')):
        return result('PUBLIC', '공공 프로그램·지구명은 있으나 개별 블록의 공급방식·혼합 여부 추가 확인 필요', 'PUBLIC_PROGRAMME_ONLY', False)
    if p.get('source_id') == 'building_general_permit':
        return result('OTHER_PRIVATE', '일반 주택 허가 원천. 매입약정·공공지원 임대·정비와 겹치는지 미확인', 'GENERAL_PERMIT_ONLY', False)
    return result('UNKNOWN', '사업명·현재 원천만으로 공식 5개 공급유형을 특정할 근거 부족', 'INSUFFICIENT_EVIDENCE')


def source_fields(project):
    assessment = assess(project, manual=False)
    return dict(supply_type=assessment['code'], supply_type_basis=assessment['basis'],
                supply_type_evidence_url=assessment['evidence_url'])
