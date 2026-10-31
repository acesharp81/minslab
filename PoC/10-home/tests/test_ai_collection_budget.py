import httpx
import pytest
from backend import ai_collection_budget as budget
from backend.ai_collection_store import Store,BudgetExceeded


def test_settlement_outbox_retries_without_losing_first_usage(tmp_path,monkeypatch):
    monkeypatch.setenv('POC10_SHARED_BUDGET_REQUIRED','true')
    s=Store(tmp_path);seen=[]
    def down(*a,**kw):raise BudgetExceeded('offline')
    monkeypatch.setattr(budget,'request',down)
    budget.settle(s,'call1',10,20,.01)
    budget.settle(s,'call1',None,None,None)
    with pytest.raises(BudgetExceeded):budget.reserve(s,'call2','gpt-5.4-mini',100,10)
    monkeypatch.setattr(budget,'request',lambda a,p=None:seen.append((a,p)) or {'settled':True})
    assert budget.flush(s) and budget.flush(s)
    assert len(seen)==1 and seen[0][1]['cost_usd']==.01
    budget.reserve(s,'call2','solar-pro4',100,10)
    assert seen[-1][1]['project']=='poc10'


def test_no_connection_fails_closed(monkeypatch):
    monkeypatch.delenv('USAGE_GATEWAY_URL',raising=False)
    with pytest.raises(BudgetExceeded):budget.request('reserve',{})
    assert budget.status()['models']==[]
