from contextlib import contextmanager
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.services.insight_pagination import insight_page


def test_filter_before_paging_includes_items_beyond_original_eighty():
    items = [{'id': str(i), 'transition_stage': 'DISCUSSION'} for i in range(90)]
    items += [{'id': str(i), 'transition_stage': 'FOLLOW_UP_TASK'} for i in range(90, 115)]
    result = {'items': items, 'count': len(items)}
    pages = [insight_page(result, 10, offset, 'institution') for offset in (0, 10, 20, 30)]
    assert [p['count'] for p in pages] == [10, 10, 5, 0]
    assert [p['next_offset'] for p in pages] == [10, 20, None, None]
    assert all(p['total_count'] == 25 for p in pages)
    assert len({item['id'] for p in pages for item in p['items']}) == 25
    assert result['count'] == 115


@contextmanager
def connection(_):
    yield object()


def test_api_pagination_and_invalid_input():
    with patch('app.main.connect', connection), patch('app.main.PolicyIssueRepository') as repo:
        repo.return_value.specific_issue_flow.return_value = {
            'items': [{'id': str(i), 'transition_stage': 'FOLLOW_UP_TASK'} for i in range(23)], 'count': 23}
        client = TestClient(app)
        result = client.get('/api/policy/specific-issues?category=institution&limit=10&offset=10')
        assert result.status_code == 200
        assert [x['id'] for x in result.json()['items']] == [str(i) for i in range(10,20)]
        assert result.json()['total_count'] == 23
        for query in ('limit=0', 'offset=-1', 'category=bad'):
            assert client.get('/api/policy/specific-issues?' + query).status_code == 422
        assert client.get('/api/policy/cross-institution-flow?offset=-1').status_code == 422


def test_search_entire_category_before_paging_and_ministry_aliases():
    items = [{'id': str(i), 'topic': '다른 주제', 'transition_stage': 'FOLLOW_UP_TASK'} for i in range(90)]
    items += [{'id': str(i), 'topic': '주택 공급', 'ministries': ['행안부'],
               'transition_stage': 'FOLLOW_UP_TASK'} for i in range(90, 113)]
    items += [{'id': 'discussion', 'topic': '주택 공급', 'ministries': ['행정안전부'], 'transition_stage': 'DISCUSSION'}]
    result = {'items': items}
    first = insight_page(result, 10, category='institution', q='행정안전부 주택')
    last = insight_page(result, 10, 20, 'institution', '행안부 주택')
    assert first['total_count'] == 23 and first['unfiltered_total_count'] == 113
    assert first['items'][0]['id'] == '90'
    assert last['count'] == 3 and not last['has_more']
    assert insight_page(result, 10, q='없는문구')['count'] == 0
    assert insight_page(result, 10, q='  ')['total_count'] == 114


def test_search_timeline_text_but_not_internal_ids():
    items = [{'topic': '정책', 'executive_evidence': {'agenda_topic': 'AI 지원'},
              'legislative_evidence': {'text': '성능 검증'}, 'id': 'private-marker'}]
    assert insight_page({'items':items}, 10, q='ai 검증')['count'] == 1
    assert insight_page({'items':items}, 10, q='private-marker')['count'] == 0


def test_search_query_reaches_api_and_length_is_validated():
    with patch('app.main.connect', connection), patch('app.main.PolicyIssueRepository') as repo:
        repo.return_value.specific_issue_flow.return_value = {'items':[{'topic':'첫 주제'},{'topic':'숨은 주제'}]}
        client=TestClient(app)
        result=client.get('/api/policy/specific-issues',params={'q':'숨은','limit':10}).json()
        assert result['count']==1 and result['query']=='숨은'
        for path in ('specific-issues','cross-institution-flow'):
            assert client.get('/api/policy/'+path,params={'q':'x'*201}).status_code==422
