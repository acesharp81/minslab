from unittest.mock import patch
from backend import ai_collection_budget as budget
from backend.ai_collection_models import key_for

def test_key2_has_no_silent_fallback_to_suspended_key(monkeypatch):
 monkeypatch.setenv('SHARED_SOLAR_POOL','key2');monkeypatch.setenv('UPSTAGE_SECRET_KEY','old')
 monkeypatch.delenv('UPSTAGE_SECRET_KEY2',raising=False);assert key_for('SOLAR')==''
 monkeypatch.setenv('UPSTAGE_SECRET_KEY2','new');assert key_for('SOLAR')=='new'
 monkeypatch.setenv('SHARED_SOLAR_POOL','default');assert key_for('SOLAR')=='old'

def test_only_solar_admission_selects_key2(monkeypatch):
 monkeypatch.setenv('SHARED_SOLAR_POOL','key2')
 with patch.object(budget,'required',return_value=True),patch.object(budget,'flush',return_value=True),patch.object(budget,'request',return_value={}) as request:
  budget.reserve(object(),'solar-call','solar-pro4',100,20)
  assert request.call_args.args[1]['solar_pool']=='key2'
  budget.reserve(object(),'openai-call','gpt-5.4',100,20)
  assert 'solar_pool' not in request.call_args.args[1]
