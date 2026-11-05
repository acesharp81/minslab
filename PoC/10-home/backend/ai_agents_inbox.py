"""Current role outcomes; officer CSV exposes YES/NO/HOLD and actual effects."""
import csv,io,json
from datetime import datetime,timezone
from .ai_agent_catalog import ROLES
from .ai_agents_store import latest
from .publication_reviews import queue
from .ai_collection import annotations
from .publication_review_export import cell
from .publication_supplements import load as load_supplements, usable


def decision_after(doc,created):
 try:return datetime.fromisoformat((doc.get('decision') or {}).get('reviewed_at','')).timestamp()>=created
 except (ValueError,TypeError):return False

def enrich(row,doc,supplement,analysis):
 if not doc:return row
 decision=doc.get('decision') or {}
 row.update(business_status=doc['status'],business_status_label=doc['status_label'],business_reason=decision.get('reason',''))
 if usable(supplement,doc['source_revision_no'],analysis):
  row.update(body_text=supplement['body_text'],body_source_revision_no=supplement['source_revision_no'],body_origin='담당자 원문 복구',manual_summary=supplement.get('summary',''))
 if row.get('role')=='collection' and row.get('state')=='HOLD' and row.get('body_origin')=='담당자 원문 복구' and row.get('stage') in ('DOCUMENT_ERROR','ANALYSIS_ERROR'):
  row.update(reanalysis_required=True,reason='유효 수동본문 확보 · 이전 수집 오류 이후 재분석 필요',action='복구된 원문으로 수집·업무 분석 재실행 · 기존 담당자 판단은 보존')
 if row.get('role')!='algorithm' and doc['status']=='HOLD' and decision_after(doc,row.get('created') or 0):
  row.update(reason=decision.get('reason') or row.get('reason'),stage='HUMAN_HOLD',state='HOLD')
 return row


def items(service,store,role,evidence_export=False):
 if role not in ROLES:raise ValueError('지원하지 않는 에이전트')
 data=queue(service,include_options=False);docs={d['id']:d for d in data['items']};supplements=load_supplements(service,list(docs));ai=annotations(service,list(docs))
 if role!='collection':
  results=list(latest(store,role).values())
  for r in results:
   doc=docs.get(r['subject']);r['role']=role
   if doc and r.get('source_revision_no') and doc['source_revision_no']!=r['source_revision_no']:
    r.update(state='HOLD',stage='SOURCE_CHANGED',reason='분석 이후 원문 판본 변경 · 다시 검토 필요')
   elif role=='officer' and doc and decision_after(doc,r['created']) and not (doc.get('decision') or {}).get('actor','').startswith('업무담당자 AI') and r['state']=='HOLD' and doc['status'] in ('APPROVED','EXCLUDED','REGISTRATION_REQUIRED') and not doc['source_changed'] and not doc['link_changed']:
    r.update(state='DONE',stage='HUMAN_RESOLVED',reason='담당자의 후속 판단으로 처리됨 · '+doc['status_label'])
  if role=='officer':
   # Existing human HOLD decisions are visible without inventing an AI execution.
   covered={r['subject'] for r in results}
   for d in docs.values():
    if d['status']=='HOLD' and d['id'] not in covered:
     results.append(dict(role=role,subject=d['id'],state='HOLD',stage='EXISTING_HOLD',title=d['title'],url=d['evidence_url'],
       reason=(d['decision'] or {}).get('reason') or '기존 담당자 보류',source_revision_no=d['source_revision_no'],
       model=None,evidence=[],action='원문과 기존 판단 근거를 확인해 연결·제외 판단',created=None))
  if role=='officer':
   from .stage_reconciliation import list_items, LIVE
   from .publication_evidence import safe_value
   proposals=list_items(service,include_proof=evidence_export);by_id={p['id']:p for p in proposals}
   for r in results:
    ids=[p['id'] for p in r.get('stage_proposals',[])]
    if ids and all(by_id.get(pid,{}).get('status') in ('APPLIED','DISMISSED') for pid in ids):
     r.update(state='DONE',stage='STAGE_RESOLVED',reason='단계별 실적 제안 처리 완료 · 승인·제외 이력 확인')
   for proposal in proposals:
    p=safe_value(proposal)
    results.append(dict(role=role,subject=p['id'],state='HOLD' if p['status'] in LIVE else 'DONE',stage='STAGE_REVIEW',
     title=p['project_name']+' · '+p['stage_label']+' 실적 반영',url=p['url'],reason=' / '.join(p['blockers']+p['review_reasons']) or p['status'],
     source_revision_no=p['source_ref']['revision_no'],created=None,action='신규 자료 검토 → 단계별 실적 반영 검토에서 기존값·새 근거 확인',
     result=p,evidence=[v for k,v in p['quotes'].items() if k in ('date_quote','units_quote') and isinstance(v,str) and v],body_text=p.get('evidence_package',{}).get('body',''),model=None,cross_review=p.get('cross_review',{})))
  if role=='algorithm':
   from .algorithm_review import review_map
   reviews=review_map(store)
   for r in results:
    review=reviews.get(r['subject'],{});r['algorithm_review']=review
    if review.get('result_id')==r['id'] and r.get('stage')!='SOURCE_CHANGED':
     action=review.get('action')
     r.update(state='HOLD' if action=='RETRY' else 'DONE',stage={'APPLY':'RULE_APPLIED','IGNORE':'TRANSIENT_DISMISSED','RETRY':'REANALYSIS_REQUESTED','DISABLE':'RULE_DISABLED'}[action],reason=review['effect'],action='담당자 판단: '+review['reason'])
  results=attach_reviews(service,[enrich(r,docs.get(r['subject']),supplements.get(r['subject']),ai.get(r['subject'])) for r in results])
  if role=='officer':
   for r in results:
    if r['state']=='HOLD':r['verdict']='HOLD'
    elif r.get('verdict') not in ('YES','NO'):
     r['verdict']='NO' if r.get('business_status')=='EXCLUDED' or (r.get('result') or {}).get('status')=='DISMISSED' else 'YES' if r.get('business_status')=='APPROVED' or (r.get('result') or {}).get('status')=='APPLIED' else 'HOLD'
    r['state']='HOLD' if r['verdict']=='HOLD' else 'DONE'
    if r['verdict']=='HOLD' and not r.get('missing_evidence'):
     from .ai_officer_decisions import pending
     r['missing_evidence']=[pending(r.get('reason') or '최종 판단 근거 재점검 필요')]
  return results
 seen={};result=[]
 with store.db() as c:
  events=c.execute("SELECT e.*,r.config FROM events e JOIN runs r ON e.run_id=r.id WHERE e.kind IN ('SOURCE','SEARCH','SOURCE_ERROR','ANALYZED','ANALYSIS_ERROR','DOCUMENT_ERROR','UNCHANGED') ORDER BY e.id DESC").fetchall()
 for event in events:
  config=json.loads(event['config'])
  if config.get('agent_role','collection')!='collection':continue
  p=json.loads(event['payload']);subject=p.get('document_id') or 'source:'+(p.get('source') or p.get('query') or '')
  if subject in seen:continue
  seen[subject]=True;doc=docs.get(subject);value=ai.get(subject,{})
  if p.get('document_id') and not doc:continue
  flags=list(p.get('checks') or (value.get('checks') if event['kind']=='UNCHANGED' else []) or [])
  if event['kind'] in ('ANALYZED','UNCHANGED'):flags+=list((value.get('result') or {}).get('issues') or [])
  held=event['kind'] in ('SOURCE_ERROR','DOCUMENT_ERROR','ANALYSIS_ERROR') or bool(flags)
  reason=p.get('message') or ' / '.join(flags) or '수집·분석 완료'
  if doc and value.get('source_revision_no') and doc['source_revision_no']!=value['source_revision_no']:
   held=True;reason='원문 판본 변경 · 재수집 필요'
  if doc and decision_after(doc,event['created']) and doc['status'] in ('APPROVED','EXCLUDED','REGISTRATION_REQUIRED') and not doc['source_changed'] and not doc['link_changed']:
   held=False;reason='담당자 후속 판단 완료 · '+doc['status_label']
  result.append(dict(role=role,subject=subject,state='HOLD' if held else 'DONE',stage=event['kind'],
    title=(doc or {}).get('title') or p.get('source') or p.get('query') or subject,url=(doc or {}).get('evidence_url',''),
    source_revision_no=(doc or {}).get('source_revision_no'),reason=reason,model=config.get('selected_model') or config.get('profile'),
    result=dict(analysis=value.get('result'),passes=value.get('passes',[])),evidence=(value.get('result') or {}).get('evidence_quotes',[]),body_text=value.get('body_text',''),body_source_revision_no=value.get('source_revision_no'),
    run_id=event['run_id'],created=event['created'],action='원문·추출값 확인 후 재시도 또는 담당자 판단' if held else '후속 업무 검토'))
 return attach_reviews(service,[enrich(r,docs.get(r['subject']),supplements.get(r['subject']),ai.get(r['subject'])) for r in result])

def attach_reviews(service, rows):
 from .hold_review import load
 reviews=load(service,[r['subject'] for r in rows if r['subject'].startswith('DOC_')])
 for r in rows:
  if r['subject'] in reviews:r['cross_review']=reviews[r['subject']]
 return rows


FIELDS=['에이전트','대상ID','자료명','상태','처리단계','보류사유','담당자확인사항','원문URL','원문판본','검토모델','실행ID','처리시각','근거_JSON','분석결과_JSON','수집본문','현재업무상태','최근업무판단사유','본문출처','수동복구확인내용','대상유형','증빙상태','증빙패키지_JSON','사건군ID','중복검토ID_JSON','상이한값검토ID_JSON','교차검토_JSON','재분석필요','자동반영가능']
def export_csv(service,store,role='all',unique=False,verdict='HOLD'):
 from .publication_evidence import safe_value
 import hashlib
 if role not in ('all','collection','officer'):raise ValueError('수집·업무담당 판단보류만 내보낼 수 있습니다')
 if verdict not in ('ALL','YES','NO','HOLD') or verdict!='HOLD' and role!='officer':raise ValueError('업무담당자 결정 범위를 확인하세요')
 rows=[]
 for selected in ('collection','officer') if role=='all' else (role,):
  rows.extend(r for r in items(service,store,selected,evidence_export=True) if (r['state']=='HOLD' if verdict=='HOLD' else verdict=='ALL' or r.get('verdict')==verdict))
 groups={}
 for index,r in enumerate(rows):groups.setdefault(r['subject'] if unique else str(index),[]).append(r)
 output=io.StringIO(newline='');writer=csv.writer(output);writer.writerow([('판단사유' if verdict!='HOLD' and f=='보류사유' else f) for f in FIELDS]+['합쳐진기록수','에이전트별기록_JSON'])
 encode=lambda x:json.dumps(safe_value(x),ensure_ascii=False)
 for group in groups.values():
  # Keep every role's assessment, while including the longest available body once.
  original=max(group,key=lambda x:len(x.get('body_text','')));r=safe_value(original);result=dict(r.get('result') or {})
  if r.get('role')=='officer':result.update(verdict=r.get('verdict','HOLD'),missing_evidence=r.get('missing_evidence',[]),retry_after=r.get('retry_after'),effects=r.get('effects',[]))
  package=result.get('evidence_package') or dict(source_url=r.get('url'),source_revision_no=r.get('source_revision_no'),
     body_origin=r.get('body_origin','AI 수집'),body_source_revision_no=r.get('body_source_revision_no'),body_current=r.get('body_source_revision_no')==r.get('source_revision_no') if r.get('body_source_revision_no') else None,exported_body_sha256=hashlib.sha256(r.get('body_text','').encode()).hexdigest() if r.get('body_text') else None,
     quote_checks=[dict(exact=q in r.get('body_text',''),whitespace_normalized=''.join(q.split()) in ''.join(r.get('body_text','').split())) for q in r.get('evidence',[]) if isinstance(q,str) and q.strip()],
     note='현재 저장 본문 대조 · 인용 불일치는 허위 단정이 아닌 재확인 대상')
  record_summaries=[{k:v for k,v in x.items() if k not in ('body_text','cross_review')} for x in group] if unique else []
  values=[' + '.join(dict.fromkeys(ROLES[x['role']] for x in group)),r['subject'],r.get('title'),{'YES':'Yes · 업무 반영 완료','NO':'No · 제외 확정','HOLD':'보류 · 추가 자료 확보 후 재판단'}.get(r.get('verdict'),'보류') if r.get('role')=='officer' else '판단보류 · 사람 개입 필요',r.get('stage'),
    r.get('reason'),r.get('action'),r.get('url'),r.get('source_revision_no'),r.get('model'),r.get('run_id'),
    datetime.fromtimestamp(r['created'],timezone.utc).isoformat() if r.get('created') else '',encode(r.get('evidence',[])),encode(result),r.get('body_text',''),
    r.get('business_status_label',''),r.get('business_reason',''),r.get('body_origin','AI 수집'),r.get('manual_summary',''),
    'STAGE' if r['subject'].startswith('STA_') else 'DOCUMENT',result.get('body_status',('STALE_TEXT' if r.get('body_source_revision_no') and r.get('body_source_revision_no')!=r.get('source_revision_no') else 'TEXT_AVAILABLE') if r.get('body_text') else 'MISSING'),encode(package),
    result.get('event_group',''),encode(result.get('duplicate_ids',[])),encode(result.get('different_value_ids',[])),encode(r.get('cross_review',{})),
    bool(r.get('reanalysis_required')),bool(result.get('auto_eligible')),len(group),encode(record_summaries)]
  writer.writerow([cell(v) for v in values])
 return '\ufeff'+output.getvalue()
