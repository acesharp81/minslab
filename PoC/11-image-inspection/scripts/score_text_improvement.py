"""Offline paired report. Answer labels/ROIs never enter inference.

The explicit agency-name alias corrects a known semantic mismatch in the supplied
answer key; raw exact-rule scores are also retained. No status is changed.
"""
import argparse,json
from pathlib import Path
from score_suite import matches,metrics
ROOT=Path(__file__).resolve().parents[1]
IMAGES={'development':['QA_03_ocr_readability','QA_07_culture_food'],
        'validation':['QA_06_privacy_signs','QA_08_all_pass','QA_10_emblem']}


def score(evaluation,destination):
    baseline=json.loads((ROOT/'docs/qa-suite-2026-11-01/report.json').read_text())['latest_runs']
    truth=json.loads((evaluation/'scoring/ground_truth.json').read_text())
    cases=[];runs=[]
    for split,names in IMAGES.items():
        for name in names:
            revision='glyph-validation' if split=='validation' else 'glyph-isolated-scale3' if name=='QA_07_culture_food' else 'glyph-v1'
            after_path=evaluation/revision/'gpt-5.4--gpt-5.4-mini'/(name+'.json')
            if not after_path.exists():continue
            prior_path=evaluation/baseline[name+'.json']['experiment']/(name+'.json')
            before=json.loads(prior_path.read_text())['run'];after=json.loads(after_path.read_text())['run']
            image=next(i for i in truth['images'] if Path(i['image']).stem==name)
            for c in image['cases']:
                alias=c['rule_id']=='H-04-n' and '기관명' in c['target']
                if c['rule_id']!='D-02-l' and not alias:continue
                row=dict(image=name,split=split,target=c['target'],expected=c['expected_status'],original_rule=c['rule_id'],
                         semantic_rule='D-02-l' if alias else c['rule_id'],rule_mapping_reason='원 답안의 기관명 항목은 현재 국가명·국호 규칙과 의미가 달라 일반 오탈자 규칙으로 별도 집계' if alias else '')
                for phase,run in [('before',before),('after',after)]:
                    candidates=[r for r in run['results'] if not r.get('supplemental_evidence') and not r.get('reported_issues') and matches(r,c['roi_normalized'])]
                    for mode,rid in [('exact',c['rule_id']),('semantic',row['semantic_rule'])]:
                        found=[r for r in candidates if r['rule_id']==rid]
                        status=next((s for s in ('FAIL','REVIEW','PASS','ERROR','NOT_RUN','NOT_APPLICABLE') if any(r['status']==s for r in found)),'NO_LOCATION')
                        row[phase+'_'+mode]=dict(predicted=status,matches=[{k:r.get(k) for k in ['status','reason','rects','evidence_ids','error_type']} for r in found])
                cases.append(row)
            audit=after.get('glyph_audit',{})
            runs.append(dict(image=name,split=split,revision=revision,before_run=before['id'],after_run=after['id'],audit_status=audit.get('status'),
                deferred=audit.get('deferred_count'),new_calls=after['calls'],elapsed_seconds=after.get('elapsed_seconds'),
                region_readings=[{k:r.get(k) for k in ['id','rect','detector_text','assessment','error']} for r in audit.get('regions',[])],
                errors=[r for r in after['results'] if r['status']=='ERROR'],
                localization={s:sum(r.get('location_evidence',{}).get('status')==s for r in after['results']) for s in ('VERIFIED_REGION','UNRESOLVED')}))
    summaries={}
    for split in ['development','validation','all']:
        summaries[split]={}
        selected=[c for c in cases if split=='all' or c['split']==split]
        for phase in ('before','after'):
            for mode in ('exact','semantic'):
                summaries[split][phase+'_'+mode]=metrics([dict(expected=c['expected'],predicted=c[phase+'_'+mode]['predicted']) for c in selected])
    output=dict(cases=cases,metrics=summaries,runs=runs,limitations=[
        'Saved source readings and non-text results are reused; only two text rules are reanalyzed.',
        'Validation images were inspected in an earlier evaluation; they are withheld from this implementation iteration, not a never-seen benchmark.',
        'One run per condition cannot separate model sampling variation from implementation effects.',
        'Recall and false-positive rates cover labelled text ROIs only, not all words or unlabelled warnings.',
        'OCR omission is approximated by labelled-region coverage; no complete character-level truth is available.',
        'The new audit returns no PASS independently. Transcription agreement alone cannot certify source quality.'])
    destination.mkdir(parents=True,exist_ok=True)
    (destination/'text-comparison.json').write_text(json.dumps(output,ensure_ascii=False,indent=2))
    print(json.dumps({'images':len(runs),'metrics':summaries},ensure_ascii=False,indent=2))
    return output

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--evaluation-root',type=Path,default=ROOT/'data/qa-20261101');p.add_argument('--report-dir',type=Path,default=ROOT/'docs/glyph-improvement-2026-11-01');a=p.parse_args();score(a.evaluation_root,a.report_dir)
