"""Persisted, reviewable cross-source facts. Reads never run entity matching."""
from collections import defaultdict, Counter
from datetime import date
import re
from sqlalchemy import select, text
from .api_samples import today
from .db import Revision, Audit, entity_id, upsert_revision
from .supply_dashboard import block_key
from .roadmap import source_events

KIND='evidence_bridge'
VERSION='district-block-cohort-v3'


def match_key(row):
    # Never collapse Ab31 to A31 globally. A single explicit block in the
    # project title can supply a candidate key, retaining the original value.
    name=str(row.get('name','')).upper()
    hits=set(re.findall(r'(?<![A-Z0-9])([A-Z]{1,3})\s*[-－]?\s*(\d+)\s*(?:BL|블록|\b)',name))
    if len(hits)>1 or 'MULTI_SITE_CONTRACT' in row.get('warnings',[]):return None
    p=dict(row,district=row.get('district') or row.get('district_name'))
    if not p['district']:return None
    if len(hits)==1:
        prefix,num=next(iter(hits));p['block']=prefix+str(int(num))
    # Reuse district/block normalization without the supply map's source allowlist.
    # This temporary discriminator is never written into the source record.
    return block_key(dict(p,source_id='lh_sale'))


def facts(row,reference):
    if row.get('facts') is not None:return row['facts']
    result=[]
    def add(stage,kind,stamp,basis,**extra):
        if stamp and (kind!='ACTUAL' or stamp<=reference.isoformat()):
            result.append(dict(stage=stage,kind=kind,date=stamp,basis=basis,**extra))
    add('CONSTRUCTION','ACTUAL',row.get('start_actual_date'),'동일 사업 후보의 원천 착공 기록',milestone='CONSTRUCTION')
    if row.get('progress_pct') is not None:
        add('CONSTRUCTION','ACTUAL',row.get('progress_date') or row.get('base_date'),'동일 사업 후보의 원천 공정률',pct=row['progress_pct'])
    add('CONSTRUCTION','ACTUAL',row.get('completion_actual_date'),'원천 실제 준공일',milestone='COMPLETION')
    add('MOVE_IN','ACTUAL',row.get('move_in_actual_date'),'원천 입주 시작일')
    for e in source_events(row,reference):
        stage='CONSTRUCTION' if e['stage']=='COMPLETION' else e['stage']
        add(stage,'PLAN',e['due_date'] if e.get('precision')=='DAY' else e['month'],e['basis'],milestone=e['stage'])
    if row.get('sample_kind')=='lh_completion_plan':
        add('CONSTRUCTION','PLAN',row.get('completion_plan_date'),'LH 블록별 준공예정 · 실제 준공·입주 아님',milestone='COMPLETION')
    return result



def tenure_key(value):
    value=str(value or '').replace(' ', '')
    for kind in ('국민임대','영구임대','행복주택','통합공공임대','공공분양'):
        if kind in value:return kind
    return None


def contained_facts(project,source,witnesses,reference):
    """Transfer only a documented housing cohort, never proportionally guess it."""
    target=project.get('planned_units');total=source.get('planned_units');tenure=tenure_key(project.get('tenure'))
    if not tenure or not isinstance(target,int) or not isinstance(total,int) or not 0<target<total:return None
    proof_rows=[dict(w,planned_units=w['complex_total_units'],scope_breakdown=w['complex_scope_breakdown']) if w.get('complex_total_units') and w.get('complex_scope_breakdown') else w for w in witnesses]
    proofs=[w for w in proof_rows if w.get('verification_status')=='SOURCE_CONTENT_CHECKED'
            and w.get('planned_units',0)==total and w.get('scope_breakdown')
            and all(isinstance(n,int) and n>0 for n in w['scope_breakdown'].values())
            and sum(w['scope_breakdown'].values())==total
            and w['scope_breakdown'].get(tenure)==target]
    if not proofs:return None
    result=[]
    for f in facts(source,reference):
        # Construction and permits cover the complex. Supply/occupancy only
        # apply when the source explicitly identifies this exact cohort.
        cohort=(f.get('scope_partial') and f.get('scope_units')==target
                and tenure_key(source.get('tenure'))==tenure
                and source.get('notice_round','MAIN')=='MAIN'
                and source.get('offered_units') in (None,target))
        if f['stage'] not in ('BUSINESS','APPROVAL','CONSTRUCTION') and not cohort:continue
        if f['stage'] in ('BUSINESS','APPROVAL','CONSTRUCTION') and f.get('scope_partial'):continue
        item=dict(f,scope_partial=False,scope_units=target,source_total_units=total,
                  scope_label=f'{tenure} {target}호 · 전체 {total}호 중 해당 유형',
                  scope_proof_entity_id=proofs[0]['id'],scope_proof_revision_no=proofs[0].get('revision_no'))
        if item.get('units') is not None:item['units']=target
        item['basis']=f.get('basis','')+f' · 공식 유형별 구성 대조: {tenure} {target}호에 한정'
        result.append(item)
    return result or None


def reconcile(service,apply=False):
    projects=service.rows('project');sources=projects+service.rows('lh_completion_plan')+service.rows('document_evidence')
    # A mixed housing/non-housing contract is only eligible after a separate
    # official approval explicitly corroborates its housing total and breakdown.
    scoped={(match_key(r),r.get('planned_units')) for r in sources
            if r.get('scope_breakdown') and r.get('verification_status')=='SOURCE_CONTENT_CHECKED'
            and r.get('planned_units')==sum(r['scope_breakdown'].values())
            and any(f.get('stage')=='APPROVAL' and f.get('kind')=='ACTUAL' for f in r.get('facts',[]))}
    def key_for(row):
        key=match_key(row)
        if key is None and 'MULTI_SITE_CONTRACT' in row.get('warnings',[]):
            candidate=match_key(dict(row,warnings=[w for w in row['warnings'] if w!='MULTI_SITE_CONTRACT']))
            if (candidate,row.get('planned_units')) in scoped:return candidate
        return key
    index=defaultdict(list)
    for r in sources:
        key=key_for(r)
        if key:index[key].append(r)
    saved={(r['project_id'],r['source_entity_id']):r for r in service.rows(KIND)}
    proposals=[];held=[];preserved=0
    for p in projects:
        key=key_for(p)
        if not key:continue
        for r in index[key]:
            if r['id']==p['id'] or r['source_id']==p['source_id']:continue
            evidence=facts(r,today())
            if not evidence:continue
            units=r.get('planned_units',r.get('units'));target=p.get('planned_units')
            contained=contained_facts(p,r,index[key],today())
            partial=(r['source_id']=='lh_notice_detail' and p['source_id'] in ('lh_construction','lh_incheon_construction')
                     and isinstance(units,int) and isinstance(target,int) and 0<units<target)
            subtype_conflict=(r['source_id']=='lh_notice_detail' and p.get('tenure') in ('국민임대','영구임대','행복주택','통합공공임대')
                              and p['tenure']!=r.get('tenure'))
            if (subtype_conflict and not contained) or units is None or target is None or (units!=target and not partial and not contained) or units<=0:
                held.append(dict(project_id=p['id'],name=p['name'],source_name=r['name'],source_entity_id=r['id'],
                    project_units=target,source_units=units,reason='동일 블록이나 물량 범위가 다르거나 미확인 · 부분 공급/계약 확인 필요'))
                continue
            if contained:evidence=contained
            # Do not duplicate identical facts already present in the project.
            own={(f['stage'],f['kind'],f.get('date'),f.get('pct'),f.get('milestone')) for f in facts(p,today())}
            evidence=[f for f in evidence if r['source_id']=='lh_notice_detail' or (f['stage'],f['kind'],f.get('date'),f.get('pct'),f.get('milestone')) not in own]
            if not evidence:continue
            old=saved.get((p['id'],r['id']))
            if old:
                preserved+=1
                if old.get('source_revision_no')!=r.get('revision_no'):
                    held.append(dict(project_id=p['id'],name=p['name'],source_name=r['name'],source_entity_id=r['id'],
                        reason='연결 원천 새 판본 · 기존 연결/담당자 판정 보존, 새 판본 검토 필요'))
                continue
            basis=('시도·지구·블록 일치 · 일부 주택유형 '+str(units)+'호 / 건설사업 '+str(target)+'호 · 부분 범위 후보, 전체 실적·목표로 합산 금지'
                   if partial else '시도·지구·사업명 블록·총세대수 일치 · 동일 사업 후보, 담당자 최종 확인 필요')
            if contained:basis=f'시도·지구·블록 일치 및 공식 유형별 구성 확인 · 전체 {units}호 중 {tenure_key(p.get("tenure"))} {target}호의 포함 관계 · 담당자 검토 필요'
            if partial and not contained:
                evidence=[dict(f,scope_partial=True,scope_units=units,scope_label=(r.get('tenure') or '주택유형')+' '+str(units)+'호 / 전체 '+str(target)+'호') for f in evidence]
            if 'MULTI_SITE_CONTRACT' in p.get('warnings',[]):basis+=' · 복합 계약: 별도 공식 승인 문서의 주택 구성·총호수 대조, 비주택 범위 제외 검토'
            if str(p.get('block'))!=str(r.get('block')):basis+=' · 원천 블록 표기 '+str(p.get('block'))+' / '+str(r.get('block'))
            proposals.append(dict(project_id=p['id'],name=p['name'],region=p['region'],source_entity_id=r['id'],
                source_revision_no=r.get('revision_no'),source_id=r['source_id'],evidence_source_id=r['source_id'],source_name=r['name'],
                relation_type='CONTAINED_SCOPE' if contained else 'PARTIAL_SCOPE' if partial else 'SAME_SCOPE',
                evidence_url=r.get('evidence_url'),units=units,match_key=list(key),facts=evidence,
                status='REVIEW',reviewed=False,basis=basis,matching_version=VERSION,base_date=today().isoformat()))
    added=0
    if apply:
        with service.sessions.begin() as db:
            if service.engine.dialect.name=='postgresql':db.execute(text('SELECT pg_advisory_xact_lock(1019081)'))
            for payload in proposals:
                key=payload['project_id']+':'+payload['source_entity_id']
                eid=entity_id(KIND,'cross_source',key)
                if db.scalar(select(Revision.id).where(Revision.entity_id==eid,Revision.superseded_at.is_(None))):continue
                row,_=upsert_revision(db,KIND,'cross_source',key,payload,'cross_source_repair')
                db.add(Audit(entity_id=row.entity_id,action='EVIDENCE_BRIDGE_AUTO',before={},after=payload));added+=1
    return dict(as_of_date=today().isoformat(),project_records=len(projects),proposed_links=len(proposals),
                affected_projects=len({p['project_id'] for p in proposals}),added_links=added,preserved_links=preserved,
                proposed_stage_facts=dict(Counter(f['stage'] for p in proposals for f in p['facts'])),proposals=proposals,held=held,
                notice='자료 연결 후보만 저장. 사업 물량 추가 합산·정책 귀속 확정·날짜 보간 없음. 담당자 판정/해제 링크는 재수집해도 보존.')


def review(service,link_id,revision_no,status,basis):
    if status not in ('REVIEW','CONFIRMED','RELEASED') or not basis.strip():raise ValueError('검토 상태와 근거를 입력하세요')
    with service.sessions.begin() as db:
        if service.engine.dialect.name=='postgresql':db.execute(text('SELECT pg_advisory_xact_lock(1019081)'))
        old=db.scalar(select(Revision).where(Revision.entity_id==link_id,Revision.kind==KIND,Revision.superseded_at.is_(None)).with_for_update())
        if old is None:raise ValueError('저장된 연결이 없습니다')
        if old.revision_no!=revision_no:return dict(conflict=True)
        payload=dict(old.payload,status=status,reviewed=True,review_basis=basis.strip(),reviewed_on=today().isoformat())
        row,_=upsert_revision(db,KIND,'cross_source',payload['project_id']+':'+payload['source_entity_id'],payload,'review')
        db.add(Audit(entity_id=link_id,action='EVIDENCE_BRIDGE_REVIEW',before=old.payload,after=payload))
        return dict(payload,id=row.entity_id,revision_no=row.revision_no)


def by_project(service,reference):
    result=defaultdict(list)
    origins={r['id']:r['source_id'] for kind in ('project','lh_completion_plan','document_evidence') for r in service.rows(kind,reference)}
    for row in service.rows(KIND,reference):
        row=dict(row,source_id=row.get('evidence_source_id') or origins.get(row['source_entity_id'],row['source_id']))
        result[row['project_id']].append(row)
    return result


def supply_notices(service,reference):
    """Full-scope stored recruitment evidence for map quantities; never sum rounds."""
    results={};owners=defaultdict(set)
    for pid,bridges in by_project(service,reference).items():
        choices=[]
        for bridge in bridges:
            if bridge.get('status') not in ('REVIEW','CONFIRMED'):continue
            for f in bridge.get('facts',[]):
                if f.get('stage')!='SUPPLY' or f.get('kind')!='ACTUAL' or f.get('scope_partial'):continue
                if not f.get('date') or f['date']>reference.isoformat() or not f.get('units'):continue
                key=bridge['source_entity_id'];owners[key].add(pid)
                choices.append(dict(id=key,name=bridge['source_name'],units=f['units'],source_date=f['date'],
                    source_id=bridge['source_id'],evidence_url=bridge['evidence_url'],review_status=bridge['status']))
        if choices:results[pid]=max(choices,key=lambda n:(n['units'],n['source_date']))
    return {pid:n for pid,n in results.items() if len(owners[n['id']])==1}
