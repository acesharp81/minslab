from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest

from app.services.public_response_cache import PublicResponseCache


def test_concurrent_requests_build_once_and_other_keys_are_independent():
    cache = PublicResponseCache()
    entered, release = Event(), Event()
    calls = []
    def build():
        calls.append(1)
        entered.set()
        assert release.wait(3)
        return b'public'
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(cache.get, 'one', build, ttl=2) for _ in range(6)]
        assert entered.wait(3)
        assert pool.submit(cache.get, 'two', lambda: b'other', ttl=2).result(2) == b'other'
        release.set()
        assert [f.result(3) for f in futures] == [b'public'] * 6
    assert len(calls) == 1


def test_expiry_capacity_and_errors_do_not_cache_failures():
    clock = Mock(return_value=0)
    cache = PublicResponseCache(max_entries=2, max_bytes=6, clock=clock)
    build = Mock(return_value=b'abc')
    assert cache.get('a', build, ttl=2) == b'abc'
    assert cache.get('a', build, ttl=2) == b'abc'
    assert build.call_count == 1
    clock.return_value = 2
    cache.get('a', build, ttl=2)
    assert build.call_count == 2
    cache.get('b', lambda: b'abcd', ttl=2)
    cache.get('a', build, ttl=2)
    assert build.call_count == 3
    with pytest.raises(ValueError):
        cache.get('error', Mock(side_effect=ValueError()), ttl=2)
    assert cache.get('error', lambda: b'ok', ttl=2) == b'ok'
    assert cache.get('large', lambda: b'1234567', ttl=2) == b'1234567'
    assert 'large' not in cache._entries


def test_public_routes_serialize_uuid_and_keep_cache_keys_separate():
    from fastapi.testclient import TestClient
    from app import main
    one, two = uuid4(), uuid4()
    with patch.object(main, '_public_responses', PublicResponseCache()), \
         patch.object(main, 'live_transcript_snapshot', side_effect=lambda committee, bid: {'broadcast_id': bid}) as build, \
         patch.object(main, 'ended_live_broadcast_brief', return_value={'broadcast_id': one}):
        client = TestClient(main.app)
        for bid in (one, one, two):
            response = client.get('/api/live/transcript/snapshot', params={'broadcast_id': str(bid)})
            assert response.status_code == 200
            assert response.json()['broadcast_id'] == str(bid)
            assert response.headers['cache-control'] == 'no-store'
        assert build.call_count == 2
        assert client.get(f'/api/live/broadcasts/{one}/brief').json() == {'broadcast_id': str(one)}
