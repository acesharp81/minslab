"""Discover residential new-build starts without inventing policy attribution.

Native source anchors are review candidates, never extra measured housing supply.
Existing aliases/approvals are retained, and every source revision stays traceable.
"""
from datetime import date
from sqlalchemy import select,text
from .db import Revision,ProjectIdentity,IdentityAlias,ProjectEvidence,Audit
from .identity import project_id


def eligible(payload, start, end):
    stamp=(payload.get('dates') or {}).get('실제착공일 (realStcnsDay)')
    try:date.fromisoformat(stamp)
    except (ValueError,TypeError):return False
    return (start<=stamp<=end and payload.get('construction_type')=='신축'
        and payload.get('main_purpose') in ('공동주택','단독주택'))


def reconcile(service, reference=None):
    from .api_samples import today
    day=reference or today(); start=f'{day.year}-01-01'; end=day.isoformat()
    added=evidence_added=0; items=[]
    with service.sessions.begin() as db:
        if service.engine.dialect.name=='postgresql':db.execute(text('SELECT pg_advisory_xact_lock(1019191)'))
        stamp=Revision.payload['dates']['실제착공일 (realStcnsDay)'].as_string()
        rows=db.scalars(select(Revision).where(Revision.kind=='general_permit',Revision.superseded_at.is_(None),
            stamp>=start,stamp<=end).order_by(Revision.entity_id)).all()
        aliases={a.source_entity_id:a for a in db.scalars(select(IdentityAlias))}
        evidence={(e.project_id,e.revision_id) for e in db.scalars(select(ProjectEvidence))}
        for row in rows:
            p=row.payload
            if not eligible(p,start,end):continue
            old=aliases.get(row.entity_id)
            pid=old.project_id if old else project_id(row.entity_id)
            if not old:
                if db.get(ProjectIdentity,pid) is None:
                    db.add(ProjectIdentity(id=pid,name=p.get('name') or p['address'],region=p['region'],identity_status='REVIEW'))
                    db.flush()
                alias=IdentityAlias(project_id=pid,source_entity_id=row.entity_id,source_id=row.source_id,
                    relation_status='REVIEW',match_rule='RESIDENTIAL_NEW_BUILD_START_CANDIDATE',
                    basis='원천의 주거용·신축·실제착공일 일치. 원천 고유 관리번호의 후보 앵커; 기존 사업 중복·정책 귀속·호수 범위 추가 대조.',
                    evidence_revision_id=row.id,evidence_url=p.get('evidence_url') or '')
                db.add(alias);aliases[row.entity_id]=alias;added+=1
                db.add(Audit(entity_id=pid,action='START_CANDIDATE_FOUND',before={},after=dict(
                    actor='수집 후보 발견',reason='일반 건축인허가 실제착공 기록',source_entity_id=row.entity_id,
                    source_revision_id=row.id,status='REVIEW',policy_assignment=None)))
            if (pid,row.id) not in evidence:
                db.add(ProjectEvidence(project_id=pid,revision_id=row.id,evidence_role='CONSTRUCTION_CANDIDATE'))
                evidence.add((pid,row.id));evidence_added+=1
            items.append(dict(source_entity_id=row.entity_id,canonical_id=pid,name=p.get('name'),
                units=p.get('units'),actual_start=p['dates']['실제착공일 (realStcnsDay)'],
                status=aliases[row.entity_id].relation_status))
    return dict(period_start=start,period_end=end,candidate_rows=len(items),candidates_added=added,
        evidence_added=evidence_added,approval_effect='NONE',actual_events_created=0,
        items=items,note='사업 식별 검토 후보. 확정 정책 물량이나 신규 착공 실적에 자동 가산하지 않음')
