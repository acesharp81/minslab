"""Hold only new, unreviewed LH candidates introduced by the 2026-10-19 route expansion.

Retain source evidence and every pre-existing/staff-approved mapping. Idempotent.
"""
import json
from datetime import datetime,timezone
from sqlalchemy import select,text
from backend.db import engine_for,Revision,Mapping,Audit,upsert_revision
from backend.service import HomeService


def main():
    service=HomeService(engine_for());changes=[]
    with service.sessions.begin() as db:
        db.execute(text('SELECT pg_advisory_xact_lock(1019198)'))
        ids=set(db.scalars(select(Revision.entity_id).where(Revision.kind=='project',Revision.source_id=='lh_progress',
            Revision.revision_no==1,Revision.recorded_at>=datetime(2026,10,19,9,26,tzinfo=timezone.utc),
            Revision.recorded_at<datetime(2026,10,19,10,0,tzinfo=timezone.utc))))
        for r in db.scalars(select(Revision).where(Revision.entity_id.in_(ids),Revision.superseded_at.is_(None))):
            m=db.scalar(select(Mapping).where(Mapping.project_id==r.entity_id).with_for_update())
            if not m or m.status!='REVIEW' or m.reviewed_at is not None:continue
            if m.program_id=='UNASSIGNED' and m.policy_id=='UNASSIGNED':continue
            before={k:getattr(m,k) for k in ('policy_id','program_id','status','revision_no','basis')}
            m.policy_id=m.program_id='UNASSIGNED';m.revision_no+=1
            m.basis='2026-10-19 수집 경로 확대 신규 후보 · 일반 프로그램명만으로 정책 자동 상속 보류. 원천 사업/블록 중복·정책 근거 대조 후 연결'
            p=dict(r.payload,policy_candidate_only=True)
            upsert_revision(db,'project','lh_progress',p['source_object_id'],p,'route-scope-review-20261019')
            after={k:getattr(m,k) for k in before}
            db.add(Audit(entity_id=m.project_id,action='MAPPING_SCOPE_HOLD',before=before,after=after))
            changes.append(dict(project_id=m.project_id,name=p['name'],before=before,after=after))
    print(json.dumps(dict(changed=len(changes),changes=changes,approved_values_changed=0),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
