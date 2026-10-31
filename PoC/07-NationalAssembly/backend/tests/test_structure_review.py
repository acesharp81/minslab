from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.services.structure_retry import retry_allowance, failed_batch_status
from app.services.structure_review import (PROFILE, review_candidates, apply_reviews,
                                          validated_review, annotate_review_state)
from app.services.topic_structure import build_snapshot, materialize, validate_response
from app.db.topic_structure_repository import TopicStructureRepository


def history(count=3, error='ConnectionError', age=60):
    now = datetime.now(timezone.utc)
    return [dict(index=1, attempt=i+1, status='FAILED', request={'schema_revision': 2},
                 error=error, created_at=now-timedelta(minutes=age)) for i in range(count)]


def test_network_failure_retries_after_cooldown_but_not_forever():
    assert retry_allowance(history()) == 3
    assert retry_allowance(history(age=10)) == 0
    assert retry_allowance(history(count=9)) == 0
    assert retry_allowance(history(error='MISSING_ATOMS')) == 0
    assert retry_allowance(history(error='HTTPError:HTTP_401')) == 0
    assert retry_allowance([]) == 3


def test_success_supersedes_failed_attempts():
    rows = history()
    assert failed_batch_status(rows) == 'RETRY_PENDING'
    rows.append({**rows[-1], 'attempt': 4, 'status': 'READY'})
    assert failed_batch_status(rows) is None
    assert retry_allowance(rows) == 0


def test_completed_consolidation_does_not_hide_failed_source_batches():
    c = MagicMock()
    c.execute.return_value.fetchone.side_effect = [('sid', 'version', 7, 'last-batch'), ('READY', 6, 1, 0), ('sid',)]
    with patch.object(TopicStructureRepository, 'batches', return_value=history()):
        result = TopicStructureRepository(c).progress({'brief_id': 'b', 'brief': {}})
    assert result['status'] == 'RETRY_PENDING'


def fixture():
    original = {'topics': [{'id': 'old', 'evidence_ids': ['u1','u2']}], 'tasks': [],
                'live_topic_lineage': {'clusters': [{'id': 'c', 'title': '위치추적', 'utterance_ids': ['u1','u2']}]}}
    snapshot = build_snapshot({'brief_id': 'b', 'brief': original, 'transcript_hash': 'h'}, [
        {'utterance_id': 'u1', 'text': '휴대전화 위치추적 범위가 너무 넓어서 실종자 발견이 어렵습니다.', 'content_hash': 'h1', 'revision_ids': ['r1'], 'segment_ids': ['s1']},
        {'utterance_id': 'u2', 'text': '위치추적 기술을 개선해서 실종자를 신속히 찾도록 하겠습니다.', 'content_hash': 'h2', 'revision_ids': ['r2'], 'segment_ids': ['s2']},
    ])
    response = {'assignments': {a['id']: [{'parent': '경찰 수사', 'issue': '실종자 위치추적 정확도 개선',
                    'role': 'QUESTION' if i == 0 else 'UNCERTAIN', 'span_index': 0}]
                    for i,a in enumerate(snapshot['atoms'])}}
    facets = validate_response(response, snapshot['atoms'])
    return original, snapshot, facets, materialize(original, snapshot, facets, [], 'sid')


def request_response():
    original, snapshot, facets, brief = fixture()
    pending = review_candidates(brief, snapshot, [])
    request = {'profile': PROFILE, 'schema_revision': 2, 'atoms': [p['atom'] for p in pending],
               'targets': [f for p in pending for f in p['targets']]}
    aid = request['atoms'][0]['id']
    response = {'assignments': {aid: [{'parent': '경찰 수사', 'issue': '실종자 위치추적 정확도 개선',
                                     'role': 'ANSWER', 'span_index': 0}]},
                'reasons': {aid: '앞선 위치추적 정확도 질의에 대한 기술 개선 답변이다.'}}
    return original, snapshot, facets, brief, request, response


def test_context_review_recovers_answer_preserves_confirmed_source_and_original():
    original, snapshot, facets, brief, request, response = request_response()
    before = deepcopy((original, snapshot, facets))
    updated, reviewed = apply_reviews(facets, [(400000, request, response)])
    result = materialize(original, snapshot, updated, [], 'sid')
    annotate_review_state(result, reviewed)
    assert (original, snapshot, facets) == before
    assert len(result['topics']) == 1
    assert {p['role'] for p in result['topics'][0]['speaker_points']} == {'QUESTION', 'ANSWER'}
    assert not result['topic_structure']['uncertain']
    assert result['live_topic_lineage']['unmapped_cluster_count'] == 0
    assert result['topic_structure']['automatic_review']['status'] == 'COMPLETED'
    span = next(p['evidence_span'] for p in result['topics'][0]['speaker_points'] if p['role'] == 'ANSWER')
    assert span['quote'] == snapshot['atoms'][1]['text']
    assert span['revision_ids'] == ['r2']
    assert span['classification_context_spans'][0]['quote'] == snapshot['atoms'][0]['text']


def test_model_can_retain_unclear_text_without_user_review_request():
    original, snapshot, facets, brief, request, response = request_response()
    response['assignments'][request['atoms'][0]['id']][0]['role'] = 'UNCERTAIN'
    result_facets, reviewed = apply_reviews(facets, [(400000, request, response)])
    result = materialize(original, snapshot, result_facets, [], 'sid')
    annotate_review_state(result, reviewed)
    assert result['structure_review_items'][0]['review_state'] == 'SOURCE_LIMITED'
    saved = [{'index': 400000, 'attempt': 1, 'status': 'READY', 'request': request}]
    assert review_candidates(result, snapshot, saved) == []


def test_review_rejects_invented_offsets_or_missing_reasons():
    *_, request, response = request_response()
    response['reasons'] = {}
    with pytest.raises(ValueError, match='INVALID_REVIEW_REASON'):
        validated_review(request, response)
    response['assignments'][request['atoms'][0]['id']][0]['span_index'] = 99
    with pytest.raises(ValueError, match='INVALID_SOURCE_SPAN'):
        validated_review(request, response)


def test_failed_source_check_after_review_remains_automated_work_not_source_limitation():
    original, snapshot, facets, brief, request, response = request_response()
    response['assignments'][request['atoms'][0]['id']][0].update(issue='공직선거법 위반 수사', role='ANSWER')
    replacement, reviewed = apply_reviews(facets, [(400000, request, response)])
    result = materialize(original, snapshot, replacement, [], 'sid')
    annotate_review_state(result, reviewed)
    item = result['structure_review_items'][0]
    assert item['review_state'] == 'AUTO_PENDING'
    assert result['topic_structure']['automatic_review']['status'] == 'PENDING'
    assert '공직선거법 위반 수사' not in [t['title'] for t in result['topics']]


def test_neutral_source_grounded_issue_can_replace_overbroad_catalog_title():
    original, snapshot, facets, brief, request, response = request_response()
    response['assignments'][request['atoms'][0]['id']][0].update(issue='실종자 위치추적 기술 개선 약속', role='ANSWER')
    replacement, reviewed = apply_reviews(facets, [(400000, request, response)])
    result = materialize(original, snapshot, replacement, [], 'sid')
    assert len(result['topics']) == 2
    assert not result['topic_structure']['uncertain']


def test_old_consolidation_cannot_mark_repaired_sources_complete():
    original, snapshot, facets, brief, request, response = request_response()
    source_response = {'assignments': {a['id']: [{'parent': '경찰 수사', 'issue': '위치추적', 'role': 'QUESTION', 'span_index': 0}] for a in snapshot['atoms']}}
    history_rows = [
        {'index': 0, 'attempt': 1, 'status': 'READY', 'request': {'atoms': snapshot['atoms']}, 'response': source_response},
        {'index': 100002, 'attempt': 1, 'status': 'READY', 'request': {'issues': [], 'request_profile': 'compact-20k/1'}, 'response': {}},
    ]
    c = MagicMock()
    c.execute.return_value.fetchone.side_effect = [('sid', 'version', 2, 'last-batch'), ('READY', 1, 1, 0), ('sid',)]
    with patch.object(TopicStructureRepository, 'batches', return_value=history_rows):
        result = TopicStructureRepository(c).progress({'brief_id': 'b', 'brief': original})
    assert result['status'] == 'PROCESSING'


def test_review_prompt_does_not_repeat_unverified_catalog_or_hint_titles():
    from app.services.structure_review import review_prompt
    *_, request, response = request_response()
    request['catalog'] = [{'parent': '잘못된 대분류', 'issue': '잘못 연결된 기존 제목'}]
    request['atoms'][0]['hints'] = [{'id': 'wrong', 'title': '오염된 기존 묶음 제목'}]
    request['targets'][0]['issue'] = '오염된 과거 쟁점 제목'
    prompt = review_prompt(request)
    assert '잘못 연결된 기존 제목' not in prompt
    assert '오염된 기존 묶음 제목' not in prompt
    assert '오염된 과거 쟁점 제목' not in prompt
    assert request['targets'][0]['quote'] in prompt


def test_bad_merge_target_preserves_independent_source_and_raw_response():
    from app.services.topic_structure import preserve_unmergeable_issues, consolidation_input, apply_consolidation
    _, _, facets, _ = fixture()
    facets[1]['role'] = 'ANSWER'
    facets[1]['issue'] = '별도 정책 쟁점'
    items = consolidation_input(facets)
    response = {'assignments': {x['id']: {'parent': x['parent'], 'canonical_issue_id': 'invented-id'} for x in items}}
    before = deepcopy(response)
    repaired = preserve_unmergeable_issues(facets, response)
    assert response == before
    assert repaired['source_model_response'] == before
    assert len(repaired['unmerged_issue_ids']) == 2
    assert {f['issue'] for f in apply_consolidation(facets, repaired)} == {f['issue'] for f in facets}
    response['assignments'][items[0]['id']]['canonical_issue_id'] = items[1]['id']
    response['assignments'][items[1]['id']]['canonical_issue_id'] = items[0]['id']
    assert len(preserve_unmergeable_issues(facets, response)['unmerged_issue_ids']) == 2
    response['assignments'].pop(items[0]['id'])
    with pytest.raises(ValueError, match='INCOMPLETE_CONSOLIDATION'):
        preserve_unmergeable_issues(facets, response)


def test_unlinked_document_request_is_automatic_model_work_and_keeps_other_issue():
    from app.services.structure_review import DOCUMENT_PROFILE
    original, snapshot, facets, _ = fixture()
    snapshot['atoms'][1]['text'] = '실종자 위치추적 정확도 개선에 필요한 예산 자료를 제출해 주십시오.'
    data = {'assignments': {snapshot['atoms'][1]['id']: [{'parent': '공통 후속 과제', 'issue': '자료 제출 요구', 'role': 'REQUEST', 'span_index': 0}]}}
    facets = [facets[0], *validate_response(data, [snapshot['atoms'][1]])]
    # No substantive issue mentions the request subject: routing has no candidate.
    facets[0].update(parent='학교 정책', issue='학교 급식 예산')
    brief = materialize(original, snapshot, facets, [], 'sid')
    pending = review_candidates(brief, snapshot, [])
    assert pending[0]['profile'] == DOCUMENT_PROFILE
    request = {'profile': DOCUMENT_PROFILE, 'atoms': [pending[0]['atom']], 'targets': pending[0]['targets']}
    aid = pending[0]['atom']['id']
    response = {'assignments': {aid: [{'parent': '경찰 수사', 'issue': '실종자 위치추적 정확도 개선 예산', 'role': 'REQUEST', 'span_index': 0}]},
                'reasons': {aid: '위치추적 정확도 개선 예산 자료를 요구하는 발언이다.'}}
    updated, _ = apply_reviews(facets, [(400000, request, response)])
    result = materialize(original, snapshot, updated, [], 'sid')
    assert '학교 급식 예산' in [t['title'] for t in result['topics']]
    assert not result['live_topic_lineage']['unmapped_cluster_count']
    assert any(t.get('task_kind') == 'DOCUMENT_SUBMISSION' and t['related_topic_ids'] for t in result['tasks'])


def test_substantive_uncertain_result_gets_one_independent_model_pass():
    from app.services.structure_review import VERIFY_PROFILE
    original, snapshot, facets, brief, request, response = request_response()
    aid = request['atoms'][0]['id']
    response['assignments'][aid][0]['role'] = 'UNCERTAIN'
    request['atoms'][0]['text'] *= 4
    request['targets'][0]['quote'] = request['atoms'][0]['text'][:220]
    updated, reviewed = apply_reviews(facets, [(400000, request, response)])
    result = materialize(original, snapshot, updated, [], 'sid')
    prior = [{'index':400000, 'attempt':1, 'status':'READY', 'request':request}]
    pending = review_candidates(result, snapshot, prior)
    assert pending[0]['profile'] == VERIFY_PROFILE
    verification = {**request, 'profile': VERIFY_PROFILE}
    prior.append({'index':400001, 'attempt':1, 'status':'READY', 'request':verification})
    assert not review_candidates(result, snapshot, prior)


def test_placeholder_topic_is_pending_and_reclassified_without_losing_sources():
    from app.services.structure_review import LABEL_PROFILE, placeholder_facets
    original,snapshot,facets,_=fixture()
    facets[0].update(parent='UNCERTAIN',issue='UNCERTAIN')
    result=materialize(original,snapshot,facets,[],'sid')
    annotate_review_state(result,set())
    assert result['topic_structure']['automatic_review']['invalid_label_atom_count']==1
    pending=[p for p in review_candidates(result,snapshot,[]) if p['profile']==LABEL_PROFILE]
    assert len(pending)==1
    p=pending[0];request={'profile':LABEL_PROFILE,'atoms':[p['atom']],'targets':p['targets']}
    aid=p['atom']['id'];response={'assignments':{aid:[{'parent':'실종자 보호','issue':'휴대전화 위치추적 정확도',
                  'role':'QUESTION','span_index':0}]},'reasons':{aid:'휴대전화 위치추적 범위와 실종자 발견의 어려움을 질의한다.'}}
    updated,_=apply_reviews(facets,[(400010,request,response)])
    projected=materialize(original,snapshot,updated,[],'sid')
    assert not placeholder_facets(projected)
    assert {f['evidence_id'] for f in updated}=={f['evidence_id'] for f in facets}
    assert facets[0]['issue']=='UNCERTAIN'
    response['assignments'][aid][0]['issue']='UNCERTAIN'
    with pytest.raises(ValueError,match='INVALID_TOPIC_LABEL'):
        validated_review(request,response)


def test_new_classifier_rejects_placeholder_while_legacy_response_is_readable():
    _,snapshot,_,_=fixture()
    response={'assignments':{a['id']:[{'parent':'UNCERTAIN','issue':'UNCERTAIN','role':'QUESTION','span_index':0}]
                            for a in snapshot['atoms']}}
    assert len(validate_response(response,snapshot['atoms']))==2
    with pytest.raises(ValueError,match='INVALID_TOPIC_LABEL'):
        validate_response(response,snapshot['atoms'],strict_labels=True)


def test_review_context_can_resolve_subject_but_never_replace_source_quote():
    from app.services.structure_review import review_prompt
    _, _, _, _, request, _ = request_response()
    request['context_catalog'] = [{'parent': '조직 운영', 'issue': '인건비 현황'}]
    prompt = review_prompt(request)
    assert '맥락용이며 해당 발언의 근거로 사용하지 마라' not in prompt
    assert '직접 인용은 해당 source_spans에서만 선택' in prompt
    assert '인건비 현황' in prompt
