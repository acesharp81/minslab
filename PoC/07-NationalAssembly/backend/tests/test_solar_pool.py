from concurrent.futures import ThreadPoolExecutor
import pytest
from test_shared_budget import ledger
from app.services import shared_budget as b

def solar(c,s,pool):return next(x for x in b.snapshot(c,s,pool)['models'] if x['id']=='solar-pro4')

def test_two_projects_share_limited_key2_and_do_not_touch_old_unlimited(ledger):
 connect,s=ledger;s=s.model_copy(update={'shared_solar_unlimited':True})
 with connect() as c:
  b.reserve(c,s,'old-key-call','poc10','solar-pro4',100,100)
  b.settle(c,'old-key-call',100,100,99)
  assert solar(c,s,'default')['status']=='UNLIMITED'
  assert solar(c,s,'key2')['remaining']==100
  b.reserve(c,s,'key2-from-13','poc13','solar-pro4',100,100,solar_pool='key2')
  b.settle(c,'key2-from-13',100,100,99.9)
  b.settle(c,'key2-from-13',100,100,99.9)
  assert solar(c,s,'key2')['remaining']==pytest.approx(.1)
  assert solar(c,s,'key2')['scope']=='PoC10 · PoC13 공통 원장'
 def attempt(project):
  try:
   with connect() as c:return b.reserve(c,s,'concurrent-'+project,project,'solar-pro4',200000,10000,solar_pool='key2')
  except b.BudgetUnavailable:return None
 with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(attempt,['poc10','poc13']))
 assert sum(r is not None for r in results)==1
 with connect() as c:
  card=solar(c,s,'key2');assert card['remaining']==pytest.approx(.028)
  assert card['status']=='AVAILABLE' and card['limit']==100
  assert solar(c,s,'default')['used']==99

def test_pool_mismatch_or_foreign_project_rejected_and_unknown_remains_reserved(ledger):
 connect,s=ledger
 with connect() as c:
  b.reserve(c,s,'one-pool-only','poc10','solar-pro4',100,100,solar_pool='key2')
  with pytest.raises(b.BudgetUnavailable):b.reserve(c,s,'one-pool-only','poc10','solar-pro4',100,100)
  with pytest.raises(b.BudgetUnavailable):b.reserve(c,s,'not-authorized','poc7','solar-pro4',100,100,solar_pool='key2')
  b.settle(c,'one-pool-only',None,None,None)
  assert solar(c,s,'key2')['unknown']==pytest.approx(.00015)
  b.reserve(c,s,'mini-same-pool','poc13','solar-mini4',100,100,solar_pool='key2')
  b.settle(c,'mini-same-pool',100,100,.00005)
  assert solar(c,s,'key2')['remaining']==pytest.approx(99.9998)

def test_key2_status_route_still_requires_auth(monkeypatch):
 from fastapi.testclient import TestClient
 from app import openrouter_gateway as g
 monkeypatch.setattr(g,'METER_TOKEN','test-token')
 monkeypatch.setattr(g,'_shared_snapshot',lambda solar_pool='default':{'pool':solar_pool,'models':[]})
 client=TestClient(g.app)
 assert client.get('/internal/budget/status?solar_pool=key2').status_code==403
 r=client.get('/internal/budget/status?solar_pool=key2',headers={'x-minslab-meter-token':'test-token'})
 assert r.status_code==200 and r.json()['pool']=='key2'
