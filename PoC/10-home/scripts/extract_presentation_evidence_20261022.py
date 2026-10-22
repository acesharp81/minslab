"""Read-only presentation extracts. Run in HOME image; no collectors/mapping writes."""
import csv,json,hashlib,os,re,time
from collections import Counter,defaultdict
from datetime import datetime,date,timezone
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo
from sqlalchemy import create_engine,select,func,text
from sqlalchemy.orm import sessionmaker
from backend.db import Revision,Batch,Mapping,ProgramMapping,Audit,MetricSnapshot,IntegrityRound,CollectionJob,IdentityAlias,ProjectIdentity,ProjectEvidence,PlanEvent,PlanProjectLink
from backend.service import HomeService
from backend.read_scope import projection_reads
from backend.source_authority import authority,LABELS,public_url
from scripts.export_json import scrub,credential_values

OUT=Path(os.environ.get('PRESENTATION_OUTPUT','/out'));SECRETS=credential_values();KST=ZoneInfo('Asia/Seoul');POLICY='POL_2025_0907';ASOF=date(2026,10,22)

def clean(value):
    value=scrub(value,SECRETS)
    if isinstance(value,dict):
        return {k:('역할 표기만 공개' if k.lower() in ('actor','reviewer','username','user_name','operator','owner','contact_name') else clean(v)) for k,v in value.items() if k.lower() not in ('authentication','cookie','headers','content_text','raw_text','full_text')}
    if isinstance(value,list):return [clean(v) for v in value]
    if isinstance(value,str):
        value=value.replace('김민','업무담당자')
        value=re.sub(r'officer-[a-z]+-(\d{8})',r'officer-role-\1',value)
        value=re.sub(r'사용자 입력\s*·\s*[^·\n]+\s*·','사용자 입력 · 업무담당자 ·',value)
        value=re.sub(r'(?<!\d)01[016789][- ]?\d{3,4}[- ]?\d{4}(?!\d)','[연락처 마스킹]',value)
        value=re.sub(r'(?<!\d)0[2-6]\d?[- ]\d{3,4}[- ]\d{4}(?!\d)','[연락처 마스킹]',value)
        value=re.sub(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}','[이메일 마스킹]',value)
        value=re.sub(r'(?:https?://)?(?:127\.0\.0\.1|localhost|10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2})(?::\d+)?[^\s"<>]*','[내부주소 마스킹]',value)
        return value
    return value

def dump(name,data):
    p=OUT/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(clean(data),ensure_ascii=False,indent=2,default=str))
def csvwrite(name,rows,fields=None):
    rows=list(rows);fields=fields or list(dict.fromkeys(k for r in rows for k in r)) or ['status']
    p=OUT/name;p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader()
        for r in rows:
            r=clean(r);r={k:json.dumps(v,ensure_ascii=False,default=str) if isinstance(v,(dict,list)) else v for k,v in r.items()}
            w.writerow({k:"'"+v if isinstance(v,str) and v.lstrip().startswith(('=','+','-','@')) else v for k,v in r.items()})
def role(actor):
    actor=str(actor or '')
    if any(t in actor.lower() for t in ('대행','codex','agent','assistant')):return '사용자 위임·에이전트 담당자 대행'
    return '저장된 역할 표기·실제 인적 결재 여부 미확인' if actor else '역할 미기록'
def grade(r):
    if r.get('inferred') or str(r.get('input_rule','')).startswith(('PREDECESSOR','OFFICER_CURRENT_ESTIMATE','OFFICER_AVERAGE')):return '시스템/담당자 추정'
    cls=authority(r.get('evidence_url') or r.get('source_url'),r.get('source_id',''))
    return LABELS[cls]
def log(message):print(message,flush=True)

def main():
    t=time.monotonic();OUT.mkdir(parents=True,exist_ok=True)
    engine=create_engine(os.environ['POC10_DATABASE_URL'],connect_args={'options':'-c default_transaction_read_only=on -c statement_timeout=180000'})
    with engine.connect() as db:
        with db.begin():
            db.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY'))
            instant=db.scalar(text('SELECT CURRENT_TIMESTAMP'))
            s=HomeService(engine,'/app/data');s.sessions=sessionmaker(bind=db,expire_on_commit=False)
            log('consistent snapshot opened')
            cur=db.execute(select(Revision.kind,Revision.source_id,func.count().label('count'),func.min(Revision.recorded_at).label('first_recorded_at'),func.max(Revision.recorded_at).label('last_recorded_at')).where(Revision.superseded_at.is_(None)).group_by(Revision.kind,Revision.source_id)).mappings().all()
            csvwrite('02_collection_starmap/current_record_counts.csv',[dict(r) for r in cur]);log('current record counts')
            summary=dict(extracted_at=instant.isoformat(),as_of_date=ASOF.isoformat(),transaction='PostgreSQL REPEATABLE READ READ ONLY',current_records=sum(r['count'] for r in cur),kind_counts=dict(Counter({k:sum(r['count'] for r in cur if r['kind']==k) for k in {r['kind'] for r in cur}})))
            with projection_reads():
                sources=s.sources(compact=True);projects=s.projects(as_of=ASOF);policies=s.mapping_policies(as_of=ASOF);programs=s.program_links(ASOF,projects)
                dump('00_data/current_sources.json',sources);dump('00_data/projects.json',projects);dump('00_data/policies.json',policies);dump('00_data/programs.json',programs)
                from backend.policy_delivery import build_delivery
                model=build_delivery(s,ASOF,include_portfolio_comparisons=False);dump('00_data/policy_model.json',model)
                from backend.project_collection import collection_matrix
                matrix=collection_matrix(s,policy_id=POLICY,include_link_history=False);dump('00_data/collection_matrix.json',matrix)
                log('projects, policy model and matrix captured')
            source_counts=Counter();source_first={};source_last={}
            batches=[];files={};errors=Counter();url_hashes=defaultdict(set);success_status=Counter();source_success=Counter();audit_counts=[]
            for r in db.execute(select(Batch.id,Batch.source_id,Batch.started_at,Batch.finished_at,Batch.status,Batch.stats,Batch.error,Batch.manifest).order_by(Batch.started_at).execution_options(yield_per=32)).mappings():
                sid=r['source_id'];stats=r['stats'] or {};source_counts[sid]+=1;source_first.setdefault(sid,r['started_at']);source_last[sid]=r['finished_at'] or r['started_at'];success_status[r['status']]+=1
                if r['status']=='SUCCESS':source_success[sid]+=1
                category='NONE' if not r['error'] else 'RATE_LIMIT' if '429' in r['error'] or '한도' in r['error'] else 'TIMEOUT' if 'timeout' in r['error'].lower() else 'HTTP_UPSTREAM' if 'HTTP' in r['error'] else 'PARSE_OR_CONNECTION'
                if category!='NONE':errors[(sid,category)]+=1
                batches.append(dict(run_id=r['id'],started_at=r['started_at'],finished_at=r['finished_at'],source_id=sid,stage_name='COLLECT',status=r['status'],input_count=stats.get('fetched_count'),success_count=stats.get('record_count') if r['status']=='SUCCESS' else None,failed_count=stats.get('failed_count'),review_count=stats.get('review_count'),output_count=stats.get('record_count'),new_records=stats.get('new'),changed_records=stats.get('changed'),unchanged_records=stats.get('unchanged'),raw_response_count=len(r['manifest'] or []),error_category=category,duration_seconds=(r['finished_at']-r['started_at']).total_seconds() if r['finished_at'] else None,code_version='배치별 커밋 미기록',notes='공고/문서 성공률 아님. record_count는 해당 실행에서 반환한 추출 레코드 수. null은 미측정.'))
                for m in r['manifest'] or []:
                    sha=m.get('sha256');path=m.get('file','');key=sha or sid+':'+path
                    if not key:continue
                    url=public_url(m.get('url'));url_hashes[url].add(key)
                    item=files.setdefault(key,dict(file_id='FILE_'+str(key)[:24],sha256=sha,stored_extensions=set(),storage_paths=set(),source_ids=set(),urls=set(),first_collected_at=r['started_at'],last_collected_at=r['started_at'],fetch_observations=0,byte_count=m.get('bytes'),parser_versions=set(),credentials_removed=False))
                    item['stored_extensions'].add(Path(path).suffix.lower().lstrip('.') or 'unknown');item['storage_paths'].add(path);item['source_ids'].add(sid);item['urls'].add(url);item['parser_versions'].add(m.get('parser_version','미기록'));item['fetch_observations']+=1;item['last_collected_at']=r['started_at'];item['credentials_removed']|=bool(m.get('credentials_removed'))
            csvwrite('03_pipeline/pipeline_runs.csv',batches)
            csvwrite('03_pipeline/error_summary.csv',[dict(source_id=sid,error_category=cat,batch_count=count) for (sid,cat),count in sorted(errors.items())]);log('batch and raw file manifests extracted')
            file_rows=[dict(x,**{k:sorted(x[k]) for k in ('stored_extensions','storage_paths','source_ids','urls','parser_versions')},format_basis='보관 확장자 기준; MIME·스캔 여부 판정 아님') for x in files.values()]
            csvwrite('02_collection_starmap/file_inventory.csv',file_rows)
            csvwrite('02_collection_starmap/same_url_changed_content_candidates.csv',[dict(url=url,distinct_response_hashes=len(hashes),sample_hashes=sorted(hashes)[:6],interpretation='동일 URL의 응답 내용 변경 후보. API 응답 변화·정정·삭제·파일 교체 여부를 개별 확정한 건수가 아님') for url,hashes in url_hashes.items() if len(hashes)>1])
            summary.update(collection_batches=len(batches),batch_status_counts=dict(success_status),manifest_observations=sum(x['fetch_observations'] for x in files.values()),unique_response_hashes=len(files),stored_source_paths=sum(len(x['storage_paths']) for x in files.values()),same_url_changed_response_candidates=sum(len(v)>1 for v in url_hashes.values()),repeat_response_observations=sum(x['fetch_observations']-1 for x in files.values()))
            source_table=[];registry={x['id']:x for x in sources}
            for src in sources:
                sid=src['id'];op=src.get('operations',{})
                source_table.append(dict(source_id=sid,机构名=src.get('org'),기관명=src.get('org'),기관유형='공공·공식 등록 수집원' if src.get('authority')=='OFFICIAL' else src.get('authority_label'),시스템명=src['name'],접근URL=src.get('url'),관할지역=src.get('scope') or '경로별 조회범위 확인',자료형태=src.get('data_type_label'),수집방법=op.get('mode'),수집주기=op.get('frequency') or op.get('cycle'),최초수집일=source_first.get(sid),최종시도일=src.get('last_attempt'),마지막정상수집=src.get('last_success'),최근상태=src.get('status'),성공실행수=source_success[sid],전체실행수=source_counts[sid],현재레코드수=sum(r['count'] for r in cur if r['source_id']==sid),발견방식=op.get('discovery'),전처리=op.get('parser'),파일보완=op.get('pdf'),담당자수동보완=op.get('manual_note'),자동순회대상=not src.get('manual_only',False) and src.get('implemented',True),구현여부=src.get('implemented',True),주석='최근 성공 유무와 실행 성공률·모집단 수집률 구분'))
            for row in source_table:row.pop('机构名',None)
            csvwrite('01_process_sources/source_registry.csv',source_table);csvwrite('02_collection_starmap/source_inventory.csv',source_table)
            # Document/publication entities: no full-text or person contact export.
            doc_kinds=('document_evidence','document','lh_notice','notice','gh_notice','plan_notice','notice_catalogue')
            docs=[];attachments=[];doc_facts=[];history=[];profiles=[];evidence_rows=[];links=[]
            for kind in doc_kinds:
                for r in db.execute(select(Revision).where(Revision.kind==kind,Revision.superseded_at.is_(None)).execution_options(yield_per=32)).mappings():
                    p=r['payload'];url=p.get('evidence_url') or p.get('original_url');stored=p.get('original_file');sha=p.get('original_sha256')
                    docs.append(dict(document_id=r['entity_id'],revision_id=r['id'],revision_no=r['revision_no'],record_kind=kind,source_id=r['source_id'],title=p.get('name') or p.get('title'),publisher=registry.get(r['source_id'],{}).get('org'),url=url,publication_date=p.get('source_publication_date') or p.get('source_date') or p.get('notice_date'),original_reference_date=p.get('base_date'),date_precision=p.get('date_precision'),collected_at=r['recorded_at'],batch_id=r['batch_id'],raw_file=stored,original_sha256=sha,payload_sha256=r['payload_hash'],attachment_count=len(p.get('attachments') or []),downloaded_attachment_count=len(p.get('downloaded_attachments') or []),extraction_status=p.get('verification_status') or p.get('status'),pdf_text_extracted=p.get('pdf_text_extracted'),original_scan_classification='미판정 — 저장 상태가 명시된 경우만 별도 해석',evidence_grade=grade(p)))
                    for i,a in enumerate(p.get('attachments') or []):
                        if isinstance(a,str):a={'url':a}
                        attachments.append(dict(parent_document_id=r['entity_id'],attachment_index=i+1,title=a.get('title') or a.get('name'),url=a.get('url') or a.get('href'),sha256=a.get('sha256'),storage_file=a.get('file'),relationship='저장 문서 attachments 배열의 명시적 참조',collection_state=a.get('status')))
                    if kind=='document_evidence':doc_facts.append(dict(id=r['entity_id'],source_id=r['source_id'],revision_no=r['revision_no'],recorded_at=r['recorded_at'],payload={k:v for k,v in p.items() if k not in ('content_text','text','raw_text','full_text')}))
            csvwrite('02_collection_starmap/document_inventory.csv',docs);csvwrite('02_collection_starmap/attachment_inventory.csv',attachments);dump('00_data/document_facts.json',doc_facts)
            summary.update(document_inventory_records=len(docs),document_records=sum(d['record_kind']=='document_evidence' for d in docs),notice_records=sum(d['record_kind'] in ('lh_notice','notice','gh_notice') for d in docs),attachment_references=len(attachments),source_count=len(sources),sources_with_any_success=sum(source_success[x['id']]>0 for x in sources),sources_latest_success=sum(x.get('status')=='SUCCESS' for x in sources))
            for kind in ('project_profile','stage_evidence','evidence_bridge','collection_link','policy_relationship','sequence_review'):
                for r in s.rows(kind):
                    if kind=='project_profile':profiles.append(r)
                    else:evidence_rows.append(dict(r,record_kind=kind))
            dump('00_data/profiles.json',profiles);dump('00_data/link_evidence.json',evidence_rows)
            relation_rows=[]
            for p in programs:
                relation_rows.append(dict(relation_id=p['id'],parent_type='정책',parent_id=p['policy_id'],child_type='프로그램',child_id=p['id'],relation_type='POLICY_PROGRAM',first_seen_at=p.get('created_at'),last_verified_at=p.get('reviewed_at'),source_document_id=None,method='담당자 검토 상태 및 자동 제안 구분',confidence=None,review_status=p['status'],valid_from=None,valid_to=None,evidence_url=p.get('evidence_url'),basis=p.get('basis')))
            for p in projects:
                m=p.get('mapping',{});relation_rows.append(dict(relation_id='MAP_'+p['id'],parent_type='프로그램',parent_id=m.get('program_id'),child_type='사업 원천',child_id=p['id'],relation_type='PROGRAM_PROJECT',first_seen_at=None,last_verified_at=m.get('reviewed_at'),source_document_id=None,method='저장 매핑',confidence=None,review_status=m.get('status'),valid_from=None,valid_to=None,evidence_url=m.get('evidence_url'),basis=m.get('basis')))
            for r in evidence_rows:
                for link in r.get('links',[]) if r['record_kind']=='collection_link' else [r]:
                    sid=link.get('source_entity_id') or (link.get('selected') or {}).get('source_entity_id')
                    if sid:relation_rows.append(dict(relation_id=r['id']+':'+str(sid),parent_type='사업 원천',parent_id=r.get('project_id'),child_type='수집 기록',child_id=sid,relation_type=r['record_kind'],first_seen_at=r.get('recorded_at'),last_verified_at=r.get('reviewed_on'),source_document_id=sid,method=link.get('method') or link.get('match_rule'),confidence=link.get('confidence'),review_status=link.get('status') or r.get('status'),valid_from=None,valid_to=None,evidence_url=link.get('evidence_url'),basis=link.get('basis')))
            # Stable identity aliases are separate from policy membership.
            alias_rows=[dict(r) for r in db.execute(select(IdentityAlias.__table__)).mappings()]
            for a in alias_rows:relation_rows.append(dict(relation_id=a['id'],parent_type='동일 현장 관리ID',parent_id=a['project_id'],child_type='사업 원천',child_id=a['source_entity_id'],relation_type='IDENTITY_ALIAS',first_seen_at=a['created_at'],last_verified_at=a['reviewed_at'],source_document_id=a['source_entity_id'],method=a['match_rule'],confidence=None,review_status=a['relation_status'],valid_from=None,valid_to=None,evidence_url=a['evidence_url'],basis=a['basis']))
            for c in model['portfolio_cohorts']:
                for sid in c['source_ids']:relation_rows.append(dict(relation_id='COHORT:'+c['id']+':'+sid,parent_type='정책 집계 관리사업',parent_id=c['id'],child_type='사업 원천',child_id=sid,relation_type='COUNTED_COHORT_SOURCE',review_status='CURRENT_LEDGER',method='기존 정책 집계 원장',evidence_url=None,basis='원천 사업을 단순 합산하지 않고 관리사업 단위로 1회 집계'))
            csvwrite('04_entity_linking/relations.csv',relation_rows);csvwrite('04_entity_linking/identity_aliases.csv',alias_rows)
            action_counts=[dict(r) for r in db.execute(select(Audit.action,func.count().label('count')).group_by(Audit.action)).mappings()];csvwrite('03_pipeline/audit_action_counts.csv',action_counts)
            excluded=('START_CANDIDATE_FOUND','INDEPENDENT_SNAPSHOT','INDEPENDENT_METRIC_FREEZE')
            review=[];events=[]
            q=select(Audit.__table__).where(Audit.action.not_in(excluded)).order_by(Audit.recorded_at.desc()).limit(20000).execution_options(yield_per=32)
            for r in db.execute(q).mappings():
                before=r['before'] or {};after=r['after'] or {};who=after.get('actor') or before.get('actor')
                events.append(dict(event_id=r['id'],event_time=r['recorded_at'],document_id=after.get('source_entity_id'),record_id=r['entity_id'],project_id=after.get('project_id') or (r['entity_id'] if r['entity_id'].startswith('PRO_') else None),from_stage=None,to_stage=r['action'],result=after.get('status'),reason_code=r['action'],evidence_ref=after.get('evidence_url'),review_status=after.get('status'),reviewer_role=role(who),previous_value=before,new_value=after))
                if any(t in r['action'] for t in ('REVIEW','CONFIRM','MAPPING','PROFILE','PROGRESS','TARGET','ESTIMATE','EVIDENCE','PROGRAM')):
                    review.append(dict(review_id=r['id'],candidate_relation_id=r['entity_id'],submitted_at=None,decision_at=r['recorded_at'],reviewer_role=role(who),decision=after.get('status') or r['action'],reason_code=r['action'],reference_document_id=after.get('source_entity_id'),previous_value=before,new_value=after))
            csvwrite('04_entity_linking/match_review.csv',review)
            p=OUT/'03_pipeline/processing_events.jsonl';p.parent.mkdir(parents=True,exist_ok=True)
            with p.open('w') as f:
                for row in events:f.write(json.dumps(clean(row),ensure_ascii=False,default=str)+'\n')
            csvwrite('03_pipeline/collection_jobs.csv',[dict(r) for r in db.execute(select(CollectionJob.__table__)).mappings()]);log('relations and review samples extracted')
            history_kinds=('project','project_profile','execution_schedule','document_evidence','stage_evidence','policy_profile')
            histq=select(Revision.id,Revision.entity_id,Revision.kind,Revision.source_id,Revision.revision_no,Revision.previous_id,Revision.recorded_at,Revision.superseded_at,Revision.payload_hash,Revision.payload).where(Revision.kind.in_(history_kinds),Revision.revision_no>1).order_by(Revision.recorded_at).execution_options(yield_per=16)
            for r in db.execute(histq).mappings():
                p=r['payload'];fields={k:p.get(k) for k in ('name','planned_units','units','start_actual_date','completion_plan_date','due_date','stage','event_date','status','evidence_url','original_sha256','source_date','verification_status') if k in p}
                history.append({k:v for k,v in dict(r).items() if k!='payload'}|{'tracked_fields':fields})
            csvwrite('09_map_dashboard/status_history.csv',history)
            snapshots=[dict(r) for r in db.execute(select(MetricSnapshot.id,MetricSnapshot.known_at,MetricSnapshot.created_at,MetricSnapshot.digest,MetricSnapshot.result['counts'].label('counts'),MetricSnapshot.context['algorithm_version'].label('algorithm_version'))).mappings()]
            csvwrite('06_data_quality/metric_snapshot_register.csv',snapshots)
            rounds=[]
            for r in db.execute(select(IntegrityRound.id,IntegrityRound.created_at,IntegrityRound.actor,IntegrityRound.snapshot_id,IntegrityRound.score,IntegrityRound.digest,IntegrityRound.result)).mappings():rounds.append(dict(r))
            dump('06_data_quality/integrity_rounds.json',rounds)
            summary.update(project_source_records=len(projects),linked_source_records=sum(p.get('mapping',{}).get('policy_id')==POLICY and p['mapping']['status']!='RELEASED' for p in projects),management_cohorts=len(model['portfolio_cohorts']),contributing_source_ids=len({p for c in model['portfolio_cohorts'] for p in c['source_ids']}),policy_count=sum(p.get('monitor_kind')=='POLICY' for p in policies),program_count=len(programs),policy_program_count=sum(p.get('policy_id')==POLICY and p['status']!='RELEASED' for p in programs),relations=len(relation_rows),audit_total=sum(r['count'] for r in action_counts),audit_exported=len(events),audit_export_limit=20000,audit_excluded_actions=list(excluded),metric_snapshot_count=len(snapshots),integrity_round_count=len(rounds),collection_first_at=min(source_first.values()).isoformat() if source_first else None,source_organization_count=len({s.get('org') for s in sources}),source_domain_count=len({urlsplit(s.get('url','')).hostname for s in sources}),capture_seconds=round(time.monotonic()-t,3))
            dump('00_data/capture_summary.json',summary)
            dump('00_data/coverage_latest.json',s.coverage_details())
            log(json.dumps(summary,ensure_ascii=False,default=str))
    engine.dispose()

if __name__=='__main__':main()
