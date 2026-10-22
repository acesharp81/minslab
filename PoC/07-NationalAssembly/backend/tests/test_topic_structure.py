from copy import deepcopy

import pytest

from app.services.topic_structure import build_snapshot, validate_response, materialize, source_hash
from app.services.topic_structure import consolidation_input, apply_consolidation
from app.services.topic_structure import snapshot_evidence_items


def fixture():
    brief = {'topics': [{'id': 'old', 'title': '기존 요약', 'evidence_ids': ['u1']}],
             'tasks': [], 'live_topic_lineage': {'clusters': [
                 {'id': 'c1', 'title': '혼합된 묶음', 'utterance_ids': ['u1', 'u2'],
                  'mapping_status': 'UNMAPPED', 'final_topic_ids': [], 'utterance_count': 2}]}}
    item = {'brief_id': 'b1', 'transcript_hash': 'hash1', 'brief': brief}
    turns = [{'utterance_id': f'u{i}', 'text': text, 'content_hash': f'h{i}',
              'revision_ids': [f'r{i}'], 'segment_ids': [f's{i}']}
             for i, text in enumerate(['재판 진행을 위한 독립성을 지켜야 합니다.',
                                       '학교급식 노동자의 건강 보호가 필요합니다.'], 1)]
    return brief, build_snapshot(item, turns)


def response(snapshot, same=False):
    return {'assignments': [{'atom_id': a['id'], 'facets': [
        {'parent': '제도 개선' if same else str(i), 'issue': '같은 쟁점' if same else f'별도 쟁점 {i}',
         'role': 'QUESTION' if i == 0 else 'ANSWER', 'span_index': 0}]} for i, a in enumerate(snapshot['atoms'])]}


def test_split_mixed_cluster_without_changing_source():
    brief, snapshot = fixture()
    old = deepcopy(brief)
    facets = validate_response(response(snapshot), snapshot['atoms'])
    result = materialize(brief, snapshot, facets, [], 'revision')
    assert brief == old
    assert len(result['topics']) == 2
    assert result['live_topic_lineage']['split_cluster_count'] == 1
    assert result['live_topic_lineage']['unmapped_cluster_count'] == 0
    assert result['topics'][0]['speaker_points'][0]['evidence_span']['revision_ids'] == ['r1']


def test_question_answer_share_issue_without_losing_positions():
    brief, snapshot = fixture()
    facets = validate_response(response(snapshot, same=True), snapshot['atoms'])
    result = materialize(brief, snapshot, facets, [], 'revision')
    assert len(result['topics']) == 1
    assert {p['role'] for p in result['topics'][0]['speaker_points']} == {'QUESTION', 'ANSWER'}
    assert result['topics'][0]['evidence_ids'] == ['u1', 'u2']
    assert result['topics'][0]['authority_status'] == 'PROVISIONAL'


def test_requested_plan_submission_is_linked_with_original_source():
    brief, snapshot = fixture()
    snapshot['atoms'][0]['text'] = '수사 독립성을 지킬 방안을 만들어서 제출하시겠습니까? 취임하면 제출하겠습니다.'
    data = response(snapshot)
    data['assignments'][0]['facets'][0].update(parent='공통 후속 과제', issue='자료 제출 요구', role='REQUEST')
    result = materialize(brief, snapshot, validate_response(data, snapshot['atoms']), [], 'r')
    assert not any(t['title'] == '자료 제출 요구' for t in result['topics'])
    task = next(t for t in result['tasks'] if t.get('task_kind') == 'DOCUMENT_SUBMISSION')
    assert task['summary'] in snapshot['atoms'][0]['text']
    assert task['request_spans'][0]['revision_ids'] == ['r1']
    assert task['topic_link_status'] == 'REVIEW_REQUIRED'


def test_derived_task_uses_issue_summary_and_preserves_full_source():
    brief, snapshot = fixture()
    quote = '청주교도소 이전 타당성조사비 5억 원 반영을 건의드립니다. 주민 불편 해소가 필요합니다.'
    snapshot['atoms'][0]['text'] = quote
    data = response(snapshot)
    title = '청주교도소 이전 타당성조사비 5억 원 반영 요청'
    data['assignments'][0]['facets'][0].update(parent='교정시설 이전', issue=title, role='REQUEST')
    facets = validate_response(data, snapshot['atoms'])
    original = deepcopy((brief, snapshot, facets))
    result = materialize(brief, snapshot, facets, [], 'r')
    task, = result['tasks']
    assert task['title'] == title
    assert task['task_evidence_spans'][0]['quote'] == quote
    assert task['task_evidence_spans'][0]['revision_ids'] == ['r1']
    assert task['evidence_ids'] == ['u1']
    assert task['topic_id'] in task['related_topic_ids']
    assert (brief, snapshot, facets) == original


def test_partial_cluster_identifies_only_remaining_evidence():
    brief, snapshot = fixture()
    data = response(snapshot)
    data['assignments'][1]['facets'][0]['role'] = 'UNCERTAIN'
    result = materialize(brief, snapshot, validate_response(data, snapshot['atoms']), [], 'r')
    cluster = result['live_topic_lineage']['clusters'][0]
    assert cluster['mapping_status'] == 'REVIEW_REQUIRED'
    assert cluster['final_topic_ids']
    assert cluster['review_evidence_ids'] == ['u2']


@pytest.mark.parametrize('fault', ['quote', 'missing', 'duplicate', 'unknown'])
def test_reject_untraceable_model_output(fault):
    _, snapshot = fixture()
    data = response(snapshot)
    if fault == 'quote':
        data['assignments'][0]['facets'][0]['span_index'] = 999
    elif fault == 'missing':
        data['assignments'].pop()
    elif fault == 'duplicate':
        data['assignments'].append(data['assignments'][0])
    else:
        data['assignments'][0]['atom_id'] = 'unknown'
    with pytest.raises(ValueError):
        validate_response(data, snapshot['atoms'])


def test_procedure_uncertain_and_failed_remain_visible():
    brief, snapshot = fixture()
    data = response(snapshot)
    data['assignments'][0]['facets'][0]['role'] = 'PROCEDURE'
    data['assignments'][1]['facets'][0]['role'] = 'UNCERTAIN'
    result = materialize(brief, snapshot, validate_response(data, snapshot['atoms']), [], 'r')
    assert not result['topics']
    assert len(result['topic_structure']['procedure']) == 1
    assert len(result['topic_structure']['uncertain']) == 1
    assert result['live_topic_lineage']['unmapped_cluster_count'] == 1


def test_entire_long_turn_retained_with_source_offsets():
    brief, _ = fixture()
    text = '첫 문장부터 끝까지 보존합니다. ' * 400 + '마지막 근거 문장도 보존합니다.'
    snapshot = build_snapshot({'brief_id': 'b', 'transcript_hash': 'h', 'brief': brief},
                              [{'utterance_id': 'u1', 'text': text}])
    assert len(snapshot['atoms']) > 2
    assert snapshot['atoms'][-1]['text'].endswith('마지막 근거 문장도 보존합니다.')
    for atom in snapshot['atoms']:
        assert text[atom['offset']:atom['offset'] + len(atom['text'])] == atom['text']
    assert snapshot_evidence_items(snapshot, ['u1'])[0]['text'] == text
    assert snapshot['missing_evidence_ids'] == ['u2']


def test_changed_evidence_invalidates_derived_result():
    brief, _ = fixture()
    changed = deepcopy(brief)
    changed['topics'][0]['evidence_ids'].append('new')
    assert source_hash(brief) != source_hash(changed)


def test_whole_report_consolidation_preserves_spans_and_roles():
    brief, snapshot = fixture()
    facets = validate_response(response(snapshot), snapshot['atoms'])
    before = deepcopy(facets)
    mapping = {'assignments': [{'id': x['id'], 'parent': '공통 대상', 'issue': '통합 쟁점'}
                               for x in consolidation_input(facets)]}
    consolidated = apply_consolidation(facets, mapping)
    result = materialize(brief, snapshot, consolidated, [], 'r')
    assert len(result['topics']) == 1
    assert facets == before
    for old, new in zip(facets, consolidated):
        for key in ('quote', 'role', 'start', 'end', 'revision_ids', 'evidence_id'):
            assert old[key] == new[key]
    with pytest.raises(ValueError):
        apply_consolidation(facets, {'assignments': mapping['assignments'][:1]})


def test_structured_entity_ids_and_original_task_trace():
    brief, snapshot = fixture()
    brief['tasks'] = [{'id': 'task-1', 'title': '자료 제출 요구', 'topic_id': 'old',
                       'evidence_ids': ['u1'], 'status': 'OPEN'}]
    result = materialize(brief, snapshot, validate_response(response(snapshot), snapshot['atoms']), [], 'r')
    assert result['tasks'][0]['id'].startswith('structured-')
    assert result['tasks'][0]['source_task_id'] == 'task-1'
    assert result['live_topic_lineage']['clusters'][0]['source_cluster_id'] == 'c1'
    assert result['live_topic_lineage']['clusters'][0]['id'].startswith('structured-')


def test_broad_parent_does_not_collapse_distinct_cases():
    _, snapshot = fixture()
    facets = validate_response(response(snapshot), snapshot['atoms'])
    facets[0].update(parent='사법부 신뢰', issue='인천지방법원 개인회생 처리 지연 개선')
    facets[1].update(parent='사법부 신뢰', issue='의정부지방법원 개인회생 처리 지연 개선')
    items = consolidation_input(facets)
    data = {'assignments': {x['id']: {'parent': '개인회생', 'canonical_issue_id': items[0]['id']} for x in items}}
    result = apply_consolidation(facets, data)
    assert len({f['issue'] for f in result}) == 2


def test_constitutional_interpretations_keep_opposing_roles_in_one_issue():
    _, snapshot = fixture()
    facets = validate_response(response(snapshot), snapshot['atoms'])
    facets[0].update(parent='헌법 해석', issue='헌법 84조 소추 조항의 해석 및 내부 논의')
    facets[1].update(parent='대통령 재판', issue='현직 대통령 소추 가능성 및 형사소송법 해석')
    items = consolidation_input(facets)
    data = {'assignments': {x['id']: {'parent': x['parent'], 'canonical_issue_id': x['id']} for x in items}}
    result = apply_consolidation(facets, data)
    assert len({f['issue'] for f in result}) == 1
    assert {f['role'] for f in result} == {'QUESTION', 'ANSWER'}


def test_ppt_request_is_not_document_submission():
    brief, snapshot = fixture()
    atom = snapshot['atoms'][0]
    atom['text'] = 'PPT를 띄워 주세요. 김건희 구속기간 만료 전에 추가영장 발부가 필요한지 질문드립니다.'
    atom['hints'] = [{'id': 'c1', 'title': '김건희 구속기간 만료 및 추가영장 요청'}]
    data = response(snapshot)
    data['assignments'][0]['facets'][0].update(parent='공통 후속 과제', issue='자료 제출 요구', role='REQUEST')
    result = materialize(brief, snapshot, validate_response(data, snapshot['atoms']), [], 'r')
    assert not any(t['title'] == '자료 제출 요구' for t in result['topics'])
    assert any(t['title'] == '김건희 구속기간 만료 및 추가영장 요청' for t in result['topics'])


def test_procedural_document_request_becomes_task_under_existing_subject():
    brief, snapshot = fixture()
    snapshot['atoms'][0]['text'] = '법원행정처 격려금 지급회계서류 일체를 열람할 수 있겠습니까?'
    snapshot['atoms'][1]['text'] = '법원행정처 격려금 지급의 적정성을 확인합니다.'
    data = response(snapshot)
    data['assignments'][0]['facets'][0].update(parent='회의 진행', issue='자료 제출 요구', role='PROCEDURE')
    data['assignments'][1]['facets'][0].update(parent='대법관 격려금', issue='법원행정처 격려금 지급 적정성')
    old = deepcopy(brief)
    result = materialize(brief, snapshot, validate_response(data, snapshot['atoms']), [], 'r')
    assert brief == old
    assert len(result['topics']) == 1
    task = result['tasks'][0]
    assert task['topic_id'] == result['topics'][0]['id']
    assert task['evidence_ids'] == ['u1']
    assert task['request_spans'][0]['quote'] in snapshot['atoms'][0]['text']
    assert not result['structure_review_items']
    assert result['live_topic_lineage']['unmapped_cluster_count'] == 0


def test_unrelated_task_in_same_turn_does_not_hide_document_request():
    brief, snapshot = fixture()
    snapshot['atoms'][0]['text'] = '학교급식 노동자의 건강검진 자료를 제출해 주십시오.'
    brief['tasks'] = [{'id': 'other', 'title': '학교급식 노동자 건강 보호 제도 개선',
                       'evidence_ids': ['u1'], 'status': 'OPEN'}]
    data = response(snapshot)
    data['assignments'][0]['facets'][0].update(parent='공통 후속 과제', issue='자료 제출 요구', role='REQUEST')
    data['assignments'][1]['facets'][0].update(parent='학교급식 노동', issue='학교급식 노동자 건강 보호')
    result = materialize(brief, snapshot, validate_response(data, snapshot['atoms']), [], 'r')
    assert len(result['tasks']) == 2
    assert sum(t.get('task_kind') == 'DOCUMENT_SUBMISSION' for t in result['tasks']) == 1


@pytest.mark.parametrize('text', [
    '증인은 서면답변에 거짓이 있으면 위증의 벌을 받기로 선서합니다.',
    '지난 청문회에서 자료 제출을 요구했는데 끝까지 오지 않았습니다.',
    'PPT 자료 화면을 띄워 주세요.',
])
def test_non_requests_are_not_promoted_from_procedure(text):
    brief, snapshot = fixture()
    snapshot['atoms'][0]['text'] = text
    data = response(snapshot)
    data['assignments'][0]['facets'][0].update(parent='회의 진행', issue='진행 발언', role='PROCEDURE')
    result = materialize(brief, snapshot, validate_response(data, snapshot['atoms']), [], 'r')
    assert not result['tasks']


def test_old_common_parent_is_restored_without_changing_issue_id():
    from app.services.topic_structure import digest
    brief, snapshot = fixture()
    facets = validate_response(response(snapshot), snapshot['atoms'])
    facets[0].update(parent='공통 후속 과제', source_parent='사법 독립', issue='재판 독립성', role='QUESTION')
    facets[1].update(parent='공통 후속 과제', source_parent='학교급식 노동', issue='학교급식 노동자 건강 보호', role='ANSWER')
    result = materialize(brief, snapshot, facets, [], 'r')
    assert {g['title'] for g in result['topic_groups']} == {'사법 독립', '학교급식 노동'}
    assert result['topics'][0]['id'] == 'structured-topic-' + digest(['공통 후속 과제', '재판 독립성'])[:16]
