"""Offline before/after ROI evaluation. Labels never enter inference."""
import argparse
import json
from pathlib import Path
from score_suite import matches, metrics

ROOT = Path(__file__).resolve().parents[1]


def compare(evaluation, baseline_root, baseline_report, destination, revision='release-candidate'):
    truth = json.loads((evaluation / 'scoring/ground_truth.json').read_text())
    prior = json.loads(baseline_report.read_text())['latest_runs']
    rows, runs, unlabelled = [], [], []
    directory = evaluation / revision / 'gpt-5.4--gpt-5.4-mini'
    for image in truth['images']:
        name = Path(image['image']).stem + '.json'
        path = directory / name
        recovered=evaluation/'release-reused/gpt-5.4--gpt-5.4-mini'/name
        if revision=='release-candidate' and recovered.exists():path=recovered
        if not path.exists():
            continue
        saved = json.loads(path.read_text())
        after = saved['run']
        before = json.loads((baseline_root / prior[name]['experiment'] / name).read_text())['run']
        runs.append(dict(image=name, run_id=after['id'], selected=len(after['selected']),
                         source_revision=saved['revision'],observation_reused=bool(after.get('observation_reused_from')),
                         calls=len(after['calls']), elapsed_seconds=after.get('elapsed_seconds'),
                         errors=sum(r['status']=='ERROR' for r in after['results']),
                         stopped_reason=after.get('stopped_reason'),
                         source_hashes=saved.get('source_hashes'),
                         pixel_status=after.get('pixel_text',{}).get('status')))
        for case in image['cases']:
            alias=case['rule_id']=='H-04-n' and '기관명' in case['target']
            semantic='D-02-l' if alias else case['rule_id']
            row=dict(image=name,target=case['target'],expected=case['expected_status'],
                     rule_id=case['rule_id'],semantic_rule=semantic,roi=case['roi_normalized'])
            for phase, run in [('before',before),('after',after)]:
                for mode, rid in [('strict',case['rule_id']),('semantic',semantic)]:
                    candidates=[r for r in run['results'] if r['rule_id']==rid
                                and not r.get('supplemental_evidence') and not r.get('reported_issues')]
                    found=[r for r in candidates if matches(r,case['roi_normalized'])]
                    if not found and case.get('kind')=='document_required':
                        found=[r for r in candidates if r.get('document_review') or r.get('evidence_quality')=='DOCUMENT']
                    row[phase+'_'+mode]=next((s for s in ('FAIL','REVIEW','PASS','NOT_APPLICABLE','ERROR','NOT_RUN')
                        if any(r['status']==s for r in found)),'NO_LOCATION')
                    if mode=='semantic':
                        row[phase+'_reasons']=[dict(status=r['status'],reason=r['reason'],rects=r.get('rects'),evidence_ids=r.get('evidence_ids')) for r in found]
            rows.append(row)
        for r in after['results']:
            if r['status']=='FAIL' and not r.get('supplemental_evidence') and not any(
                    r['rule_id'] in (c['rule_id'],'D-02-l' if c['rule_id']=='H-04-n' and '기관명' in c['target'] else c['rule_id'])
                    and matches(r,c['roi_normalized']) for c in image['cases']):
                unlabelled.append(dict(image=name,rule_id=r['rule_id'],reason=r['reason'],rects=r.get('rects')))
    report=dict(images=len(runs),revision=revision,runs=runs,cases=rows,unlabelled_failures=unlabelled,
        metrics={phase+'_'+mode:metrics([dict(expected=r['expected'],predicted=r[phase+'_'+mode]) for r in rows])
                 for phase in ('before','after') for mode in ('strict','semantic')},
        limitations=['Fresh or explicitly recorded reused-observation recovery is identified per run; model variability is not isolated.',
                     'These are regression fixtures, not unseen holdouts.',
                     'Strict metrics require the supplied rule ID. Semantic metrics explicitly map agency-name H-04-n labels to D-02-l.',
                     'ROI/status matching is provisional; explanations need manual review.',
                     'Unlabelled FAIL rows are not automatically errors and are excluded from labelled false-positive rate.',
                     'Character-level truth is unavailable; no character error rate or comprehensive OCR recall is claimed.',
                     'No ground-truth labels or ROIs are supplied to runtime inference.'])
    destination.mkdir(parents=True,exist_ok=True)
    (destination/'comparison.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--evaluation-root',type=Path,default=ROOT/'data/qa-release-20261101')
    p.add_argument('--baseline-root',type=Path,default=ROOT/'data/qa-20261101')
    p.add_argument('--baseline-report',type=Path,default=ROOT/'docs/qa-suite-2026-11-01/report.json')
    p.add_argument('--report-dir',type=Path,default=ROOT/'docs/release-2026-11-01')
    p.add_argument('--revision',default='release-candidate')
    a=p.parse_args();r=compare(a.evaluation_root,a.baseline_root,a.baseline_report,a.report_dir,a.revision)
    print(json.dumps(dict(images=r['images'],metrics=r['metrics']),ensure_ascii=False,indent=2))
