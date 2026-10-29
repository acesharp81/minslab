"""Evaluate human-labelled JSONL. Never mistake mock outputs for model accuracy.
Each line: {rule_id, expected, predicted, expected_cells:[], predicted_cells:[]}.
"""
import argparse,json
from collections import defaultdict
from pathlib import Path

def metrics(rows):
    n=len(rows);tp=sum(r['expected']=='FAIL' and r['predicted']=='FAIL' for r in rows)
    fp=sum(r['expected']!='FAIL' and r['predicted']=='FAIL' for r in rows)
    # REVIEW/ERROR/NOT_RUN are not correct detections; counted in missed FAIL and separately as abstentions.
    fn=sum(r['expected']=='FAIL' and r['predicted']!='FAIL' for r in rows)
    tn=sum(r['expected']=='PASS' and r['predicted']=='PASS' for r in rows)
    loc=[];over=[]
    for r in rows:
        a,b=set(r.get('expected_cells',[])),set(r.get('predicted_cells',[]))
        if a|b:loc.append(len(a&b)/len(a|b))
        if b:over.append(len(b-a)/len(b))
    na=[r for r in rows if r['expected']=='NOT_APPLICABLE']
    return dict(samples=n,tp=tp,fp=fp,fn=fn,tn=tn,precision=tp/(tp+fp) if tp+fp else None,
                recall=tp/(tp+fn) if tp+fn else None,false_positive_rate=fp/sum(r['expected']!='FAIL' for r in rows) if any(r['expected']!='FAIL' for r in rows) else None,
                false_negative_rate=fn/(tp+fn) if tp+fn else None,review_rate=sum(r['predicted']=='REVIEW' for r in rows)/n if n else None,
                error_rate=sum(r['predicted'] in ('ERROR','NOT_RUN') for r in rows)/n if n else None,
                na_accuracy=sum(r['predicted']=='NOT_APPLICABLE' for r in na)/len(na) if na else None,
                mean_cell_iou=sum(loc)/len(loc) if loc else None,overmark_rate=sum(over)/len(over) if over else None)

def main():
    p=argparse.ArgumentParser();p.add_argument('labels',type=Path);args=p.parse_args()
    rows=[json.loads(l) for l in args.labels.read_text().splitlines() if l.strip()];groups=defaultdict(list)
    for r in rows:groups[r['rule_id']].append(r)
    print(json.dumps({'notice':'입력 라벨의 품질·표본 대표성은 별도 검증 필요','overall':metrics(rows),'rules':{k:metrics(v) for k,v in groups.items()}},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
