from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from app.db.summary_repository import SummaryRepository
from app.services.summary_contract import validated_summary_items
from app.services.summary_language import language_error, summary_language_error, utterance_sources
from app.services.summary_cache import cache_missing_summaries


@pytest.mark.parametrize('bad', [
    '중앙선거관리위원회委員長직무대행 인사말',
    '중앙선거관리위원회委员长직무대행 인사말咕',
    '박덕_minimumbleissen으로 의사진행 발언 요청',
    '박requencies委员의 의사진행 발언 부탁',
    '국정감사 proceeding 중 인사말_ordinance 요청',
])
def test_rejects_reported_corruption_without_rewriting_source(bad):
    source = '박덕흠 위원님 의사진행발언해 주시기 바랍니다'
    assert language_error(bad, source)
    assert source == '박덕흠 위원님 의사진행발언해 주시기 바랍니다'


@pytest.mark.parametrize('field', ['summary', 'topic', 'topic_key', 'task', 'owners'])
def test_every_generated_display_field_is_checked(field):
    row = dict(id='a', summary='박주민 위원에게 의사진행 발언을 요청했다.',
               topic='의사진행 발언 안내', topic_key='의사진행 발언', role='STATEMENT',
               task='', owners=[])
    row[field] = ['국회委员'] if field == 'owners' else '국회委员 의사진행 발언'
    assert validated_summary_items([row], [{'content_hash': 'a',
        'text': '다음은 박주민 위원님 의사진행발언해 주시기 바랍니다'}]) == []


def test_good_item_survives_partial_bad_response_and_legitimate_acronyms_survive():
    good = dict(id='a', summary='CCTV와 AI, RE100 관련 예산을 질의했다.',
                topic='CCTV 예산', topic_key='CCTV 예산', role='QUESTION', task='', owners=[])
    bad = {**good, 'id': 'b', 'task': 'Prepare improvement measures'}
    source = [{'content_hash': key, 'text': 'AI 예산 질문', 'conversation_context': [
        {'text': 'CCTV 및 RE100, OpenAI를 논의합니다.'}]} for key in ['a', 'b']]
    result = validated_summary_items([good, bad], source)
    assert [r['content_hash'] for r in result] == ['a']
    assert not language_error('OpenAI와 CCTV의 활용', source[0]['conversation_context'][0]['text'])


def test_corrupted_input_does_not_authorize_hanja_in_generated_summary():
    assert language_error('위원회委员에게 요청했다.', '위원회委员 질의') == 'NON_KOREAN_SCRIPT'
    assert summary_language_error('박덕_minimumbleissen 발언 요청', {})


def test_cached_corrupt_rows_are_not_reused_or_published():
    conn = Mock()
    conn.execute.return_value.fetchall.return_value = [
        ('bad', '위원회委员에게 요청했다.', {}), ('good', '자료 제출을 요구했다.', {})]
    assert SummaryRepository(conn).existing_hashes('bid', ['bad', 'good'],
        provider='x', model='m', prompt_version='v') == {'good'}
    conn.execute.return_value.fetchall.return_value = [
        ('bid', 'bad', '박덕_minimumbleissen 요청', 'x', 'm', 'v', {}, None),
        ('bid', 'good', '자료 제출을 요구했다.', 'x', 'm', 'v', {}, None)]
    assert set(SummaryRepository(conn).summary_map(['bid'], provider='x', model='m',
        prompt_version='v')) == {('bid', 'good')}


def test_old_latin_only_corruption_is_rechecked_against_raw_context():
    conn = Mock()
    conn.execute.return_value.fetchall.return_value = [
        ('a', '예산 budgets 편성을 질의했다.', {}),
        ('b', 'CCTV 예산 편성을 질의했다.', {})]
    repo = SummaryRepository(conn)
    assert repo.existing_hashes('bid', ['a', 'b'], provider='p', model='m',
        prompt_version='v', source_text_by_hash={
            'a': '예산을 질의합니다.', 'b': 'CCTV 예산을 질의합니다.'}) == {'b'}
    conn.execute.return_value.fetchall.return_value = [
        ('bid', 'a', '예산 budgets 편성을 질의했다.', 'p', 'm', 'v', {}, None)]
    assert not repo.summary_map(['bid'], provider='p', model='m', prompt_version='v',
        utterances=[{'broadcast_id': 'bid', 'content_hash': 'a', 'text': '예산을 질의합니다.'}])


def test_source_allowlist_cannot_be_polluted_by_ai_text_or_another_broadcast():
    sources = utterance_sources([
        {'broadcast_id': 'one', 'content_hash': 'a', 'text': '예산을 질의합니다.',
         'summary': 'budgets 예산 질의'},
        {'broadcast_id': 'two', 'content_hash': 'b', 'text': 'CCTV budgets 관련 질의'},
    ])
    assert language_error('budgets 예산 질의', sources[('one', 'a')])
    assert not language_error('CCTV budgets 관련 질의', sources[('two', 'b')])


def test_rejected_response_is_archived_and_singleton_retry_is_bounded():
    repo = Mock()
    repo.existing_hashes.return_value = set()
    repo.deferred_hashes.return_value = set()
    client = Mock(provider='test', model='fixture', prompt_version='v')
    metadata = {'rejected_ids': ['a'], 'raw_response': '위원회委员 발언'}
    client.summarize.return_value = SimpleNamespace(items=[], usage_metadata=metadata)
    with patch('app.services.summary_cache.SummaryRepository', return_value=repo):
        stats = cache_missing_summaries(Mock(), 'bid', [{'content_hash': 'a',
            'text': '자료 제출을 요구합니다.'}], client, include_short=True)
    assert stats['failed'] == 1
    client.summarize.assert_called_once()
    repo.save_many.assert_not_called()
    repo.record_rejected_response.assert_called_once()
    assert repo.record_rejected_response.call_args.kwargs['response'] == metadata
    assert repo.record_failure.call_args.kwargs['retry_hours'] == 5 / 60
