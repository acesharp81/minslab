"""Program fields and project membership: manual overlays, atomic audit, no read-time writes."""
from copy import deepcopy
from datetime import date
import re
from sqlalchemy import select, text
from .db import Revision, Audit, ProgramMapping, Mapping, entity_id, upsert_revision, now
from .api_samples import today
from .policy_profile import REGIONS, LABELS, STAGES, cumulative_progress

METRICS=dict(BUSINESS='사업화',APPROVAL='인허가',CONSTRUCTION='착공',SUPPLY='공급·모집',COMPLETION='준공',MOVE_IN='입주',CAPACITY='전체 규모·개소')
BASE=dict(name='',overview='',developer='',period_start='2026-01-01',period_end='2030-12-31',target_units=None,unit='호',metric='CONSTRUCTION',advice=None,target_mode='INDEPENDENT')

def profiles(service, as_of=None):
    sources={r['program_id']:r for r in service.rows('program_source',as_of)}
    manual={r['program_id']:r for r in service.rows('program_profile',as_of)}
    result={}
    for pid in sources.keys()|manual.keys():
        source=sources.get(pid,{})
        values=dict(BASE,**source.get('fields',{}))
        overrides=manual.get(pid,{}).get('overrides',{})
        values.update({k:v['value'] for k,v in overrides.items()})
        result[pid]=dict(values=values,source=source,overrides=overrides,revision_no=manual.get(pid,{}).get('revision_no',0))
    return result

def validate(values, overrides):
    for k,item in overrides.items():
        v=item['value']
        if k in ('name','overview','developer','advice'):
            if not isinstance(v,str) or not v.strip() or len(v)>(150 if k in ('name','developer') else 4000):raise ValueError('명칭·설명·담당기관 길이를 확인하세요')
        elif k in ('period_start','period_end'):
            if not isinstance(v,str) or date.fromisoformat(v).isoformat()!=v:raise ValueError('날짜 형식 오류')
        elif k=='target_mode':
            if v not in ('INDEPENDENT','PROJECT_SUM'):raise ValueError('목표 관리방식 오류')
        elif k=='metric':
            if v not in METRICS:raise ValueError('목표 기준을 선택하세요')
        elif k=='unit':
            if v not in ('호','명','개소'):raise ValueError('목표 단위 오류')
        elif k=='target_units' or k in ['region:'+r for r in REGIONS] or re.fullmatch(r'annual:(전체|서울특별시|경기도|인천광역시):\d{4}',k):
            if type(v) is not int or not 0<=v<=100000000:raise ValueError('목표량은 0~1억 사이의 정수입니다')
        else:raise ValueError('편집할 수 없는 프로그램 항목입니다')
    start,end=date.fromisoformat(values['period_start']),date.fromisoformat(values['period_end'])
    if start>end or end.year-start.year>30 or start.year<1900 or end.year>2100:raise ValueError('추진기간을 확인하세요 (최대 31개 연도)')
    for k in overrides:
        if k.startswith('annual:') and not start.year<=int(k.rsplit(':',1)[1])<=end.year:raise ValueError('추진기간 밖의 연간 목표를 먼저 원천값으로 되돌리세요')
    cap=values.get('target_units')
    if cap is not None and sum(values.get('region:'+r) or 0 for r in REGIONS)>cap:raise ValueError('지역 목표 합계가 전체 목표를 초과합니다')
    for region in ('전체',*REGIONS):
        limit=cap if region=='전체' else values.get('region:'+region)
        if limit is not None and sum(values.get(f'annual:{region}:{y}') or 0 for y in range(start.year,end.year+1))>limit:raise ValueError('연간 목표 합계가 총목표를 초과합니다')
    for year in range(start.year,end.year+1):
        limit=values.get(f'annual:전체:{year}')
        if limit is not None and sum(values.get(f'annual:{r}:{year}') or 0 for r in REGIONS)>limit:raise ValueError('지역별 연간 목표가 전체 연간 목표를 초과합니다')

def save(service,pid,revision_no,changes,actor,reason,program_changes=None,mapping_revision_no=None):
    if not changes and not program_changes:raise ValueError('변경 내용이 없습니다')
    if not actor.strip() or not reason.strip():raise ValueError('변경자와 사유를 입력하세요')
    source=profiles(service).get(pid,{}).get('source',{})
    with service.sessions.begin() as db:
        if service.engine.dialect.name=='postgresql':db.execute(text('SELECT pg_advisory_xact_lock(9072026)'))
        program=db.scalar(select(ProgramMapping).where(ProgramMapping.id==pid).with_for_update())
        if program is None:raise ValueError('등록된 프로그램이 아닙니다')
        if mapping_revision_no!=program.revision_no:return dict(conflict=True)
        eid=entity_id('program_profile','manual_program',pid)
        old=db.scalar(select(Revision).where(Revision.entity_id==eid,Revision.superseded_at.is_(None)).with_for_update())
        if revision_no!=(old.revision_no if old else 0):return dict(conflict=True)
        overrides=deepcopy(old.payload.get('overrides',{})) if old else {}
        stamp=now().isoformat()
        for k,v in changes.items():
            if k not in BASE and k not in ['region:'+r for r in REGIONS] and not re.fullmatch(r'annual:(전체|서울특별시|경기도|인천광역시):\d{4}',k):raise ValueError('편집할 수 없는 프로그램 항목입니다')
            if v is None:overrides.pop(k,None)
            else:overrides[k]=dict(value=v,origin='MANUAL',actor=actor.strip(),reason=reason.strip(),changed_at=stamp)
        values=dict(BASE,**source.get('fields',{}));values['name']=values['name'] or program.name
        values.update({k:v['value'] for k,v in overrides.items()});validate(values,overrides)
        updates=[]
        for project_id,c in sorted((program_changes or {}).items()):
            mapping=db.scalar(select(Mapping).where(Mapping.project_id==project_id).with_for_update())
            if mapping is None or type(c.get('selected')) is not bool or type(c.get('revision_no')) is not int:raise ValueError('사업 연결 정보 오류')
            if mapping.revision_no!=c['revision_no']:return dict(conflict=True)
            parent=db.get(ProgramMapping,mapping.program_id) if mapping.program_id else None
            current_policy=parent.policy_id if parent and parent.status!='RELEASED' else mapping.policy_id
            if c['selected'] and current_policy not in (program.policy_id,'UNASSIGNED'):raise ValueError('다른 정책 사업은 정책 귀속을 먼저 확인하세요')
            if not c['selected'] and mapping.program_id!=pid:raise ValueError('다른 프로그램 연결은 해제할 수 없습니다')
            before={k:getattr(mapping,k) for k in ('program_id','policy_id','status','basis','evidence_url','revision_no')}
            after=dict(program_id=pid if c['selected'] else 'UNASSIGNED',policy_id=program.policy_id if c['selected'] else 'UNASSIGNED',status='CONFIRMED' if c['selected'] else 'RELEASED',basis='사용자 입력 · '+actor.strip()+' · '+reason.strip(),evidence_url='https://www.minslab.kr/poc/home/#program-progress',revision_no=mapping.revision_no+1)
            updates.append((mapping,before,after))
        if changes.get('target_mode')=='PROJECT_SUM':
            from .policy_delivery import build_delivery
            from .program_management import assessment,scoped_model
            class CandidateService:
                def __getattr__(self,key):return getattr(service,key)
                def projects(self,**kwargs):
                    target=kwargs.pop('policy_id',None);rows=deepcopy(service.projects(**kwargs))
                    for p in rows:
                        for mapping,before,after in updates:
                            if p['id']==mapping.project_id:p['mapping'].update(after)
                    return [p for p in rows if not target or p['mapping'].get('policy_id')==target]
            candidate=CandidateService();model=build_delivery(candidate,today(),include_portfolio_comparisons=False)
            model=scoped_model(candidate,dict(id=pid,policy_id=program.policy_id),model)
            summary=assessment(pid,values,source,model,candidate.projects())
            if not summary['aggregate_allowed']:raise ValueError('사업 합산 기준 목표는 같은 단계·기간의 계획 물량이 모두 확인되어야 합니다. 촉진 효과·다른 단위·부분 합계는 채택할 수 없습니다')
            amount=summary['period_plan_units']
            if values.get('target_units')!=amount:raise ValueError('사업 합계가 변경됐습니다. 최신 정보를 조회해 목표로 적용하세요')
            overrides.setdefault('target_units',dict(value=amount,origin='MANUAL',actor=actor.strip(),reason=reason.strip(),changed_at=stamp)).update(calculation=dict(origin='PROJECT_SUM_SNAPSHOT',units=amount,project_ids=[r['id'] for r in summary['rows']],metric=values['metric'],period_start=values['period_start'],period_end=values['period_end']))
        for mapping,before,after in updates:
            for k,v in after.items():setattr(mapping,k,v)
            mapping.reviewed_at=now();db.add(Audit(entity_id=mapping.project_id,action='PROGRAM_PROJECT_REVIEW',before=before,after=dict(after,actor=actor,changed_at=stamp)))
        payload=dict(program_id=pid,base_date=today().isoformat(),overrides=overrides,actor=actor.strip(),reason=reason.strip(),changed_at=stamp,program_changes=[dict(id=m.project_id,name=m.project_id,before=b,after=a) for m,b,a in updates])
        record,outcome=upsert_revision(db,'program_profile','manual_program',pid,payload,'manual')
        db.add(Audit(entity_id=pid,action='PROGRAM_PROFILE_UPDATED',before=old.payload if old else {},after=payload))
        return dict(revision_no=record.revision_no,outcome=outcome)

def view(service,pid,model):
    alias=next((r for r in service.rows('program_alias') if r['alias_id']==pid),None)
    if alias:pid=alias['canonical_id']
    programs=service.program_links()
    program=next((p for p in programs if p['id']==pid),None)
    if not program:raise ValueError('등록된 프로그램이 아닙니다')
    from .program_management import scoped_model
    model=scoped_model(service,program,model)
    parent=next((p for p in service.mapping_policies() if p['policy_id']==program['policy_id']),{})
    stored=profiles(service).get(pid,{})
    source=stored.get('source',{});original=dict(BASE,**source.get('fields',{}));original['name']=original['name'] or program['name']
    overrides=stored.get('overrides',{});values=dict(original,**{k:v['value'] for k,v in overrides.items()})
    years=list(range(int(values['period_start'][:4]),int(values['period_end'][:4])+1))
    keys=original.keys()|overrides.keys()|{'region:'+r for r in REGIONS}|{f'annual:{r}:{y}' for r in ('전체',*REGIONS) for y in years}
    fields={}
    for k in keys:
        evidence=dict(value=original.get(k),origin='SOURCE',basis=source.get('basis') or program['basis'],excerpt=source.get('basis') or program['basis'],evidence_url=source.get('evidence_url') or program['evidence_url'],document_name=source.get('document_name'),printed_page=source.get('printed_page'),pdf_page=source.get('pdf_page'))
        if k=='advice':evidence.update(basis='담당자 판단과 조치 방향',excerpt='담당자 판단과 조치 방향',evidence_url=None)
        fields[k]=dict(value=values.get(k),manual=k in overrides,evidence=([overrides[k]] if k in overrides else [])+[evidence])
    for row in service.rows('program_district_plan'):
        if row.get('program_id')==pid:
            fields['overview']['evidence'].append(dict(origin='SOURCE',value=row['사업명']+' · '+row['공급목표량또는분양계획량'],excerpt=row['분양시기']+' · '+row['검토내용'],basis=row.get('evidence_basis','지구 단위 분양계획 · 블록 미특정'),evidence_url=row['검증근거URL'],document_name=row.get('document_name','주택공급 확대방안.pdf'),printed_page=row.get('printed_page',10),pdf_page=row.get('source_page',13)))
    from .program_management import members,assessment,current_parts
    cohorts=members(model,pid)
    actual={}
    for region in ('전체',*REGIONS):
        records=[]
        for c in cohorts:
            if values['unit']!='호' or values['metric']=='CAPACITY' or region!='전체' and c['region']!=region:continue
            events=[e for e in c['events'] if e['stage']==values['metric'] and e.get('status','ACTUAL')=='ACTUAL' and values['period_start']<=e['event_date']<=min(model['as_of_date'],values['period_end'])]
            if events:
                e=max(events,key=lambda e:(e.get('units') or c['units'],e['event_date']))
                records.append(dict(name=c['name'],date=e['event_date'],value=min(c['units'],e.get('units') if e.get('units') is not None else c['units']),evidence_url=e.get('evidence_url'),mapping_status=c.get('mapping_status')))
        actual[region]=dict(value=sum(r['value'] for r in records) if records else None,annual={str(y):sum(r['value'] for r in records if r['date'].startswith(str(y))) if any(r['date'].startswith(str(y)) for r in records) else None for y in years},evidence=records,basis='연결 사업의 동일 단계 확인량 · 귀속 검토 중 포함 · 미확보 ≠ 0')
    totals=current_parts(cohorts,model['as_of_date'])
    progress=cumulative_progress(totals,values['target_units'] if values['unit']=='호' else None)
    raw=service.projects()
    management=assessment(pid,values,source,model,raw)
    from .api_requests import board
    management['api_guides']=[c for c in board(service)['items'] if c['id'] in management['api_ids']]
    projects=[]
    with service.sessions() as db:
        audit=db.scalars(select(Audit).where(Audit.action.in_(['PROGRAM_PROJECT_REVIEW','PROGRAM_SOURCE_SUPPLEMENT','PROGRAM_PROJECT_MERGE'])).order_by(Audit.recorded_at.desc())).all()
        for p in raw:
            m=p['mapping'];selected=m.get('program_id')==pid and m['status']!='RELEASED'
            if m.get('policy_id') not in (program['policy_id'],'UNASSIGNED') and not selected:continue
            prior=[a for a in audit if a.entity_id==p['id']]
            evidence=[dict(origin='MANUAL' if a.action=='PROGRAM_PROJECT_REVIEW' else 'SOURCE',value=a.after.get('program_id'),actor=a.after.get('actor','관리자'),changed_at=a.recorded_at.isoformat(),reason=a.after.get('basis') or a.after.get('reason'),basis=a.after.get('basis') or a.after.get('reason'),status=a.after.get('status'),evidence_url=a.after.get('evidence_url')) for a in prior]
            base=prior[-1].before if prior else m
            evidence.append(dict(origin='SOURCE',value=base.get('program_id'),basis=base.get('basis'),evidence_url=base.get('evidence_url')))
            projects.append(dict(id=p['id'],name=p['name'],region=p.get('region') or '지역 미확인',municipality=p.get('municipality') or '',policy_id=m.get('program_id') or 'UNASSIGNED',selected=selected,status=m['status'],revision_no=m['revision_no'],basis=m.get('basis'),evidence=evidence))
        history=[dict(recorded_at=a.recorded_at.isoformat(),actor=a.after.get('actor'),reason=a.after.get('reason'),program_changes=a.after.get('program_changes',[]),changes=[dict(field=k,before=a.before.get('overrides',{}).get(k),after=a.after.get('overrides',{}).get(k)) for k in a.before.get('overrides',{}).keys()|a.after.get('overrides',{}).keys() if a.before.get('overrides',{}).get(k)!=a.after.get('overrides',{}).get(k)]) for a in db.scalars(select(Audit).where(Audit.entity_id==pid,Audit.action=='PROGRAM_PROFILE_UPDATED').order_by(Audit.recorded_at.desc()).limit(50))]
    return dict(policy_id=pid,program_id=pid,parent_policy_name=parent.get('name','정책 미연결'),parent_policy_evidence_url=parent.get('evidence_url'),parent_policy_id=program['policy_id'],parent_basis=program['basis'],mapping_revision_no=program['revision_no'],programs=projects,revision_no=stored.get('revision_no',0),fields=fields,years=years,regions=REGIONS,actual=actual,progress=progress,stages=LABELS,as_of_date=model['as_of_date'],unknown_units=totals['UNKNOWN'],progress_evidence=[dict(name=c['name'],parts=current_parts([c],model['as_of_date']),evidence_url=c.get('evidence_url'),events=c['events']) for c in cohorts],history=history,source=source,management=management)
