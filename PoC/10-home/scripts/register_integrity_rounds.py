"""Register prepared, reviewable reports as append-only assessment rounds.

Default imports the preserved baseline and authorized R01. Future rounds may
use --id/--sequence/--parent/--json/--html with the same forty-item rubric.
"""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.db import engine_for
from backend.service import HomeService
from backend.data_integrity import save_round


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--id');parser.add_argument('--sequence',type=int);parser.add_argument('--parent')
    parser.add_argument('--json',type=Path);parser.add_argument('--html',type=Path)
    parser.add_argument('--actor',default='김민');parser.add_argument('--reason',default='공식 발표 후 도출된 보완 사항 적용')
    args=parser.parse_args();service=HomeService(engine_for(),'/app/data');folder=service.data_dir/'remediation/r01'
    if args.id:
        if args.sequence is None or not args.json or not args.html:parser.error('id·sequence·json·html이 모두 필요합니다')
        data=json.loads(args.json.read_text())
        identity=save_round(service,args.id,args.sequence,data,args.html.read_text(),args.actor,args.reason,
                            snapshot_id=data.get('snapshot_id'),parent_id=args.parent)
        print(identity);return
    baseline=json.loads((folder/'baseline.json').read_text());current=json.loads((folder/'round.json').read_text())
    print(save_round(service,'HOME-INTEGRITY-R00',0,baseline,(folder/'baseline.html').read_text(),args.actor,
                     args.reason+' · 처음 성적표 원점수 보존 및 4대 지표 소급 추가'))
    print(save_round(service,'HOME-INTEGRITY-R01',1,current,(folder/'round.html').read_text(),args.actor,args.reason,
                     snapshot_id=current['snapshot_id'],parent_id='HOME-INTEGRITY-R00'))


if __name__=='__main__':main()
