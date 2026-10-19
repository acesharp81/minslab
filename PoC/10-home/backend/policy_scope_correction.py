"""Withdraw only the type-only policy assertions created by the 19 October batch.

Source identities, quantities, dates, approved profiles and their provenance stay
intact. Never rewrite a staff decision or an unrelated mapping.
"""
from collections import Counter
from sqlalchemy import select, text
from .db import Mapping, ProgramMapping, Revision, Audit, upsert_revision, now
from .start_linkage import BATCH, POLICY, category
from .program_hierarchy import program_id

ACTION='POLICY_SCOPE_CORRECTED'
REASON='사업유형 일치는 정책 귀속 근거가 아님. 2026-10-19 신규 자동 연결의 정책 확정만 철회; 사업 원천·관리값은 보존'


def correct(service, plan):
    counts=Counter()
    with service.sessions.begin() as db:
        if service.engine.dialect.name=='postgresql':db.execute(text('SELECT pg_advisory_xact_lock(1019192)'))
        for item in plan['items']:
            if item['policy_id']!=POLICY or item['existing']:continue
            pid=item['project_id']
            done=db.scalar(select(Audit).where(Audit.entity_id==pid,Audit.action==ACTION))
            if done:
                counts['already_corrected']+=1;continue
            original=db.scalar(select(Revision).where(Revision.entity_id==pid,Revision.revision_no==1))
            mapping=db.scalar(select(Mapping).where(Mapping.project_id==pid).with_for_update())
            if not original or original.batch_id!=BATCH or not mapping or mapping.revision_no!=1 or mapping.policy_id!=POLICY:
                raise ValueError('현재 배치 외의 판정은 변경할 수 없음: '+pid)
            before={k:getattr(mapping,k) for k in ('policy_id','program_id','status','revision_no','basis','evidence_url')}
            name,policy=category(item['source']);assert policy=='UNASSIGNED'
            pgid=program_id(name,policy)
            if not db.get(ProgramMapping,pgid):
                db.add(ProgramMapping(id=pgid,name=name,seed_policy_id=policy,policy_id=policy,status='REVIEW',
                    revision_no=1,basis=REASON,evidence_url=item['source']['evidence_url'],reviewed_at=now()))
            mapping.policy_id=policy;mapping.program_id=pgid;mapping.status='REVIEW'
            mapping.revision_no+=1;mapping.basis=REASON;mapping.reviewed_at=now()
            goals=db.scalars(select(Revision).where(Revision.kind=='execution_schedule',Revision.superseded_at.is_(None))).all()
            for goal in goals:
                if goal.payload.get('project_id')!=pid:continue
                if goal.payload.get('batch_id')!=BATCH+'-estimates':raise ValueError('기존 담당자 일정 보존 필요: '+pid)
                payload=dict(goal.payload,policy_id=policy,policy_scope_correction=REASON)
                row,_=upsert_revision(db,'execution_schedule','officer',pid+':'+payload['stage'],payload,'scope-correction-20261019-v1')
                db.add(Audit(entity_id=row.entity_id,action='SCHEDULE_SCOPE_CORRECTED',before=goal.payload,after=payload))
                counts['schedule_scope_corrected']+=1
            after={k:getattr(mapping,k) for k in before}
            db.add(Audit(entity_id=pid,action='MAPPING_REVIEW',before=before,after=after))
            db.add(Audit(entity_id=pid,action=ACTION,before=before,after=after))
            counts['policy_assertions_withdrawn']+=1
    return dict(counts)
