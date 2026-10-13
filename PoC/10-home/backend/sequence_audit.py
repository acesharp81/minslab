"""Identify missing prerequisite evidence without creating past events from plans."""
LABELS={'BUSINESS':'사업화','APPROVAL':'인허가','CONSTRUCTION':'건설','SUPPLY':'공급','MOVE_IN':'입주'}


def sequence_checks(cells):
    def facts(stage):return cells.get(stage,{}).get('sources',[])
    def actual(stage):return any(f.get('kind')=='ACTUAL' and not f.get('scope_partial') for f in facts(stage))
    def planned(stage):return any(f.get('kind')=='PLAN' for f in facts(stage))
    result=[]
    for downstream,prereqs in (('MOVE_IN',('APPROVAL','CONSTRUCTION','SUPPLY')),('SUPPLY',('APPROVAL','CONSTRUCTION')),('CONSTRUCTION',('BUSINESS','APPROVAL'))):
        observed=any(f.get('kind')=='ACTUAL' for f in facts(downstream));plan=planned(downstream)
        if not observed and not plan:continue
        for stage in prereqs:
            if actual(stage):continue
            # Presale may precede construction and rental housing never has sale.
            explanation=('공급은 분양·임대 모집을 함께 조회. 실제 입주와 입주 예정 구분' if downstream=='MOVE_IN' else
                         '선분양·사전예약은 착공보다 앞설 수 있음' if downstream=='SUPPLY' else '실제 착공과 착공 계획 구분')
            result.append(dict(stage=stage,downstream=downstream,code='PREDECESSOR_SOURCE_GAP' if observed else 'PLAN_PREDECESSOR_CHECK',
                priority='HIGH' if observed else 'NORMAL',label=LABELS[downstream]+(' 실적' if observed else ' 예정')+' 대비 '+LABELS[stage]+' 근거 확인',
                reason=explanation+' · 자동 완료 보정 금지; 공식 고시·공사 상세·모집공고 우선 수집'))
    return result
