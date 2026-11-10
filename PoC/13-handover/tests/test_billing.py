import httpx
import pytest
from app.billing import Meter, completion_request
from app.store import Store


def config(meter, key='independent-key'):
    return {'key': key, 'url': 'https://api.upstage.ai/v1', 'model': 'solar-pro4', '_meter': meter}


def test_cost_persists_and_isolates_keys_including_rejected_content(tmp_path, monkeypatch):
    store = Store(tmp_path)
    meter = Meter(store)
    c = config(meter)
    class Client:
        def __init__(self, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, *args, **kw):
            return httpx.Response(200, json={'model': 'solar-pro4-260806', 'usage': {'prompt_tokens': 1000000, 'completion_tokens': 100000, 'prompt_tokens_details': {'cached_tokens': 200000}}, 'choices': [{'message': {'content': 'INVALID JSON'}}]})
    monkeypatch.setattr(httpx, 'Client', Client)
    completion_request(c, {}, 1, 'question')
    summary = meter.summary(c)
    assert summary['used_usd'] == pytest.approx(.372)
    assert summary['calls'] == 1 and summary['unknown_calls'] == 0
    assert 'independent-key' not in str(summary)
    assert Meter(Store(tmp_path)).summary(c)['used_usd'] == summary['used_usd']
    assert meter.summary(config(meter, 'other-key'))['used_usd'] == 0
    assert meter.summary(c)['calls'] == 1  # Reading/cache doesn't charge twice.
    assert store.one('SELECT fingerprint FROM llm_costs')['fingerprint'] != c['key']


def test_failed_and_missing_usage_remain_unknown(tmp_path, monkeypatch):
    meter = Meter(Store(tmp_path)); c = config(meter)
    event = meter.start(c, 'extraction')
    meter.finish(event, c, httpx.Response(429, json={'error': 'limit'}))
    event = meter.start(c, 'question')
    meter.finish(event, c, httpx.Response(200, json={'usage': {'prompt_tokens': -1, 'completion_tokens': 3}}))
    class Client:
        def __init__(self, **kw): pass
        def __enter__(self): raise httpx.ConnectError('offline')
        def __exit__(self, *args): pass
    monkeypatch.setattr(httpx, 'Client', Client)
    with pytest.raises(httpx.ConnectError): completion_request(c, {}, 1, 'question')
    assert meter.summary(c)['unknown_calls'] == 3
    assert meter.summary(c)['used_usd'] == 0
