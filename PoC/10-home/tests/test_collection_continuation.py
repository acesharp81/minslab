"""Regression coverage for observed backfill interruptions and stale notices."""
from unittest.mock import patch

import httpx
import pytest

from backend.collectors import Fetcher
from backend.route_documents import select_eum_details


def test_empty_http_success_retries_same_page_without_losing_credentials_redaction(tmp_path):
    requests=[]
    def respond(request):
        requests.append(str(request.url))
        return httpx.Response(200,content=b'' if len(requests)<3 else b'{"totalCount":0,"echo":"private-key"}')
    f=Fetcher('building_register',tmp_path)
    f.client.close();f.client=httpx.Client(transport=httpx.MockTransport(respond))
    try:
        with patch('backend.collectors.time.sleep'):
            body=f.get('https://apis.data.go.kr/test','json',params={'serviceKey':'private-key','pageNo':7})
        assert len(requests)==3 and len(set(requests))==1
        assert b'private-key' not in body and b'[REDACTED]' in body
        assert len(f.manifest)==1 and 'private-key' not in str(f.manifest)
        assert len(list(tmp_path.rglob('*.json')))==1
    finally:f.close()


def test_persistent_empty_response_never_becomes_successful_zero_row_page(tmp_path):
    calls=[]
    def respond(request):
        calls.append(request)
        return httpx.Response(200,content=b'')
    f=Fetcher('building_register',tmp_path)
    f.client.close();f.client=httpx.Client(transport=httpx.MockTransport(respond))
    try:
        with patch('backend.collectors.time.sleep'),pytest.raises(ValueError,match='비었거나'):
            f.get('https://apis.data.go.kr/test','json')
        assert len(calls)==3 and f.manifest==[]
        assert not list(tmp_path.rglob('*.json'))
    finally:f.close()


def test_latest_amendments_and_old_backlog_both_get_detail_capacity():
    old=[dict(source_object_id=str(i),notice_date='2025-10-01') for i in range(100)]
    recent=[dict(source_object_id='new'+str(i),notice_date='2026-10-19') for i in range(6)]
    rows=select_eum_details(old+recent,{})
    assert len(rows)==len({r['source_object_id'] for r in rows})==15
    assert sum(r['notice_date']=='2026-10-19' for r in rows)==5
    assert sum(r['notice_date']=='2025-10-01' for r in rows)==10


def test_small_notice_backlog_is_not_duplicated_or_lost():
    rows=[dict(source_object_id=str(i),notice_date='2026-10-19') for i in range(3)]
    assert sorted(select_eum_details(rows,{}),key=lambda r:r['source_object_id'])==rows
    assert select_eum_details([],{})==[]
