"""Current stage fields with per-field revision history, read lazily by the evidence dialog."""
from sqlalchemy import select
from .db import Revision,entity_id
from .project_collection import collection_matrix,STAGES
from .project_profile import STAGES as MILESTONES
from .source_authority import clean
from scripts.export_json import scrub,credential_values


def flatten(value,path=()):
    if isinstance(value,dict) and value:
        return {p:v for k,item in value.items() for p,v in flatten(item,path+(str(k),)).items()}
    return {path:value}


def metadata(payload,path,recorded_at):
    context=payload;actor=payload.get('actor');reason=payload.get('reason');stamp=payload.get('changed_at')
    for key in path[:-1]:
        context=context.get(key,{}) if isinstance(context,dict) else {}
        if isinstance(context,dict):
            actor=context.get('actor') or actor;reason=context.get('reason') or context.get('input_basis') or reason;stamp=context.get('changed_at') or stamp
    for repair in payload.get('sequence_date_repairs',[]):
        for change in repair.get('changes',[]):
            if flatten(payload).get(path)==change['after'] and path[-1]==change['field'] and (len(path)==1 and payload.get('stage')==change['stage'] or len(path)>1 and path[-2]==change['stage']):
                actor=repair.get('actor');reason=repair.get('reason');stamp=repair.get('at')
    return dict(changed_at=stamp or recorded_at,recorded_at=recorded_at,
                time_kind='수정 기록 시각' if stamp else '수집·저장 시각',actor=actor or '미기록',reason=reason or '미기록')


def record_fields(revisions,selected_no,paths=None):
    selected=next((r for r in revisions if r.revision_no==selected_no),None)
    if selected is None:return []
    secrets=credential_values()
    current=flatten(clean(scrub(selected.payload,secrets)))
    keys={k for r in revisions if r.revision_no<=selected_no for k in flatten(clean(scrub(r.payload,secrets)))} if paths is None else set(paths)
    histories={k:[] for k in keys};previous={};seen=False
    for r in revisions:
        if r.revision_no>selected_no:break
        values=flatten(clean(scrub(r.payload,secrets)));stamp=r.recorded_at.isoformat()
        for key in keys:
            present=key in values;old_present=key in previous
            if (not seen and present) or seen and (present!=old_present or values.get(key)!=previous.get(key)):
                histories[key].append(dict(before=previous.get(key),after=values.get(key),before_present=old_present,after_present=present,
                    action='최초 기록' if not seen else '삭제' if not present else '추가' if not old_present else '변경',revision_no=r.revision_no,
                    **metadata(r.payload,key,stamp)))
        previous=values;seen=True
    return [dict(path=list(k),field=' → '.join(k),value=current.get(k),present=k in current,history=list(reversed(histories[k]))) for k in sorted(keys)]


def build(service,project_id,stage):
    if stage not in STAGES:raise KeyError(stage)
    matrix=collection_matrix(service,project_ids=(project_id,),include_link_history=False)
    if not matrix['items']:raise KeyError(project_id)
    project=matrix['items'][0];cell=project['cells'][stage];milestones=['CONSTRUCTION','COMPLETION'] if stage=='CONSTRUCTION' else [stage]
    refs={};current=[];profiles=entity_id('project_profile','manual_project',project_id)
    for kind in ('target','measurement'):
        for r in cell['management'][kind]:
            for field in ('date','units'):
                source_id=entity_id('execution_schedule','officer',project_id+':'+r['milestone']) if kind=='target' else profiles
                path=('due_date' if field=='date' else 'units',) if kind=='target' else ('progress',r['milestone'],'event_date' if field=='date' else 'units')
                current.append(dict(label=MILESTONES.get(r['milestone'],'정책')+' · '+('목표' if kind=='target' else '측정값')+' · '+('일자' if field=='date' else '호수'),
                    value=r.get(field),tag=r.get('field_tags',{}).get(field) or r.get('collection_tag'),record_id=source_id,path=path))
    pct=cell['management'].get('progress_pct')
    if pct:
        for f,label in [('date','기준일'),('pct','공정률(%)')]:current.append(dict(label='공정률 · '+label,value=pct.get(f),tag=pct.get('collection_tag'),record_id=profiles,path=('overrides','progress_date' if f=='date' else 'progress_pct','value')))
    for r in cell.get('sources',[]):
        if r.get('source_entity_id'):refs[(r['source_entity_id'],r.get('source_revision_no'))]=r.get('name') or r.get('source_id') or '수집 원천'
    ids={i for i,_ in refs}|{r['record_id'] for r in current};groups=[]
    with service.sessions() as db:
        records=list(db.scalars(select(Revision).where(Revision.entity_id.in_(ids)).order_by(Revision.entity_id,Revision.revision_no)))
        by_id={i:[r for r in records if r.entity_id==i] for i in ids}
        for r in current:
            revisions=by_id.get(r.pop('record_id'),[]);path=r.pop('path');selected=revisions[-1] if revisions else None
            values=record_fields(revisions,selected.revision_no,[path]) if selected else []
            entry=values[0] if values else {};r['history']=entry.get('history',[])
            r['history_note']='저장된 관리 입력 이력입니다. 원천 채택·계산 결과의 모든 변화를 뜻하지 않습니다.' if r['history'] else '별도 관리 입력 변경 기록 없음 · 아래 원천별 항목 이력 확인'
            r['management_value']=entry.get('value');r['matches_management_record']=entry.get('present',False) and entry.get('value')==r['value']
        for (eid,no),name in refs.items():
            revisions=by_id.get(eid,[]);selected=next((r for r in revisions if r.revision_no==no),None) if no else next((r for r in reversed(revisions) if r.superseded_at is None),None)
            if selected is None:
                groups.append(dict(name=name,id=eid,revision_no=no,missing=True,fields=[]));continue
            # Keep the selected/pinned source revision, not an unrelated latest sample.
            groups.append(dict(name=name,id=eid,revision_no=selected.revision_no,evidence_url=selected.payload.get('evidence_url'),fields=record_fields(revisions,selected.revision_no)))
    result=dict(project_id=project_id,stage=stage,as_of_date=matrix['as_of_date'],current=current,sources=groups,remaining=cell['management']['remaining'],
                notice='현재 채택값을 항목별로 표시합니다. 변경 시각·담당자·사유는 저장된 기록만 사용합니다. 원천 수집은 저장 시각이며 외부 기관의 실제 수정 시각과 다를 수 있습니다. 고정 원천은 연결된 판본까지의 이력입니다.')
    return clean(scrub(result,credential_values()))
