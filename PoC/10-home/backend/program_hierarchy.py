"""Programme identities and review-only policy proposals."""
import hashlib


def program_id(name, seed_policy_id):
    digest = hashlib.sha256(f'{name}\0{seed_policy_id}'.encode()).hexdigest()[:24]
    return 'PRG_' + digest


def parent_policy(seed_policy_id, real_policy_ids):
    return seed_policy_id if seed_policy_id in real_policy_ids else 'UNASSIGNED'


# A category-level suggestion is not evidence that a particular project was
# included in a policy announcement. Every such link stays in REVIEW.
PROGRAM_POLICY_CANDIDATES = {
    '공공재개발': ('POL_2026_0813', '공공재개발 추진 가속화가 언급된 공급대책과 사업 유형이 일치'),
    '공공재건축': ('POL_2026_0813', '정비사업 추진 가속화가 언급된 공급대책과 사업 유형이 일치'),
    '3기 신도시': ('POL_2025_0907', '같은 이름의 기존 프로그램 묶음이 9·7 공급대책에 제안됨'),
    '공공주택 건설': ('POL_2025_0907', '같은 이름의 기존 프로그램 묶음이 9·7 공급대책에 제안됨'),
    '토지임대부': ('POL_2025_0907', '공공택지·공공주택 공급 범주와 가장 가까움; 개별 정책 귀속 근거는 미확보'),
    'GH 통합공공임대': ('POL_2025_0907', '공공임대주택 공급 범주와 가장 가까움; 개별 정책 귀속 근거는 미확보'),
}


def policy_proposal(name, seed_policy_id, real_policy_ids):
    """Choose a reviewable parent; never assert a confirmed project-policy link."""
    if seed_policy_id in real_policy_ids:
        return seed_policy_id, '원천 정책 제안을 프로그램 단위로 이관'
    candidate, reason = PROGRAM_POLICY_CANDIDATES.get(name, (
        'POL_2025_0907', '세부 근거 미확보; 가장 포괄적인 공공주택 공급대책을 임시 후보로 선택'))
    if candidate not in real_policy_ids:
        return 'UNASSIGNED', '활성 정책 후보 미확보'
    return candidate, reason


def effective_mapping(project_mapping, program):
    """One programme belongs to at most one policy; project review remains separate."""
    result = dict(project_mapping)
    if program is None:
        if result.get("program_id") == "UNASSIGNED":
            result["policy_id"] = "UNASSIGNED"
            result["program_name"] = "프로그램 미연계"
        return result
    result['program_id'] = program['id']
    result['program_name'] = program['name']
    result['policy_id'] = program['policy_id'] if program['status'] != 'RELEASED' else 'UNASSIGNED'
    result['policy_status'] = program['status']
    result['policy_link_revision_no'] = program['revision_no']
    return result
