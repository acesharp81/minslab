"""Save bounded production checks for the R01 scorecard; never alter approvals."""
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import hashlib
import sys
from sqlalchemy import select, text
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.db import engine_for, Mapping, Audit, now
from backend.service import HomeService, today
from backend.policy_delivery import build_delivery
from backend.evidence_bridge import supply_notices
from backend.independent_metrics import get_snapshot
from backend.collection_jobs import enqueue, run_next


def main():
    s=HomeService(engine_for(),'/app/data');folder=s.data_dir/'remediation/r01'
    baseline=json.loads((folder/'selected-before.json').read_text())
    before={r['project_id']:r for r in baseline['approved_mappings']}
    with s.sessions() as db:
        after={r.project_id:dict(id=r.id,project_id=r.project_id,policy_id=r.policy_id,program_id=r.program_id,status=r.status,revision_no=r.revision_no) for r in db.scalars(select(Mapping))}
    assert all(after.get(key)==value for key,value in before.items())
    notices=supply_notices(s,today())
    delivery=build_delivery(s,today(),include_portfolio_comparisons=False)
    dashboard=s.supply_dashboard(analysis_year=2026,measure='SUPPLY',policy_id='POL_2025_0907')
    cohorts={c['id']:c for c in delivery['portfolio_cohorts']};mapitems={r['id']:r for r in dashboard['items']}
    examples=[]
    for pid,expected in [('PRO_c96377d9ec7e60cf32e1ccdb',381),('PRO_12d91632b8ca640e1505869f',309)]:
        notice=notices[pid];mapped=mapitems[pid]['map_quantities']['current_notice_units']
        supplied=[e for e in cohorts[pid]['events'] if e['stage']=='SUPPLY']
        assert notice['units']==mapped==expected
        assert any(e.get('units')==expected for e in supplied)
        examples.append(dict(project_id=pid,name=cohorts[pid]['name'],expected=expected,stored_notice_units=notice['units'],
                             map_notice_units=mapped,policy_supply_units=[e.get('units') for e in supplied],
                             policy_inferred=[bool(e.get('inferred')) for e in supplied],
                             note='기존 담당자 추정 입력은 원래 표식을 보존. 독립 사건 집계는 별도 원천 직접 근거만 사용.'))
    # Exercise the real database queue and source lock with an inexpensive
    # already-collected SH derivation. No fake network result is injected.
    with ThreadPoolExecutor(max_workers=6) as pool:
        reservations=list(pool.map(lambda _:enqueue(s,'sh_inventory',force=True),range(6)))
    assert len([r for r in reservations if r])==1
    job=next(r for r in reservations if r)
    key=int.from_bytes(hashlib.sha256(b'home-source:sh_inventory').digest()[:8],'big',signed=True)
    from backend.sources import SOURCES
    with s.engine.connect() as lock:
        lock.execute(text('SELECT pg_advisory_lock(:key)'),dict(key=key))
        try:
            assert s.collect_one(next(r for r in SOURCES if r['id']=='sh_inventory'))['status']=='BUSY'
        finally:lock.execute(text('SELECT pg_advisory_unlock(:key)'),dict(key=key))
    steps=[]
    if job:
        for _ in range(3):
            step=run_next(s,'LATEST');steps.append(step)
            if not step or step['status'] not in ('ADVANCED','SUCCESS'):break
        assert steps[-1]['status']=='SUCCESS'
    remediation=json.loads((folder/'remediation-result.json').read_text())
    fixed=get_snapshot(s,remediation['after_snapshot_id'])
    assert all(e['evidence_origin'] in ('PRIMARY_OPERATION','PRIMARY_NOTICE') for e in fixed['result']['selected_events'])
    with s.sessions() as db:
        audits=db.scalars(select(Audit).where(Audit.action.in_(('COLLECTION_REPAIR','REFERENCE_CANDIDATE','REFERENCE_PROMOTED','REFERENCE_DUPLICATE_HELD')))).all()
        attribution=[a for a in audits if a.after.get('reason')=='공식 발표 후 도출된 보완 사항 적용' and a.after.get('actor')=='김민']
    assert attribution
    result=dict(verified_at=now().isoformat(),approved_mappings_preserved=len(before),approved_mappings_changed=0,
                representative_supply_checks=examples,live_queue_steps=steps,independent_snapshot_id=fixed['id'],
                independent_counts=fixed['result']['counts'],attributed_audit_rows=len(attribution),
                concurrent_reservations=6,created_jobs=1,source_lock_conflict_preserved=True,
                benchmark_promotions=0,platform_population_status='UNVERIFIED',status='PASS')
    (folder/'operational-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    (folder/'sources-after.json').write_text(json.dumps(dict(items=s.sources()),ensure_ascii=False))
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
