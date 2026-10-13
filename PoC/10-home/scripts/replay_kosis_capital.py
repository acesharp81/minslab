"""Reparse last successful official KOSIS snapshots, verifying original hashes.
Use after a geographic parser extension. No new API requests or guessed values.
"""
import hashlib,json
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
from unittest.mock import patch
from sqlalchemy import select
from backend.db import Batch,engine_for
from backend.service import HomeService

SAFE_EXCLUDE={'apikey','servicekey','key','cert_id'}
def signature(url,params=None):
    q=parse_qs(urlsplit(url).query)
    q.update({k:[str(v)] for k,v in (params or {}).items()})
    return tuple(sorted((k,tuple(v)) for k,v in q.items() if k.lower() not in SAFE_EXCLUDE))

class Replay:
    def __init__(self,sid,raw_dir):
        self.raw_dir=Path(raw_dir);self.manifest=[];self.entries={}
        with service.sessions() as db:
            b=db.scalar(select(Batch).where(Batch.source_id==sid,Batch.status=='SUCCESS').order_by(Batch.finished_at.desc()))
            if not b:raise ValueError('정상 수집 원본 없음: '+sid)
            for m in b.manifest:self.entries[signature(m['url'])]=m
    def get(self,url,suffix='json',params=None,headers=None):
        m=self.entries.get(signature(url,params))
        if not m:raise ValueError('동일 조회조건 원본 미확보 · 원천 재수집 필요')
        content=(self.raw_dir/m['file']).read_bytes()
        if hashlib.sha256(content).hexdigest()!=m['sha256']:raise ValueError('원본 해시 불일치')
        self.manifest.append(dict(m,reprocessed=True));return content
    def close(self):pass

if __name__=='__main__':
    service=HomeService(engine_for())
    with patch('backend.service.Fetcher',Replay):
        for sid in ('kosis_housing','kosis_household_size','kosis_household_forecast','kosis_employment'):
            print(json.dumps(service.collect_all(sid),ensure_ascii=False),flush=True)
