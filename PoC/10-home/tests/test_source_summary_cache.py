from concurrent.futures import Future
from backend.source_summary_cache import SourceSummaryCache

class Queue:
    def __init__(self): self.jobs=[]
    def submit(self, fn):
        f=Future(); self.jobs.append((f,fn)); return f
    def run(self):
        f,fn=self.jobs.pop(0)
        try: f.set_result(fn())
        except Exception as e: f.set_exception(e)

def test_background_single_flight_persistence_and_failed_refresh(tmp_path):
    state={'version':1,'fail':False}
    def build():
        if state['fail']: raise RuntimeError('upstream')
        return {'generated_at':'2026-10-20T09:00:00+09:00','current':{'sources':7}}
    c=SourceSummaryCache(tmp_path/'summary.json',build,lambda:state['version']);c.pool.shutdown();c.pool=Queue()
    assert c.get()['status']=='BUILDING';c.get();assert len(c.pool.jobs)==1
    c.pool.run();assert c.get()['current']['sources']==7
    saved=SourceSummaryCache(c.path,build,lambda:state['version']);saved.pool.shutdown();saved.pool=Queue()
    assert saved.get()['current']['sources']==7
    state.update(version=2,fail=True);c.checked=0;c.get();c.pool.run()
    result=c.get();assert result['refresh_failed'] and result['current']['sources']==7
