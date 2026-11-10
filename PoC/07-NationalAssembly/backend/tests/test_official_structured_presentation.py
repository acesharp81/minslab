from copy import deepcopy
from contextlib import contextmanager
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.services.official_structured_presentation import official_structured_view
from app.services.report_presentation import narrative_projection

QUOTE = '국가채무 증가를 줄이기 위하여 미래대응기금의 재원을 적립하는 방안을 검토하겠습니다.'


def fixture():
    structured = {
        'topic_structure': {'source_brief_id': 'b', 'revision_id': 'r', 'source_hash': 'h', 'consolidation_status': 'COMPLETED'},
        'topics': [{'id': 'structured-topic-a', 'title': '기금 운용', 'evidence_ids': ['u'],
                    'speaker_points': [{'id': 'structured-point-a', 'evidence_ids': ['u'], 'evidence_span': {'quote': QUOTE}}]}],
        'topic_groups': [{'id': 'structured-group-a', 'title': '재정', 'topic_ids': ['structured-topic-a']}],
        'report_summary': {'topics': [{'id': 'structured-summary-a', 'source_structured_topic_id': 'structured-topic-a',
                                      'title': '기금 운용', 'summary': '기금의 재원 적립 방안을 검토하기로 했다.', 'evidence_ids': ['u'],
                                      'speaker_points': [{'id': 'structured-summary-point-a', 'summary': '재원 적립을 검토한다.',
                                                          'evidence_ids': ['u'], 'source_point_ids': ['structured-point-a']}]}],
                           'topic_groups': [{'id': 'sg', 'title': '재정', 'topic_ids': ['structured-summary-a']}]},
        'tasks': [{'id': 'structured-task-a', 'source_task_id': 'task-a', 'title': '기금 검토',
                   'related_topic_ids': ['structured-topic-a'], 'evidence_ids': ['u']}],
    }
    official = {'headline': '공식 대조 개요', 'summary': '대조 반영 요약',
                'topics': [{'id': 'topic-a', 'title': '수정 주제', 'summary': '공식 대조 수정 내용', 'evidence_ids': ['u'],
                            'official_evidence_ids': ['o'], '_official_diffs': {'summary': [{'kind': 'changed', 'text': '수정 내용'}]}}],
                'tasks': [{'id': 'task-a', 'title': '공식 수정된 기금 검토', 'official_evidence_ids': ['o']},
                          {'id': 'official-task-new', 'title': '산림청 추가 요구', 'topic_id': 'topic-a', 'official_evidence_ids': ['o']}],
                'topic_groups': [{'id': 'g', 'title': '기존 그룹', 'topic_ids': ['topic-a']}]}
    rows = [{'utterance_id': 'o', 'text': QUOTE, 'speaker_name': '김위원'}]
    changes = [{'entity_type': 'topic', 'entity_id': 'topic-a', 'operation': 'UPDATE'}]
    return official, structured, rows, changes


def test_detail_hierarchy_sources_and_official_corrections_are_all_preserved():
    official, structured, rows, changes = fixture()
    before = deepcopy((official, structured))
    result = official_structured_view(official, structured, 'b', rows, changes)
    narrative = narrative_projection(result)
    assert (official, structured) == before
    assert result['headline'] == official['headline']
    assert narrative['topic_groups'][0] == structured['report_summary']['topic_groups'][0]
    topic = narrative['topics'][0]
    assert topic['summary'] == structured['report_summary']['topics'][0]['summary']
    assert topic['official_evidence_ids'] == ['o']
    assert topic['authority_status'] == 'PROVISIONAL'
    assert topic['speaker_points'][0]['speaker_label'] == '김위원'
    assert result['tasks'][0]['title'] == '공식 수정된 기금 검토'
    assert result['tasks'][0]['related_topic_ids'] == ['structured-topic-a']
    assert result['tasks'][1]['comparison_topic_id'] == 'topic-a'
    assert result['tasks'][1]['topic_id'] == 'structured-official-task-additions'
    assert any(t.get('_official_diffs') for t in narrative['topics'])
    assert {t['id'] for t in result['tasks']} == {'structured-task-a', 'official-task-new'}
    assert 'official-task-new' in narrative['topics'][-1]['task_ids']
    assert result['official_detail_presentation']['additional_llm_calls'] == 0


@pytest.mark.parametrize('damage', ['short', 'ambiguous', 'different_number', 'missing_source'])
def test_only_unique_substantive_source_quotes_get_official_links(damage):
    official, structured, rows, changes = fixture()
    if damage == 'short': structured['topics'][0]['speaker_points'][0]['evidence_span']['quote'] = '검토하겠습니다'
    elif damage == 'ambiguous': rows.append({**rows[0], 'utterance_id': 'other', 'speaker_name': '다른위원'})
    elif damage == 'different_number': rows[0]['text'] = '1조 원 예산을 확대합니다.'
    else: rows = []
    result = official_structured_view(official, structured, 'b', rows, changes)
    topic = result['report_summary']['topics'][0]
    assert topic['official_evidence_ids'] == []
    assert topic['summary_verification'] == 'LIVE_SOURCE_ONLY'
    assert topic['speaker_points'][0]['speaker_label'] == '화자 미확인'


def test_stale_structure_does_not_replace_official_comparison():
    official, structured, rows, changes = fixture()
    assert official_structured_view(official, structured, 'other', rows, changes) is official


def test_decimal_changes_are_not_accepted_as_exact_official_evidence():
    official, structured, rows, changes = fixture()
    structured['topics'][0]['speaker_points'][0]['evidence_span']['quote'] = QUOTE + '증가율은 1.5%로 설명하였습니다'
    rows[0]['text'] = QUOTE + '증가율은 15%로 설명하였습니다'
    result = official_structured_view(official, structured, 'b', rows, changes)
    assert result['report_summary']['topics'][0]['official_evidence_ids'] == []


@pytest.mark.parametrize('damage', [None, 'hash', 'position', 'snapshot', 'ambiguous'])
def test_short_facet_uses_only_verified_parent_source_for_speaker(damage):
    official, structured, rows, changes = fixture()
    quote = '검토하겠습니다'
    start = QUOTE.index(quote)
    span = {'atom_id': 'a', 'evidence_id': 'u', 'quote': quote, 'start': start,
            'end': start + len(quote), 'content_hash': 'content'}
    structured['topics'][0]['speaker_points'][0]['evidence_span'] = span
    snapshot = {'brief_id': 'b', 'source_hash': 'h', 'atoms': [
        {'id': 'a', 'evidence_id': 'u', 'text': QUOTE, 'offset': 0, 'content_hash': 'content'}]}
    if damage == 'hash': span['content_hash'] = 'changed'
    elif damage == 'position': span['start'] -= 1
    elif damage == 'snapshot': snapshot['source_hash'] = 'other'
    elif damage == 'ambiguous': rows.append({**rows[0], 'utterance_id': 'other', 'speaker_name': '다른위원'})
    result = official_structured_view(official, structured, 'b', rows, changes, snapshot)
    point = result['report_summary']['topics'][0]['speaker_points'][0]
    assert point['speaker_official'] is (damage is None)
    assert point['speaker_label'] == ('김위원' if damage is None else '화자 미확인')


def test_full_snapshot_speaker_does_not_change_live_source_authority():
    from app.services.official_structured_presentation import present_structured_source_speakers
    _, _, rows, _ = fixture()
    items = [{'text': QUOTE, 'speaker_label': '화자 미확인', 'authority_status': 'PROVISIONAL'},
             {'text': '예', 'speaker_label': '화자 미확인', 'authority_status': 'PROVISIONAL'}]
    result = present_structured_source_speakers(items, rows)
    assert items[0]['speaker_label'] == '화자 미확인'
    assert result[0]['speaker_label'] == '김위원'
    assert result[0]['authority_status'] == 'PROVISIONAL'
    assert result[1]['speaker_label'] == '화자 미확인'


@pytest.mark.parametrize('view', ['official', 'structured'])
def test_evidence_endpoint_separates_official_rows_from_live_snapshot(view):
    from app.main import ended_live_broadcast_brief_evidence
    official, structured, rows, changes = fixture()
    snapshot = {'atoms': [{'id': 'a', 'evidence_id': 'u', 'text': QUOTE, 'offset': 0,
                          'content_hash': 'h', 'revision_ids': ['r'], 'segment_ids': ['s']}]}
    @contextmanager
    def connection(_): yield MagicMock()
    with patch('app.main.connect', connection), patch('app.main.MeetingBriefRepository') as briefs, \
         patch('app.main.TopicStructureRepository') as structures, patch('app.main.LiveRepository') as live, \
         patch('app.main.OfficialIntegrationRepository') as integrations, patch('app.main.official_evidence_items') as evidence:
        briefs.return_value.latest.return_value = {'brief_id': 'b', 'brief': official}
        structures.return_value.ready_current.return_value = structured
        structures.return_value.snapshot.return_value = snapshot
        live.return_value.snapshot_official_source_matches.return_value = []
        live.return_value.broadcast_official_context.return_value = {'official_document_id': 'doc'}
        live.return_value.broadcast_official_material.return_value = {'document': {'document_id': 'doc'}, 'utterances': rows}
        integrations.return_value.latest_for_brief_document.return_value = {'status': 'READY', 'integrated_brief': official, 'changes': []}
        evidence.return_value = [{'utterance_id': 'o', 'text': QUOTE, 'speaker_label': '김위원'}]
        response = ended_live_broadcast_brief_evidence(uuid4(), 'summary_topic', 'structured-summary-a', view)
    assert response['items'][0]['text'] == QUOTE
    assert response['authority_status'] == 'PROVISIONAL'
    assert len(response['official_items']) == (1 if view == 'official' else 0)
    if view == 'official':
        assert response['official_items'][0]['comparison_status'] == 'STYLE_ONLY'
        assert response['official_items'][0]['diff_spans']
        assert response['official_items'][0]['live_text'] == QUOTE
        assert response['official_reference_count'] == 1


def test_reconciled_source_links_editing_variants_without_changing_source():
    from app.services.official_structured_presentation import reconciled_atom_sources
    from app.services.official_structured_presentation import supported_reconciled_sources, _exact_text
    quote = '예 그래서 당연히 지금 3대 메가 프로젝트는 성장 관련된 부분들이고 양극화에서는 3대 민생 프로젝트 균형 있게 진행해야 된다고 생각합니다'
    official_text = '예, 그래서 당연히 지금 3대 메가프로젝트는 성장 관련된 부분들이고 양극화 해소는 3대 민생 프로젝트를 균형 있게 진행해야 된다고 생각합니다.'
    sources = [{'utterance_id': 'o', '_compact_text': _exact_text(official_text)}]
    atoms = {'a': {'id': 'a', 'text': quote, 'revision_ids': ['r'], 'segment_ids': ['s:1']}}
    match = {'segment_id': 's:1', 'revision_id': 'r', 'text': quote,
             'official_reconciliation': {'status': 'MATCHED', 'official_utterance_id': 'o'}}
    assert reconciled_atom_sources(atoms, [match], sources) == {'a': ['o']}
    assert supported_reconciled_sources(quote, ['o'], sources) == (['o'], True)
    assert reconciled_atom_sources(atoms, [{**match, 'revision_id': 'old'}], sources) == {'a': []}
    assert reconciled_atom_sources(atoms, [{**match, 'segment_id': 's:0'}], sources) == {'a': []}
    assert reconciled_atom_sources(atoms, [{**match, 'text': '다른 내용'}], sources) == {'a': []}
    assert reconciled_atom_sources(atoms, [match], []) == {'a': []}
    assert supported_reconciled_sources('생각합니다 그래서', ['o'], sources) == ([], False)


@pytest.mark.parametrize('replacement', ['1.5%', '하지 않겠습니다'])
def test_source_navigation_does_not_attribute_changed_numbers_or_negation(replacement):
    from app.services.official_structured_presentation import supported_reconciled_sources, _exact_text
    prefix = '국가의 재정 지속 가능성을 위해 예산을 신중하게 편성하고 추가 심사를 거쳐 '
    suffix = ' 그리고 세부 집행 계획을 공개하여 위원회에 제출하는 절차를 진행하겠습니다.'
    original = '15%' if replacement == '1.5%' else '하겠습니다'
    quote = prefix + original + suffix
    sources = [{'utterance_id': 'o', '_compact_text': _exact_text(prefix + replacement + suffix)}]
    refs, named = supported_reconciled_sources(quote, ['o'], sources)
    assert refs == ['o']  # Related official source remains available to inspect.
    assert named is False


def test_partial_reconciliation_never_labels_an_entire_summary_with_one_speaker():
    official, structured, rows, changes = fixture()
    extra = ' 다른 발언자가 주장한 내용은 이 원문에 포함되지 않았습니다.'
    quote = QUOTE + extra
    span = {'atom_id': 'a', 'evidence_id': 'u', 'quote': quote, 'start': 0,
            'end': len(quote), 'content_hash': 'content'}
    structured['topics'][0]['speaker_points'][0]['evidence_span'] = span
    snapshot = {'brief_id': 'b', 'source_hash': 'h', 'atoms': [
        {'id': 'a', 'evidence_id': 'u', 'text': quote, 'offset': 0, 'content_hash': 'content',
         'revision_ids': ['r'], 'segment_ids': ['s']}]}
    matches = [{'segment_id': 's', 'revision_id': 'r', 'text': quote,
                'official_reconciliation': {'status': 'MATCHED', 'official_utterance_id': 'o'}}]
    result = official_structured_view(official, structured, 'b', rows, changes, snapshot, matches)
    point = result['report_summary']['topics'][0]['speaker_points'][0]
    assert point['official_evidence_ids'] == ['o']
    assert point['speaker_official'] is False
    assert point['speaker_match_status'] == 'PARTIAL'


def test_snapshot_loader_does_not_apply_whole_revision_speaker_to_other_piece():
    from app.db.live_repository import LiveRepository
    from app.services.transcript_presentation import utterance_content_hash
    revision, segment, document, broadcast = uuid4(), uuid4(), uuid4(), uuid4()
    parts = [{'speaker': 'a', 'text': QUOTE}, {'speaker': 'b', 'text': '그 의견에는 동의하지 않습니다.'}]
    connection = MagicMock()
    connection.execute.return_value.fetchall.return_value = [(segment, revision, QUOTE, {'speaker_segments': parts})]
    whole = {revision: {'status': 'MATCHED', 'official_utterance_id': 'wrong-whole'}}
    specific = {revision: {0: {'status': 'MATCHED', 'official_utterance_id': 'o',
                              'source_text_hash': utterance_content_hash(QUOTE)}}}
    repo = LiveRepository(connection)
    with patch.object(repo, 'broadcast_reconciliation_details', return_value=whole), \
         patch.object(repo, 'broadcast_part_reconciliation_details', return_value=specific):
        result = repo.snapshot_official_source_matches(broadcast, document, {'atoms': [{'revision_ids': [str(revision)]}]})
        assert len(result) == 1
        assert result[0]['segment_id'] == f'{segment}:0'
        assert result[0]['official_reconciliation']['official_utterance_id'] == 'o'
        specific[revision][0]['source_text_hash'] = 'stale'
        assert repo.snapshot_official_source_matches(broadcast, document, {'atoms': [{'revision_ids': [str(revision)]}]}) == []


def comparison_fixture():
    prefix = '지역 경제 회복을 위한 사업의 세부 집행 계획을 마련하고 위원회에 보고하겠습니다. '
    before = prefix + '예산 20억 원을 편성합니다. 추가로 현장 의견도 받겠습니다.'
    after = prefix + '예산 30억 원을 편성합니다.'
    items = [{'utterance_id': 'u', 'text': before, 'segment_ids': ['s:0'], 'revision_ids': ['r']}]
    matches = [{'segment_id': 's:0', 'revision_id': 'r', 'text': before,
                'official_reconciliation': {'status': 'MATCHED', 'official_utterance_id': 'o'}}]
    rows = [{'utterance_id': 'o', 'speaker_name': '김위원', 'sequence_number': 1, 'text': after}]
    return items, matches, rows


def test_structured_official_diff_restores_changes_and_live_only_text():
    from app.services.official_structured_presentation import structured_official_comparisons
    items, matches, rows = comparison_fixture()
    before = deepcopy(items)
    result = structured_official_comparisons(items, matches, rows, ['o'], publication_stage='TEMPORARY', authority_status='PROVISIONAL')
    assert items == before
    assert result[0]['live_text'] == items[0]['text']
    assert result[0]['comparison_status'] == 'COMPARED'
    assert result[0]['change_count'] > 0
    assert any(s.get('before') for s in result[0]['diff_spans'])
    assert result[0]['live_only_fragments']
    assert ''.join(s['text'] for s in result[0]['diff_spans']) == rows[0]['text']


def test_structured_diff_uses_complete_turn_including_continuation():
    from app.services.official_structured_presentation import structured_official_comparisons
    items, matches, rows = comparison_fixture()
    matches[0]['text'] = items[0]['text'][:50]
    result = structured_official_comparisons(items, matches, rows, ['o'], publication_stage='FINAL', authority_status='OFFICIAL')
    assert result[0]['live_text'] == items[0]['text']
    assert result[0]['authority_status'] == 'OFFICIAL'


@pytest.mark.parametrize('damage', ['revision', 'part', 'text', 'document', 'unmatched'])
def test_structured_diff_does_not_compare_unrelated_or_stale_baseline(damage):
    from app.services.official_structured_presentation import structured_official_comparisons
    items, matches, rows = comparison_fixture()
    if damage == 'revision': matches[0]['revision_id'] = 'old'
    elif damage == 'part': matches[0]['segment_id'] = 's:1'
    elif damage == 'text': matches[0]['text'] = '다른 발언입니다.'
    elif damage == 'document': matches[0]['official_reconciliation']['official_utterance_id'] = 'old-document-source'
    else: matches[0]['official_reconciliation']['status'] = 'CONFLICT'
    result = structured_official_comparisons(items, matches, rows, ['o'], publication_stage='TEMPORARY', authority_status='PROVISIONAL')
    assert result[0]['comparison_status'] == 'OFFICIAL_ONLY'
    assert result[0]['change_count'] == 0
    assert result[0]['live_text'] == ''


def test_structured_diff_splits_mixed_speakers_and_preserves_source_order():
    from app.services.official_structured_presentation import structured_official_comparisons
    a = '지방 재정의 안정성을 높이기 위해 사업별 집행 상황을 꼼꼼하게 점검하겠습니다.'
    b = '청년들의 주거 문제를 해결하기 위해 공공 주택 공급 계획을 조속하게 마련하겠습니다.'
    c = '또한 지역의 교통 개선 사업도 지방 정부와 협의하여 추진하도록 하겠습니다.'
    items = [{'utterance_id': 'mixed', 'text': a + ' ' + b + ' ' + c,
              'segment_ids': ['s:0', 's:1', 's:2'], 'revision_ids': ['r']}]
    matches = [{'segment_id': f's:{i}', 'revision_id': 'r', 'text': text,
                'official_reconciliation': {'status': 'MATCHED', 'official_utterance_id': oid}}
               for i, text, oid in [(2, c, 'a'), (1, b, 'b'), (0, a, 'a')]]
    rows = [{'utterance_id': 'a', 'speaker_name': '가위원', 'text': a + ' ' + c},
            {'utterance_id': 'b', 'speaker_name': '나위원', 'text': b}]
    result = structured_official_comparisons(items, matches, rows, ['a', 'b'], publication_stage='TEMPORARY', authority_status='PROVISIONAL')
    assert result[0]['live_text'] == a + ' ' + c
    assert result[1]['live_text'] == b
    assert all(r['change_count'] == 0 for r in result)


def test_partial_caption_does_not_turn_missing_context_into_official_additions():
    from app.services.official_structured_presentation import structured_official_comparisons
    fragment = '지방 재정의 안정성을 높이기 위해 사업별 집행 상황을 점검하겠습니다.'
    unrelated = '이어서 완전히 다른 주제인 인공지능 교육 지원 예산에 대한 질의를 하겠습니다.'
    official = '지역의 재정 지원 정책에 대해 설명드리겠습니다. ' + fragment + ' 또한 향후 진행 상황을 지역 주민들에게 충분히 알려 드리도록 하겠습니다.'
    items = [{'utterance_id': 'u', 'text': fragment + ' ' + unrelated, 'segment_ids': ['s:0'], 'revision_ids': ['r']}]
    matches = [{'segment_id': 's:0', 'revision_id': 'r', 'text': fragment,
                'official_reconciliation': {'status': 'MATCHED', 'official_utterance_id': 'o'}}]
    rows = [{'utterance_id': 'o', 'speaker_name': '김위원', 'text': official}]
    result = structured_official_comparisons(items, matches, rows, ['o'], publication_stage='TEMPORARY', authority_status='PROVISIONAL')
    assert result[0]['comparison_status'] == 'PARTIAL_BASELINE'
    assert result[0]['change_count'] == 0
    assert result[0]['live_only_fragments'] == []
    assert result[0]['diff_spans'] == [{'kind': 'equal', 'text': official}]
