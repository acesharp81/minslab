"""Audit all current 9.7 management timelines and correct only explicitly estimated dates."""
import argparse,json
from copy import deepcopy
from datetime import datetime
from zoneinfo import ZoneInfo
from sqlalchemy import select,text
from backend.db import engine_for,Revision,Audit,entity_id,upsert_revision
from backend.service import HomeService
from backend.project_collection import collection_matrix
from backend.stage_chronology import constrain_estimated_dates,EDGES


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    s=HomeService(engine_for());matrix=collection_matrix(s,policy_id='POL_2025_0907',include_link_history=False)
    profiles={r['project_id']:r for r in s.rows('project_profile')};schedules={(r['project_id'],r['stage']):r for r in s.rows('execution_schedule') if r.get('status')!='RELEASED'}
    updates=[];conflicts=[];stamp=datetime.now(ZoneInfo('Asia/Seoul')).isoformat()
    with s.sessions() as db:
        for p in matrix['items']:
            for kind,date_key in [('target','due_date'),('measurement','event_date')]:
                display={r['milestone']:deepcopy(r) for c in p['cells'].values() for r in c['management'][kind] if r['milestone']!='POLICY'}
                for r in display.values():r[date_key]=r.get('date')
                fixes=constrain_estimated_dates(display,date_key)
                for a,b in EDGES:
                    x,y=display.get(a,{}).get(date_key),display.get(b,{}).get(date_key)
                    if x and y and x>y:conflicts.append(dict(project_id=p['id'],name=p['name'],kind=kind,before=a,before_date=x,after=b,after_date=y,action='PRESERVE_SOURCE_CONFLICT'))
                if not fixes:continue
                by_stage={f['stage'] for f in fixes}
                records=[(None,profiles.get(p['id']))] if kind=='measurement' else [(stage,schedules.get((p['id'],stage))) for stage in by_stage]
                for stage,stored in records:
                    if not stored:raise ValueError('관리 원본 없음: '+p['id'])
                    row=db.get(Revision,stored['source_revision_id']);payload=deepcopy(row.payload)
                    relevant=fixes if stage is None else [f for f in fixes if f['stage']==stage]
                    for f in relevant:
                        target=payload['progress'][f['stage']] if kind=='measurement' else payload
                        if target[date_key]!=f['before']:raise ValueError('원본 날짜와 화면 불일치')
                        target.update({date_key:f['after'],'inferred':True})
                        target.setdefault('field_provenance',{})[date_key]=display[f['stage']]['field_provenance'][date_key]
                        target['changed_at']=stamp
                    payload.setdefault('sequence_date_repairs',[]).append(dict(at=stamp,actor='담당자 대행',reason='사용자 요청: 추정일 선후관계 보완',changes=relevant))
                    key=p['id'] if kind=='measurement' else p['id']+':'+stage
                    if entity_id(row.kind,row.source_id,key)!=row.entity_id:raise ValueError('저장 키 확인 필요')
                    updates.append(dict(id=row.id,entity_id=row.entity_id,kind=row.kind,source_id=row.source_id,key=key,before=row.payload,after=payload,project_name=p['name'],changes=relevant))
    report=dict(checked_projects=len(matrix['items']),updates=updates,preserved_source_conflicts=conflicts,applied=args.apply)
    folder=s.data_dir/'remediation/sequence-repair-20261022';folder.mkdir(parents=True,exist_ok=True)
    (folder/(('apply' if args.apply else 'preview')+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2))
    if args.apply and updates:
        with s.sessions.begin() as db:
            db.execute(text('SELECT pg_advisory_xact_lock(9701022)'))
            for u in updates:
                old=db.scalar(select(Revision).where(Revision.entity_id==u['entity_id'],Revision.superseded_at.is_(None)).with_for_update())
                if old.id!=u['id']:raise ValueError('검토 후 원본 변경')
                new,_=upsert_revision(db,u['kind'],u['source_id'],u['key'],u['after'],'sequence-repair-20261022')
                db.add(Audit(entity_id=u['entity_id'],action='ESTIMATED_SEQUENCE_REPAIR',before={'revision_id':old.id},after={'revision_id':new.id,'changes':u['changes'],'actor':'담당자 대행'}))
    print(json.dumps(dict(checked_projects=len(matrix['items']),revised_records=len(updates),revised_dates=sum(len(u['changes']) for u in updates),preserved_source_conflicts=len(conflicts),applied=args.apply),ensure_ascii=False))
if __name__=='__main__':main()
