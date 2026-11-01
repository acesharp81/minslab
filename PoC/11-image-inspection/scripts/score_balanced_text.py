"""Offline labelled ROI scoring; never imported by inference workers."""
import json,sys
from pathlib import Path
from score_suite import matches,metrics
ROOT=Path(__file__).resolve().parents[1]

def score():
    e=ROOT/'data/qa-20261101';dest=ROOT/'docs/balanced-text-2026-11-01';dest.mkdir(exist_ok=True)
    baseline=json.loads((ROOT/'docs/qa-suite-2026-11-01/report.json').read_text())['latest_runs']
    truth=json.loads((e/'scoring/ground_truth.json').read_text())
    cases=[];runs=[]
    for path in sorted((e/'balanced-v1/gpt-5.4--gpt-5.4-mini').glob('*.json')):
        if path.name.endswith('.progress.json'):continue
        after=json.loads(path.read_text())['run'];prior=baseline[path.name]
        before=json.loads((e/prior['experiment']/path.name).read_text())['run']
        target=next(i for i in truth['images'] if Path(i['image']).stem==path.stem)
        for c in target['cases']:
            alias=c['rule_id']=='H-04-n' and '기관명' in c['target']
            if c['rule_id']!='D-02-l' and not alias:continue
            item=dict(image=path.stem,target=c['target'],expected=c['expected_status'],rule_id=c['rule_id'],semantic_rule='D-02-l' if alias else c['rule_id'])
            for phase,run in [('before',before),('after',after)]:
                rows=[r for r in run['results'] if r['rule_id']==item['semantic_rule'] and not r.get('supplemental_evidence') and not r.get('reported_issues') and matches(r,c['roi_normalized'])]
                item[phase]=next((s for s in ('FAIL','REVIEW','PASS','ERROR','NOT_RUN','NOT_APPLICABLE') if any(r['status']==s for r in rows)),'NO_LOCATION')
                item[phase+'_evidence']=[{k:r.get(k) for k in ('reason','evidence_ids','rects')} for r in rows]
            cases.append(item)
        runs.append(dict(image=path.name,run_id=after['id'],calls=after['calls'],text_coverage=after.get('text_coverage'),errors=sum(r['status']=='ERROR' for r in after['results']),stopped_reason=after.get('stopped_reason'),elapsed_seconds=after.get('elapsed_seconds'),readings=[{k:c.get(k) for k in ('object_id','coverage','text','quality','text_legibility','glyph_checks')} for c in after.get('verification',{}).get('results',[])]))
    report=dict(cases=cases,runs=runs,metrics={p:metrics([dict(expected=c['expected'],predicted=c[p]) for c in cases]) for p in ('before','after')},limitations=['One rerun per image; model variability is not isolated.','Previously inspected images are regression cases, not an unseen holdout.','Semantic agency-name mapping H-04-n to D-02-l is explicit.','No full character-level truth; cannot report character error rate or comprehensive OCR omission rate.','Unlabelled text warnings are not included in false-positive rate.','No answer labels or ROIs enter inference.'])
    (dest/'comparison.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps({'cases':[{k:c[k] for k in ('image','target','expected','before','after')} for c in cases],'metrics':report['metrics'],'runs':len(runs)},ensure_ascii=False,indent=2))
    return report
if __name__=='__main__':score()
