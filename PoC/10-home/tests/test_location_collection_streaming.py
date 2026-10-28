import json
from unittest.mock import patch
from sqlalchemy import create_engine
from backend.db import Base, upsert_revision
from backend.service import HomeService
from backend.sources import SOURCES
from backend.api_samples import collect_locations


def test_geocode_reads_only_address_columns_and_keeps_per_region_limit(tmp_path,monkeypatch):
    engine=create_engine('sqlite://');Base.metadata.create_all(engine);service=HomeService(engine,tmp_path)
    source=next(s for s in SOURCES if s['id']=='vworld')
    try:
        with service.sessions.begin() as db:
            for i in range(12):
                upsert_revision(db,'permit','test',str(i),dict(name='허가'+str(i),source_object_id=str(i),
                    region='서울특별시',address='서울특별시 테스트로 '+str(i),large_raw_payload='x'*100000),'seed')
        original_rows=service.rows
        def bounded_rows(kind,*args,**kwargs):
            assert kind=='location','Full permit/notice payloads must not be materialized'
            return original_rows(kind,*args,**kwargs)
        class Fetcher:
            def get(self,*args,**kwargs):return json.dumps({'response':{'status':'NOT_FOUND'}})
        monkeypatch.setenv('POC10_GEOCODE_PER_KIND_REGION','2')
        with patch.object(service,'rows',side_effect=bounded_rows),patch('backend.api_samples.key_for',return_value='fixture'):
            records,stats=collect_locations(source,Fetcher(),service)
        assert len(records)==2 and stats['candidate_parent_count']==12 and stats['remaining_parents']==10
        assert all(p['longitude'] is None and p['latitude'] is None for _,_,p in records)
    finally:engine.dispose()
