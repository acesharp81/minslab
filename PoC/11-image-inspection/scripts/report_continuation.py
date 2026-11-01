"""Offline report for a bounded continuation. Never imports a model provider."""
import argparse
import csv
import json
import sqlite3
from pathlib import Path
import score_suite

ROOT=Path(__file__).resolve().parents[1]


def report(evaluation,destination):
    score_suite.EVAL=evaluation
    snapshot=json.loads((evaluation/'snapshot.json').read_text())
    experiments={};latest={}
    names={Path(n).stem+'.json' for n in snapshot['images']}
    for directory in sorted(evaluation.glob('*/*')):
        files=[p for p in directory.glob('QA_*.json') if p.name in names]
        if not files:continue
        key=str(directory.relative_to(evaluation))
        experiments[key]=score_suite.score(directory)
        for path in files:
            saved=json.loads(path.read_text());run=saved['run']
            if path.name not in latest or latest[path.name]['created_at']<run['created_at']:
                latest[path.name]=dict(created_at=run['created_at'],experiment=key,run_id=run['id'],
                                      selected=len(run['selected']),errors=sum(r['status']=='ERROR' for r in run['results']))
    cases=[dict(c,experiment=item['experiment']) for name,item in latest.items()
           for c in experiments[item['experiment']]['cases'] if c['image']==name]
    usage={};used={pool:0 for pool in snapshot['limits']}
    with sqlite3.connect(evaluation/'budget.sqlite3') as db:
        db.row_factory=sqlite3.Row
        for event in db.execute('SELECT * FROM reservations'):
            used[event['pool']]+=event['amount']
            if event['state']=='REJECTED':continue
            meter=usage.setdefault(event['model'],dict(attempts=0,input_tokens=0,output_tokens=0,unknown=0,pending=0,failed=0))
            payload=json.loads(event['event']);meter['attempts']+=1
            for field in ('input_tokens','output_tokens'):meter[field]+=payload.get(field,0)
            for field,state in [('unknown','UNKNOWN'),('pending','RESERVED'),('failed','FAILED')]:meter[field]+=event['state']==state
    result=dict(starting_time=snapshot['created_at'],starting_limits=snapshot['limits'],
                task_used_and_reserved=used,task_remaining={p:snapshot['limits'][p]-n for p,n in used.items()},
                usage=usage,images=len(latest),runs=sum(len(e['files']) for e in experiments.values()),
                latest_runs=latest,latest_metrics=score_suite.metrics(cases),latest_cases=cases,experiments=experiments,
                limitations=['Latest-run composite is heterogeneous: reused observations and OCR experiments are identified per image.',
                             'Exact rule/ROI/status matching is provisional; reasons need qualitative audit.',
                             'Missing required references and HUMAN_REQUIRED rules are not silently converted to FAIL/PASS to match labels.',
                             'UNKNOWN usage retains the full reserved bound and is not treated as free.',
                             'Baseline QA_10 had an unscoped fixture reference; subsequent comparisons correct that input-scope defect.',
                             'Answers and answer ROIs are read only by this offline report, never by inference.'])
    destination.mkdir(parents=True,exist_ok=True)
    (destination/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    with (destination/'cases.csv').open('w',newline='') as handle:
        writer=csv.writer(handle);writer.writerow(['experiment','image','rule','target','expected','predicted','reasons'])
        for name,experiment in experiments.items():
            for c in experiment['cases']:writer.writerow([name,c['image'],c['rule_id'],c['target'],c['expected'],c['predicted'],' / '.join(m['reason'] for m in c['matches'])])
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evaluation-root',type=Path,default=ROOT/'data/qa-20261101')
    parser.add_argument('--report-dir',type=Path,default=ROOT/'docs/qa-suite-2026-11-01')
    args=parser.parse_args();result=report(args.evaluation_root,args.report_dir)
    print(json.dumps({k:result[k] for k in ('images','runs','usage','task_remaining','latest_metrics')},ensure_ascii=False,indent=2))
