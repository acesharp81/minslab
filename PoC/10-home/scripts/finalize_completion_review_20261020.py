"""Reconcile the completed source review and freeze reproducible checks."""
import json
from collections import Counter
from datetime import date, datetime, timezone
from sqlalchemy import select, or_, func
from backend.db import Revision, engine_for
from backend.service import HomeService
from backend.identity import reconcile_identity_links
from backend.stage_evidence import refresh
from backend.lh_spring_followup import review_key as evidence_key
from backend.project_collection import refresh_links
from backend.evidence_bridge import reconcile
from backend.parcel_identity import reconcile as parcels
from backend.construction_candidates import reconcile as starts
from backend.policy_delivery import build_delivery
from backend.independent_metrics import freeze
from scripts.review_policy_readmission_20261019 import protected, digest
from scripts.build_continuation_review_20261020 import metrics
from scripts.complete_collection_review_20261020 import IDS, slim


def main(refresh_sources=True):
    s=HomeService(engine_for());folder=s.data_dir/'completion-20261020'
    before=protected(s);results={}
    operations=[('identity',lambda:reconcile_identity_links(s)),
        ('stage',lambda:refresh(s,refresh_candidates=True,actor='담당자 대행',reason='2026-10-20 공식 고시·공모 및 API 잔여 수집 검증')),
        ('collection',lambda:refresh_links(s,actor='담당자 대행',reason='2026-10-20 잔여 수집 근거 갱신')),
        ('bridge',lambda:reconcile(s,apply=True,actor='담당자 대행',reason='2026-10-20 잔여 수집 근거 갱신')),
        ('parcels',lambda:parcels(s)),('start_candidates',lambda:starts(s,date(2026,10,20)))]
    for name,fn in operations if refresh_sources else []:
        value=fn();(folder/(name+'-refresh.json')).write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str))
        results[name]={k:v for k,v in value.items() if k not in ('items','proposals','held')}
        print(name,json.dumps(results[name],ensure_ascii=False,default=str),flush=True)
    model=build_delivery(s,date(2026,10,20),include_portfolio_comparisons=False)
    (folder/'model-after.json').write_text(json.dumps(model,ensure_ascii=False,indent=2,default=str))
    projects=s.projects();(folder/'projects-after.json').write_text(json.dumps(projects,ensure_ascii=False,indent=2,default=str))
    # Query candidate names in SQL; never load millions of raw records in memory.
    target=[p for p in projects if p.get('source_id')=='lh_policy_followup']
    terms=sorted({p.get('district') for p in target if p.get('district')})
    with s.sessions() as db:
        raw=db.scalars(select(Revision).where(Revision.superseded_at.is_(None),
            Revision.kind.in_(('permit','general_permit','register')),
            or_(*(Revision.sample_name.contains(t,autoescape=True) for t in terms))).limit(20001)).all()
        if len(raw)>20000:raise ValueError('대조 후보 상한 초과: 구간 분할 필요')
        records=[dict(r.payload,id=r.entity_id,source_id=r.source_id,revision_no=r.revision_no,kind=r.kind) for r in raw]
        counts=dict(db.execute(select(Revision.source_id,func.count()).where(Revision.superseded_at.is_(None),
            Revision.source_id.in_(IDS)).group_by(Revision.source_id)).all())
        began=datetime.fromtimestamp((folder/'protected-before.json').stat().st_mtime,timezone.utc)
        ended=datetime.now(timezone.utc)
        additions=dict(db.execute(select(Revision.source_id,func.count()).where(
            Revision.kind.in_(('general_permit','register','register_recap','permit_dong','permit_parcel')),
            Revision.source_id.in_(IDS),Revision.revision_no==1,
            Revision.recorded_at>=began,Revision.recorded_at<=ended).group_by(Revision.source_id)).all())
    target_checks=[]
    for p in target:
        key=evidence_key(p);matches=[r for r in records if key and evidence_key(r)==key]
        # Reviewed C5/B4 and C1/B5, C4/B7 aliases remain explicit, not fuzzy rules.
        aliases={('수원당수','C5'):['B4'],('수원당수2','B5'):['C1'],('수원당수2','B7'):['C4']}
        alternate=aliases.get((p.get('district'),p.get('block')),[])
        for r in records:
            other=evidence_key(r)
            if other and key and other[:2]==key[:2] and other[2] in alternate and r not in matches:matches.append(r)
        target_checks.append(dict(project_id=p['id'],name=p['name'],units=p.get('planned_units'),matches=[
            {k:r.get(k) for k in ('id','source_id','revision_no','kind','name','units','dates','evidence_url')} for r in matches]))
    (folder/'target-source-recheck.json').write_text(json.dumps(target_checks,ensure_ascii=False,indent=2))
    frozen=freeze(s,'담당자 대행','2026-10-20 공식 고시·공모 및 API 잔여 수집 검증')
    (folder/'independent-snapshot.json').write_text(json.dumps(frozen,ensure_ascii=False,indent=2,default=str))
    after=protected(s);changed=[k for k,v in before.items() if after.get(k)!=v]
    original=json.loads((folder/'protected-before.json').read_text())
    original_changed=[k for k,v in original.items() if after.get(k)!=v]
    ids=[pid for c in model['portfolio_cohorts'] for pid in c['source_ids']]
    old_model=json.loads((folder/'model-before.json').read_text());old={c['id']:c for c in old_model['portfolio_cohorts']}
    manual=lambda c:sorted((x['stage'],x['due_date'],x.get('units')) for x in c['schedules'] if x.get('origin')=='MANUAL')
    schedule_changed=[c['id'] for c in model['portfolio_cohorts'] if c['id'] in old and manual(c)!=manual(old[c['id']])]
    result=dict(protected_existing_records=len(original),changed_existing_keys=original_changed,
        refresh_changed_keys=changed,manual_schedule_changes=schedule_changed,project_records=len(projects),
        confirmed_907=sum(p.get('mapping',{}).get('policy_id')=='POL_2025_0907' and p['mapping']['status']=='CONFIRMED' for p in projects),
        portfolio_cohorts=len(model['portfolio_cohorts']),contributing_source_ids=len(ids),unique_source_ids=len(set(ids)),
        metrics_before=metrics(old_model),metrics_after=metrics(model),
        protected_before=digest(original),protected_after=digest({k:after.get(k) for k in original}),
        scopes={sid:slim(s.latest_collection_stats(sid)) for sid in IDS},raw_current_counts=counts,
        raw_new_records_in_review_window=additions,review_window_start=began.isoformat(),review_window_end=ended.isoformat(),
        independent_snapshot_id=frozen['id'],independent_counts=frozen['result']['counts'])
    (folder/'final-validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,default=str))
    assert not changed and not original_changed and not schedule_changed
    assert len(ids)==len(set(ids))
    print(json.dumps(result,ensure_ascii=False,default=str),flush=True)

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--snapshot-only',action='store_true')
    main(not parser.parse_args().snapshot_only)
