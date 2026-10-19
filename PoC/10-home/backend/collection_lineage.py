"""Read-only field-level provenance of stored project links (no new matching)."""
import re
from datetime import datetime,time,timedelta,timezone
from zoneinfo import ZoneInfo
from sqlalchemy import select, func, tuple_
from .db import Revision, ProgramMapping, Audit

SOURCE_FIELDS = {
    'name':'사업·공고명', 'region':'시도', 'municipality':'시군구',
    'district':'지구명', 'block':'블록', 'address':'주소', 'program':'사업 유형·프로그램',
    'source_object_id':'기관 원본 번호', 'house_manage_no':'주택관리번호',
    'sigungu_code':'시군구 코드', 'bjdong_code':'법정동 코드',
    'pnu':'필지 PNU', 'bun':'지번 본번', 'ji':'지번 부번',
    'planned_units':'계획 호수', 'units':'원천 호수', 'tenure':'분양·임대 유형', 'developer':'시행기관',
}
MATCH_LABELS = {
    'EXACT':'지구·블록 또는 사업명·지역 일치', 'SIMILAR':'사업명·주소·지역 대조',
    'OFFICIAL_DOCUMENT':'공식 문서의 사업·사건 근거 대조',
    'CROSS_SOURCE':'시도·지구·블록과 물량 범위 대조',
    'PREREQUISITE':'착공 기록으로 선행 단계 연결', 'STAGE_INFERENCE':'원천 추진단계로 선행 단계 연결',
    'POLICY_ASSIGNMENT':'프로그램·사업 유형에 따른 정책 배정',
    'DIRECT_INPUT':'대상 사업·단계를 지정해 입력', 'SOURCE_RECORD':'같은 수집 사업 기록의 단계 정보',
    'STORED_LINK':'저장된 원천 연결 근거 적용',
}

def comparison_fields(row):
    return {k:row[k] for k in SOURCE_FIELDS if row.get(k) is not None and str(row[k]).strip()}


def assignment_explanation(raw, mapping, program, project_history, program_history, policy_names, source_id=None):
    """Compare saved values and retain historical reasons, without rematching."""
    def compare(label, left_label, left, right_label, right):
        available=left not in (None,'','UNASSIGNED') and right not in (None,'','UNASSIGNED')
        return dict(label=label,left_label=left_label,left=left,right_label=right_label,right=right,
                    result='일치' if available and left==right else '다른 값으로 배정' if available else '대조값 미기록')
    def history(records):
        result=[]
        for record in records:
            for side in ('before','after'):
                value=record[side]
                if value.get('basis') and (not result or result[-1]['basis']!=value['basis']):
                    result.append(dict(basis=value['basis'],rule=value.get('rule'),
                        label='변경 전 배정 근거' if side=='before' else '자동 배정 기록' if record['action'].endswith('_AUTO') else '배정·확인 기록',
                        recorded_at=record['recorded_at'] if side=='after' else None))
        return result
    source_program=raw.get('program')
    target_program=program.get('name') or mapping.get('program_name')
    seed=program.get('seed_policy_id')
    target_policy=mapping.get('policy_id')
    policy_name=lambda pid: policy_names.get(pid,pid)
    project_rows=[compare('저장 분류 → 프로그램 배정','저장된 사업 분류값',source_program,'배정 프로그램',target_program)]
    classification=None
    if source_id=='lh_construction' and raw.get('district'):
        from .matching_rules import construction_program_classification
        rule=construction_program_classification(raw['district'])
        # Explicitly a comparison with the collector rule, not a fabricated historical trace.
        classification=dict(label='수집 분류 기준과 저장값 대조',field=rule['field'],value=rule['value'],
            criterion='지구명에 '+', '.join(rule['keywords'])+' 중 하나가 포함되면 3기 신도시, 그 외는 공공주택 건설',
            matched=' · '.join(rule['matched']) if rule['matched'] else '해당 키워드 없음',
            output=rule['program'],agrees=rule['program']==source_program)
        if not rule['matched']:
            classification['note']='기존 수집기가 키워드 미해당 사업에 부여한 기본 분류입니다. 공공주택 여부를 별도 추출 항목으로 대조한 기록은 아닙니다.'
    if source_id in ('lh_rent','lh_incheon_rent','lh_sale','lh_incheon_sale'):
        from .matching_rules import lh_plan_program_classification
        rent=source_id in ('lh_rent','lh_incheon_rent')
        rule=lh_plan_program_classification(rent,raw.get('name'),raw.get('tenure'))
        extracted=[{k:r.get(k) for k in ('name','region','tenure','area','units','supply_raw')}
                   for r in raw.get('rows',[]) if isinstance(r,dict)]
        source_name='LH 연간 임대주택 공급계획' if rent else 'LH 연간 분양주택 공급계획'
        classification=dict(label='원문 추출값 → 시스템 분류',field='유형',value=raw.get('tenure'),
            source_name=source_name,source_url=raw.get('evidence_url'),source_title=raw.get('name'),
            extracted_rows=extracted,output=rule['program'],agrees=rule['program']==source_program,
            checks=[dict(field='수집 대상 자료',value=source_name,condition='임대 공급계획 출처' if rent else '분양 공급계획 출처',result='해당'),
                    dict(field='원문 유형',value=raw.get('tenure'),condition='유형에 ‘매입’ 또는 ‘전세’가 포함된 행은 제외',
                         result='제외 대상' if rule['excluded'] else '제외 조건에 해당하지 않음' if raw.get('tenure') else '유형 값 미기록')],
            criterion='임대 공급계획 출처에서 매입·전세 유형을 제외하고 남은 행에 ‘건설형 공공임대’를 부여' if rent else
                      '분양 공급계획의 지구명/공급예정지역에 왕숙·창릉·교산·대장이 포함되면 3기 신도시, 그 외는 공공택지·공공분양',
            note='‘'+str(source_program or '미기록')+'’는 시스템이 부여한 분류명입니다. 원문 ‘유형’ 열의 추출값과 구분합니다.')
        if not rent:
            classification['checks'].append(dict(field='지구명/공급예정지역',value=raw.get('name'),
                condition='왕숙·창릉·교산·대장 포함 여부',result=' · '.join(rule['matched']) or '키워드 없음 · 기본 분류 적용'))
    policy_rows=[compare('프로그램의 상위 정책','프로그램 생성 시 정책 후보',policy_name(seed),
                         '배정 정책',policy_name(target_policy))]
    # IDs determine equality; a policy title can be shared by different records.
    policy_rows[0]['result']=compare('', '',seed,'',target_policy)['result']
    source_candidate=raw.get('proposed_policy')
    if source_candidate:
        row=compare('사업 수집 시 정책 후보','수집기에 설정된 정책 후보',source_candidate,'배정 정책',target_policy)
        row['left'],row['right']=policy_name(source_candidate),policy_name(target_policy)
        policy_rows.append(row)
    project_rule=('수집·분류된 사업 유형과 배정된 프로그램명이 같습니다.' if source_program and source_program==target_program
                  else '수집 분류값과 다른 프로그램으로 배정되었습니다. 아래 배정·변경 기록을 적용합니다.' if source_program and target_program
                  else '분류값만으로 대조할 수 없어 저장된 배정 기록을 표시합니다.')
    if mapping.get('status')=='RELEASED':project_rule='해제된 사업 배정입니다.'
    policy_rule=('프로그램 생성 시 연결한 정책 후보를 상위 정책으로 유지한 배정입니다.' if seed and seed==target_policy and seed!='UNASSIGNED'
                 else '프로그램의 최초 정책 후보에서 상위 정책을 변경한 배정입니다. 아래 배정·변경 기록을 적용합니다.' if seed and seed!='UNASSIGNED' and target_policy and target_policy!='UNASSIGNED'
                 else '저장된 프로그램–정책 배정 기록을 적용합니다.')
    return dict(project=dict(rows=project_rows,classification=classification,explanation=project_rule,history=history(project_history)),
                policy=dict(rows=policy_rows,explanation=policy_rule,history=history(program_history),
                    note='정책 후보는 수집·분류 과정에서 부여한 값입니다. 정책 원문에서 사업명·지구명이 일치한 결과를 뜻하지 않습니다.'))


def matching_info(e, project, raw):
    """Explain persisted decisions; never rerun matching or invent a field trace."""
    method=e.get('original_method') or e.get('method')
    if e.get('link_origin')=='POLICY_ASSIGNMENT':method='POLICY_ASSIGNMENT'
    elif e.get('source_id') in ('officer','manual_delivery'):method='DIRECT_INPUT'
    elif not method:
        method='SOURCE_RECORD' if raw and e.get('source_id')==project.get('source_id') and (
            not e.get('source_entity_id') or e['source_entity_id']==project['id']) else 'STORED_LINK'
    return dict(method=method,label=MATCH_LABELS.get(method,'저장된 연결 규칙: '+method),
                basis=e.get('basis') or '저장된 상세 매칭 사유 없음',
                decision_basis=e.get('decision_basis'),score=e.get('match_score'),
                match_key=e.get('match_key'),version=e.get('matching_version'),
                relation_type=e.get('relation_type'),status=e.get('review_status'))

LABELS={'region':'시도','municipality':'시군구','legal_dong':'법정동 코드','pnu':'필지 PNU',
        'block':'지구·블록','project':'사업 ID','policy':'정책 ID','program':'프로그램 ID',
        'permit':'허가 PK','notice':'주택관리번호','start':'실제 착공일','progress':'공정률',
        'completion':'준공 근거','supply':'모집공고일','move_plan':'입주 예정월','move_actual':'입주 시작일',
        'target':'사업 계획량','due':'목표·예정일','actual':'실적 관측일','coordinates':'사업 자체 좌표'}

def fields(row,kind=None):
    result={}
    for key,field in [('region','region'),('municipality','municipality'),('target','planned_units'),
                      ('start','start_actual_date'),('progress','progress_pct'),('completion','completion_actual_date'),
                      ('move_actual','move_in_actual_date'),('notice','house_manage_no')]:
        if row.get(field) is not None and str(row[field]).strip():result[key]=str(row[field])
    code=str(row.get('sigungu_code') or '')+str(row.get('bjdong_code') or '')
    if re.fullmatch(r'\d{10}',code):result['legal_dong']=code
    pnu=str(row.get('pnu') or '')
    if re.fullmatch(r'\d{19}',pnu):result['pnu']=pnu
    if row.get('district') and row.get('block'):result['block']=str(row['district'])+' / '+str(row['block'])
    if kind=='permit' and row.get('source_object_id'):result['permit']=str(row['source_object_id'])
    if kind=='notice' and row.get('source_date'):result['supply']=row['source_date']
    if row.get('move_in_plan_month'):result['move_plan']=row['move_in_plan_month']
    if row.get('longitude') is not None and row.get('latitude') is not None:
        result['coordinates']=str(row['longitude'])+', '+str(row['latitude'])+(' · '+row.get('location_label','근사 위치') if str(row.get('coordinate_basis','')).startswith('APPROXIMATE') else '')
    return result

def enrich(service,projects,items,reference,source_states,baselines=None,policy_names=None):
    refs={(e.get('source_entity_id'),e.get('source_revision_no')) for p in items for c in p['cells'].values()
          for e in c['sources'] if e.get('source_entity_id')}
    refs.update((p['id'],p.get('revision_no')) for p in projects)
    versions={}
    cutoff=datetime.combine(reference+timedelta(days=1),time.min,ZoneInfo('Asia/Seoul')).astimezone(timezone.utc)
    if refs:
        with service.sessions() as db:
            columns=(Revision.entity_id,Revision.revision_no,Revision.kind,Revision.payload)
            pinned=[(eid,rev) for eid,rev in refs if rev is not None]
            # Fetch the persisted revision only, rather than its entire history.
            for offset in range(0,len(pinned),400):
                query=select(*columns).where(tuple_(Revision.entity_id,Revision.revision_no).in_(pinned[offset:offset+400]),Revision.recorded_at<cutoff)
                for eid,rev,kind,payload in db.execute(query):versions[(eid,rev)]=(kind,payload)
            unpinned=[eid for eid,rev in refs if rev is None]
            if unpinned:
                latest=select(Revision.entity_id,func.max(Revision.revision_no).label('rev')).where(
                    Revision.entity_id.in_(unpinned),Revision.recorded_at<cutoff).group_by(Revision.entity_id).subquery()
                query=select(*columns).join(latest,(Revision.entity_id==latest.c.entity_id)&(Revision.revision_no==latest.c.rev))
                for eid,rev,kind,payload in db.execute(query):versions[(eid,None)]=(kind,payload)
    program_ids={p.get('mapping',{}).get('program_id') for p in projects}-{None,'UNASSIGNED'}
    programs={}
    if program_ids:
        with service.sessions() as db:
            for r in db.scalars(select(ProgramMapping).where(ProgramMapping.id.in_(program_ids),ProgramMapping.created_at<cutoff)):
                programs[r.id]=dict(name=r.name,seed_policy_id=r.seed_policy_id,policy_id=r.policy_id,basis=r.basis,status=r.status,evidence_url=r.evidence_url)
            for change in db.scalars(select(Audit).where(Audit.entity_id.in_(program_ids),
                    Audit.action.in_(('PROGRAM_POLICY_REVIEW','PROGRAM_POLICY_AUTO','PROGRAM_POLICY_MERGE')),
                    Audit.recorded_at>=cutoff).order_by(Audit.recorded_at.desc())):
                if change.entity_id in programs:programs[change.entity_id].update(change.before)
    histories={}
    ids=program_ids|{p['id'] for p in projects}
    if ids:
        with service.sessions() as db:
            for change in db.scalars(select(Audit).where(Audit.entity_id.in_(ids),Audit.recorded_at<cutoff,
                    Audit.action.in_(('MAPPING_AUTO','MAPPING_REVIEW','PROGRAM_PROJECT_REVIEW','PROGRAM_SOURCE_SUPPLEMENT',
                                     'PROGRAM_PROJECT_MERGE','PROGRAM_POLICY_REVIEW','PROGRAM_POLICY_AUTO','PROGRAM_POLICY_MERGE'))
                    ).order_by(Audit.recorded_at,Audit.id)):
                histories.setdefault(change.entity_id,[]).append(dict(action=change.action,before=change.before or {},
                    after=change.after or {},recorded_at=change.recorded_at.isoformat()))
    lookup={p['id']:p for p in projects}
    baselines=baselines if baselines is not None else service.rows('execution_schedule',reference)
    baseline_stages={}
    for b in baselines:
        if b.get('baseline') and b.get('status')!='RELEASED':baseline_stages.setdefault(b['project_id'],[]).append(b['stage'])
    parcel_links={r['project_id']:r for r in service.rows('project_parcel',reference)}
    for item in items:
        p=lookup[item['id']];keys=fields(p,'project');keys['project']=p['id']
        mapping=p.get('mapping',{})
        _,base_raw=versions.get((p['id'],p.get('revision_no')),(None,{}))
        if mapping.get('status')!='RELEASED':
            for key,field in [('policy','policy_id'),('program','program_id')]:
                if mapping.get(field) and mapping[field]!='UNASSIGNED':keys[key]=mapping[field]
        sources={p['source_id']:dict(keys=fields(p,'project'),inferred=False,review=False,base=True)}
        stage_keys={}
        stage_links={}
        for stage,cell in item['cells'].items():
            stage_keys[stage]={}
            stage_links[stage]=[]
            if stage=='CONSTRUCTION':stage_keys[stage].update({k:v for k,v in fields(p,'project').items() if k in ('start','progress','completion')})
            if stage=='MOVE_IN':stage_keys[stage].update({k:v for k,v in fields(p,'project').items() if k=='move_actual'})
            for e in cell['sources']:
                if e['kind']=='PLAN_STATUS':continue
                kind,raw=versions.get((e.get('source_entity_id'),e.get('source_revision_no')),(None,{}))
                match_kind,match_raw=kind,raw
                # Own-record dates have no separate evidence reference in the matrix.
                if not e.get('source_entity_id') and e.get('source_id')==p['source_id']:
                    match_kind,match_raw=('project',base_raw) if base_raw else (None,{})
                own=fields(raw,kind)
                if stage=='POLICY':own.update({k:keys[k] for k in ('policy','program') if k in keys})
                if e['kind']=='PLAN' and e.get('date'):
                    own['due']=e['date']
                    if stage=='MOVE_IN':own['move_plan']=e['date']
                if e['kind']=='ACTUAL' and e.get('date'):
                    own['actual']=e['date']
                    if stage=='MOVE_IN':own['move_actual']=e['date']
                    if stage=='SUPPLY':own['supply']=e['date']
                if e.get('pct') is not None:own['progress']=str(e['pct'])
                stage_links[stage].append(dict(
                    project_id=p['id'], stage=stage, source_id=e['source_id'],
                    source_entity_id=e.get('source_entity_id'),
                    source_revision_no=e.get('source_revision_no'),
                    source_object_id=match_raw.get('source_object_id'),
                    source_record_available=match_kind is not None, keys=dict(own),
                    source_fields=comparison_fields(match_raw),matching=matching_info(e,p,match_raw),
                    source_title=match_raw.get('name') or match_raw.get('title') or e.get('name'),
                    source_date=match_raw.get('source_date') or match_raw.get('base_date'),
                    source_url=match_raw.get('evidence_url') or e.get('evidence_url'),
                    source_facts=fields(match_raw,match_kind),
                    kind=e['kind'], method=e.get('method'),
                    name=e.get('name'), basis=e.get('basis'), date=e.get('date'),
                    evidence_url=e.get('evidence_url')))
                keys.update(own)
                stage_keys[stage].update(own)
                s=sources.setdefault(e['source_id'],dict(keys={},inferred=False,review=False,base=False))
                s['keys'].update(own);s['inferred']|=e.get('method') in ('PREREQUISITE','STAGE_INFERENCE');s['review']|=e.get('review_status')=='REVIEW'
        parcel=parcel_links.get(p['id'])
        if parcel and parcel.get('status')!='RELEASED':
            active_refs={(e.get('source_entity_id'),e.get('source_revision_no')) for cell in item['cells'].values() for e in cell['sources']}
            candidates=[c for c in parcel.get('candidates',[]) if (c['permit_entity_id'],c['permit_revision_no']) in active_refs]
            parcel=dict(parcel,candidates=candidates,pnus=sorted({c['pnu'] for c in candidates}))
            if not parcel['pnus'] and parcel.get('status')=='CANDIDATE':parcel=dict(parcel,status='MISSING',missing_reasons=['PERMIT_LINK_MISSING'])
            if parcel.get('pnus'):keys['pnu']=' / '.join(parcel['pnus'])
            from .parcel_identity import REASONS
            item['parcel_identity']=dict(parcel,missing_reason_labels=[REASONS.get(k,k) for k in parcel.get('missing_reasons',[])])
            for candidate in parcel.get('candidates',[]):
                source=sources.setdefault(candidate['source_id'],dict(keys={},inferred=False,review=True,base=False))
                source['keys']['pnu']=candidate['pnu'];source['review']=True
        shared={k:v for k,v in keys.items() if k in ('region','municipality','legal_dong','pnu','block','project','policy','program','target','coordinates')}
        item['lineage']=dict(keys=keys,stage_keys={s:{**shared,**v} for s,v in stage_keys.items()},
                            stage_links=stage_links,
                            identity=dict(project_id=p['id'],source_id=p['source_id'],
                                source_fields=comparison_fields(base_raw),
                                source_title=base_raw.get('name'),source_url=base_raw.get('evidence_url'),
                                source_date=base_raw.get('base_date'),
                                mapping={k:mapping.get(k) for k in ('policy_id','program_id','program_name','basis','status','revision_no','evidence_url')},
                                program_mapping=programs.get(mapping.get('program_id'),{}),
                                assignment=assignment_explanation(base_raw,mapping,programs.get(mapping.get('program_id'),{}),
                                    histories.get(p['id'],[]),histories.get(mapping.get('program_id'),[]),policy_names or {},p['source_id'])),
                            sources=sources,baseline_stages=baseline_stages.get(p['id'],[]))
    return dict(key_labels=LABELS,source_field_labels=SOURCE_FIELDS,sources={sid:dict(name=s['name'],org=s.get('org'),record_count=s.get('record_count',0),
        status=s.get('status'),last_success=s.get('last_success'),method='API' if s.get('key_env') else '파일' if s.get('collection_mode') in ('PUBLIC_FILE','AGENCY_PLAN_FILE','HISTORY','LEGAL_PLAN_PILOT','PUBLIC_DOCUMENT') else '웹') for sid,s in source_states.items()},
        note='키 확보는 해당 필드가 연결된 자료에 있다는 뜻입니다. 코드 변환·필지 결합·사업 동일성 검토의 완료 여부와는 별개입니다.')
