"""Current role-specific outcomes; CSV includes only actionable human decisions."""
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
  row.update(body_text=supplement['body_text'],body_origin='담당자 원문 복구',manual_summary=supplement.get('summary',''))
 if doc['status']=='HOLD' and decision_after(doc,row.get('created') or 0):
  row.update(reason=decision.get('reason') or row.get('reason'),stage='HUMAN_HOLD',state='HOLD')
 return row


def items(service,store,role):
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
  return [enrich(r,docs.get(r['subject']),supplements.get(r['subject']),ai.get(r['subject'])) for r in results]
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
    result=dict(analysis=value.get('result'),passes=value.get('passes',[])),evidence=(value.get('result') or {}).get('evidence_quotes',[]),body_text=value.get('body_text',''),
    run_id=event['run_id'],created=event['created'],action='원문·추출값 확인 후 재시도 또는 담당자 판단' if held else '후속 업무 검토'))
 return [enrich(r,docs.get(r['subject']),supplements.get(r['subject']),ai.get(r['subject'])) for r in result]

FIELDS=['에이전트','대상ID','자료명','상태','처리단계','보류사유','담당자확인사항','원문URL','원문판본','검토모델','실행ID','처리시각','근거_JSON','분석결과_JSON','수집본문','현재업무상태','최근업무판단사유','본문출처','수동복구확인내용']
def export_csv(service,store,role='all'):
 if role not in ('all','collection','officer'):raise ValueError('수집·업무담당 판단보류만 내보낼 수 있습니다')
 output=io.StringIO(newline='');writer=csv.writer(output);writer.writerow(FIELDS)
 for selected in ('collection','officer') if role=='all' else (role,):
  for r in items(service,store,selected):
   if r['state']!='HOLD':continue
   writer.writerow([cell(v) for v in [ROLES[selected],r['subject'],r.get('title'), '판단보류 · 사람 개입 필요',r.get('stage'),
    r.get('reason'),r.get('action'),r.get('url'),r.get('source_revision_no'),r.get('model'),r.get('run_id'),
    datetime.fromtimestamp(r['created'],timezone.utc).isoformat() if r.get('created') else '',
    json.dumps(r.get('evidence',[]),ensure_ascii=False),json.dumps(r.get('result',{}),ensure_ascii=False),r.get('body_text',''),r.get('business_status_label',''),r.get('business_reason',''),r.get('body_origin','AI 수집'),r.get('manual_summary','')]])
 return '\ufeff'+output.getvalue()
