"""Read-only field-level provenance of stored project links (no new matching)."""
import re
from datetime import datetime,time,timedelta,timezone
from zoneinfo import ZoneInfo
from sqlalchemy import select, func, tuple_
from .db import Revision

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

def enrich(service,projects,items,reference,source_states,baselines=None):
    refs={(e.get('source_entity_id'),e.get('source_revision_no')) for p in items for c in p['cells'].values()
          for e in c['sources'] if e.get('source_entity_id')}
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
    lookup={p['id']:p for p in projects}
    baselines=baselines if baselines is not None else service.rows('execution_schedule',reference)
    baseline_stages={}
    for b in baselines:
        if b.get('baseline') and b.get('status')!='RELEASED':baseline_stages.setdefault(b['project_id'],[]).append(b['stage'])
    parcel_links={r['project_id']:r for r in service.rows('project_parcel',reference)}
    for item in items:
        p=lookup[item['id']];keys=fields(p,'project');keys['project']=p['id']
        mapping=p.get('mapping',{})
        if mapping.get('status')!='RELEASED':
            for key,field in [('policy','policy_id'),('program','program_id')]:
                if mapping.get(field) and mapping[field]!='UNASSIGNED':keys[key]=mapping[field]
        sources={p['source_id']:dict(keys=fields(p,'project'),inferred=False,review=False,base=True)}
        stage_keys={}
        for stage,cell in item['cells'].items():
            stage_keys[stage]={}
            if stage=='CONSTRUCTION':stage_keys[stage].update({k:v for k,v in fields(p,'project').items() if k in ('start','progress','completion')})
            if stage=='MOVE_IN':stage_keys[stage].update({k:v for k,v in fields(p,'project').items() if k=='move_actual'})
            for e in cell['sources']:
                if e['kind']=='PLAN_STATUS':continue
                kind,raw=versions.get((e.get('source_entity_id'),e.get('source_revision_no')),(None,{}))
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
        item['lineage']=dict(keys=keys,stage_keys={s:{**shared,**v} for s,v in stage_keys.items()},sources=sources,baseline_stages=baseline_stages.get(p['id'],[]))
    return dict(key_labels=LABELS,sources={sid:dict(name=s['name'],org=s.get('org'),record_count=s.get('record_count',0),
        status=s.get('status'),last_success=s.get('last_success'),method='API' if s.get('key_env') else '파일' if s.get('collection_mode') in ('PUBLIC_FILE','HISTORY','LEGAL_PLAN_PILOT','PUBLIC_DOCUMENT') else '웹') for sid,s in source_states.items()},
        note='키 확보는 해당 필드가 연결된 자료에 있다는 뜻입니다. 코드 변환·필지 결합·사업 동일성 검토의 완료 여부와는 별개입니다.')
