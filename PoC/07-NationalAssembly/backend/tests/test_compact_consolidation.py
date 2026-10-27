import json
from copy import deepcopy
import pytest
from app.services import compact_consolidation as compact
from app.services.topic_structure import consolidation_schema,apply_consolidation,consolidation_input


def items(n=369):
    return [{'id':str(i),'parent':'정책 대상','issue':f'서로 다른 구체적 쟁점 {i}',
             'evidence':[{'role':'ANSWER','quote':f'원문 근거 {i}'}]} for i in range(n)]


def test_large_schema_size_does_not_grow_with_number_of_issues():
    source=items()
    assert len(json.dumps(compact.schema(source))) < len(json.dumps(consolidation_schema(source)))/50
    assert len(json.dumps(compact.schema(source)))<1000


def test_every_source_and_quote_survives_compact_request_and_response():
    source=items();before=deepcopy(source)
    request=compact.prompt(source)
    assert all(x['evidence'][0]['quote'] in request for x in source)
    result=compact.normalize(source,{'groups':[{'parent':'정책 대상','issue_groups':[[i] for i in range(len(source))]}]})
    assert set(result['assignments'])=={x['id'] for x in source}
    assert source==before


@pytest.mark.parametrize('groups',[[[0]],[[0],[0,1]],[[0,2]],[[0,True]],[[]]])
def test_missing_duplicate_unknown_boolean_and_empty_indices_rejected(groups):
    with pytest.raises(ValueError):compact.normalize(items(2),{'groups':[{'parent':'정책 대상','issue_groups':groups}]})


def test_existing_guard_still_rejects_unsupported_issue_merge():
    facets=[{'parent':'교통 정책','issue':'서울 한강버스 운항 안전','role':'ANSWER','quote':'한강버스 운항 현황입니다.'},
            {'parent':'교통 정책','issue':'제주 공항 소음 보상','role':'ANSWER','quote':'제주 공항 소음 보상입니다.'}]
    source=consolidation_input(facets)
    mapped=compact.normalize(source,{'groups':[{'parent':'교통 정책','issue_groups':[[0,1]]}]})
    result=apply_consolidation(facets,mapped)
    assert [f['issue'] for f in result]==[f['issue'] for f in facets]
