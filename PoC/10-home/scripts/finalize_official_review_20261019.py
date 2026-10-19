"""Bounded final review: source collection, six explicit plan admissions, immutable audit."""
import argparse, json, hashlib
from pathlib import Path
from backend.db import engine_for
from backend.service import HomeService
from backend.sources import SOURCES
from backend.lh_spring_followup import admit_reviewed
from scripts.review_policy_readmission_20261019 import protected, digest


def main(apply=False, collect=False):
    s=HomeService(engine_for());folder=s.data_dir/'final-review-20261019';folder.mkdir(exist_ok=True)
    before=protected(s)
    baseline=folder/'protected-before.json'
    if not baseline.exists():baseline.write_text(json.dumps(before,ensure_ascii=False,indent=2))
    if collect:
        result=s.collect_one(next(r for r in SOURCES if r['id']=='lh_policy_followup'))
        (folder/'collection.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,default=str))
        print('COLLECTION',json.dumps(result,ensure_ascii=False,default=str))
    result=admit_reviewed(s,apply)
    after=protected(s);changed=[k for k,v in before.items() if after.get(k)!=v]
    result.update(protected_existing_records=len(before),protected_before=digest(before),protected_after=digest({k:after.get(k) for k in before}),changed_existing_keys=changed)
    dest=folder/('admission-applied.json' if apply else 'admission-plan.json')
    if dest.exists() and all(r['result']=='existing_preserved' for r in result['projects']):dest=folder/'admission-idempotence.json'
    dest.write_text(json.dumps(result,ensure_ascii=False,indent=2))
    projects=s.projects();(folder/'projects-final.json').write_text(json.dumps(projects,ensure_ascii=False,indent=2,default=str))
    print(json.dumps(dict(file=str(dest),rows=len(result['projects']),units=sum(r['units'] for r in result['projects']),results=[r['result'] for r in result['projects']],protected_unchanged=not changed),ensure_ascii=False))
    if changed:raise ValueError('기존 승인기록 변경: '+str(changed))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--apply',action='store_true');p.add_argument('--collect',action='store_true');a=p.parse_args();main(a.apply,a.collect)
