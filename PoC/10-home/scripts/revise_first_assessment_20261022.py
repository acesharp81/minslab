"""Recompute documented candidate progress credit without changing official match verdicts."""
import argparse,csv,hashlib,json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from backend.service import HomeService
from backend.db import engine_for
from backend.data_integrity import get_round,rounds
from backend.integrity_first import ID,revise_scoring,publish,markdown,html


def main():
    p=argparse.ArgumentParser();p.add_argument('--evidence',type=Path,required=True);p.add_argument('--publish',action='store_true');args=p.parse_args()
    service=HomeService(engine_for());old=get_round(service,ID)['result']
    if old['rubric_version'].endswith('REV2'):print('REV2 already published');return
    facts={}
    for key,name,count,units in [('sale','A01_public_sale_partial.csv',24,14451),('rental','rental_partial_notices_updated.csv',18,4461)]:
        path=args.evidence/name;rows=list(csv.DictReader(path.open(encoding='utf-8-sig')))
        total=sum(int(r['units']) for r in rows)
        if len(rows)!=count or total!=units or len({r['home_id'] for r in rows})!=count or not all(r['evidence_url'].startswith('https://') for r in rows):raise ValueError('명세 변경 또는 검증 불가: '+name)
        facts[key]=dict(units=total,rows=count,evidence_file=name,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),home_ids=[r['home_id'] for r in rows])
    result=revise_scoring(old,facts,datetime.now(ZoneInfo('Asia/Seoul')).isoformat())
    folder=service.data_dir/'remediation/first-assessment-revision-20261022';folder.mkdir(parents=True,exist_ok=True)
    for name in ('A01_public_sale_partial.csv','rental_partial_notices_updated.csv','A01_cross_source_dedup.csv'):(folder/name).write_bytes((args.evidence/name).read_bytes())
    (folder/'assessment.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    (folder/'report.md').write_text(markdown(result));(folder/'report.html').write_text(html(result))
    if args.publish:publish(service,result,{r['id']:r['digest'] for r in rounds(service)['items']})
    print(json.dumps(dict(score=result['display_score'],official=result['official_score'],self=result['self_score'],published=args.publish),ensure_ascii=False))
if __name__=='__main__':main()
