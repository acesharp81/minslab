"""Apply validated collection snapshots and refresh review-only approval candidates."""
import argparse,json,hashlib
from pathlib import Path
from urllib.parse import urlsplit,parse_qsl
from unittest.mock import patch
from backend.service import HomeService
from backend.db import engine_for
from backend.sources import SOURCES
from backend.stage_evidence import refresh,list_links
from backend.evidence_bridge import reconcile
from backend.project_collection import collection_matrix


def replay(service,snapshot,sid):
    snap=Path(snapshot);result=json.loads(snap.read_text());root=snap.parent
    def key(url,params=None):
        u=urlsplit(url);q=dict(parse_qsl(u.query));q.update(params or {});q={k:str(v) for k,v in q.items() if k.lower() not in ('servicekey','key','apikey')}
        return (u.scheme,u.netloc,u.path,tuple(sorted(q.items())))
    saved={key(m['url']):m for m in result['manifest']}
    class SnapshotFetcher:
        def __init__(self,source_id,raw_dir):self.manifest=[];self.raw_dir=Path(raw_dir)
        def close(self):pass
        def get(self,url,suffix='html',params=None,**kwargs):
            m=saved[key(url,params)];b=(root/'raw'/m['file']).read_bytes()
            if hashlib.sha256(b).hexdigest()!=m['sha256']:raise ValueError('보관 원문 해시 불일치')
            target=self.raw_dir/m['file'];target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(b);self.manifest.append(m);return b
    with patch('backend.service.Fetcher',SnapshotFetcher):out=service.collect_one(next(s for s in SOURCES if s['id']==sid))
    if out['status']!='SUCCESS':raise ValueError(str(out))
    return out

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--notice-snapshot');p.add_argument('--detail-snapshot');p.add_argument('--output',required=True);a=p.parse_args()
    service=HomeService(engine_for(),'/app/data');before=list_links(service);collections=[]
    if a.notice_snapshot:collections.append(replay(service,a.notice_snapshot,'lh_notice'))
    if a.detail_snapshot:collections.append(replay(service,a.detail_snapshot,'lh_notice_detail'))
    change=refresh(service,refresh_candidates=True);bridges=reconcile(service,apply=True)
    after=list_links(service)
    result=dict(before=before,after=after,collections=collections,refresh=change,
                evidence_bridges={k:v for k,v in bridges.items() if k not in ('proposals','held')},matrix=collection_matrix(service))
    Path(a.output).write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(dict(collections=collections,refresh=change,evidence_bridges=result['evidence_bridges']),ensure_ascii=False))
