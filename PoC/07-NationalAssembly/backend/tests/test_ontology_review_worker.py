from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock

import requests

from app.ingestion import ontology_review_worker as worker


def setup_worker(monkeypatch, count=32):
    connection = MagicMock()
    def execute(sql, *_args):
        value = False if 'EXISTS' in sql else 'ENDED' if 'lifecycle_status' in sql else True
        return SimpleNamespace(fetchone=lambda: (value,))
    connection.execute.side_effect = execute
    @contextmanager
    def connect(_url):
        yield connection
    repo = MagicMock()
    repo.batches.return_value = []
    monkeypatch.setattr(worker, 'connect', connect)
    monkeypatch.setattr(worker, 'get_settings', lambda: SimpleNamespace(database_url='unused'))
    monkeypatch.setattr(worker, 'TopicStructureRepository', lambda _c: repo)
    monkeypatch.setattr(worker, 'MeetingBriefRepository', lambda _c: SimpleNamespace(latest=lambda _id: {'brief_id': 'b'}))
    monkeypatch.setattr(worker, 'selected_structure', lambda *_: {'topic_structure': {'revision_id': 's'}})
    quote = '노동자 임금 체불에 따른 생활 안정을 위한 지원을 추진하고 있습니다.'
    items = [{'topic_id': str(i), 'title': '체불 노동자 지원', 'fingerprint': str(i), 'spans': [{'quote': quote}]}
             for i in range(count)]
    monkeypatch.setattr(worker, 'pending_items', lambda *_: items)
    monkeypatch.setattr(worker, 'pace_nim', lambda _client: None)
    monkeypatch.setattr(worker.time, 'monotonic', lambda: 100.0)
    return repo, quote


def test_nim_429_uses_router_and_keeps_nim_cooldown_across_batches(monkeypatch):
    repo, quote = setup_worker(monkeypatch)
    response = requests.Response()
    response.status_code = 429
    response._content = b'{"detail":"rate limited"}'
    nim = SimpleNamespace(provider='nvidia', model='nim', _post=MagicMock(side_effect=requests.HTTPError(response=response)))
    def router_post(_prompt, schema, name):
        fields = ({'target': 'youth-employment', 'approve': True, 'reason': '지원 대상 확인', 'support_quote': quote}
                  if name == 'ontology_verification' else
                  {'target': 'youth-employment', 'span_index': 0, 'reason': '임금 체불 지원'})
        return {key: dict(fields) for key in schema['properties']}, {}
    router = SimpleNamespace(provider='openrouter', model='router', _post=MagicMock(side_effect=router_post))
    openai = SimpleNamespace(provider='openai', model='mini', _post=MagicMock(side_effect=AssertionError('unnecessary fallback')))
    monkeypatch.setattr(worker, 'clients', lambda: [nim, router, openai])
    result = worker.process_one('broadcast', batch_limit=2)
    assert result['status'] == 'COMPLETED'
    assert result['accepted'] == 32
    assert nim._post.call_count == 1
    assert router._post.call_count == 4
    openai._post.assert_not_called()
    assert [call.args[-1] for call in repo.record.call_args_list] == [
        'NIM_RATE_DEFERRED', 'VERIFICATION_PENDING', None, 'VERIFICATION_PENDING', None,
    ]


def test_daily_budget_defers_without_inventing_a_completed_review(monkeypatch):
    repo, _quote = setup_worker(monkeypatch, 1)
    client = SimpleNamespace(provider='openai', model='mini', _post=MagicMock(side_effect=worker.DailyTokenLimitReached()))
    monkeypatch.setattr(worker, 'clients', lambda: [client])
    result = worker.process_one('broadcast')
    assert result['status'] == 'BUDGET_DEFERRED'
    assert repo.record.call_args.args[-1] == 'DAILY_TOKEN_LIMIT'
