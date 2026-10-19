"""Project × stage provenance. Read stored links; absence never proves non-planning."""
from collections import Counter, defaultdict
from datetime import date
import hashlib
import json

from sqlalchemy import select, func, text
from .db import Revision, Audit, entity_id, upsert_revision
from .api_samples import today
from .roadmap import source_events, month
from .plan_schedule import plan_schedule
from .construction_plan import construction_plan
from .supply_dashboard import inventory, linked_notices, block_key, SOURCE_ALIASES
from .occupancy_targets import occupancy_schedules
from .sources import SOURCES

STAGES = {'POLICY':'정책','BUSINESS':'사업화','APPROVAL':'인허가','CONSTRUCTION':'건설','SUPPLY':'공급','MOVE_IN':'입주'}
STATUS = {'ACQUIRED':'원천 확보','NOT_PLANNED':'미확보 · 아직 계획 미수립',
          'COLLECTION_REQUIRED':'원천 수집 필요','COLLECTION_UNAVAILABLE':'수집 불가 · 담당자 확인','LINK_REQUIRED':'원천 후보 있음 · 연결 필요','METHOD_UNKNOWN':'수집 방안 미확인'}
SHORT = {'policy_907':'9·7 정책 발표','policy_907_plan':'9·7 연도별 계획',
         'policy_129':'1·29 정책 발표','policy_813':'8·13 정책 발표','urban_930':'도심복합 후속자료',
         'policy_history':'정책 발표 이력','lh_sale':'LH 분양계획','lh_rent':'LH 임대계획',
         'lh_incheon_sale':'LH 인천 분양계획','lh_incheon_rent':'LH 인천 임대계획',
         'lh_construction':'LH 건설현황','lh_incheon_construction':'LH 인천 건설현황',
         'building_hub':'건축HUB 인허가','building_hub_incheon':'건축HUB 인천 인허가',
         'building_hub_details':'건축HUB 동별 상세','building_register':'건축물대장',
         'building_register_recap':'건축물대장 총괄표제부','molit_renewal_inventory':'국토부 정비사업 현황',
         'sh_inventory':'SH 사업현황','sh_supply_plan':'SH 공급계획','sh_redevelopment':'SH 정비사업 현황',
         'gh_supply_plan':'GH 공급계획','gh_notice':'GH 모집공고','cheongyak':'청약홈 본 모집공고',
         'lh_notice':'LH 모집공고','lh_notice_detail':'LH 공고 상세','lh_progress':'LH 공정 이력','lh_reit_progress':'LH 리츠 공정 보고',
         'lh_movein_history':'LH 연간 입주계획','lh_completion_plan':'LH 준공예정',
         'seoul_plan_notice_pilot':'서울 계획 고시','gyeonggi_plan_notice_pilot':'경기 계획 고시',
         'gh_completion_evidence':'GH 사용검사 증빙','official_document':'공식 공고·고시 원문','officer':'담당자 입력', 'manual_delivery':'담당자 목표·실적'}
CATALOG = {
 'POLICY':['policy_907','policy_129','policy_813','urban_930','policy_history'],
 'BUSINESS':['molit_renewal_inventory','sh_inventory','sh_redevelopment','lh_sale','lh_rent','gh_supply_plan','seoul_plan_notice_pilot','gyeonggi_plan_notice_pilot'],
 'APPROVAL':['building_hub','building_hub_incheon','building_hub_details','sh_redevelopment'],
 'CONSTRUCTION':['lh_construction','lh_incheon_construction','lh_progress','lh_reit_progress','lh_completion_plan','building_register_recap','gh_completion_evidence'],
 'SUPPLY':['cheongyak','lh_notice','gh_notice','lh_sale','lh_rent','sh_supply_plan','gh_supply_plan'],
 'MOVE_IN':['lh_notice_detail','lh_movein_history','cheongyak','lh_rent','lh_incheon_rent']}
for _stage in ('BUSINESS','CONSTRUCTION','SUPPLY'):
    CATALOG[_stage].append('ih_notice')
SHORT['ih_notice']='iH 공식 사업·주택 모집공고'
KEYS = {'POLICY':'정책 ID → 프로그램 ID → 사업 ID','BUSINESS':'사업 ID · 지구/블록 · 사업명',
        'APPROVAL':'사업 ID → 허가 PK · 상세주소/필지', 'CONSTRUCTION':'사업 ID · 지구/블록 · 공사번호',
        'SUPPLY':'사업 ID → 주택관리번호 · 지구/블록','MOVE_IN':'사업 ID · 지구/블록 → 시작일/예정월'}

def short(sid):
    return SHORT.get(sid, next((s['name'] for s in SOURCES if s['id']==sid),sid or '근거 원천'))


def collection_owner(project):
    """Agency of the project, not the publisher of a linked notice."""
    sid=project.get('source_id','');developer=project.get('developer') or ''
    for prefix,names,label in [('lh_',('LH','한국토지주택공사'),'LH'),
                               ('sh_',('SH','서울주택도시공사','서울주택도시개발공사'),'SH'),
                               ('gh_',('GH','경기주택도시공사'),'GH')]:
        if sid.startswith(prefix) or developer in names:return label
    return developer if developer and '확인' not in developer else '시행기관 미확인'


def summarize_gaps(items):
    groups={}
    for p in items:
        for gap in p.get('gaps',[]):
            key=(p['collection_owner'],gap['stage'],gap['code'],gap['reason'])
            group=groups.setdefault(key,dict(owner=key[0],**gap,project_ids=[],planned_projects=0))
            group['project_ids'].append(p['id'])
            group['planned_projects']+=bool(p['cells'][gap['stage']]['targets'])
    return sorted([dict(g,project_count=len(g['project_ids'])) for g in groups.values()],
                  key=lambda g:(-g['project_count'],g['owner'],g['stage'],g['code']))


PROGRESS = {'ACTUAL_REPORTED':'실적·진척 확인','PARTIAL_REPORTED':'일부 범위 실적 확인',
    'NOT_REACHED_REPORTED':'미진행 · 원천 추진단계 기준','UPCOMING':'예정 · 기한 전',
    'SCHEDULE_PENDING':'일정 미정 · 원문 확인','LINK_REQUIRED':'출처 확인 · 연결 필요',
    'ACTUAL_UNVERIFIED':'실적 미확인 · 추가 조회 필요','METHOD_UNKNOWN':'조회 방법 미확인'}

def progress_state(cell,stage,reference,phase=None,discovery=None):
    if cell['actual_available']:return dict(code='ACTUAL_REPORTED',label=PROGRESS['ACTUAL_REPORTED'])
    if cell.get('partial_actual_available'):return dict(code='PARTIAL_REPORTED',label=PROGRESS['PARTIAL_REPORTED'],reason='확보 자료는 사업 일부 범위이며 전체 단계 실적과 구분합니다.')
    if phase:
        name=phase['reported_phase'];rank=next((r for word,r in [('조합청산',5),('조합해산',5),('이전고시',5),('준공',4),('착공',3),('관리처분',2),('사업시행계획인가',2),('사업시행인가',2),('사업시행자지정',1),('조합설립',1),('추진위원회',1),('정비계획',1)] if word in name),None)
        need={'BUSINESS':1,'APPROVAL':2,'CONSTRUCTION':3,'SUPPLY':3,'MOVE_IN':4}.get(stage)
        if rank is not None and need and rank<need:
            return dict(code='NOT_REACHED_REPORTED',label=PROGRESS['NOT_REACHED_REPORTED'],source_phase=name,
                reason='공식 목록의 현재 표시는 '+name+'입니다. 후속 단계 완료나 일정 미정을 임의 확정하지 않으며 원천 갱신 상태는 담당자 확인 대상입니다.',
                observed_at=phase.get('phase_observed_at') or phase.get('base_date'),evidence_url=phase.get('evidence_url'))
    plans=[t for t in cell.get('targets',[]) if not t.get('reference_only') and (stage!='CONSTRUCTION' or t.get('milestone')!='COMPLETION')]
    dated=[t for t in plans if t.get('date') and len(t['date'])>=7]
    if dated and all(t['date'][:7]>reference.strftime('%Y-%m') for t in dated):
        return dict(code='UPCOMING',label=PROGRESS['UPCOMING'],reason='확보한 해당 단계 예정월이 기준월 이후입니다. 실제 미진행을 단정하지 않으며 계획과 실적을 구분합니다.',due_date=min(t['date'] for t in dated))
    if any(t.get('schedule_status')=='UNDETERMINED' for t in plans):
        return dict(code='SCHEDULE_PENDING',label=PROGRESS['SCHEDULE_PENDING'],reason='공식 원문이 일정 미정으로 표기한 경우입니다. 공란·항목 미제공·연결 누락과 다릅니다.')
    if discovery and discovery.get('status')=='LINK_PENDING' and stage in discovery.get('link_stages',[]):return dict(code='LINK_REQUIRED',label=PROGRESS['LINK_REQUIRED'],reason='관련 원문 후보를 발견했으나 사업 범위·사건 의미·원문 내용을 확인하고 DB 연결해야 합니다.')
    code='METHOD_UNKNOWN' if cell['status']=='METHOD_UNKNOWN' else 'ACTUAL_UNVERIFIED'
    return dict(code=code,label=PROGRESS[code])

def collection_gaps(cells):
    gaps=[]
    for stage,c in cells.items():
        if c['status']=='NOT_PLANNED':continue
        progress=c.get('progress',{})
        if stage!='POLICY' and not c['actual_available'] and progress.get('code') in ('UPCOMING','NOT_REACHED_REPORTED','SCHEDULE_PENDING'):
            gaps.append(dict(stage=stage,code=progress['code'],label=progress['label'],reason=progress.get('reason',''),action_required=False));continue
        # A timetable does not resolve the missing actual-occupancy feed.
        if stage in ('CONSTRUCTION','SUPPLY','MOVE_IN') and not c['actual_available']:
            code='LINK_REQUIRED' if progress.get('code')=='LINK_REQUIRED' else 'METHOD_UNKNOWN' if c['status']=='METHOD_UNKNOWN' or stage=='MOVE_IN' and c['status']=='ACQUIRED' else 'COLLECTION_REQUIRED'
            label={'CONSTRUCTION':'건설 현황','SUPPLY':'공급 실적','MOVE_IN':'입주 현황'}[stage]
            reason=c['assessment']['basis'] if c.get('assessment') and c['assessment']['status']!='RELEASED' else (
                '입주 예정자료와 별개로 실제 입주 시작일을 확인할 사업별 자료·조회 방법 미확인' if stage=='MOVE_IN' else
                '목표 일정과 별개로 실제 착공·공정률·준공 근거 연결 필요' if stage=='CONSTRUCTION' else
                '분양·모집 실적을 확인할 공고와 해당 사업의 저장 연결 필요')
        elif c['status'] in ('METHOD_UNKNOWN','COLLECTION_REQUIRED','LINK_REQUIRED'):
            code=c['status'];label=STAGES[stage]+' 자료';reason=c['reason']
        else:continue
        gaps.append(dict(stage=stage,code=code,label=label+(' 조회 방법 미확인' if code=='METHOD_UNKNOWN' else ' 원천 연결 필요' if code=='LINK_REQUIRED' else ' 원천 수집 필요'),reason=reason,action_required=True))
    return gaps


def collection_cell_text(cell):
    targets=' / '.join(t['label']+': '+str(t.get('date') or t.get('date_label'))+' ('+t['name']+')'+
        (' · 공급일 대체 아님' if t.get('reference_only') else '') for t in cell['targets']) or '일정 미확보'
    sources=' / '.join(dict.fromkeys(e['name'] for e in cell['sources'] if e['kind']!='PLAN_STATUS')) or cell['label']
    notes=' / '.join(e['basis'] for e in cell['sources'] if e['kind']=='PLAN_STATUS')
    if notes:sources+=' · '+notes
    progress=cell.get('progress',{})
    return (progress.get('label','')+' | ' if progress else '')+'목표: '+targets+' | 확보 정보: '+sources+(' · 실적·진척 있음' if cell['actual_available'] else ' · 실적 미확인')+(' · 연결 확인 필요' if cell['review_required'] else '')

def refresh_links(service, actor='자동 수집', reason='원천 변경 후 수집 연결 후보 갱신'):
    """Backfill once, then propose only new/changed unmatched objects at collection time."""
    projects=service.projects();saved={(r['project_id'],r['stage']):r for r in service.rows('collection_link')}
    with service.sessions() as db:
        versions=list(db.execute(select(Revision.kind,func.count(),func.max(Revision.recorded_at)).where(
            Revision.kind.in_(('notice','lh_movein_plan')),Revision.superseded_at.is_(None)).group_by(Revision.kind)))
    version=repr(sorted(tuple(str(v) for v in row) for row in versions))
    fingerprints={p['id']:hashlib.sha256((version+json.dumps({k:p.get(k) for k in ('id','revision_no','name','district','block','region','planned_units','rows')},sort_keys=True)).encode()).hexdigest() for p in projects}
    work={(p['id'],stage) for p in projects for stage in ('SUPPLY','MOVE_IN') if
          not (saved.get((p['id'],stage),{}).get('links') or saved.get((p['id'],stage),{}).get('fingerprint')==fingerprints[p['id']])}
    if not work:return {'preserved':len(saved)}
    normalized=[dict(p,source_id=SOURCE_ALIASES.get(p['source_id'],p['source_id'])) for p in projects]
    chosen,_=inventory(normalized)
    notices=linked_notices(chosen,service.rows('notice'),today())
    movein=occupancy_schedules(service,projects,today())
    # Preserve the existing conservative diagram/map proposal rules, then save them.
    by_key={block_key(p):notices[p['id']] for p in chosen if p['id'] in notices and block_key(p)}
    count=Counter()
    for p in projects:
        notice=notices.get(p['id']) or by_key.get(block_key(p));proposals={'SUPPLY':[],'MOVE_IN':[]}
        if notice:
            proposals['SUPPLY']=[dict(source_id=notice['source_id'],source_entity_id=notice['id'],source_revision_no=notice.get('revision_no'),
                evidence_url=notice['evidence_url'],date=notice['source_date'],basis='동일 지구·블록 본 모집공고 · 연결 확인 필요',kind='ACTUAL',review_status='REVIEW')]
            stamp=notice.get('move_in_plan_month')
            if stamp and len(stamp.replace('-',''))==6 and stamp.replace('-','').isdigit():
                stamp=stamp.replace('-','');proposals['MOVE_IN'].append(dict(source_id=notice['source_id'],source_entity_id=notice['id'],source_revision_no=notice.get('revision_no'),
                    evidence_url=notice['evidence_url'],date=stamp[:4]+'-'+stamp[4:],basis='본 모집공고 입주 예정월 · 실제 시작 아님',kind='PLAN',review_status='REVIEW'))
        proposals['MOVE_IN'] += [dict(source_id=s['source_id'],source_entity_id=s['source_object_id'],evidence_url=s.get('evidence_url'),
            date=s['due_date'],basis=s['basis'],kind='PLAN',review_status='REVIEW') for s in movein.get(p['id'],[]) if s['source_id']!=p['source_id']]
        for stage,links in proposals.items():
            if (p['id'],stage) not in work:count['preserved']+=1;continue
            with service.sessions.begin() as db:
                if service.engine.dialect.name=='postgresql':db.execute(text('SELECT pg_advisory_xact_lock(1019080)'))
                eid=entity_id('collection_link','stage_collection',p['id']+':'+stage)
                old=db.scalar(select(Revision).where(Revision.entity_id==eid,Revision.superseded_at.is_(None)))
                if old and old.payload.get('links'):count['preserved']+=1;continue
                payload=dict(project_id=p['id'],stage=stage,links=links,fingerprint=fingerprints[p['id']],base_date=today().isoformat())
                row,outcome=upsert_revision(db,'collection_link','stage_collection',p['id']+':'+stage,payload,'collection_link')
                if outcome!='unchanged':db.add(Audit(entity_id=eid,action='COLLECTION_LINK_AUTO',before=old.payload if old else {},after=dict(payload,actor=actor,reason=reason)))
                count['linked' if links else 'unmatched']+=1
    return dict(count)

def save_assessment(service,project_id,stage,revision_no,status,basis):
    if stage not in STAGES or status not in ('NOT_PLANNED','METHOD_UNKNOWN','COLLECTION_REQUIRED','COLLECTION_UNAVAILABLE','RELEASED'):
        raise ValueError('수집 판정 값 오류')
    if not basis.strip():raise ValueError('확인 근거 또는 제공처 조사 결과를 입력하세요')
    if not any(p['id']==project_id for p in service.projects()):raise ValueError('사업을 찾을 수 없습니다')
    with service.sessions.begin() as db:
        if service.engine.dialect.name=='postgresql':db.execute(text('SELECT pg_advisory_xact_lock(1019080)'))
        eid=entity_id('collection_assessment','officer',project_id+':'+stage)
        old=db.scalar(select(Revision).where(Revision.entity_id==eid,Revision.superseded_at.is_(None)))
        if revision_no!=(old.revision_no if old else 0):return {'conflict':True}
        payload=dict(project_id=project_id,stage=stage,status=status,basis=basis.strip(),base_date=today().isoformat())
        row,outcome=upsert_revision(db,'collection_assessment','officer',project_id+':'+stage,payload,'officer')
        if outcome!='unchanged':db.add(Audit(entity_id=eid,action='COLLECTION_ASSESSMENT',before=old.payload if old else {},after=payload))
        return dict(payload,revision_no=row.revision_no)

def collection_matrix(service,as_of=None,**filters):
    from .read_scope import projection_reads
    with projection_reads():
        return _collection_matrix(service,as_of,**filters)


def _collection_matrix(service,as_of=None,project_ids=None,**filters):
    reference=as_of or today();projects=service.projects(as_of=reference,**filters)
    if project_ids is not None:
        selected=set(project_ids)
        projects=[p for p in projects if p['id'] in selected]
    from .evidence_bridge import by_project
    bridges=by_project(service,reference)
    policies={p['policy_id']:p for p in service.policy_rows(reference)}
    stage_links={(r['project_id'],r['stage']):r for r in service.rows('stage_evidence',reference)}
    links={(r['project_id'],r['stage']):r for r in service.rows('collection_link',reference)}
    assessments={(r['project_id'],r['stage']):r for r in service.rows('collection_assessment',reference)}
    research=defaultdict(list)
    for r in service.rows('collection_research',reference):
        for pid in r.get('project_ids',[]):research[pid].append(r)
    all_documents={r['id']:r for r in service.rows('document_evidence',reference)}
    manual_events=defaultdict(list);manual_goals=defaultdict(list)
    for setting in service.rows('delivery_setting',reference):
        for e in setting.get('events',[]):manual_events[e['project_id']].append(e)
        for g in setting.get('targets',[]):
            if g.get('scope_kind')=='project' and g.get('origin')!='SCENARIO':manual_goals[g['scope_id']].append(g)
    profiles={r['project_id']:r for r in service.rows('project_profile',reference)}
    baselines=service.rows('execution_schedule',reference)
    for s in baselines:
        if s.get('status')!='RELEASED':manual_goals[s['project_id']].append(s)
    source_states={s['id']:s for s in service.sources()};items=[]
    documents=[r for r in service.rows('document_evidence',reference) if r['source_id']=='official_document']
    if documents:source_states['official_document']=dict(name='공식 공고·고시 원문',org='LH·국토부·지자체',record_count=len(documents),status='SUCCESS',collection_mode='PUBLIC_DOCUMENT')
    for p in projects:
        phase_sources=[all_documents.get(b.get('source_entity_id'),{}) for b in bridges.get(p['id'],[]) if b.get('status')!='RELEASED']
        phase_sources=[r for r in phase_sources if r.get('reported_phase')]
        phase=max(phase_sources,key=lambda r:r.get('phase_observed_at') or r.get('base_date',''),default=None)
        discovery=max(research.get(p['id'],[]),key=lambda r:(r.get('checked_at',''),r.get('iteration',1),r.get('status')=='LINK_PENDING'),default=None)
        evidence={stage:[] for stage in STAGES}
        def add(stage,sid,kind,basis,when=None,url=None,review=None,source_entity_id=None,**extra):
            if when and kind=='ACTUAL' and when>reference.isoformat():return
            evidence[stage].append(dict(source_id=sid,name=short(sid),kind=kind,basis=basis,date=when,evidence_url=url,
                review_status=review,source_entity_id=source_entity_id,**extra))
        mapping=p.get('mapping',{});policy=policies.get(mapping.get('policy_id'))
        if policy and mapping.get('status')!='RELEASED':
            add('POLICY',policy['source_id'],'LINK',mapping.get('basis') or '저장된 정책–프로그램–사업 연결',
                url=mapping.get('evidence_url') or policy.get('evidence_url'),review=mapping.get('status'),source_entity_id=policy['id'],officer_confirmed=mapping.get('basis','').startswith('사용자 입력'),link_origin='POLICY_ASSIGNMENT')
        for stage in ('BUSINESS','APPROVAL'):
            r=stage_links.get((p['id'],stage),{});picked=r.get('selected')
            if picked and r.get('status') in ('REVIEW','CONFIRMED'):
                add(stage,picked.get('source_id'),'ACTUAL' if picked.get('event_date') and (picked.get('original_method') or picked.get('method')) not in ('PREREQUISITE','STAGE_INFERENCE') else 'STATE',picked.get('basis'),picked.get('event_date') or picked.get('observed_on'),picked.get('evidence_url'),r['status'],picked.get('source_entity_id'),source_revision_no=picked.get('source_revision_no'),method=picked.get('method'),original_method=picked.get('original_method'),scope_partial=picked.get('scope_partial',False),scope_label=picked.get('scope_label'),relation_type=picked.get('relation_type'),source_units=picked.get('source_units'),units=picked.get('units'),event_type=picked.get('event_type'),officer_confirmed=bool(r.get('actor')),link_origin='STAGE_EVIDENCE',match_score=picked.get('score'),decision_basis=r.get('basis'))
        if p.get('start_actual_date'):add('CONSTRUCTION',p['source_id'],'ACTUAL','원천 실제 착공일',p['start_actual_date'],p.get('evidence_url'),milestone='CONSTRUCTION')
        source_progress=p.get('source_values',p)
        if source_progress.get('progress_pct') is not None:
            sid='lh_progress' if p.get('progress_evidence_url') and p.get('progress_evidence_url')!=p.get('evidence_url') else p['source_id']
            add('CONSTRUCTION',sid,'ACTUAL','준공까지 원천 공정률',source_progress.get('progress_date') or p.get('base_date'),p.get('progress_evidence_url') or p.get('evidence_url'),pct=source_progress['progress_pct'])
        if p.get('completion_actual_date') and p.get('completion_evidence_url'):
            add('CONSTRUCTION',p['source_id'],'ACTUAL','원천 실제 준공일',p['completion_actual_date'],p['completion_evidence_url'],milestone='COMPLETION')
        if p.get('move_in_actual_date'):
            add('MOVE_IN',p['source_id'],'ACTUAL','원천 입주 시작일',p['move_in_actual_date'],p.get('move_in_evidence_url') or p.get('evidence_url'))
        for e in source_events(p,reference):
            stage='CONSTRUCTION' if e['stage']=='COMPLETION' else e['stage']
            if stage in evidence:
                stamp=e['month']
                field={'CONSTRUCTION':'start_plan_date','COMPLETION':'completion_plan_date'}.get(e['stage'])
                if field and month(p.get(field))==stamp:stamp=p[field]
                add(stage,p['source_id'],'PLAN',e['basis'],stamp,e.get('evidence_url'),milestone=e['stage'],date_label=e.get('source_date_label'),date_conversion=e.get('date_conversion'),units=e.get('units'))
        # These sources already store contract schedules; the old matrix only read lh_construction.
        for field,milestone in [('start_plan_date','CONSTRUCTION'),('completion_plan_date','COMPLETION')]:
            stamp=p.get(field)
            if month(stamp) and not any(e['kind']=='PLAN' and e.get('milestone')==milestone and e['date']==stamp for e in evidence['CONSTRUCTION']):
                add('CONSTRUCTION',p['source_id'],'PLAN','원천 계약 착공 예정일' if milestone=='CONSTRUCTION' else '원천 예상 준공일 · 입주일 아님',stamp,p.get('evidence_url'),milestone=milestone)
        if p.get('start_plan_year') and not any(e['kind']=='PLAN' and e.get('milestone')=='CONSTRUCTION' for e in evidence['CONSTRUCTION']):
            add('CONSTRUCTION',p['source_id'],'PLAN',p.get('schedule_basis') or '공식 자료 착공 예정연도',str(p['start_plan_year']),p.get('evidence_url'),milestone='CONSTRUCTION')
        # Keep half-years/ranges verbatim; never manufacture an exact day or month.
        if p['source_id']=='gh_supply_plan':
            for stage,field in [('SUPPLY','source_supply_label'),('MOVE_IN','source_move_in_label')]:
                label=p.get(field)
                if label and label.strip() not in ('-','—') and not any(e['kind']=='PLAN' for e in evidence[stage]):
                    add(stage,p['source_id'],'PLAN','GH 공식 공급계획 원문 일정 · 실제 이행 아님',url=p.get('evidence_url'),date_label=label,milestone=stage)
        for stage,field in [('SUPPLY','supply'),('MOVE_IN','move_in')]:
            for dimension in p.get('rows') or []:
                if p['source_id'] not in ('lh_sale','lh_rent','lh_incheon_sale','lh_incheon_rent') and field+'_raw' not in dimension:continue
                schedule=plan_schedule(dimension,field,p['source_id'])
                if schedule['status']=='DATED':continue
                field_label='입주 일정' if stage=='MOVE_IN' else '분양·모집 일정'
                if schedule['status'] in ('UNDETERMINED','TEXT'):
                    add(stage,p['source_id'],'PLAN',field_label+' 원문 표기 · 일정 확정 또는 실적 아님',
                        url=p.get('evidence_url'),date_label=schedule['label'],milestone=stage,schedule_status=schedule['status'])
                else:
                    basis={'NOT_PROVIDED':field_label+' 미제공 · 확보한 계획표에 해당 항목 없음',
                           'EMPTY':field_label+' 원천 공란 · 미정 여부 확인 필요',
                           'UNVERIFIED':field_label+' 원문 표기 미확인 · 날짜 공란만으로 미정 판정 불가'}[schedule['status']]
                    add(stage,p['source_id'],'PLAN_STATUS',basis,url=p.get('evidence_url'),
                        date_label=schedule['label'],schedule_status=schedule['status'])
        for stage in ('SUPPLY','MOVE_IN'):
            for e in links.get((p['id'],stage),{}).get('links',[]):
                add(stage,e.get('source_id'),e['kind'],e['basis'],e.get('date'),e.get('evidence_url'),e.get('review_status'),e.get('source_entity_id'),source_revision_no=e.get('source_revision_no'),officer_confirmed=bool(e.get('actor')))
        for e in manual_events[p['id']]:
            stage='CONSTRUCTION' if e['stage']=='COMPLETION' else e['stage']
            if stage in evidence and e.get('status','ACTUAL')=='ACTUAL':add(stage,'officer','ACTUAL',e.get('basis') or '담당자 실적 기록',e['event_date'],e.get('evidence_url'),e.get('review_status'),milestone=e['stage'],units=e.get('units'),inferred=e.get('inferred',False),input_rule=e.get('input_rule'),field_provenance=e.get('field_provenance',{}))
        for e in manual_goals[p['id']]:
            stage='CONSTRUCTION' if e['stage']=='COMPLETION' else e['stage']
            if stage in evidence:add(stage,'officer','PLAN',e.get('basis'),e['due_date'],e.get('evidence_url'),e.get('status','REVIEW'),milestone=e['stage'],units=e.get('units'),actor=e.get('actor'),reason=e.get('reason'),inferred=e.get('inferred',False),input_rule=e.get('input_rule'),input_basis=e.get('input_basis'),field_provenance=e.get('field_provenance',{}),calculation=e.get('calculation'),changed_at=e.get('changed_at'))
        for stage,r in profiles.get(p['id'],{}).get('progress',{}).items():
            target='CONSTRUCTION' if stage=='COMPLETION' else stage
            add(target,'officer','ACTUAL','사용자 입력 · '+r['actor']+' · '+r['reason'],r.get('event_date') or None,
                review='CONFIRMED',milestone=stage,units=r.get('units'),changed_at=r['changed_at'],manual_priority=True,actor=r['actor'],reason=r['reason'],inferred=r.get('inferred',False),input_rule=r.get('input_rule'),input_basis=r.get('input_basis'),field_provenance=r.get('field_provenance',{}))
        # Keep the original observation and the adopted/estimated override separately.
        manual=p.get('manual_fields',{}).get('progress_pct')
        if manual:
            add('CONSTRUCTION','officer','ACTUAL','사용자 입력 공정률',p.get('progress_date'),p.get('progress_evidence_url') or p.get('evidence_url'),
                pct=manual['value'],manual_priority=True,actor=manual.get('actor'),reason=manual.get('reason'),changed_at=manual.get('changed_at'),
                inferred=manual.get('inferred',False),input_rule=manual.get('input_rule'),input_basis=manual.get('input_basis'),field_provenance=manual.get('field_provenance',{}))
        cells={}
        for bridge in bridges.get(p['id'],[]):
            if bridge['status']=='RELEASED':continue
            for f in bridge['facts']:
                if f['kind']=='ACTUAL' and f.get('date') and f['date']>reference.isoformat():continue
                evidence[f['stage']].append(dict(f,name=short(bridge['source_id']),source_id=bridge['source_id'],
                    source_entity_id=bridge['source_entity_id'],source_revision_no=bridge['source_revision_no'],
                    evidence_url=bridge['evidence_url'],review_status=bridge['status'],bridge_id=bridge['id'],
                    officer_confirmed=bool(bridge.get('actor')),method='CROSS_SOURCE',date=f.get('date'),basis=f['basis']+' · '+bridge['basis'],link_origin='EVIDENCE_BRIDGE',match_key=bridge.get('match_key'),matching_version=bridge.get('matching_version'),decision_basis=bridge.get('review_basis'),relation_type=bridge.get('relation_type')))
        for stage,records in evidence.items():
            pending=[r for r in research.get(p['id'],[]) if r.get('status')=='LINK_PENDING' and stage in r.get('link_stages',[])]
            stage_discovery=max(pending,key=lambda r:(r.get('checked_at',''),r.get('iteration',1)),default=None) or discovery
            assessment=assessments.get((p['id'],stage));active=assessment and assessment['status']!='RELEASED'
            # Keep real evidence visible even when an older missing-data assessment exists.
            acquired=[e for e in records if e['kind']!='PLAN_STATUS']
            status='ACQUIRED' if acquired else assessment['status'] if active else 'LINK_REQUIRED' if stage_discovery and stage_discovery.get('status')=='LINK_PENDING' and stage in stage_discovery.get('link_stages',[]) else 'METHOD_UNKNOWN' if stage=='MOVE_IN' or stage=='CONSTRUCTION' and p['source_id'].startswith(('sh_','gh_')) else 'COLLECTION_REQUIRED'
            reason=assessment['basis'] if active and not acquired else '연결된 자료 없음 · 원천/사업 연결 확인 필요' if status=='COLLECTION_REQUIRED' else '사업별 제공처·조회 방법 추가 확인 필요' if status=='METHOD_UNKNOWN' else assessment.get('basis') if active else ''
            unique=list({(e['source_id'],e.get('source_entity_id'),e.get('source_revision_no'),e['kind'],e['date'],e.get('date_label'),e.get('scope_label'),e['basis']):e for e in records}.values())
            labels={'CONSTRUCTION':'착공 예정','COMPLETION':'예상 준공','SUPPLY':'분양·모집 예정','MOVE_IN':'입주 예정'}
            targets=[dict(e,label=labels.get(e.get('milestone',stage),STAGES[stage]+' 목표')+(' · '+e['scope_label'] if e.get('scope_partial') else ''),reference_only=bool(e.get('scope_partial')))
                     for e in unique if e['kind']=='PLAN' and (e.get('date') or e.get('date_label'))]
            targets.sort(key=lambda t:({'CONSTRUCTION':0,'COMPLETION':1}.get(t.get('milestone'),0),t.get('date') or t.get('date_label') or '',t['name']))
            cells[stage]=dict(status=status,construction_plan=(p.get('construction_plan') or construction_plan(p,reference)) if stage=='CONSTRUCTION' else None,targets=targets,label=STATUS[status],sources=unique,source_names=list(dict.fromkeys(e['name'] for e in unique)),
                actual_available=any(e['kind']=='ACTUAL' and not e.get('scope_partial') for e in unique),plan_available=any(e['kind']=='PLAN' for e in unique),
                dated_plan_available=any(e['kind']=='PLAN' and e.get('date') and not e.get('scope_partial') for e in unique),
                partial_actual_available=any(e['kind']=='ACTUAL' and e.get('scope_partial') for e in unique),
                evidence_count=sum(e['kind']!='PLAN_STATUS' for e in unique),
                inferred_available=any(e.get('method') in ('PREREQUISITE','STAGE_INFERENCE') for e in unique),
                review_required=any(e.get('review_status')=='REVIEW' for e in unique),reason=reason,
                assessment=assessment,assessment_conflict=bool(active and acquired))
            cells[stage]['progress']=progress_state(cells[stage],stage,reference,phase,stage_discovery)
        from .stage_display import annotate
        annotate(cells,p,profiles.get(p['id'],{}),{r['stage']:r for r in manual_goals[p['id']] if r.get('origin')=='MANUAL'},reference,policy)
        from .sequence_audit import sequence_checks
        items.append(dict(id=p['id'],name=p['name'],region=p['region'],municipality=p.get('municipality'),program=p.get('program'),
            policy_id=mapping.get('policy_id'),policy_name=(policy or {}).get('name'),mapping_status=mapping.get('status'),stage_label=p.get('stage_label'),collection_owner=collection_owner(p),research=research.get(p['id'],[]),cells=cells,sequence_checks=sequence_checks(cells),gaps=collection_gaps(cells),evidence_bridges=bridges.get(p['id'],[])))
    diagrams=[]
    for stage,label in STAGES.items():
        counts=Counter(p['cells'][stage]['status'] for p in items);sources=[]
        used=Counter(e['source_id'] for p in items for e in {e['source_id']:e for e in p['cells'][stage]['sources'] if e['kind']!='PLAN_STATUS'}.values())
        for sid in dict.fromkeys(CATALOG[stage]+list(used)):
            s=source_states.get(sid,{})
            mode=s.get('collection_mode','');method='API' if s.get('key_env') else '파일' if mode in ('PUBLIC_FILE','HISTORY','LEGAL_PLAN_PILOT','PUBLIC_DOCUMENT') else '내부' if sid=='officer' else '웹'
            sources.append(dict(id=sid,name=short(sid),org=s.get('org'),method=method,linked_projects=used[sid],
                collection_status=s.get('status'),last_success=s.get('last_success')))
        diagrams.append(dict(stage=stage,label=label,join_key=KEYS[stage],sources=sources,counts=dict(counts)))
    from .collection_lineage import enrich
    lineage=enrich(service,projects,items,reference,source_states,baselines=baselines,policy_names={k:p['name'] for k,p in policies.items()})
    from .collection_repairs import enrich as enrich_repairs, REPAIR_TYPES
    repairs=enrich_repairs(service,items,reference)
    return dict(repair_types=REPAIR_TYPES,repairs=repairs,items=items,gap_groups=summarize_gaps(items),total=len(items),stages=STAGES,statuses=STATUS,progress_statuses=PROGRESS,diagram=diagrams,lineage=lineage,as_of_date=reference.isoformat(),
        policies=[dict(policy_id=k,name=p['name']) for k,p in policies.items()],
        notice='자료 확보와 실적 확인은 다릅니다. 예정·실적·연결 검토를 구분하며 빈칸으로 미계획이나 원천 0건을 추정하지 않습니다.')
