"""Prepare and optionally publish the user-requested 50/50 first scorecard."""
import argparse,csv,json
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from urllib.request import urlopen
from backend.db import engine_for
from backend.service import HomeService,today
from backend.data_integrity import rounds,get_round
from backend.integrity_first import calculate,markdown,html,publish,ID
from backend.policy_delivery import build_delivery


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--publish',action='store_true');args=parser.parse_args()
    s=HomeService(engine_for());folder=s.data_dir/'remediation/first-assessment-20261022';folder.mkdir(parents=True,exist_ok=True)
    save=lambda name,value:(folder/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str))
    old_list=rounds(s)['items']
    if any(r['id']==ID for r in old_list):print('이미 1차 보고서가 발행되어 있습니다.');return
    previous=get_round(s,old_list[0]['id']);save('previous-assessment.json',previous)
    get=lambda route:json.load(urlopen('http://127.0.0.1:8000/poc/home/api/'+route,timeout=180))
    sources=get('sources')['items'];requirements=get('requirements-status');summary=get('source-summary');schema=get('collection-schema')
    save('sources.json',sources);save('requirements.json',requirements);save('source-summary.json',summary)
    model=build_delivery(s,today(),include_portfolio_comparisons=False)
    cohorts={x['id']:x for x in model['portfolio_cohorts']}
    path=s.data_dir/'remediation/r02-current-20261022/official-32.csv'
    rows=list(csv.DictReader(path.open(encoding='utf-8-sig')))
    for row in rows:
        current=cohorts.get(row['home_cohort_id'])
        if current is None or current['units']!=int(row['home_quantity']):raise ValueError('공식 대조의 사업 범위 또는 수량 변경: '+row['official_name'])
    (folder/'official-32.csv').write_bytes(path.read_bytes())
    grouped={r['home_cohort_id']:r for r in rows};equal=[r for r in grouped.values() if int(r['group_difference'])==0]
    items=deepcopy(previous['result']['official_comparison_scorecard']['items'])
    for i in items:
        if i['id']=='O1':i.update(numerator=len(rows),denominator=32)
        if i['id']=='O2':i.update(numerator=len(equal),denominator=len(grouped))
        if i['id']=='O3':i.update(numerator=sum(bool(r['source_url'] and r['source_revision'] and r['home_project_id']) for r in rows),denominator=32)
        i['verified_at']=today().isoformat() if i['id'] in ('O1','O2','O3') else previous['result']['official_comparison_scorecard']['assessed_at']
    docs=schema.get('document_sources',[])
    collection=dict(registered_sources=len(sources),successful_sources=sum(r['status']=='SUCCESS' for r in sources),failed_sources=sum(r['status']=='FAILED' for r in sources),
        api_sources=sum(r.get('data_type')=='API' for r in sources),official_web_sources=sum(r.get('data_type')!='API' for r in sources)+sum(r['authority']=='OFFICIAL' for r in docs),unofficial_web_sources=sum(r['authority']=='NONOFFICIAL' for r in docs),
        extracted_cells=summary['current']['extracted_cells'],linked_records=summary['current']['linked_records'],snapshot_at=summary['generated_at'])
    at=datetime.now(ZoneInfo('Asia/Seoul')).isoformat()
    result=calculate(previous['result'],requirements,sources,collection,items,at)
    result['official_verification']=dict(rows=len(rows),groups=len(grouped),equal_groups=len(equal),official_source_urls=sorted({r['government_appendix_url'] for r in rows}),current_cohort_ids=list(grouped),quantity_changes=0)
    result['evidence_files']=['official-32.csv','sources.json','requirements.json','source-summary.json','previous-assessment.json']
    save('assessment.json',result);(folder/'report.md').write_text(markdown(result));(folder/'report.html').write_text(html(result))
    if args.publish:save('published.json',publish(s,result,{r['id']:r['digest'] for r in old_list}))
    print(json.dumps({'score':result['display_score'],'official_score':result['official_score'],'self_score':result['self_score'],'official_rows_checked':len(rows),'collection':collection,'acquisition':result['acquisition'],'published':args.publish},ensure_ascii=False))
if __name__=='__main__':main()
