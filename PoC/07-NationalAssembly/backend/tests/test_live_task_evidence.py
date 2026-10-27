import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from app.services.live_task_evidence import grounded_task
from app.services.summary_contract import validated_summary_items, summary_response_schema, build_summary_prompt
from app.db.summary_repository import SummaryRepository

FIXTURE = json.loads((Path(__file__).parent / 'fixtures/live-task-review/judiciary-20261026.json').read_text())


def test_all_reviewed_tasks_and_non_tasks_remain_source_grounded():
    assert len(FIXTURE) == 78
    assert sum(bool(r['task']) for r in FIXTURE) == 21
    for row in FIXTURE:
        result = validated_summary_items([{**row, 'id': row['content_hash']}], [row])[0]
        insight = result['live_insight']
        assert insight.get('task') == (row['task'] or None), row['content_hash']
        assert insight['role'] == row['role']
        if row['task']:
            assert row['text'][insight['task_evidence_start']:insight['task_evidence_end']] == row['task_evidence_quote']


@pytest.mark.parametrize('text,task', [
    ('대법원장은 이미 제청을 하셨습니다.', '대법원장 제청'),
    ('어느 말이 사실입니까?', '격려금 관리 의혹 질문'),
    ('다음은 김기표 위원님 질의해 주십시오.', '대법원장 탄핵 동의 여부 답변 요구'),
    ('보복성 수사를 왜 하지 않느냐는 질의로 정쟁을 합니다.', '보복성 수사 추진'),
    ('아직 자료를 제출할 수 없습니다.', '자료 제출'),
    ('자료를 제출하지 마십시오.', '자료 제출'),
])
def test_no_task_is_invented_from_question_procedure_negative_or_past(text, task):
    result = grounded_task({'role': 'ANSWER', 'task': task, 'task_kind': 'FOLLOW_UP_REQUEST',
                            'task_evidence_quote': text}, text, require_quote=True)
    assert result['task'] is None
    assert result['role'] == 'ANSWER'


def test_neighbor_evidence_cannot_be_attached_to_target_or_delete_answer():
    source = {'content_hash': 'a', 'text': '예 그렇습니다.',
              'conversation_context': [{'text': '예산 자료를 제출해 주십시오.'}]}
    row = dict(id='a', summary='앞선 설명에 동의했다.', topic='예산', topic_key='예산',
               role='ANSWER', task='예산 자료 제출', owners=[],
               task_kind='FOLLOW_UP_REQUEST', task_evidence_quote='예산 자료를 제출해 주십시오.')
    result = validated_summary_items([row], [source])[0]
    assert result['summary'] == row['summary']
    assert result['live_insight']['role'] == 'ANSWER'
    assert result['live_insight']['task'] is None


def test_direct_data_request_is_task_even_in_question_turn():
    text = '예산은 얼마입니까? 집행 자료를 제출해 주십시오.'
    quote = '집행 자료를 제출해 주십시오.'
    r = grounded_task({'role': 'QUESTION', 'task': '집행 자료 제출',
                       'task_kind': 'FOLLOW_UP_REQUEST', 'task_evidence_quote': quote}, text, require_quote=True)
    assert r['task'] == '집행 자료 제출'
    assert r['role'] == 'QUESTION'
    assert text[r['task_evidence_start']:r['task_evidence_end']] == quote


def test_new_contract_requires_model_kind_and_exact_target_quote():
    schema = summary_response_schema()['properties']['summaries']['items']
    assert {'task_kind', 'task_evidence_quote'} <= set(schema['required'])
    assert 'target_text' in build_summary_prompt([{'content_hash': 'a', 'text': '예'}])


def test_projection_preserves_source_and_queues_unverified_legacy_tasks():
    conn = Mock()
    legacy = {'task': '자료 제출', 'role': 'REQUEST'}
    invalid = {**legacy, 'task_kind': 'FOLLOW_UP_REQUEST', 'task_evidence_quote': '자료 제출해 주십시오.'}
    conn.execute.return_value.fetchall.return_value = [
        ('bid', 'a', '동의했다.', 'p', 'm', 'v', invalid, None),
        ('bid', 'b', '자료 제출을 요구했다.', 'p', 'm', 'old', legacy, None)]
    result = SummaryRepository(conn).summary_map(['bid'], provider='p', model='m', prompt_version='v',
        utterances=[{'broadcast_id': 'bid', 'content_hash': key, 'text': '예.'} for key in ('a','b')])
    assert result[('bid','a')]['live_insight']['task'] is None
    assert result[('bid','b')]['live_insight']['task'] is None
    assert result[('bid','b')]['summary'] == '자료 제출을 요구했다.'
    assert legacy['task'] == '자료 제출'
    assert invalid['task'] == '자료 제출'


def test_old_task_cache_is_reprocessed_but_good_questions_and_reviewed_tasks_are_reused():
    from app.services.live_task_evidence import VERSION
    conn = Mock()
    legacy = {'task':'자료 제출','role':'REQUEST'}
    approved = {**legacy,'task_validation':VERSION,'task_evidence_quote':'자료를 제출해 주십시오.'}
    conn.execute.return_value.fetchall.return_value = [
        ('legacy','자료 제출을 요구했다.',legacy),
        ('good','질의했다.',{'task':None,'role':'QUESTION'}),
        ('checked','자료 제출을 요구했다.',approved)]
    repo = SummaryRepository(conn)
    assert repo.existing_hashes('bid',['legacy','good','checked'],provider='p',model='m',prompt_version='v') == {'good','checked'}
    conn.execute.return_value.fetchall.return_value = [('legacy',legacy),('checked',approved)]
    assert repo.task_review_hashes('bid',['legacy','checked']) == {'legacy'}


def test_real_document_requests_with_colloquial_source_are_not_lost():
    for text in ['검토와 협의 내용을 내놔야 할 것입니다',
                 '장비 구축 사진을 보내 주시기 바랍니다']:
        title = '검토·협의 내용 제출' if '검토' in text else '장비 구축 사진 제출'
        insight = {'task':title,'task_kind':'FOLLOW_UP_REQUEST','task_evidence_quote':text}
        assert grounded_task(insight,text,require_quote=True)['task'] == title


def test_law_description_alone_is_not_a_new_follow_up():
    text='법에 따라 감사를 하도록 되어 있습니다.'
    assert grounded_task({'task':'감사 실시','task_kind':'FOLLOW_UP_REQUEST','task_evidence_quote':text},text,require_quote=True)['task'] is None


def test_interior_live_review_preserves_real_requests_and_excludes_questions():
    rows = json.loads((Path(__file__).parent / 'fixtures/live-task-review/interior-tasks-20261026.json').read_text())
    assert len(rows) == 92
    assert sum(bool(r['task']) for r in rows) == 29
    for row in rows:
        result = validated_summary_items([{**row, 'id': row['content_hash']}], [row])[0]
        assert result['live_insight'].get('task') == (row['task'] or None), row['content_hash']
        if row['task']:
            insight = result['live_insight']
            assert row['text'][insight['task_evidence_start']:insight['task_evidence_end']] == row['task_evidence_quote']


def test_stitched_evidence_and_neighbor_request_are_rejected():
    source = '내년부터 확대해 주셔야 될 것 같습니다. 대상 지역에 관심이 많습니다. 확대를 적극적으로 해 주셔야 될 것 같습니다.'
    for quote in ['내년부터 확대해 주셔야 될 것 같습니다. 확대를 적극적으로 해 주셔야 될 것 같습니다.',
                  '장관님께서도 청장님을 도와주시기를 부탁드리겠습니다']:
        result = grounded_task({'task':'대상 지역 확대', 'task_kind':'FOLLOW_UP_REQUEST',
                                'task_evidence_quote':quote},source,require_quote=True)
        assert result['task'] is None
