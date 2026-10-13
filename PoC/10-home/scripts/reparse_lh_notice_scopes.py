"""Replay archived notice HTML and repair only unreviewed, matching pinned links."""
import hashlib
import json
from pathlib import Path
from sqlalchemy import select
from backend.db import Audit,Revision,engine_for,upsert_revision
from backend.service import HomeService
from backend.lh_notice_detail import parse_detail


def apply(s):
    notices={r['id']:r for r in s.rows('lh_notice')};changed={};out={'documents':0,'links':0,'preserved':0}
    for r in s.rows('document_evidence'):
        if r['source_id']!='lh_notice_detail':continue
        n=notices.get(r['notice_entity_id'])
        if not n or n['revision_no']!=r['notice_revision_no']:continue
        path=(s.data_dir/r['original_file']).resolve()
        if not path.is_relative_to((s.data_dir/'raw').resolve()):raise ValueError('원문 경로 검증 실패')
        body=path.read_bytes()
        if hashlib.sha256(body).hexdigest()!=r['original_sha256']:raise ValueError('원문 해시 불일치')
        p=parse_detail(body,n,(r['region'],r['district'],r['block']));p['original_file']=r['original_file']
        key=n['notice_no']+':'+r['district']+':'+r['block'] if p['multi_complex'] else n['notice_no']
        with s.sessions.begin() as db:
            row,result=upsert_revision(db,'document_evidence','lh_notice_detail',key,p,'notice_scope_replay')
            if result!='unchanged':
                changed[r['id']]=(r['revision_no'],row.revision_no,p);out['documents']+=1
    # Pin a repaired copy only when no officer decision or different source version intervened.
    for bridge in s.rows('evidence_bridge'):
        change=changed.get(bridge['source_entity_id'])
        if not change:continue
        before_version,after_version,source=change
        with s.sessions.begin() as db:
            old=db.scalar(select(Revision).where(Revision.entity_id==bridge['id'],Revision.superseded_at.is_(None)).with_for_update())
            before=old.payload
            if before['status']!='REVIEW' or before.get('reviewed') or before['source_revision_no']!=before_version:
                out['preserved']+=1;continue
            # Preserve existing partial-contract constraints; tighten any whole-scope claim.
            evidence=[]
            for f in before['facts']:
                new=next((x for x in source['facts'] if (x['stage'],x['kind'],x.get('date'))==(f['stage'],f['kind'],f.get('date'))),None)
                if new and new.get('scope_partial') and not f.get('scope_partial'):
                    f=dict(f,**{k:new[k] for k in ('scope_partial','scope_units','scope_label')},basis=new['basis'])
                evidence.append(f)
            payload=dict(before,facts=evidence,source_revision_no=after_version)
            row,result=upsert_revision(db,'evidence_bridge','cross_source',before['project_id']+':'+before['source_entity_id'],payload,'notice_scope_replay')
            if result!='unchanged':
                db.add(Audit(entity_id=row.entity_id,action='EVIDENCE_BRIDGE_AUTO',before=before,after=payload));out['links']+=1
    return out

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    if not args.apply:raise SystemExit('--apply required')
    print(json.dumps(apply(HomeService(engine_for(),'/app/data')),ensure_ascii=False))
