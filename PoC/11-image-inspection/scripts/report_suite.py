"""Summarize blind QA runs and the independent task budget; no inference calls."""
import csv,json,sqlite3,sys
from pathlib import Path
from score_suite import EVAL,ROOT,score,metrics


def report():
    destination=ROOT/'docs/qa-suite-2026-10-31';destination.mkdir(exist_ok=True)
    experiments={}
    for directory in sorted(EVAL.glob('*/*')):
        if directory.is_dir() and any(p for p in directory.glob('QA_*.json') if not p.name.endswith('.progress.json')):
            experiments[str(directory.relative_to(EVAL))]=score(directory)
    with sqlite3.connect(EVAL/'budget.sqlite3') as db:
        db.row_factory=sqlite3.Row;events=[dict(r) for r in db.execute('select * from reservations')]
    usage={}
    for event in events:
        if event['state']=='REJECTED':continue
        meter=usage.setdefault(event['model'],dict(attempts=0,completed=0,failed=0,pending=0,input_tokens=0,output_tokens=0,accounting_cost_usd=0,unknown=0,pool=event['pool']))
        meter['attempts']+=1
        payload=json.loads(event['event'])
        meter['completed']+=event['state']=='COMPLETED';meter['failed']+=event['state']=='FAILED';meter['pending']+=event['state']=='RESERVED';meter['unknown']+=event['state']=='UNKNOWN'
        meter['input_tokens']+=payload.get('input_tokens',0);meter['output_tokens']+=payload.get('output_tokens',0);meter['accounting_cost_usd']+=payload.get('cost_usd') or 0
    snapshot=json.loads((EVAL/'snapshot.json').read_text())
    cap_used={pool:sum(e['amount'] for e in events if e['pool']==pool) for pool in snapshot['limits']}
    cap_remaining={p:None if n is None else round(n-cap_used[p],6) for p,n in snapshot['limits'].items()}
    baseline=experiments['baseline/gpt-5.4-mini--gpt-5.4-mini']
    comparison_images={'QA_02_hands.json','QA_03_ocr_readability.json','QA_07_culture_food.json','QA_08_all_pass.json','QA_10_emblem.json'}
    paired_baseline=metrics([c for c in baseline['cases'] if c['image'] in comparison_images])
    result=dict(dataset=dict(images=14,cases=61,parents=25,excluded='exploratory/*; answer_key_previews/*',input_source='docs/테스트용.zip',ground_truth_used_by_inference=False),
        starting_allowances=snapshot['limits'],starting_time=snapshot['created_at'],usage=usage,task_cap_remaining=cap_remaining,
        paired_mini_baseline=paired_baseline,experiments=experiments,
        audit_notes=[
            'baseline mini QA01 H04h: lower-left ROI was scored FAIL but the reason describes the upper-right trigram. Not a correct localized finding.',
            'baseline mini QA05 D02m: bar-length ROI matched a total-amount explanation. Not correct bar-length detection.',
            'baseline mini QA09 D02l: typo ROI matched year mismatch/crop clipping. Not correct typo detection.',
            'baseline mini QA01 H04n: agency typo was found, but the current action concerns country names. Rule mapping mismatch.',
            'baseline 5.4 QA03 D02l: agency typo ROI matched crop-edge glyph clipping. Before-fix detection was not valid spelling evidence.',
            'baseline 5.4 QA07 D02l: typo ROI matched adjacent blurred text. Do not count it as correct spelling detection.',
            'PASS/FAIL does not override HUMAN_REQUIRED or unavailable policy/culture evidence in the current user-managed rules.',
            'Per-model comparisons use small, different subsets; they do not establish a universal model ranking.',
            'No manual annotation, expected status or truth ROI was supplied to inference. Author MASTER_COPY and fictional reference drawing were allowed input.',
        ])
    (destination/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    with (destination/'cases.csv').open('w',newline='') as f:
        writer=csv.writer(f);writer.writerow(['experiment','image','rule_id','target','expected','predicted','match_mode','review_policy','reasons'])
        for name,experiment in experiments.items():
            for c in experiment['cases']:writer.writerow([name,*[c.get(k) for k in ['image','rule_id','target','expected','predicted','match_mode','review_policy']], ' / '.join(m['reason'] for m in c['matches'])])
    print(json.dumps(dict(experiments=len(experiments),runs=sum(len(e['files']) for e in experiments.values()),usage=usage,task_cap_remaining=cap_remaining,paired_mini_baseline=paired_baseline),ensure_ascii=False,indent=2))
    return result

if __name__=='__main__':report()
