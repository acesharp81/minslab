import sys
from contextlib import contextmanager
from threading import Event,Lock
from types import SimpleNamespace
import pytest
from app.ingestion import executive_caption_worker as w

def test_four_streams_start_before_any_long_stream_finishes(monkeypatch):
    started=[];mutex=Lock();all_started=Event()
    @contextmanager
    def connection(_):yield object()
    class Repo:
        def __init__(self,c):pass
        def claim_audio_fallback_capture(self,*a):
            with mutex:
                if len(claims)>=4:return None
                i=len(claims);claims.append(i)
                return {'broadcast_id':i,'lifecycle_status':'LIVE'}
    claims=[]
    def capture(claim,**kw):
        with mutex:
            started.append(claim['broadcast_id'])
            if len(started)==4:all_started.set()
        assert all_started.wait(3),'One broadcast monopolized the capture worker'
        return {'broadcast_id':claim['broadcast_id']}
    class EndTest(Exception):pass
    def stop(_):
        assert all_started.wait(3)
        raise EndTest()
    monkeypatch.setattr(sys,'argv',['worker','--workers','4'])
    monkeypatch.setattr('app.config.get_settings',lambda:SimpleNamespace(database_url='test',mistral_api_key='test'))
    monkeypatch.setattr('app.db.connection.connect',connection)
    monkeypatch.setattr('app.db.live_repository.LiveRepository',Repo)
    monkeypatch.setattr('app.db.migrate.apply_migrations',lambda _:None)
    monkeypatch.setattr(w,'capture_broadcast',capture)
    monkeypatch.setattr(w.time,'sleep',stop)
    with pytest.raises(EndTest):w.main()
    assert sorted(started)==[0,1,2,3]
