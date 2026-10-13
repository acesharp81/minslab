"""Run in the HOME container: python -m scripts.collect [--source lh_sale | --samples]."""
import argparse
import json

from backend.db import engine_for
from backend.service import HomeService

parser = argparse.ArgumentParser()
parser.add_argument("--source")
parser.add_argument("--samples", action="store_true", help="Collect bounded API samples, separately from projects")
parser.add_argument("--history",action="store_true",help="Backfill policy origins and all available dated LH reports")
parser.add_argument('--expand-building',action='store_true',help='Continue statutory-area permit/register collection')
parser.add_argument('--expand-building-details',action='store_true',help='Continue Housing HUB dong/parcel detail collection')
parser.add_argument('--rounds',type=int,default=1,help='Number of resumable area batches (1~1000)')
args = parser.parse_args()
service = HomeService(engine_for())
if args.expand_building_details:
    if args.samples or args.source or args.history or args.expand_building or not 1<=args.rounds<=1000:
        parser.error('상세 확대 수집은 --rounds 1~1000과 함께 사용하세요')
    if not service.rows('legal_dong'):
        print(json.dumps(service.collect_all('legal_dongs'),ensure_ascii=False),flush=True)
    for iteration in range(args.rounds):
        meta=service.latest_collection_stats('building_hub_details')
        if meta.get('complete_scope'):break
        result=service.collect_all('building_hub_details')
        print(json.dumps(dict(round=iteration+1,result=result),ensure_ascii=False),flush=True)
        if result.get('status')=='BUSY' or any(r.get('status')=='FAILED' for r in result.get('results',[])):
            raise SystemExit('상세 수집 중단: 정상 배치 보존. 원천 응답·호출량 확인 후 재실행하세요')
    result={'status':'FINISHED','coverage':{k:v for k,v in service.latest_collection_stats('building_hub_details').items() if k.startswith('scope_')}}
elif args.expand_building:
    if args.samples or args.source or args.history or not 1<=args.rounds<=1000:parser.error('확대 수집은 --rounds 1~1000과 함께 사용하세요')
    if not service.rows('legal_dong'):
        print(json.dumps(service.collect_all('legal_dongs'),ensure_ascii=False),flush=True)
    for iteration in range(args.rounds):
        results=[]
        for sid in ('building_hub','building_register'):
            meta=service.latest_collection_stats(sid)
            if meta.get('complete_scope'):continue
            item=service.collect_all(sid);results.append(item)
            print(json.dumps(dict(round=iteration+1,source_id=sid,result=item),ensure_ascii=False),flush=True)
            if item.get('status')=='BUSY' or any(r.get('status')=='FAILED' for r in item.get('results',[])):
                raise SystemExit('수집 중단: 정상 배치 보존. 원천 응답·호출량 확인 후 재실행하세요')
        if not results:break
    result={'status':'FINISHED','coverage':{sid:{k:v for k,v in service.latest_collection_stats(sid).items() if k.startswith('scope_')} for sid in ('building_hub','building_register')}}
elif args.history:
    if args.samples or args.source:parser.error('--history는 --samples/--source와 함께 사용하지 않습니다')
    result={'status':'FINISHED','collections':[service.collect_all(source) for source in ('policy_history','lh_history')]}
else:
    result = service.collect_samples(args.source) if args.samples else service.collect_all(args.source)
print(json.dumps(result, ensure_ascii=False, indent=2))
