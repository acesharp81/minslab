"""Officer inbox for discovered publications; adoption is not a stage achievement."""
import re
from collections import Counter
from sqlalchemy import select
from .db import Revision, Mapping, Audit, entity_id, upsert_revision, now
from .sources import SOURCES
from .source_authority import public_url, authority
from .publication_review_guidance import guidance

KIND='publication_review'
OWNER='publication_review'
STATES={'REVIEW':'검토 대기','HOLD':'보류','EXCLUDED':'제외','APPROVED':'자료 연결 승인','REGISTRATION_REQUIRED':'검토 승인 · 사업 등록 대기'}
RULES=[
 (r'고덕\s*강일(?:지구)?\s*3단지',2,['고덕강일'],'기존 분양공고의 정정·가격 변경 확인','기존 고덕강일 3단지 공고와 대조하고, 정정 항목과 공고 물량을 구분하세요. 같은 호수를 다시 더하지 않습니다.'),
 (r'면목.*사당|사당.*면목',1,['면목','사당'],'2027년 계획·중복 범위 확인','정책 포함 여부, 구역별 물량·착공 예정일과 기존 반영 여부를 확인하세요. 예정 물량은 실제 착공이 아닙니다.'),
 (r'신길4|녹번동근린공원|송중동',2,['신길4','녹번동근린공원','송중동'],'정책 귀속·기존 보류 사유 확인','기존 사업의 정책 연결 상태와 이전 판단 사유를 원문과 대조하세요. 자료 연결 승인과 정책 귀속 확정은 별도입니다.'),
 (r'제물포',2,['제물포'],'동일 구역·실제 착공 근거 확인','이주율과 연내 착공 전망을 실제 착공으로 확정하지 마세요. 기존 사업과 동일 구역인지 확인하세요.'),
 (r'구월2',2,['구월2'],'지구·블록 범위 확인','보상 착수 자료입니다. 관리 정책과 지구·개별 블록 범위를 확인하고 착공 실적과 구분하세요.'),
 (r'성북동',3,['성북'],'대상 주소·단지 범위 확인','계획·자문 대상 주소와 단지를 확인하세요. 기존 수서 사업과 동일하다고 이름만으로 판단하지 마세요.'),
 (r'수서택지',3,['수서'],'대상 단지 범위 확인','자문 대상 단지와 기존 수서 사업의 범위를 대조하세요. 이름만으로 같은 사업으로 판단하지 마세요.'),
 (r'시흥거모.*S-?1',3,['시흥거모S1'],'기존 공급공고 중복 확인','기존 시흥거모 S1 300호와 동일 공고인지 확인하세요. 보도자료의 호수를 다시 더하지 마세요.'),
]

def normalized(value):return re.sub(r'[^가-힣a-z0-9]','',str(value).lower())

def triage(title):
 for pattern,priority,terms,label,question in RULES:
  if re.search(pattern,title):return dict(priority=priority,terms=terms,review_topic=label,question=question)
 secondary=any(t in title for t in ('감사패','교육 성료','전시회','전력망','경전철','교통망'))
 return dict(priority=4 if secondary else 3,terms=[],review_topic='사업 실적 관련성 분류' if secondary else '정책·사업 범위 확인',
             question='홍보·교육·교통·일반 기사인지 확인하고 사업 사건과 무관하면 제외하세요.' if secondary else '원문에서 사업명·구역·사건·일정을 확인하고 기존 사업 또는 신규 등록 대상으로 분류하세요.')

def source_ids():return [s['id'] for s in SOURCES if s.get('discovery_only')]

def queue(service, include_options=True):
 with service.sessions() as db:
  docs=list(db.scalars(select(Revision).where(Revision.kind=='document_evidence',Revision.source_id.in_(source_ids()),Revision.superseded_at.is_(None))))
  decisions={r.payload['document_id']:r for r in db.scalars(select(Revision).where(Revision.kind==KIND,Revision.superseded_at.is_(None)))}
  bridge_ids={entity_id('evidence_bridge','cross_source',pid+':'+doc_id)
              for doc_id,r in decisions.items() if r.payload.get('status')=='APPROVED'
              for pid in r.payload.get('project_ids',[])}
  bridges={r.entity_id:r.payload for r in db.scalars(select(Revision).where(Revision.entity_id.in_(bridge_ids),Revision.superseded_at.is_(None)))} if bridge_ids else {}
  projects=[]
  policies=[dict(id=p['policy_id'],name=p['name']) for p in service.mapping_policies() if p.get('monitor_kind')=='POLICY'] if include_options else []
  policy_names={p['id']:p['name'] for p in policies}
  if include_options:
   for r,m in db.execute(select(Revision,Mapping).outerjoin(Mapping,Mapping.project_id==Revision.entity_id).where(Revision.kind=='project',Revision.superseded_at.is_(None))):
    projects.append(dict(id=r.entity_id,name=r.payload.get('name',''),region=r.payload.get('region'),units=r.payload.get('planned_units'),revision_no=r.revision_no,
        mapping_status=m.status if m else None,policy_id=m.policy_id if m else None,policy_name=policy_names.get(m.policy_id, m.policy_id) if m else None,mapping_basis=m.basis if m else '',program_id=m.program_id if m else None))
  items=[]
  for doc in docs:
   p=doc.payload;old=decisions.get(doc.entity_id);decision=old.payload if old else None
   stale=bool(decision and decision['source_revision_no']!=doc.revision_no)
   link_changed=bool(decision and decision['status']=='APPROVED' and any(bridges.get(entity_id('evidence_bridge','cross_source',pid+':'+doc.entity_id),{}).get('status')!='CONFIRMED' for pid in decision.get('project_ids',[])))
   state='REVIEW' if stale or link_changed or not decision else decision['status'];t=triage(p.get('name',''))
   matches=[dict(project,match_basis='사업명 유사 후보 · 주소·구역 대조 전 동일 사업 미확정') for project in projects
            if any(normalized(term) in normalized(project['name']) for term in t['terms'])]
   items.append(dict(id=doc.entity_id,source_id=doc.source_id,source_name=next(s['name'] for s in SOURCES if s['id']==doc.source_id),
       title=p.get('name'),source_date=p.get('source_date'),evidence_url=public_url(p.get('evidence_url')),authority=authority(p.get('evidence_url')),
       source_revision_no=doc.revision_no,review_revision_no=old.revision_no if old else 0,
       status=state,status_label=STATES[state],source_changed=stale,link_changed=link_changed,decision=decision,candidates=matches,guidance=guidance(p.get('name',''),matches,t['priority']) if include_options else None,**t))
  items.sort(key=lambda r:(r['priority'],tuple(-ord(c) for c in (r['source_date'] or '')),r['id']))
  counts=dict(Counter(r['status'] for r in items))
  pending=sum(counts.get(k,0) for k in ('REVIEW','HOLD','REGISTRATION_REQUIRED'))
  result=dict(items=items,counts=counts,pending=pending,total=len(items),status_labels=STATES)
  if include_options:
   result.update(projects=sorted(projects,key=lambda p:p['name']),policies=policies)
  return result

def history(service, document_id):
 with service.sessions() as db:
  eid=entity_id(KIND,OWNER,document_id)
  return [dict(r.payload,revision_no=r.revision_no,recorded_at=r.recorded_at.isoformat()) for r in db.scalars(select(Revision).where(Revision.entity_id==eid).order_by(Revision.revision_no.desc()))]

def save(service, document_id, source_revision_no, review_revision_no, status, policy_id, project_ids, new_project_names, actor, reason, source_checked):
 if status not in STATES:raise ValueError('지원하지 않는 검토 상태입니다')
 if not actor.strip() or len(reason.strip())<5:raise ValueError('담당자와 5자 이상의 판단 사유를 입력하세요')
 if len(project_ids)!=len(set(project_ids)):raise ValueError('중복 사업 선택을 제거하세요')
 approved=status in ('APPROVED','REGISTRATION_REQUIRED')
 names=[n.strip() for n in new_project_names if n.strip()]
 if any(len(n)>200 for n in names):raise ValueError('신규 사업명은 각 200자 이내로 입력하세요')
 if approved and not source_checked:raise ValueError('원문과 적용 범위를 확인한 뒤 승인하세요')
 if approved and not policy_id:raise ValueError('검토 대상 정책을 선택하세요')
 if status=='APPROVED' and not project_ids:raise ValueError('자료를 연결할 기존 사업을 선택하세요. 대응 사업이 없으면 사업 등록 대기로 검토 승인하세요')
 if status=='APPROVED' and names:raise ValueError('신규 사업이 포함된 자료는 사업 등록 대기로 승인하세요')
 if status=='REGISTRATION_REQUIRED' and not names:raise ValueError('등록 검토할 사업명을 입력하세요. 복수 구역은 각각 구분하세요')
 # A verified document/project identity does not establish policy membership.
 # Registration review also records candidates only; policy membership is
 # decided later, without inventing a policy just to create a review task.
 policy_unassigned=approved and policy_id=='UNASSIGNED'
 if approved and not policy_unassigned and policy_id not in {p['policy_id'] for p in service.mapping_policies() if p.get('monitor_kind')=='POLICY'}:raise ValueError('등록된 정책을 선택하세요')
 with service.sessions.begin() as db:
  # Lock the source row too: concurrent first decisions must not both succeed.
  doc=db.scalar(select(Revision).where(Revision.entity_id==document_id,Revision.kind=='document_evidence',Revision.source_id.in_(source_ids()),Revision.superseded_at.is_(None)).with_for_update())
  if not doc:raise ValueError('신규 수집 검토 대상이 없습니다')
  eid=entity_id(KIND,OWNER,document_id)
  old=db.scalar(select(Revision).where(Revision.entity_id==eid,Revision.superseded_at.is_(None)).with_for_update())
  if doc.revision_no!=source_revision_no or (old.revision_no if old else 0)!=review_revision_no:return dict(conflict=True)
  selected=list(db.scalars(select(Revision).where(Revision.kind=='project',Revision.entity_id.in_(project_ids),Revision.superseded_at.is_(None)))) if project_ids else []
  if len(selected)!=len(project_ids):raise ValueError('선택한 사업이 변경되었거나 없습니다')
  stamp=now().isoformat();payload=dict(document_id=document_id,source_id=doc.source_id,source_revision_no=doc.revision_no,
      title=doc.payload.get('name'),evidence_url=public_url(doc.payload.get('evidence_url')),status=status,policy_id=policy_id,
      project_ids=project_ids,project_names=[r.payload.get('name') for r in selected],new_project_names=names,
      actor=actor.strip(),reason=reason.strip(),source_checked=bool(source_checked),reviewed_at=stamp,
      effect='자료 연결 승인. 정책 귀속·호수·목표·실적 자동 변경 없음.' if status=='APPROVED' else '검토 결과 저장. 사업 등록과 정책·호수·일정 반영은 후속 처리 필요.' if status=='REGISTRATION_REQUIRED' else '판단 사유 기록. 실적 변경 없음.')
  row,_=upsert_revision(db,KIND,OWNER,document_id,payload,'officer-review')
  # Keep officer-approved links as ordinary, source-pinned evidence bridges.
  # An empty facts list cannot change a stage total or create an event.
  previous=set((old.payload if old else {}).get('project_ids',[]));active=set(project_ids) if status=='APPROVED' else set()
  for pid in previous|active:
   key=pid+':'+document_id;bridge_id=entity_id('evidence_bridge','cross_source',key)
   existing=db.scalar(select(Revision).where(Revision.entity_id==bridge_id,Revision.superseded_at.is_(None)).with_for_update())
   if existing and existing.payload.get('review_owner')!=OWNER:continue
   if pid not in active:
    if not existing:continue
    bridge=dict(existing.payload,status='RELEASED',review_basis=reason.strip(),reviewed_on=stamp[:10])
   else:
    target=next(r for r in selected if r.entity_id==pid)
    bridge=dict(project_id=pid,name=target.payload.get('name'),region=target.payload.get('region'),source_entity_id=document_id,
        source_revision_no=doc.revision_no,source_id=doc.source_id,evidence_source_id=doc.source_id,source_name=doc.payload.get('name'),
        evidence_url=public_url(doc.payload.get('evidence_url')),relation_type='DOCUMENT_REFERENCE',units=None,facts=[],
        status='CONFIRMED',reviewed=True,basis=reason.strip(),review_basis=reason.strip(),reviewed_on=stamp[:10],
        actor=actor.strip(),base_date=doc.payload.get('source_date'),review_owner=OWNER,publication_review_id=row.entity_id)
   upsert_revision(db,'evidence_bridge','cross_source',key,bridge,'officer-review')
  db.add(Audit(entity_id=row.entity_id,action='PUBLICATION_REVIEW',before=old.payload if old else {},after=payload))
  return dict(payload,id=row.entity_id,revision_no=row.revision_no)
