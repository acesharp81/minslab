"""Evidence-bearing fields for a self-contained handover field guide."""
PRACTICE_FIELDS={
 'overview':'업무 개요','objectives':'목표','scope':'업무 범위','implementation_plan':'추진 계획',
 'performance':'성과 지표','future_plan':'추후 계획','operating_steps':'실무 처리 순서',
 'completion_criteria':'완료 기준','deliverables':'인계 산출물','issue_history':'현안 경과',
 'approval_route':'보고·결재 체계','document_locations':'자료 위치·접근 방법','budget':'예산 현황'}
# These describe the work's enduring brief, not a new progress observation.
PROFILE_FIELDS=set(PRACTICE_FIELDS)|{'contacts','collaborators'}


def document_role(blocks):
    import re
    values=set()
    for b in blocks:
        values.update(re.findall(r'(?:^|[|\n])\s*(?:[A-Z]+\d*:\s*)?문서역할\s*[:：]\s*(업무기준정보|증빙대장)(?=\s|$|[|])',b['text']))
    return values.pop() if len(values)==1 else '진행보고'
