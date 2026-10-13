"""Reviewable project-to-stage evidence links. Suggestions never invent source dates."""
from collections import Counter
from datetime import date
from difflib import SequenceMatcher
import re
import hashlib
import json
from sqlalchemy import select, or_, func
from .db import Revision, Audit, entity_id, upsert_revision
from .api_samples import today
from .supply_dashboard import block_key
from .evidence_bridge import match_key
from .roadmap import source_events

STAGES = {'BUSINESS': '사업화', 'APPROVAL': '인허가'}
KIND = 'stage_evidence'

def norm(value):
    return re.sub(r'[^가-힣A-Z0-9]', '', str(value or '').upper()).replace('공공주택지구', '').replace('국제화계획', '')

def evidence_key(row):
    """Normalize explicit district/block names without relying on source allowlists."""
    key=match_key(row)
    if key:return key
    if 'MULTI_SITE_CONTRACT' in row.get('warnings',[]):return None
    name=row.get('name','').upper()
    hits=list(re.finditer(r'(?<![A-Z0-9])([A-Z]{1,3})\s*[-－]?\s*(\d+)\s*(?:BL|블록|\b)',name))
    if len({(m[1],int(m[2])) for m in hits})!=1:return None
    prefix=name[:hits[0].start()].strip()
    if not prefix:return None
    return match_key(dict(row,district=prefix,block=hits[0][1]+hits[0][2]))


def search_term(project):
    key=evidence_key(project)
    if key:return key[1]
    return re.sub(r'\([^)]*(?:\)|$)','',project.get('district') or project['name']).strip()


def similarity(project, source):
    if project.get('region') != source.get('region'): return 0, '시도 불일치'
    pkey,skey=evidence_key(project),evidence_key(source)
    if pkey and skey:
        return (1, '동일 지구·단일 블록 (명칭 부가표기 정규화)') if pkey == skey else (0, '지구·블록 불일치')
    pa,sa=norm(project.get('address')),norm(source.get('address'))
    if len(pa)>=10 and pa==sa and re.search(r'\d',pa):
        return .91,'동일 상세 주소 · 필지/사업 동일성 담당자 확인 필요'
    title, candidate = norm(project['name']), norm(source['name'])
    district = norm(search_term(project))
    if district and district in candidate and pkey:
        match = re.search(r'([A-Z]{1,3})-?0*(\d+)(?:BL|블록|\b)', source['name'].upper())
        if match:
            return (.94, '지구명·블록 표기 일치') if match[1]+str(int(match[2])) == pkey[2] else (0, '다른 블록')
        if source.get('sample_kind') == 'plan_notice': return .78, '상위 지구 근거 · 블록 귀속 확인 필요'
        return 0, '블록 식별 근거 부족'
    if min(len(title),len(candidate)) < 4: return 0, '식별 이름 부족'
    if title == candidate: return .99, '사업명·시도 일치'
    ratio=SequenceMatcher(None,title,candidate).ratio()
    if title in candidate or candidate in title: ratio=max(ratio,.86)
    pc,sc=norm(project.get('municipality')),norm(source.get('municipality'))
    if pc and sc and pc not in sc and sc not in pc:return 0,'시군구 불일치'
    return (ratio, '사업명 유사도·동일 지역') if ratio >= .76 else (0, '이름 유사도 부족')

def candidate(source, stage, score, reason, event_date=None, observed_on=None, method='SIMILAR'):
    return dict(source_entity_id=source['id'],source_revision_no=source.get('revision_no'),
                source_id=source.get('source_id'),source_name=source['name'],stage=stage,
                evidence_url=source.get('evidence_url'),units=source.get('units',source.get('planned_units')),
                event_date=event_date,observed_on=observed_on or source.get('base_date'),
                method=method,score=round(score,3),basis=reason)

def propose(project, sources, permits):
    results={k:[] for k in STAGES}
    for source in sources+permits:
        score,reason=similarity(project,source)
        if not score:continue
        kind=source.get('sample_kind')
        if kind in ('permit','document_evidence'):
            facts=([dict(stage='APPROVAL',kind='ACTUAL',date=source.get('dates',{}).get('원천 허가일 (apprvDay)'),basis='건축HUB 원천 허가일')]
                   if kind=='permit' else source.get('facts',[]))
            for fact in facts:
                if fact.get('stage') not in STAGES or fact.get('kind')!='ACTUAL' or not fact.get('date'):continue
                when=fact['date']
                if when>today().isoformat():continue
                method='OFFICIAL_DOCUMENT' if kind=='document_evidence' else 'EXACT' if score>=.99 else 'SIMILAR'
                picked=candidate(source,fact['stage'],score,reason+' · '+fact.get('basis','원천 사건일'),when,method=method)
                picked['event_type']=fact.get('milestone') or 'PERMIT'
                total=source.get('units',source.get('planned_units'));target=project.get('planned_units')
                if total and target and total!=target:
                    # A quantity mismatch requires a true block match, never only fuzzy titles.
                    if not evidence_key(project) or evidence_key(project)!=evidence_key(source):continue
                    relation='PART_OF_APPROVAL' if target<total else 'PARTIAL_APPROVAL'
                    picked.update(relation_type=relation,source_units=total,units=min(total,target),
                                  scope_partial=target>total,scope_label=f'사업 {target:,}호 / 승인 원천 {total:,}호')
                    picked['basis']+=f' · 사업 {target:,}호 / 승인 원천 {total:,}호; 전체·부분 관계 후보, 담당자 확인 필요'
                results[fact['stage']].append(picked)
        else:
            status=source.get('source_stage') or source.get('stage_label') or ''
            results['BUSINESS'].append(candidate(source,'BUSINESS',score,reason+' · '+status,method='EXACT' if score>=.99 else 'SIMILAR'))
            if any(term in status for term in ('사업시행인가','사업계획승인','관리처분','착공','준공')):
                results['APPROVAL'].append(candidate(source,'APPROVAL',score,reason+' · 단계 현황에서 승인 도달 추정 · 허가일 미확보',method='STAGE_INFERENCE'))
    # A documented start is strong prerequisite evidence, not an invented permit date.
    if project.get('source_id') in ('lh_sale','lh_rent','lh_incheon_sale','lh_incheon_rent','gh_supply_plan'):
        results['BUSINESS'].append(candidate(project,'BUSINESS',.83,'공식 사업별 공급계획에 식별된 사업 · 사업화 상태 확인 필요 · 사건일 미확보',method='SIMILAR'))
    if project.get('start_actual_date') or (project.get('progress_pct') or 0)>0:
        for stage in STAGES:
            results[stage].append(candidate(project,stage,.8,'공식 착공 기록의 선행 단계 도달 추정 · 사업화·허가 원문 및 사건일 확인 필요',
                                            observed_on=project.get('start_actual_date') or project.get('progress_date') or project['base_date'],method='PREREQUISITE'))
    return {stage:sorted(values,key=lambda v:(v['score'],v['event_date'] or '',v['source_entity_id']),reverse=True)[:5] for stage,values in results.items()}

def refresh(service, refresh_candidates=False):
    """Persisted links are authoritative. Only missing links are auto-created.

    An explicit candidate refresh updates the alternatives, never the chosen link.
    Unmatched records are retried only if the evidence/project fingerprint changed.
    """
    projects=service.projects()
    saved={(r['project_id'],r['stage']):r for r in service.rows(KIND)}
    with service.sessions() as db:
        versions=list(db.execute(select(Revision.kind,func.count(),func.max(Revision.recorded_at)).where(
            Revision.kind.in_(('permit','renewal_inventory','sh_project','plan_notice','document_evidence')),
            Revision.superseded_at.is_(None)).group_by(Revision.kind)))
    evidence_version='stored-links-v3:'+repr(sorted(tuple(str(v) for v in row) for row in versions))
    fingerprints={p['id']:hashlib.sha256((evidence_version+json.dumps({k:p.get(k) for k in
        ('id','revision_no','name','region','district','block','address','start_actual_date','progress_pct','progress_date','base_date')},sort_keys=True)).encode()).hexdigest() for p in projects}
    counts=Counter();work={}
    for p in projects:
        todo=[]
        for stage in STAGES:
            old=saved.get((p['id'],stage))
            if not refresh_candidates and old and (old.get('selected') or old.get('reviewed') or old.get('matching_fingerprint')==fingerprints[p['id']]):
                counts['preserved']+=1
            else:todo.append(stage)
        if todo:work[p['id']]=todo
    projects=[p for p in projects if p['id'] in work]
    if not projects:return dict(counts)
    sources=[]
    for kind in ('renewal_inventory','sh_project','plan_notice','document_evidence'):
        sources.extend(dict(s,sample_kind=kind) for s in service.rows(kind))
    permit_pool=[]
    # One batched query per region, instead of scanning permit names per project.
    regions={p['region'] for p in projects}
    for region in regions:
        terms={search_term(p) for p in projects if p['region']==region}
        terms={term for term in terms if len(term)>=3}
        addresses={p['address'].strip() for p in projects if p['region']==region and len(p.get('address') or '')>=10 and re.search(r'\d',p['address'])}
        if not terms:continue
        with service.sessions() as db:
            q=select(Revision).where(Revision.kind=='permit',Revision.superseded_at.is_(None),Revision.sample_region==region,
                or_(*(Revision.sample_name.contains(term,autoescape=True) for term in terms),
                    *(Revision.payload['address'].as_string()==addr for addr in addresses))).limit(10001)
            records=list(db.scalars(q))
            if len(records)>10000:raise ValueError('인허가 후보 1만 건 초과 · 조회 범위 세분화 필요')
            permit_pool.extend(dict(r.payload,id=r.entity_id,source_id=r.source_id,revision_no=r.revision_no,sample_kind='permit') for r in records)
    for p in projects:
        permits=[r for r in permit_pool if r['region']==p['region']]
        suggestions=propose(p,sources,permits)
        for stage,choices in suggestions.items():
            if stage not in work[p['id']]:continue
            key=p['id']+':'+stage
            with service.sessions.begin() as db:
                if service.engine.dialect.name=='postgresql':
                    from sqlalchemy import text
                    db.execute(text('SELECT pg_advisory_xact_lock(1019078)'))
                eid=entity_id(KIND,'stage_match',key)
                old=db.scalar(select(Revision).where(Revision.entity_id==eid,Revision.superseded_at.is_(None)))
                # Re-check under the write lock so a concurrent reviewer always wins.
                if old and not refresh_candidates and (old.payload.get('reviewed') or old.payload.get('selected')):
                    counts['preserved']+=1;continue
                picked=choices[0] if choices else None
                payload=dict(project_id=p['id'],name=p['name'],region=p['region'],stage=stage,
                    policy_id=p.get('mapping',{}).get('policy_id'),status='REVIEW' if picked else 'UNMATCHED',
                    selected=picked,candidates=choices,reviewed=False,base_date=today().isoformat(),
                    matching_fingerprint=fingerprints[p['id']],matching_version='stored-links-v3')
                if old and (old.payload.get('selected') or old.payload.get('reviewed')):
                    payload=dict(old.payload,candidates=choices,matching_fingerprint=fingerprints[p['id']],matching_version='stored-links-v3')
                    previous=old.payload.get('selected') or {}
                    if not old.payload.get('reviewed') and old.payload.get('status')=='REVIEW' and previous.get('method') in ('PREREQUISITE','STAGE_INFERENCE') and picked and picked.get('event_date') and picked['score']>=.99 and not picked.get('scope_partial'):
                        payload.update(selected=picked,status='REVIEW',upgrade_basis='미검토 선행단계 추정을 공식 사건일 후보로 보강; 담당자 최종 검토 필요')
                        counts['inference_upgraded']+=1
                    counts['candidate_lists_updated']+=int(old.payload.get('candidates')!=choices)
                row,outcome=upsert_revision(db,KIND,'stage_match',key,payload,'stage_match')
                if outcome!='unchanged':db.add(Audit(entity_id=eid,action='STAGE_CANDIDATES_UPDATED' if old and (old.payload.get('selected') or old.payload.get('reviewed')) else 'STAGE_EVIDENCE_AUTO',before=old.payload if old else {},after=payload))
                counts[payload['status']]+=1
    return dict(counts)

def list_links(service,policy_id=None,as_of=None):
    projects={p['id']:p for p in service.projects(as_of=as_of,policy_id=policy_id)}
    stored={(r['project_id'],r['stage']):r for r in service.rows(KIND,as_of)}
    evidence_ids={r['selected']['source_entity_id'] for r in stored.values() if r.get('selected') and r['selected'].get('source_entity_id')}
    current_versions={}
    if evidence_ids:
        with service.sessions() as db:
            current_versions=dict(db.execute(select(Revision.entity_id,Revision.revision_no).where(Revision.entity_id.in_(evidence_ids),Revision.superseded_at.is_(None))).all())
    items=[]
    for pid,p in projects.items():
        for stage in STAGES:
            r=stored.get((pid,stage),dict(project_id=pid,stage=stage,status='UNMATCHED',revision_no=0,selected=None,candidates=[],reviewed=False))
            selected=r.get('selected') or {};latest=current_versions.get(selected.get('source_entity_id'))
            items.append(dict(r,source_revision_changed=latest is not None and selected.get('source_revision_no') is not None and latest!=selected['source_revision_no'],current_source_revision=latest,name=p['name'],region=p['region'],planned_units=p.get('planned_units'),policy_id=p.get('mapping',{}).get('policy_id'),program=p.get('program'),source_targets=source_events(p,as_of or today())))
    from .stage_evidence_duplicates import annotate_duplicates
    items=annotate_duplicates(items,projects)
    return dict(items=items,counts=dict(Counter(r['status'] for r in items)),
        duplicate_counts=dict(suspected=sum(r['duplicate_suspected'] for r in items),not_suspected=sum(not r['duplicate_suspected'] for r in items)),stages=STAGES,
        target_settings=next((r for r in service.rows('delivery_setting',as_of) if r.get('policy_id')=='POL_2025_0907'),dict(targets=[])))

def save_link(service,project_id,stage,revision_no,status,selected,basis):
    project=next((p for p in service.projects() if p['id']==project_id),None)
    if not project or stage not in STAGES:raise ValueError('사업 또는 단계가 올바르지 않습니다')
    if status not in ('REVIEW','CONFIRMED','RELEASED'):raise ValueError('검토 상태 오류')
    if status!='RELEASED':
        if not selected or not str(selected.get('evidence_url','')).startswith('https://'):raise ValueError('연결 근거 HTTPS URL을 입력하세요')
        if not selected.get('event_date') and not selected.get('observed_on'):raise ValueError('사건일 또는 상태 확인 기준일을 입력하세요')
        for field in ('event_date','observed_on'):
            if selected.get(field):
                if date.fromisoformat(selected[field])>today():raise ValueError('실적·상태 확인일에 미래 날짜를 사용할 수 없습니다')
        units=selected.get('units')
        if selected.get('scope_partial') and selected.get('source_units') is not None and (units is None or units>selected['source_units']):raise ValueError('일부 승인 근거는 확보된 원천 호수 이내의 적용 물량을 입력하세요')
        if units is not None and (units<0 or units>(project.get('planned_units') or 1350000)):raise ValueError('연결 물량은 사업 계획량 이내로 입력하세요')
        if status=='CONFIRMED' and selected.get('method')=='PREREQUISITE':raise ValueError('착공 선행 추정의 확정은 공식 근거 또는 담당자 확인 근거로 변경하세요')
    eid=entity_id(KIND,'stage_match',project_id+':'+stage)
    with service.sessions.begin() as db:
        if service.engine.dialect.name=='postgresql':
            from sqlalchemy import text
            db.execute(text('SELECT pg_advisory_xact_lock(1019078)'))
        old=db.scalar(select(Revision).where(Revision.entity_id==eid,Revision.superseded_at.is_(None)).with_for_update())
        if (old.revision_no if old else 0)!=revision_no:return dict(conflict=True)
        payload=dict(old.payload if old else {},project_id=project_id,stage=stage,name=project['name'],region=project['region'],
            policy_id=project.get('mapping',{}).get('policy_id'),selected=selected,status=status,basis=basis,reviewed=True,base_date=today().isoformat())
        row,outcome=upsert_revision(db,KIND,'stage_match',project_id+':'+stage,payload,'manual')
        if outcome!='unchanged':db.add(Audit(entity_id=eid,action='STAGE_EVIDENCE_REVIEW',before=old.payload if old else {},after=payload))
        return dict(payload,revision_no=row.revision_no)

def linked_events(service,as_of):
    result={}
    for row in service.rows(KIND,as_of):
        picked=row.get('selected')
        if row['status'] not in ('REVIEW','CONFIRMED') or not picked:continue
        effective=picked.get('event_date') or picked.get('observed_on')
        if not effective or effective>as_of.isoformat():continue
        result.setdefault(row['project_id'],[]).append(dict(stage=row['stage'],event_date=effective,
            source_event_date=picked.get('event_date'),date_basis='EVENT' if picked.get('event_date') else 'OBSERVED_BY',
            units=picked.get('units'),status='ACTUAL' if picked.get('event_date') and picked.get('method') not in ('PREREQUISITE','STAGE_INFERENCE') else 'STATE',review_status=row['status'],origin='LINKED_EVIDENCE',
            method=picked.get('method'),basis=picked.get('basis'),evidence_url=picked['evidence_url'],source_id=picked.get('source_id')))
    return result
