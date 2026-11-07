"""Reproduce the 393-target review; --apply adds evidence/annotations, never approvals.
The input folder holds original bytes, pinned targets, the original CSV, captures,
and original role snapshots. One transaction protects all business state.
"""
import argparse,csv,io,json,hashlib
from collections import Counter,defaultdict
from pathlib import Path
from sqlalchemy import select,text
from sqlalchemy.orm import sessionmaker
from backend.db import Revision,Mapping,ProgramMapping,engine_for,now
from backend.service import HomeService
from backend.publication_supplements import save as save_body
from backend.hold_review import save as save_note
from backend.stage_reconciliation import reference,current,exact_date_in_quote
from backend.hold_evidence_integrity import package,load_registry,references,sha,quote_check
from backend.publication_evidence import safe_value
from backend.publication_review_export import cell
from backend.ai_agents_inbox import items,export_csv
from backend.ai_collection_store import Store

ACTOR='261106 업무담당자 확인(김민) · 사용자 위임 AI 증빙 교차검토'
REPORT='EVIDENCE_REVIEW_20261106'
PROTECTED=['project','project_profile','goal','policy','policy_profile','stage_evidence','stage_proposal','evidence_bridge','execution_schedule','program_source','program_district_plan','publication_review']

def protected(service):
    with service.sessions() as db:
        values=list(db.execute(select(Revision.kind,Revision.entity_id,Revision.revision_no,Revision.payload_hash).where(Revision.kind.in_(PROTECTED),Revision.superseded_at.is_(None)).order_by(Revision.kind,Revision.entity_id)))
        mappings=[{c.name:getattr(r,c.name) for c in model.__table__.columns} for model in (Mapping,ProgramMapping) for r in db.scalars(select(model).order_by(model.id))]
    return sha(json.dumps([list(map(list,values)),mappings],ensure_ascii=False,sort_keys=True,default=str))

def write_csv(path,rows):
    if not rows:return
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader()
        for r in rows:w.writerow({k:cell(json.dumps(safe_value(v),ensure_ascii=False) if isinstance(v,(dict,list)) else v) for k,v in r.items()})

def run(folder,apply=False):
    p=Path(folder);targets=json.loads((p/'targets.json').read_text());original=list(csv.DictReader(io.StringIO((p/'before.csv').read_text().lstrip('\ufeff'))))
    assert len(targets)==393 and {r['id'] for r in targets}=={r['대상ID'] for r in original}
    assert sum(int(r['합쳐진기록수']) for r in original)==481
    source_rows=[json.loads(l) for l in (p/'revisions.jsonl').open()];expected={r['id']:r for r in source_rows}
    old={r['대상ID']:r for r in original};old_roles=json.loads((p/'collection.json').read_text())+json.loads((p/'officer.json').read_text())
    baseline=defaultdict(list)
    for r in old_roles:
        if r['state']=='HOLD':baseline[r['subject']].append(r)
    captures={r['id']:r for f in (p/'fetch').glob('DOC_*.json') if '.first.' not in f.name for r in [json.loads(f.read_text())]}
    recovered=[r for r in captures.values() if r.get('status')=='RECOVERED']
    report_hash=hashlib.sha256((p/'original-report.txt').read_bytes()).hexdigest()
    engine=engine_for();conn=engine.connect();tx=conn.begin();service=HomeService(engine,'/app/data');service.sessions=sessionmaker(bind=conn,expire_on_commit=False)
    try:
        if engine.dialect.name=='postgresql':conn.execute(text('SELECT pg_advisory_xact_lock(9072026)'))
        before=protected(service);print('protected state pinned',flush=True)
        with service.sessions() as db:
            for target in targets:
                kind='document_evidence' if target['kind']=='D' else 'stage_proposal';r=current(db,kind,target['id'])
                assert r and r.payload_hash==expected[target['id']]['hash'],('target changed',target['id'])
        for capture in recovered:
            artifact=p/'raw/ai_publication'/(capture['metadata']['sha256']+'.raw')
            assert artifact.is_file() and hashlib.sha256(artifact.read_bytes()).hexdigest()==capture['metadata']['sha256']
            if apply:
                with service.sessions() as db:
                    prior=db.scalar(select(Revision).where(Revision.kind=='publication_supplement',Revision.superseded_at.is_(None),Revision.payload['document_id'].as_string()==capture['id']))
                if not prior or prior.payload.get('raw_sha256')!=capture['metadata']['sha256'] or prior.payload.get('body_text')!=capture['body']:
                    save_body(service,capture['id'],capture['source_revision_no'],capture['body'],
                        '11월 6일 원문/동일 게시물 첨부 재수집 · 제목 및 본문 대응 확인 · 내용·사업 연결·실적 승인과 별개',
                        capture['metadata'].get('attachments',[]),ACTOR,capture['metadata']['sha256'])
        print('source preflight complete',flush=True)
        store=Store('/app/data');roles=items(service,store,'collection',True)+items(service,store,'officer',True)
        print('role snapshots loaded',len(roles),flush=True)
        groups=defaultdict(list)
        for r in roles:groups[r['subject']].append(r)
        registry=load_registry(service,[ref for r in roles for ref in references(dict(r.get('result') or {},body_ref=r.get('body_ref') or (r.get('result') or {}).get('body_ref'),body_refs=r.get('body_refs',[])))])
        print('referenced versions loaded',len(registry),flush=True)
        qrows=[];vrows=[];states=[];identities=[];stages=[];conflicts=[];versions=[];notes=[]
        with service.sessions() as db:
            docids=[r['id'] for r in targets if r['kind']=='D']
            rows=list(db.scalars(select(Revision).where(Revision.kind.in_(['publication_review','publication_supplement','ai_publication_analysis','publication_assessment']),Revision.superseded_at.is_(None),Revision.payload['document_id'].as_string().in_(docids))))
            docrefs=defaultdict(list);docpayloads=defaultdict(dict)
            for r in rows:
                docrefs[r.payload['document_id']].append(reference(r));docpayloads[r.payload['document_id']][r.kind]=r.payload
        for target in targets:
            tid=target['id'];group=[x for x in groups[tid] if x['state']=='HOLD'] or groups[tid];r=max(group,key=lambda x:len(x.get('body_text') or ''));oldrow=old[tid]
            audit_record=dict(r,evidence=json.loads(oldrow['근거_JSON']));pkg=package(audit_record,group,registry)
            oldpackage=json.loads(oldrow['증빙패키지_JSON']);oldhash=oldpackage.get('exported_body_sha256');ob=oldrow['수집본문']
            hash_status='CSV_FORMULA_ESCAPE_ONLY' if ob and ob.startswith("'") and oldhash==sha(ob[1:]) and oldhash!=sha(ob) else 'MATCH' if oldhash==sha(ob) else 'MISSING_BODY' if not ob else 'UNREPRODUCED'
            findings=['저장 본문·판본 대조 결과이며 외부 원문 전수 재검증/업무 승인과 구분합니다.', 'CSV 해시: '+hash_status+' → 내보낸 최종 UTF-8 본문 기준 재계산.']
            unresolved=0
            for i,q in enumerate(pkg['quote_checks']):
                disposition=q['status'] if q['anchor'] else 'OTHER_STORED_BODY_MATCH' if q['other_agent_body_matches'] else 'UNRESOLVED'
                unresolved+=disposition=='UNRESOLVED'
                qrows.append(dict(target_id=tid,quote_index=i,quote=q['quote'],status=disposition,anchor=q['anchor'],other_body_refs=q['other_agent_body_matches'],body_sha256=q['body_sha256'],external_original_verified=False))
            findings.append('현재 본문 인용 '+str(len(pkg['quote_checks']))+'개 점검 · 저장 판본 전체에서 미재현 '+str(unresolved)+'개.')
            capture=captures.get(tid);prior_cross=json.loads(oldrow['교차검토_JSON'])
            changed=False;result=r.get('result') or {};project={}
            if target['kind']=='S':
                result=next(x['result'] for x in group if x['subject'].startswith('STA_'))
                ref=result['source_ref'];oldref=next((x for x in prior_cross.get('refs',[]) if x['id']==ref['id']),None)
                transition='NO_PRIOR_REVIEW' if not oldref else 'SELECTED_REFERENCE_DIFFERS' if (oldref.get('hash'),oldref.get('revision_no'))!=(ref.get('hash'),ref.get('revision_no')) else 'UNCHANGED'
                changed=transition!='UNCHANGED';source_entry=next((x for x in pkg['evidence_registry'] if x['requested_ref']['id']==ref['id']),{})
                versions.append(dict(target_id=tid,previous_ref=oldref,selected_ref=ref,current_ref=source_entry.get('current_ref'),comparison=transition,selected_revision_status=source_entry.get('status'),current_matches=source_entry.get('current_matches'),revalidation_complete=False,reason='기계적 참조 재조회 완료 · 실제 일자/물량/동일성 재승인 미완료'))
                project=expected.get(result['project_id'],{}).get('payload',{})
                identities.append(dict(target_id=tid,project_id=result['project_id'],standard_name=result['project_name'],address=project.get('address'),district=project.get('district'),block=project.get('block'),notice_no=project.get('notice_no'),identity_confirmed=result.get('identity_confirmed'),source_ref=ref,source_metadata=[x['metadata'] for x in pkg['evidence_registry']],verification_status='EXISTING_ASSERTION_ONLY_REQUIRES_SOURCE_MATCH'))
                proposal=result['proposed'];event_type='OBSERVATION_ONLY' if proposal.get('date_basis')=='OBSERVED_BY' else 'INITIAL_OR_AMENDMENT_REVIEW' if result['stage']=='APPROVAL' else 'RECRUITMENT_SCOPE_REVIEW' if result['stage']=='SUPPLY' else result['stage']
                stages.append(dict(target_id=tid,project_id=result['project_id'],stage=result['stage'],event_type=event_type,date_basis=proposal.get('date_basis'),event_date=proposal.get('event_date'),units=proposal.get('units'),scope=proposal.get('scope'),quantity_semantics='누적값 대체 후보 · 증분 가산 아님',previous=result.get('previous'),can_apply=result['can_apply'],identity_confirmed=result.get('identity_confirmed'),auto_eligible=result['auto_eligible'],human_hold=result.get('human_hold'),invalid_source=result.get('invalid_source'),source_current=source_entry.get('current_matches'),blockers=result['blockers'],review_reasons=result['review_reasons'],approved=False))
                conflicts.append(dict(target_id=tid,event_group=result.get('event_group'),duplicate_ids=result.get('duplicate_ids',[]),different_value_ids=result.get('different_value_ids',[]),resolution='원문 사건 구분·물량 범위 대조 전 병합/삭제/가산하지 않음',existing_approvals_preserved=True))
                findings.extend(['과거 교차검토 참조: '+transition, '선택 근거: '+str(source_entry.get('status'))+' · 최신 원천과 일치 '+str(source_entry.get('current_matches')),result.get('can_apply_note',''), '사건일/도달 확인일 '+str(proposal.get('date_basis'))+' 유지 · 실적 반영 없음.'])
                if result.get('duplicate_ids'):findings.append('중복 후보 '+str(len(result['duplicate_ids']))+'건 · 동일 단계 누적값 대체로 이중 합산 차단, 사건 동일성은 미확정.')
            if capture:
                findings.append('원문 재조회: '+capture['status']+' · '+('본문 보강' if capture['status']=='RECOVERED' else capture.get('error') or '본문/첨부 대응 추가 확인 필요'))
            reanalysis=oldrow['재분석필요']=='True'
            sync={}
            if target['kind']=='D':
                saved=docpayloads[tid];analysis=saved.get('ai_publication_analysis',{});manual=saved.get('publication_supplement',{});decision=saved.get('publication_review',{})
                sync=dict(source_revision_no=r.get('source_revision_no'),analysis_source_revision_no=analysis.get('source_revision_no'),manual_source_revision_no=manual.get('source_revision_no'),decision_source_revision_no=decision.get('source_revision_no'),analysis_body_sha256=sha(analysis.get('body_text') or ''),effective_body_sha256=pkg['stored_body_sha256'],analysis_matches_effective_body=sha(analysis.get('body_text') or '')==pkg['stored_body_sha256'],existing_business_status=decision.get('status'),automatic_reopen=False)
                if reanalysis:findings.append('최신 선택 본문과 이전 AI 본문 해시 일치: '+str(sync['analysis_matches_effective_body'])+' · 판본/본문 차이는 재분석 사유로 유지.')
            if reanalysis:findings.append('이전 수집 오류/분석과 최신 본문 재대조 · 기존 '+oldrow['현재업무상태']+' 결정 보존, 재검토 권고만 기록.')
            vrows.append(dict(target_id=tid,kind='STAGE' if target['kind']=='S' else 'DOCUMENT',source_revision_no=r.get('source_revision_no'),source_ref=result.get('source_ref') or r.get('body_ref'),original_export_sha256=oldhash,original_hash_status=hash_status,stored_body_sha256=pkg['stored_body_sha256'],redacted_body_sha256=pkg['redacted_body_sha256'],exported_body_sha256=pkg['exported_body_sha256'],hash_basis=pkg['hash_basis'],quote_checks=pkg['quote_checks'],unresolved_quotes=unresolved,capture=capture['status'] if capture else 'NOT_REQUESTED',verifier=ACTOR,verified_at=now().isoformat(),verification_scope='STORED_EVIDENCE_INTEGRITY_ONLY',business_approval=False))
            states.append(dict(target_id=tid,previous_business_status=oldrow['현재업무상태'],current_business_status=r.get('business_status_label',''),old_agent_records=int(oldrow['합쳐진기록수']),current_role_states=[dict(role=x['role'],state=x['state'],stage=x['stage']) for x in group],reanalysis_recommended=reanalysis,approved_result_preserved=True))
            with service.sessions() as db:
                primary=current(db,'document_evidence' if target['kind']=='D' else 'stage_proposal',tid);refs=[reference(primary)]
                if target['kind']=='D':refs+=docrefs[tid]
                else:
                    for selected in references(result):
                        source=current(db,selected['kind'],selected['id'])
                        if source:refs.append(reference(source))
            refs=list({(ref['kind'],ref['id']):ref for ref in refs}.values())
            notes.append(dict(subject=tid,kind='DOCUMENT' if target['kind']=='D' else 'STAGE',report_id=REPORT,report_sha256=report_hash,actor=ACTOR,
                recommendation=target['opinion'],findings=findings,outcome='증빙 점검 기록 · 기존 업무 판단 보존',next_action=target['next_action'],refs=refs,
                evidence_revalidation_required=bool(unresolved or changed or reanalysis or (target['kind']=='S' and not result.get('auto_eligible'))),
                evidence_integrity=dict(exported_body_sha256=pkg['exported_body_sha256'],hash_basis=pkg['hash_basis'],quote_checks=pkg['quote_checks']),
                analysis_synchronization=sync,
                previous_review=dict(report_id=prior_cross.get('report_id'),report_sha256=prior_cross.get('report_sha256'),refs=prior_cross.get('refs',[])),
                collection_check=dict(status=capture['status'],error=capture.get('error'),raw_sha256=capture.get('metadata',{}).get('sha256'),retry_priority=1 if capture['status']!='RECOVERED' else 3) if capture else {},
                business_approval=False,metric_approval=False,review_scope='USER_ASSISTED_OFFICER_REVIEW',external_independent_verification=False))
        print('all targets evaluated',len(notes),flush=True)
        if apply:
            for note in notes:save_note(service,note)
        after=protected(service);assert before==after,'protected business state changed'
        summary=dict(targets=len(targets),documents=254,stages=139,original_agent_records=481,original_hash_status=dict(Counter(r['original_hash_status'] for r in vrows if r['kind']=='DOCUMENT')),
            quote_results=dict(Counter(r['status'] for r in qrows if r['target_id'].startswith('DOC_'))),stage_reference_results=dict(Counter(r['comparison'] for r in versions)),
            capture_results=dict(Counter(r['status'] for r in captures.values())),recovered_bodies=len(recovered),existing_business_state_preserved=before==after,
            protected_before_sha256=before,protected_after_sha256=after,metric_units_added=0,business_approvals=0,annotations=len(notes) if apply else 0,applied=apply)
        out=p/('results' if apply else 'preflight');out.mkdir(exist_ok=True)
        for name,data in [('verification-history',vrows),('quote-verification',qrows),('identity-comparison',identities),('stage-candidates',stages),('duplicate-conflicts',conflicts),('reference-history',versions),('state-tracking',states)]:write_csv(out/(name+'.csv'),data)
        (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2));(out/'notes.json').write_text(json.dumps(notes,ensure_ascii=False,indent=2))
        if apply:tx.commit()
        else:tx.rollback()
        print(json.dumps(summary,ensure_ascii=False),flush=True)
    except BaseException:
        tx.rollback();raise
    finally:conn.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('folder');parser.add_argument('--apply',action='store_true');a=parser.parse_args();run(a.folder,a.apply)
