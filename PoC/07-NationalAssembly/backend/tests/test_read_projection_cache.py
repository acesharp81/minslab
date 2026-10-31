from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4
from app.db.read_projection_cache import ProjectionCache,projection_cache
from app.db.topic_structure_repository import TopicStructureRepository

def test_returned_or_original_mutations_never_change_cached_evidence():
    cache=ProjectionCache();value={'evidence':[{'text':'original'}]};cache.put('one',value)
    value['evidence'][0]['text']='caller mutated'
    received=cache.get('one');received['evidence'][0]['text']='another caller'
    assert cache.get('one')['evidence'][0]['text']=='original'

def test_cache_expires_and_bounds_storage():
    stamp=[0];cache=ProjectionCache(max_bytes=180,max_entries=2,ttl=5,clock=lambda:stamp[0])
    cache.put(1,{'x':'1'});cache.put(2,{'x':'2'});cache.put(3,{'x':'3'})
    assert cache.get(1) is None and cache.bytes<=180 and len(cache.rows)<=2
    stamp[0]=5;assert cache.get(3) is None

class Connection:
    def __init__(self):
        self.version=(uuid4(),'updated',1,'batch-created')
        self.info=SimpleNamespace(host='test',port=5432,dbname='isolated',user='reader')
    def execute(self,*args):return self
    def fetchone(self):return self.version

def test_appended_batch_or_updated_source_invalidates_projection_immediately():
    projection_cache.clear();connection=Connection();repo=TopicStructureRepository(connection)
    item={'brief_id':uuid4(),'brief':{'topics':[]}}
    with patch.object(repo,'_build_current',side_effect=[{'source':'first'},{'source':'new batch'},{'source':'new brief'}]) as build:
        assert repo.current(item)==repo.current(item)=={'source':'first'}
        assert build.call_count==1
        connection.version=(*connection.version[:2],2,'later batch')
        assert repo.current(item)=={'source':'new batch'}
        item['brief']['headline']='changed display metadata'
        assert repo.current(item)=={'source':'new brief'}
    projection_cache.clear()

def test_retry_progress_is_not_memoized_but_completed_progress_is():
    projection_cache.clear();repo=TopicStructureRepository(Connection());item={'brief_id':uuid4(),'brief':{}}
    with patch.object(repo,'_build_progress',side_effect=[{'status':'REVIEW_REQUIRED'},{'status':'RETRY_PENDING'},{'status':'COMPLETED'}]) as build:
        assert repo.progress(item)['status']=='REVIEW_REQUIRED'
        assert repo.progress(item)['status']=='RETRY_PENDING'
        assert repo.progress(item)['status']=='COMPLETED'
        assert repo.progress(item)['status']=='COMPLETED'
        assert build.call_count==3
    projection_cache.clear()

def test_many_large_projections_do_not_thrash_the_compressed_budget():
    cache=ProjectionCache(max_bytes=20000,max_entries=128)
    for identifier in range(57):cache.put(identifier,{'source':identifier,'evidence':['same immutable excerpt']*1000})
    assert all(cache.get(identifier)['source']==identifier for identifier in range(57))
    assert cache.bytes<20000
