"""Independent report annotations: advisory evidence, never business approvals."""
from sqlalchemy import select
from .db import Revision, Audit, upsert_revision, now, entity_id
from .publication_evidence import safe_value
KIND='hold_cross_review'


def load(service, subjects):
 if not subjects:return {}
 with service.sessions() as db:
  rows=list(db.scalars(select(Revision).where(Revision.kind==KIND,Revision.superseded_at.is_(None),Revision.payload['subject'].as_string().in_(subjects))))
  ids={ref['id'] for r in rows for ref in r.payload.get('refs',[])}
  refs={r.entity_id:r for r in db.scalars(select(Revision).where(Revision.entity_id.in_(ids),Revision.superseded_at.is_(None)))} if ids else {}
 return {r.payload['subject']:safe_value(dict(r.payload,current=all(ref['id'] in refs and refs[ref['id']].payload_hash==ref['hash'] for ref in r.payload.get('refs',[])))) for r in rows}


def save(service,payload):
 if not payload.get('actor') or not payload.get('report_sha256') or not payload.get('findings') or not payload.get('refs'):raise ValueError('검토자·보고서 해시·대조 결과·원천 판본이 필요합니다')
 with service.sessions.begin() as db:
  for ref in payload['refs']:
   r=db.scalar(select(Revision).where(Revision.entity_id==ref['id'],Revision.kind==ref['kind'],Revision.superseded_at.is_(None)).with_for_update())
   if not r or r.payload_hash!=ref['hash']:raise ValueError('교차 검토 이후 원천 판본 변경')
  old=db.scalar(select(Revision).where(Revision.kind==KIND,Revision.entity_id==entity_id(KIND,'officer_cross_review',payload['subject']),Revision.superseded_at.is_(None)))
  if old and all(old.payload.get(k)==v for k,v in payload.items()):return dict(id=old.entity_id,unchanged=True)
  value=dict(payload,reviewed_at=now().isoformat(),effect='외부 모델 의견을 활용한 업무담당자 교차 검토 · 실적 승인 아님')
  row,_=upsert_revision(db,KIND,'officer_cross_review',payload['subject'],value,'external-hold-cross-review')
  db.add(Audit(entity_id=row.entity_id,action='HOLD_CROSS_REVIEW',before=old.payload if old else {},after=value))
 return dict(id=row.entity_id,revision_no=row.revision_no)
