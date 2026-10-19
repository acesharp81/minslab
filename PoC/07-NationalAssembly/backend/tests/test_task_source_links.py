from copy import deepcopy

from app.services.task_source_links import direct_task_source_links, verified_task_spans


def fixture():
    opening = '법제처 업무에 관심을 주셔서 감사합니다 '
    commitment = '지적해 주시는 사항은 빠짐없이 검토하여 업무 개선의 기회로 삼겠습니다'
    text = opening + commitment + ' 다음은 간부를 소개합니다'
    atom = {'id': 'a', 'evidence_id': 'u', 'offset': 0, 'text': text,
            'content_hash': 'hash', 'revision_ids': ['r'], 'segment_ids': ['s']}
    topics = {
        'intro': {'title': '법제처 간부 소개', 'evidence_ids': ['u'], 'speaker_points': []},
        'improve': {'title': '업무 개선 의지 표명', 'evidence_ids': ['u'], 'speaker_points': []},
        'budget': {'title': '법제처 예산 운영', 'evidence_ids': ['u'], 'speaker_points': []},
    }
    task = {'title': '국정감사 지적사항 검토 및 업무 개선 반영', 'evidence_ids': ['u']}
    return task, topics, {'atoms': [atom]}, commitment


def test_shared_utterance_does_not_attach_task_to_every_issue():
    task, topics, snapshot, quote = fixture()
    old = deepcopy(snapshot)
    ids, spans = direct_task_source_links(task, topics, snapshot)
    assert ids == ['improve']
    assert spans[0]['quote'] == quote
    assert snapshot == old
    assert snapshot['atoms'][0]['text'][spans[0]['start']:spans[0]['end']] == quote


def test_general_interest_is_not_an_improvement_commitment():
    task, topics, snapshot, _ = fixture()
    snapshot['atoms'][0]['text'] = '법제처 업무 개선 상황에 관심을 보내 주셔서 감사합니다'
    assert direct_task_source_links(task, topics, snapshot) == ([], [])


def test_no_match_does_not_select_an_arbitrary_issue():
    task, topics, snapshot, _ = fixture()
    task['title'] = '군사법원 군 인권 제도 정비'
    assert direct_task_source_links(task, topics, snapshot) == ([], [])


def test_evidence_api_spans_require_exact_text_hash_and_revision():
    task, topics, snapshot, _ = fixture()
    _, spans = direct_task_source_links(task, topics, snapshot)
    task['task_evidence_spans'] = spans
    source = {**snapshot['atoms'][0], 'utterance_id': 'u'}
    assert verified_task_spans(task, [source]) == spans
    for field, value in [('text', '다른 원문'), ('content_hash', 'changed'), ('revision_ids', ['new'])]:
        assert verified_task_spans(task, [{**source, field: value}]) == []
