"""Source-supported policy proposals and programme membership."""
from .collection_period import ORIGINS

def construction_program_classification(district):
    """LH construction collector's category rule, also exposed for explanation."""
    keywords=('왕숙','창릉','교산','대장')
    matched=[word for word in keywords if word in (district or '')]
    return dict(program='3기 신도시' if matched else '공공주택 건설',
                field='지구명',value=district,keywords=list(keywords),matched=matched)

def lh_plan_program_classification(rent, name, tenure):
    """Describe the collector's actual source/type filter, not a semantic inference."""
    excluded=[word for word in ('매입','전세') if word in (tenure or '')]
    keywords=[word for word in ('왕숙','창릉','교산','대장') if word in (name or '')]
    return dict(program=None if excluded else '건설형 공공임대' if rent else '3기 신도시' if keywords else '공공택지·공공분양',
                excluded=excluded,matched=keywords,rent=rent)

def catalogue(policies, events):
    result = [dict(row, monitor_kind="POLICY") for row in policies]
    evidenced = {row.get("origin_id") for row in events}
    for origin_id, origin in ORIGINS.items():
        if origin_id not in evidenced:
            continue
        pid = "MON_" + origin_id
        values = dict(id=pid, name=origin["name"], announced_at=origin["origin_date"],
                      base_date=origin["origin_date"], target_units=None, target_scope="서울·경기 연결 사업",
                      metric="프로그램별 공급·입주 일정", evidence_url=origin["evidence_url"],
                      note="장기 프로그램 정책 · 개별 공급대책과 중첩되는 관리 관점", lifecycle_status="REVIEW")
        result.append(dict(values, policy_id=pid, values=values, monitor_kind="PROGRAMME"))
    return result


def automatic_proposal(payload, policy_ids):
    pid = payload.get("proposed_policy")
    basis = payload.get("mapping_basis") or "원천의 정책 제안 · 담당자 승인 대기"
    if pid in policy_ids:
        return dict(policy_id=pid, basis=basis, rule="SOURCE_POLICY", confidence="원천 제안")
    programme = payload.get("program", "")
    fallback = "MON_THIRD_NEW_TOWN" if programme == "3기 신도시" else "MON_URBAN_COMPLEX" if "도심 공공주택 복합사업" in programme else None
    return dict(policy_id=fallback if fallback in policy_ids else "UNASSIGNED",
                basis="원천 프로그램 일치 · 담당자 승인 대기" if fallback in policy_ids else "정책 귀속 근거 미확보 · 담당자 지정 필요",
                rule="SOURCE_PROGRAMME" if fallback in policy_ids else "UNRESOLVED", confidence="프로그램 일치" if fallback in policy_ids else "미확인")


def policy_members(policy, rows):
    pid = policy["policy_id"]
    if pid == 'UNASSIGNED':
        return [row for row in rows if row.get('mapping', {}).get('policy_id') in (None, 'UNASSIGNED')]
    if policy.get("monitor_kind") != "PROGRAMME":
        return [row for row in rows if row.get("mapping", {}).get("policy_id") == pid]
    programme = "3기 신도시" if pid == "MON_THIRD_NEW_TOWN" else "도심 공공주택 복합사업"
    return [row for row in rows if row.get("program") == programme or row.get("mapping", {}).get("policy_id") == pid]


