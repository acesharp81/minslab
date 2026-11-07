from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.services.narrative_retry import (NARRATIVE_PROVIDER_POLICY, truncated_provider_pause,
                                         narrative_capacity, progress_poll_delay)
from app.services.structured_narrative import pending_batches
from app.services.meeting_brief import OpenRouterMeetingBriefClient


def test_nemo_direct_json_is_scoped_to_narrative_and_exact_model():
    response = Mock(status_code=200)
    response.json.return_value = {'choices': [{'message': {'content': '{}'}, 'finish_reason': 'stop'}]}
    for model, workload, direct in [
        ('nvidia/nemotron-3.5-super-vl:free', 'structured_narrative', True),
        ('nvidia/nemotron-3.5-super-vl:free', 'meeting_chunk_analysis', False),
        ('nvidia/nemotron-3-super-120b-a12b:free', 'structured_narrative', False),
    ]:
        client = OpenRouterMeetingBriefClient('fixture', model=model, base_url='http://fixture/api/v1')
        with patch('app.services.meeting_brief.requests.post', return_value=response) as post:
            client._post('fixture', {'type': 'object'}, workload)
        body = post.call_args.kwargs['json']
        assert body['reasoning'] == ({'enabled': False, 'exclude': True} if direct else {'effort': 'low', 'exclude': True})
        assert body['max_tokens'] == 12000
        assert body['response_format']['json_schema']['strict'] is True


def test_truncation_cooldown_is_policy_model_scoped_expires_and_success_resets():
    now = datetime.now(timezone.utc)
    client = SimpleNamespace(provider='openrouter', model='nemo')
    def row(age, finish='length', policy=NARRATIVE_PROVIDER_POLICY, model='nemo'):
        return {'created_at': now-timedelta(minutes=age), 'usage': {
            'provider': 'openrouter', 'attempted_model': model,
            'narrative_policy': policy, 'finish_reason': finish}}
    assert not truncated_provider_pause(client, [row(1)], now)
    assert truncated_provider_pause(client, [row(2), row(1)], now)
    assert not truncated_provider_pause(client, [row(16), row(1)], now)
    assert not truncated_provider_pause(client, [row(2), row(1, policy='old')], now)
    assert not truncated_provider_pause(client, [row(2), row(1, model='other')], now)
    assert not truncated_provider_pause(client, [row(3), row(2), row(1, finish='stop')], now)
    assert not truncated_provider_pause(client, [row(2, finish='stop'), row(1)], now)


def test_capacity_protects_overlapping_broadcasts_and_keeps_requested_limit():
    assert narrative_capacity(3, 0) == 3
    assert narrative_capacity(3, 1) == 2
    assert narrative_capacity(3, 2) == narrative_capacity(3, 4) == 1
    assert narrative_capacity(3, 0, upcoming=True) == 1
    assert narrative_capacity(1, 0) == 1
    assert progress_poll_delay(60, [{'status': 'PROCESSING', 'phase': 'NARRATIVE'}]) == 15
    for status in ['DEFERRED', 'FAILED', 'COMPLETED']:
        assert progress_poll_delay(60, [{'status': status, 'phase': 'NARRATIVE'}]) == 60
    assert progress_poll_delay(60, []) == 60


def test_many_speaker_points_split_without_dropping_single_large_issue():
    items = [{'id': str(i), 'fingerprint': str(i), 'points': [{'id': str(j)} for j in range(n)]}
             for i, n in enumerate([13, 13, 30, 1])]
    batches, blocked = pending_batches(items, [])
    assert not blocked
    assert [x for b in batches for x in b['issues']] == items
    assert [len(b['issues']) for b in batches] == [1, 1, 1, 1]
