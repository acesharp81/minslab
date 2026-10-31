from concurrent.futures import ThreadPoolExecutor
import pytest
from scripts.evaluation_budget import capped_usage

class Base:
    def reserve(self,*args):return {'event_id':args[0]}
    def record(self,*args):pass


def test_atomic_cap_unknown_usage_and_known_settlement(tmp_path):
    Meter=capped_usage(Base,tmp_path/'budget.db',{'gpt-5.4':100},{});m=Meter()
    def reserve(i):
        try:m.reserve(str(i),'gpt-5.4',40,20);return True
        except RuntimeError:return False
    with ThreadPoolExecutor(max_workers=2) as p:assert sum(p.map(reserve,[1,2]))==1
    with m.db() as c:eid=c.execute('select id from reservations').fetchone()[0]
    m.record(dict(event_id=eid,status='FAILED',cost_usd=None,input_tokens=0,output_tokens=0),None)
    with pytest.raises(RuntimeError):m.reserve('3','gpt-5.4',40,20)
    m.record(dict(event_id=eid,status='COMPLETED',cost_usd=.01,input_tokens=10,output_tokens=10),None)
    m.reserve('4','gpt-5.4',40,20)
    # A later day cannot expand this independently frozen cap.
    with pytest.raises(RuntimeError):Meter().reserve('5','gpt-5.4',30,0)


def test_sol_and_astra_share_cap_and_preflight_rejection_releases_only_local_reservation(tmp_path):
    Meter=capped_usage(Base,tmp_path/'budget.db',{'openai-shared':1},{'gpt-6.1-sol':(2,10),'gpt-6-astra':(10,50)})
    m=Meter();m.reserve('sol','gpt-6.1-sol',50000,50000)
    with pytest.raises(RuntimeError):m.reserve('astra','gpt-6-astra',40000,0)
    class Reject(Base):
        def reserve(self,*a):raise ValueError('shared budget rejects')
    Rejected=capped_usage(Reject,tmp_path/'reject.db',{'gpt-5.4':100},{})
    with pytest.raises(ValueError):Rejected().reserve('x','gpt-5.4',50,50)
    with Rejected().db() as c:assert c.execute('select amount from reservations').fetchone()[0]==0
