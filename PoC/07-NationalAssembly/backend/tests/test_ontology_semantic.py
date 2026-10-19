from copy import deepcopy

import pytest

from app.services.meeting_topic_groups import TARGET_ONTOLOGY, build_meeting_topic_ontology
from app.services.ontology_context import verified_topic_spans
from app.services.ontology_source_context import attach_ontology_source_context
from app.services.ontology_semantic import (
    PROFILE, BATCH_START, METHOD, catalog_snapshot, review_input, apply_reviews,
    semantic_match, validate_proposals, validate_verification, prompt,
)
from test_ontology_context import topic


def reviewed():
    t = topic('체불 노동자의 생활 안정', '민생 지원', '체불 노동자의 생활 안정을 위한 지원이 필요합니다. 실제 지급 대상과 지원 조건을 확인해야 합니다.')
    item = review_input(t, TARGET_ONTOLOGY)
    request = {'profile': PROFILE, 'catalog': catalog_snapshot(TARGET_ONTOLOGY), 'items': [item]}
    response = {'proposals': {t['id']: {'target': 'youth-employment', 'span_index': 0, 'reason': '체불 노동자 지원'}},
                'verification': {t['id']: {'target': 'youth-employment', 'approve': True, 'reason': '제목과 인용에서 동일한 대상을 확인', 'support_quote': '체불 노동자의 생활 안정을 위한 지원이 필요합니다.'}}}
    return t, request, response


def test_two_stage_approval_and_immutable_source():
    t, request, response = reviewed()
    original = deepcopy(t)
    brief = apply_reviews({'topics': [t], 'tasks': []}, [(BATCH_START, request, response)], TARGET_ONTOLOGY)
    match = semantic_match(t, TARGET_ONTOLOGY)
    assert match['classification_method'] == METHOD
    assert match['supporting_spans'][0]['quote'] == original['speaker_points'][0]['summary']
    assert t['speaker_points'] == original['speaker_points']
    assert t['ontology_semantic_review']['authority_status'] == 'PROVISIONAL'


@pytest.mark.parametrize('change', ['title', 'quote', 'revision', 'catalog', 'reject', 'unknown', 'index', 'fingerprint', 'missing_verify', 'invented_quote', 'disagreement'])
def test_stale_invalid_or_rejected_reviews_never_match(change):
    t, request, response = reviewed()
    if change == 'title': t['title'] += ' 변경'
    if change == 'quote': t['speaker_points'][0]['summary'] = '다른 내용'
    if change == 'revision': t['speaker_points'][0]['evidence_span']['revision_ids'] = ['other']
    if change == 'catalog': request['catalog'] = []
    if change == 'reject': response['verification'][t['id']]['approve'] = False
    if change == 'unknown': response['proposals'][t['id']]['target'] = 'invented'
    if change == 'index': response['proposals'][t['id']]['span_index'] = 99
    if change == 'fingerprint': request['items'][0]['fingerprint'] = 'stale'
    if change == 'missing_verify': response.pop('verification')
    if change == 'invented_quote': response['verification'][t['id']]['support_quote'] = '모델이 새로 만든 존재하지 않는 인용문입니다.'
    if change == 'disagreement': response['verification'][t['id']]['target'] = 'education'
    apply_reviews({'topics': [t]}, [(BATCH_START, request, response)], TARGET_ONTOLOGY)
    assert semantic_match(t, TARGET_ONTOLOGY) is None


def test_generic_or_brief_answers_cannot_be_semantically_promoted():
    for title, quote in [('사과만으로 끝낼지 후속 조치 여부 질의', '사과로만 끝을 냅니까?'),
                         ('스마트폰 과의존 기술 확보 및 사회적 합의', '사회적 합의를 이뤄내야 되죠. 대한민국의 핵심 기술로 현실화하는데 특별한 문제가 없을 것 같다는 답변을 받았습니다.'),
                         ('후보자 자질 검증', '교육부 정책의 다양한 목표를 계속 살펴보면서 국민 의견을 적극적으로 듣겠습니다. 더욱 노력하겠습니다.')]:
        assert review_input(topic(title, '공직 인사 검증', quote), TARGET_ONTOLOGY) is None


def test_failed_attempt_limit_and_cached_rejection():
    from app.ingestion.ontology_review_worker import pending_items
    t = topic('휴대기기 사용이 늘어난 저학년 학생들', '디지털 안전',
              '저학년 학생들이 휴대기기를 사용하는 시간이 늘고 있습니다. 보호 기능이 있는 기기 도입을 논의해야 합니다.')
    item = review_input(t, TARGET_ONTOLOGY)
    assert item
    assert pending_items({'topics': [t]}, []) == [item]
    failures = [{'index': BATCH_START, 'status': 'FAILED', 'request': {'profile': PROFILE, 'items': [item]}}] * 3
    assert pending_items({'topics': [t]}, failures) == []
    for failure in failures:
        failure['error'] = 'NIM_RATE_DEFERRED'
    assert pending_items({'topics': [t]}, failures) == [item]
    t['ontology_semantic_review'] = {'fingerprint': item['fingerprint'], 'verification': {'approve': False}}
    assert pending_items({'topics': [t]}, []) == []


def test_verifier_only_receives_selected_quote_without_first_judgment():
    import json
    t, request, response = reviewed()
    rendered = prompt(request['items'], TARGET_ONTOLOGY, response['proposals'])
    payload = json.loads(rendered[rendered.index('{"catalog"'):])
    assert payload['proposals'] is None
    assert payload['items'][0]['sources'] == [{'quote': t['speaker_points'][0]['summary']}]
    assert response['proposals'][t['id']]['reason'] not in rendered


def test_requests_rate_limit_is_detected_without_exception_code_attribute():
    import requests
    from app.ingestion.ontology_review_worker import is_rate_limited
    response = requests.Response()
    response.status_code = 429
    assert is_rate_limited(requests.HTTPError('upstream', response=response))
    response.status_code = 503
    assert not is_rate_limited(requests.HTTPError('upstream', response=response))


def test_approved_semantic_result_counts_with_provisional_example():
    t = topic('휴대기기 사용이 늘어난 저학년 학생들', '디지털 안전',
              '저학년 학생들이 휴대기기를 사용하는 시간이 늘고 있습니다. 보호 기능이 있는 기기 도입을 논의해야 합니다.')
    item = review_input(t, TARGET_ONTOLOGY)
    request = {'profile': PROFILE, 'catalog': catalog_snapshot(TARGET_ONTOLOGY), 'items': [item]}
    response = {'proposals': {t['id']: {'target': 'children-digital-safety', 'span_index': 0, 'reason': '기기 보호'}},
                'verification': {t['id']: {'target': 'children-digital-safety', 'approve': True, 'reason': '저학년 보호',
                                          'support_quote': '보호 기능이 있는 기기 도입을 논의해야 합니다.'}}}
    brief = apply_reviews({'topics': [t], 'tasks': []}, [(BATCH_START, request, response)], TARGET_ONTOLOGY)
    result = build_meeting_topic_ontology([brief])
    assert result['metrics']['semantic_topic_count'] == 1
    assert result['metrics']['semantic_reviewed_topic_count'] == 1
    assert result['metrics']['policy_topic_count'] == 1
    example = next(g for g in result['groups'] if g['semantic_topic_count'])['context_examples'][0]
    assert example['authority_status'] == 'PROVISIONAL'
    assert example['method'] == METHOD


def test_malformed_model_shapes_rejected():
    t, request, response = reviewed()
    for data in ({}, {'unknown': {}}, {t['id']: {'target': 'youth-employment', 'span_index': True, 'reason': ''}}):
        with pytest.raises(ValueError): validate_proposals(request['items'], data, TARGET_ONTOLOGY)
    with pytest.raises(ValueError): validate_verification(request['items'], {t['id']: {'approve': 'true', 'reason': ''}})


def source_fixture():
    t = topic('외부회생위원 보수지급 기준', '회생 절차', '처음에는 인사를 나눴습니다.')
    text = t['speaker_points'][0]['summary'] + ' ' * 350 + '외부회생위원 보수지급 기준에 대해 답변합니다.'
    atom = {'id': 'a1', 'evidence_id': 'u1', 'content_hash': 'saved-hash', 'revision_ids': ['r1'],
            'segment_ids': ['s1'], 'text': text, 'offset': 100}
    return {'topics': [t]}, {'atoms': [atom]}


def test_relocated_quote_exact_source_and_original_preserved():
    brief, snapshot = source_fixture()
    before = deepcopy(brief)
    result = attach_ontology_source_context(brief, snapshot, {brief['topics'][0]['id']})
    t = result['topics'][0]
    assert brief == before
    assert t['speaker_points'] == before['topics'][0]['speaker_points']
    assert len(verified_topic_spans(t)) > 1
    for s in t['ontology_evidence_spans']:
        assert snapshot['atoms'][0]['text'][s['start'] - 100:s['end'] - 100] == s['quote']
    for span in t['ontology_evidence_spans']:
        span['revision_ids'] = ['foreign']
    assert len(verified_topic_spans(t)) == 1


@pytest.mark.parametrize('change', ['utterance', 'hash', 'generic'])
def test_no_borrowing_from_other_sources(change):
    brief, snapshot = source_fixture()
    if change == 'utterance': snapshot['atoms'][0]['evidence_id'] = 'u2'
    if change == 'hash': snapshot['atoms'][0]['content_hash'] = 'new-revision'
    if change == 'generic': brief['topics'][0]['title'] = '문제 관련 개선 방안'
    result = attach_ontology_source_context(brief, snapshot, {brief['topics'][0]['id']})
    assert not result['topics'][0].get('ontology_evidence_spans')
