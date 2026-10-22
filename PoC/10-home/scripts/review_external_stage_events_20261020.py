"""Apply the user-supplied external register after checking pinned originals.

No new project or policy mapping is created. Recruitment, waiting lists,
completion, planned occupancy and actual occupancy remain separate events.
"""
import argparse
from copy import deepcopy
from datetime import date
import hashlib
import json
import re
from pathlib import Path
from sqlalchemy import select, text
from backend.db import Audit, Mapping, ProgramMapping, Revision, engine_for, entity_id, now, upsert_revision
from backend.service import HomeService

BATCH='external-events-20261020'
ACTOR='담당자 대행 · 사용자 외부 착공·준공·공급·입주 자료 보완 지시'
POLICY='POL_2025_0907'
WAITLIST_PAN='2015122300020531'


def protected(db):
    result={r.entity_id:r.payload_hash for r in db.scalars(select(Revision).where(
        Revision.superseded_at.is_(None),Revision.kind=='project'))}
    result['mappings']=[(m.project_id,m.policy_id,m.program_id,m.status,m.revision_no) for m in db.scalars(select(Mapping).order_by(Mapping.project_id))]
    result['programs']=[(p.id,p.policy_id,p.status,p.revision_no) for p in db.scalars(select(ProgramMapping).order_by(ProgramMapping.id))]
    return result


def norm(value):
    return re.sub(r'\s|,','',value).upper()


def repair_waitlist(payload):
    """Correct this checked waiting-list notice without changing original history."""
    if WAITLIST_PAN not in str(payload.get('evidence_url','')):return None
    value=deepcopy(payload);changed=False
    for f in value.get('facts',[]):
        if f.get('stage')=='SUPPLY' and f.get('kind')=='ACTUAL':
            f.update(kind='STATE',units=None,notice_round='WAITLIST',recruitment_persons=300,
                event_kind='WAITLIST_RECRUITMENT_NOTICE',basis='담당자 확인 완료 - 공식 자료: LH 2026-08-13 이천장호원 B2 예비입주자300명 모집. 신규 주택 공급량 아님')
            changed=True
    if not changed:return None
    value.update(notice_round='WAITLIST',source_notice_round='WAITLIST',reviewed=True,
        review_actor=ACTOR,review_basis='원문 제목의 예비입주자 모집과 총 단지620호·모집인원300명을 구분',
        review_label='담당자 확인 완료 - 공식 자료: LH 예비입주자 모집공고',officer_review_status='CONFIRMED')
    return value


def apply(service,plan,manifest):
    folder=service.data_dir/BATCH
    indexed={r['key']:r for r in manifest}
    # Validate every file and claim before any write; HTTP 200 alone is not proof.
    for spec in plan['specs']:
        source=indexed[spec['source_key']]
        if source.get('status')!=200:raise ValueError('원문 응답 확인 실패: '+spec['source_key'])
        body=(folder/source['file']).read_bytes()
        if hashlib.sha256(body).hexdigest()!=source['sha256']:raise ValueError('원문 판본 변경: '+spec['source_key'])
        content=norm((folder/source['text_file']).read_text())
        if any(norm(term) not in content for term in spec['checks']):raise ValueError('확인 항목 불일치: '+spec['key'])
    results=[];profiles=[];schedules=[];repairs=[]
    with service.sessions.begin() as db:
        if service.engine.dialect.name=='postgresql':db.execute(text('SELECT pg_advisory_xact_lock(10203034)'))
        before=protected(db)
        def current(eid):return db.scalar(select(Revision).where(Revision.entity_id==eid,Revision.superseded_at.is_(None)))
        def put(kind,source,key,payload,action='EXTERNAL_EVENT_CONFIRMED'):
            old=current(entity_id(kind,source,key));prior=deepcopy(old.payload) if old else {}
            if prior.get('status')=='RELEASED':raise ValueError('담당자 해제 기록 보존: '+key)
            row,outcome=upsert_revision(db,kind,source,key,payload,BATCH)
            if outcome!='unchanged':db.add(Audit(entity_id=row.entity_id,action=action,before=prior,after=payload))
            return row,outcome
        for spec in plan['specs']:
            pid=spec['project_id'];project=current(pid);mapping=db.scalar(select(Mapping).where(Mapping.project_id==pid))
            if not project or not mapping or mapping.status!='CONFIRMED':raise ValueError('기존 확인 사업 누락: '+pid)
            parent=db.get(ProgramMapping,mapping.program_id) if mapping.program_id else None
            if mapping.policy_id!=POLICY and not(parent and parent.policy_id==POLICY and parent.status=='CONFIRMED'):raise ValueError('정책 귀속 미확인: '+pid)
            source=indexed[spec['source_key']];source_type='OFFICIAL' if spec['official'] else 'NON_OFFICIAL'
            label='담당자 확인 완료 - '+('공식 자료: ' if spec['official'] else '비공식 자료: ')+spec['source_name']
            label+=('('+spec['published_at']+')') if spec.get('published_at') else ''
            facts=[dict(f,review_label=label,source_type=source_type,evidence_url=source['url']) for f in spec['facts']]
            for f in facts:
                if f['kind']=='ACTUAL' and f.get('date','9999')>'2026-10-20':raise ValueError('미래 실제 실적 금지')
                if f['stage'] in ('COMPLETION','MOVE_IN') and f['kind']=='ACTUAL':raise ValueError('이번 원문에는 실제 준공·실입주 증빙 없음')
            payload=dict(name=project.payload['name']+' · '+spec['case_id']+' '+label,source_object_id=BATCH+':'+spec['key'],
                sample_kind='document_evidence',base_date='2026-10-20',source_date=spec.get('published_at'),
                published_at=spec.get('published_at'),date_precision='DAY' if spec.get('published_at') else 'UNKNOWN',
                evidence_url=source['url'],original_sha256=source['sha256'],original_file=BATCH+'/'+source['file'],
                source_manifest_key=spec['source_key'],case_id=spec['case_id'],checked_source_type=source_type,
                review_label=label,review_actor=ACTOR,actor=ACTOR,status='CONFIRMED',reviewed=True,
                officer_review_status='CONFIRMED',verification_status='SOURCE_CONTENT_CHECKED',
                confirmed_scope=[dict(stage=f['stage'],kind=f['kind'],event_kind=f.get('event_kind'),units=f.get('units'),date=f.get('date')) for f in facts],
                official_actual_verified=spec['official'] and any(f['kind']=='ACTUAL' for f in facts),
                facts=facts,units=None,planned_units=None,exclude_from_project_totals=True,
                basis=label+' · '+next(d['result'] for d in plan['decisions'] if d['case_id']==spec['case_id']))
            doc,outcome=put('document_evidence','external_officer',payload['source_object_id'],payload)
            bridge=dict(project_id=pid,name=payload['name'],region=project.payload.get('region'),
                source_entity_id=doc.entity_id,source_revision_no=doc.revision_no,source_id='external_officer',evidence_source_id='external_officer',
                source_name=label,evidence_url=source['url'],facts=facts,units=None,status='CONFIRMED',reviewed=True,
                review_actor=ACTOR,actor=ACTOR,review_label=label,checked_source_type=source_type,
                officer_review_status='CONFIRMED',relation_type='OFFICER_VERIFIED_EVENT_SCOPE',review_basis=payload['basis'],basis=payload['basis'],base_date='2026-10-20')
            link,action=put('evidence_bridge','cross_source',pid+':'+doc.entity_id,bridge)
            results.append(dict(case_id=spec['case_id'],project_id=pid,document_id=doc.entity_id,bridge_id=link.entity_id,source=spec['source_key'],document_outcome=outcome,bridge_outcome=action,label=label))
            if spec.get('adopt_progress'):
                update=spec['adopt_progress'];stage=update['stage'];old=current(entity_id('project_profile','manual_project',pid));value=deepcopy(old.payload) if old else dict(project_id=pid,overrides={},approvals={},progress={})
                prior=value.setdefault('progress',{}).get(stage)
                if prior and prior.get('batch_id')==BATCH:
                    if (prior['event_date'],prior['units'])!=(update['event_date'],update['units']):raise ValueError('반영 후 담당자 입력 변경: '+pid)
                    profiles.append(dict(project_id=pid,stage=stage,outcome='unchanged'));continue
                if prior and not prior.get('inferred'):raise ValueError('추정 아닌 기존 담당자 값은 덮어쓰지 않음: '+pid)
                if update['units']>project.payload['planned_units']:raise ValueError('공급량이 사업 총량 초과')
                stamp=now().isoformat();reason=payload['basis']
                value['progress'][stage]=dict(origin='MANUAL',actor=ACTOR,reason=reason,changed_at=stamp,
                    batch_id=BATCH,input_rule='OFFICER_VERIFIED_SOURCE',input_basis=reason,inferred=False,
                    event_date=update['event_date'],units=update['units'],review_label=label,evidence_url=source['url'],
                    source_type=source_type,previous_estimate=prior,source_entity_id=doc.entity_id,source_revision_no=doc.revision_no,
                    field_provenance={k:dict(rule='VERIFIED_SOURCE_EVENT',value=update[k],evidence_url=source['url'],original_sha256=source['sha256']) for k in ('event_date','units')})
                value.update(base_date='2026-10-20',actor=ACTOR,reason=reason)
                _,action=put('project_profile','manual_project',pid,value,'EXTERNAL_ESTIMATE_REPLACED')
                profiles.append(dict(project_id=pid,stage=stage,outcome=action,before=prior,after=value['progress'][stage]))
            if spec.get('adopt_schedule'):
                update=spec['adopt_schedule'];stage=update['stage'];key=pid+':'+stage;old=current(entity_id('execution_schedule','officer',key));prior=deepcopy(old.payload) if old else {}
                if prior.get('batch_id')==BATCH:
                    if prior.get('due_date')!=update['due_date']:raise ValueError('反映後 일정 변경')
                    schedules.append(dict(project_id=pid,stage=stage,outcome='unchanged'));continue
                # All changed schedules here are plans, never actual occupancy.
                value=dict(prior,project_id=pid,policy_id=POLICY,stage=stage,due_date=update['due_date'],
                    units=project.payload['planned_units'],status='CONFIRMED',basis=payload['basis'],reason=payload['basis'],
                    responsible_org=ACTOR,actor=ACTOR,origin='MANUAL',base_date='2026-10-20',name=project.payload['name'],
                    region=project.payload.get('region'),evidence_url=source['url'],batch_id=BATCH,input_rule='OFFICER_VERIFIED_PLAN',
                    inferred=False,source_precision=update['precision'],review_label=label,source_type=source_type,
                    source_entity_id=doc.entity_id,source_revision_no=doc.revision_no,previous_schedule=prior,
                    changed_at=now().isoformat())
                _,action=put('execution_schedule','officer',key,value,'EXTERNAL_PLAN_CONFIRMED')
                schedules.append(dict(project_id=pid,stage=stage,outcome=action,before=prior,after=value))
        for row in list(db.scalars(select(Revision).where(Revision.superseded_at.is_(None),Revision.kind.in_(['document_evidence','evidence_bridge'])).order_by(Revision.kind))):
            value=repair_waitlist(row.payload)
            if value:
                key=value.get('source_object_id') or value.get('notice_no')
                if row.kind=='document_evidence' and value.get('multi_complex'):
                    key=value['notice_no']+':'+value['district']+':'+value['block']
                if row.kind=='evidence_bridge':
                    key=value['project_id']+':'+value['source_entity_id']
                    pinned=current(value['source_entity_id'])
                    if pinned:value['source_revision_no']=pinned.revision_no
                if not key:raise ValueError('정정 원천 식별키 미확보')
                if entity_id(row.kind,row.source_id,key)!=row.entity_id:raise ValueError('정정 식별키 불일치')
                _,outcome=put(row.kind,row.source_id,key,value,'WAITLIST_SCOPE_CORRECTED')
                repairs.append(dict(id=row.entity_id,kind=row.kind,outcome=outcome))
        db.flush();after=protected(db)
        if before!=after:raise ValueError('기존 사업 총량·정책/프로그램 연결 변경 감지')
    return dict(batch=BATCH,case_count=len(plan['decisions']),linked_project_count=len({r['project_id'] for r in results}),
        results=results,progress_changes=profiles,schedule_changes=schedules,waitlist_repairs=repairs,
        new_projects=0,actual_completion_added=0,actual_move_in_added=0,project_and_mapping_preserved=True,
        decisions=plan['decisions'])


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    service=HomeService(engine_for());folder=service.data_dir/BATCH
    plan=json.loads((folder/'plan.json').read_text());raw=(folder/'source_manifest.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=plan['source_manifest_sha256']:raise ValueError('검토 원천 목록 판본 변경')
    if not args.apply:print(json.dumps(plan,ensure_ascii=False));return
    from backend.policy_delivery import build_delivery
    from scripts.build_continuation_review_20261020 import metrics
    before=metrics(build_delivery(service,date(2026,10,20),include_portfolio_comparisons=False))
    result=apply(service,plan,json.loads(raw));after=metrics(build_delivery(service,date(2026,10,20),include_portfolio_comparisons=False))
    result.update(metrics_before=before,metrics_after=after)
    changed=any(r['document_outcome']!='unchanged' or r['bridge_outcome']!='unchanged' for r in result['results']) or result['waitlist_repairs']
    filename='applied.json' if changed else 'idempotence.json'
    (folder/filename).write_text(json.dumps(result,ensure_ascii=False,indent=2,default=str))
    print(json.dumps({k:v for k,v in result.items() if k not in ('results','decisions','progress_changes','schedule_changes')},ensure_ascii=False))


if __name__=='__main__':main()
