"""Recover omitted HUB components from pinned raw batches and persist parcel candidates.

Run inside the application environment: python -m scripts.reconcile_parcels --apply
No network requests; original permit revisions and officer selections are retained.
"""
import argparse
import hashlib
import json
from collections import defaultdict, Counter
from pathlib import Path
from sqlalchemy import select
from backend.db import Batch, engine_for, upsert_revision
from backend.service import HomeService
from backend.parcel_identity import selected_permits, compose, reconcile


def recover(service, apply=False):
    permits={k:p for ps in selected_permits(service).values() for k,p in ps.items()}
    by_batch=defaultdict(dict)
    for key,p in permits.items():
        if p.get('plat_gb_cd') is None:by_batch[p['batch_id']][key]=p
    results=Counter(); found=[]
    with service.sessions() as db:
        batches={b.id:b for b in db.scalars(select(Batch).where(Batch.id.in_(list(by_batch))))}
    for bid,group in by_batch.items():
        batch=batches.get(bid)
        if not batch:results['batch_missing']+=len(group);continue
        native={str(p['source_object_id']): (key,p) for key,p in group.items()}
        for entry in batch.manifest:
            path=service.data_dir/'raw'/entry['file']
            try:
                body=path.read_bytes();parsed=json.loads(body)
                rows=(parsed.get('response',{}).get('body',{}).get('items') or {}).get('item',[])
                if isinstance(rows,dict):rows=[rows]
            except (OSError,ValueError,AttributeError):continue
            for raw in rows:
                hit=native.get(str(raw.get('mgmHsrgstPk')))
                if not hit:continue
                key,p=hit
                if str(raw.get('sigunguCd'))!=p.get('sigungu_code') or str(raw.get('bjdongCd'))!=p.get('bjdong_code'):continue
                row={k:p.get(k) for k in ('name','region','sigungu_code','bjdong_code','base_date','evidence_url')}
                row.update(plat_gb_cd=str(raw['platGbCd']) if raw.get('platGbCd') is not None else None,
                           bun=str(raw['bun']) if raw.get('bun') is not None else None,
                           ji=str(raw['ji']) if raw.get('ji') is not None else None)
                pnu,reason=compose(row)
                row.update(pnu=pnu,pnu_status=reason,source_entity_id=key[0],source_revision_no=key[1],
                    native_permit_id=p['source_object_id'],raw_file=entry['file'],raw_sha256=hashlib.sha256(body).hexdigest(),
                    basis='선택된 허가 판본의 보관 원문에서 산 여부·본번·부번 복원')
                found.append((key,row));native.pop(str(raw.get('mgmHsrgstPk')))
            if not native:break
        results['raw_not_found']+=len(native)
    results['raw_recovered']=len(found)
    results['composable']=sum(bool(p['pnu']) for _,p in found)
    if apply:
        with service.sessions.begin() as db:
            for (eid,version),payload in found:
                _,status=upsert_revision(db,'parcel_evidence','parcel_recovery',f'{eid}:{version}',payload,'parcel_recovery')
                results['revision_'+status]+=1
    return dict(results)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    service=HomeService(engine_for(),'/app/data')
    result={'recovery':recover(service,args.apply)}
    if args.apply:result['projects']=reconcile(service)
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
