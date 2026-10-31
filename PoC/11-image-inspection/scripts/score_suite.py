"""Offline evaluation only. Never constructs a provider or passes labels to inference."""
import argparse,json
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
EVAL=ROOT/'data/qa-20261031'


def area(r):return max(0,r[2]-r[0])*max(0,r[3]-r[1])


def matches(pred,roi):
    # Half-cell boundary tolerance is too permissive on adjacent labels. Require
    # actual overlap plus center containment or >=50% of the predicted cell.
    for r in pred.get('rects',[]):
        overlap=max(0,min(r[2],roi[2])-max(r[0],roi[0]))*max(0,min(r[3],roi[3])-max(r[1],roi[1]))
        center=roi[0]<=(r[0]+r[2])/2<=roi[2] and roi[1]<=(r[1]+r[3])/2<=roi[3]
        if area(r)<=4*area(roi) and overlap>0 and (center or overlap/max(area(r),1e-10)>=.5):return True
    return False


def metrics(rows):
    faults=[x for x in rows if x['expected']=='FAIL'];normal=[x for x in rows if x['expected']=='PASS'];reviews=[x for x in rows if x['expected']=='REVIEW']
    rate=lambda n,d:round(n/d,4) if d else None
    return dict(cases=len(rows),expected=dict(Counter(r['expected'] for r in rows)),predicted=dict(Counter(r['predicted'] for r in rows)),
        fail_recall=rate(sum(x['predicted']=='FAIL' for x in faults),len(faults)),
        false_positive_rate=rate(sum(x['predicted']=='FAIL' for x in normal),len(normal)),
        normal_pass_rate=rate(sum(x['predicted']=='PASS' for x in normal),len(normal)),
        required_review_accuracy=rate(sum(x['predicted']=='REVIEW' for x in reviews),len(reviews)),
        review_rate=rate(sum(x['predicted']=='REVIEW' for x in rows),len(rows)),
        error_or_omission_rate=rate(sum(x['predicted'] in ('ERROR','NOT_RUN','NO_LOCATION') for x in rows),len(rows)))


def score(directory):
    truth=json.loads((EVAL/'scoring/ground_truth.json').read_text());rows=[];extra=[];usage={};files=[];runs=[]
    for image in truth['images']:
        path=directory/(Path(image['image']).stem+'.json')
        if not path.exists():continue
        saved=json.loads(path.read_text());run=saved['run'];files.append(path.name)
        runs.append(dict(image=path.name,selected=len(run['selected']),completed_actions=run['progress'],analysis_errors=run.get('analysis',[]),
            budget_deferred=[d for d in run.get('verification',{}).get('deferred',[]) if '예산' in d['reason'] or '평가 시작 시점' in d['reason']],
            stopped_reason=run.get('stopped_reason'),elapsed_seconds=run.get('elapsed_seconds'),reused_observation=run.get('observation_reused_from'),
            inherited_analysis=run.get('analysis_reused_from'),error_rows=sum(p['status']=='ERROR' for p in run['results']),evaluation_repairs=run.get('evaluation_repairs',[])))
        preds=[p for p in run['results'] if not p.get('reported_issues') and not p.get('supplemental_evidence')]
        for case in image['cases']:
            matched=[p for p in preds if p['rule_id']==case['rule_id'] and matches(p,case['roi_normalized'])]
            match_mode='ROI'
            if not matched and case.get('kind')=='document_required':
                matched=[p for p in preds if p['rule_id']==case['rule_id'] and (p.get('document_review') or p.get('evidence_quality')=='DOCUMENT')]
                if matched:match_mode='DOCUMENT'
            status=next((s for s in ('FAIL','REVIEW','PASS','NOT_APPLICABLE','ERROR','NOT_RUN') if any(p['status']==s for p in matched)),'NO_LOCATION')
            if not matched and any(p['rule_id']==case['rule_id'] and p['status']=='ERROR' for p in preds):status='ERROR'
            text_case=case['rule_id'] in ('D-02-l','H-04-n') or case.get('kind')=='readability'
            observed=[]
            if text_case:
                for o in run.get('observation',{}).get('objects',[]):
                    if not (o.get('text') or o.get('text_legibility') in ('CLEAR','DEGRADED','UNREADABLE')):continue
                    rects=[]
                    for cell in o.get('cell_ids',[]):
                        y,x=int(cell[1:3])-1,int(cell[4:6])-1;rects.append([x/12,y/12,(x+1)/12,(y+1)/12])
                    if matches(dict(rects=o.get('rects') or rects),case['roi_normalized']):observed.append(o)
            step=next((s for s in run['rule_pack']['steps'] if s['rule_id']==case['rule_id']),{})
            rows.append(dict(image=path.name,rule_id=case['rule_id'],target=case['target'],expected=case['expected_status'],predicted=status,match_mode=match_mode,
                review_policy=step.get('review_policy'),text_case=text_case,detected_text=bool(observed) if text_case else None,
                readable_text=any(o.get('text') and '[판독불가]' not in o['text'] and o.get('text_legibility')!='UNREADABLE' for o in observed) if text_case else None,
                matches=[dict(status=p['status'],reason=p['reason'],rects=p.get('rects'),evidence_ids=p.get('evidence_ids'),error_type=p.get('error_type')) for p in matched]))
        for p in preds:
            if p['status']=='FAIL' and not any(p['rule_id']==c['rule_id'] and matches(p,c['roi_normalized']) for c in image['cases']):extra.append(dict(image=path.name,rule_id=p['rule_id'],reason=p['reason'],rects=p.get('rects')))
        for c in run['calls']:
            m=c.get('requested_model',c.get('model'));u=usage.setdefault(m,dict(calls=0,input_tokens=0,output_tokens=0,cost_usd=0,unknown=0));u['calls']+=1
            for key in ('input_tokens','output_tokens'):u[key]+=c.get('usage',{}).get(key,0)
            u['cost_usd']+=c.get('cost_usd') or 0;u['unknown']+=int(bool(c.get('usage_unknown')))
    texts=[r for r in rows if r['text_case']]
    text_metrics=dict(labelled_text_cases=len(texts),detection_omissions=sum(not r['detected_text'] for r in texts),unreadable_or_absent=sum(not r['readable_text'] for r in texts))
    text_metrics['detection_omission_rate']=round(text_metrics['detection_omissions']/len(texts),4) if texts else None
    report=dict(scope='14 deterministic images / 61 labelled cases; exploratory excluded',files=files,runs=runs,metrics=metrics(rows),text_metrics=text_metrics,cases=rows,unlabelled_failures=extra,usage=usage,
        limitations=['REVIEW is not FAIL detection.','Rule/status/ROI matches are provisional: a wrong explanation can still overlap a labelled box; qualitative audit is required.','Case matching requires the exact provided rule ID and ROI; document_required cases allow nonvisual document reviews.','Text coverage is labelled-region detection, not character accuracy or all-text OCR recall.','H-04-n agency-name cases differ from the current national-name-only rule; reported separately during adjudication.','Unlabelled FAIL is not automatically a false positive.','No user-reported or hand-positioned supplemental findings count toward model accuracy.'])
    directory.mkdir(parents=True,exist_ok=True);(directory/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);a=p.parse_args();r=score(a.directory)
    print(json.dumps({k:v for k,v in r.items() if k not in ('cases','unlabelled_failures')},ensure_ascii=False,indent=2))
