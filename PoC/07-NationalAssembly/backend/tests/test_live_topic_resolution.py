from copy import deepcopy

import pytest

from app.services.live_topic_resolution import build_live_topic_resolution


def fixture():
    legacy = {'live_topic_lineage': {'clusters': [
        {'id': 'c1', 'title': '실시간 논의', 'utterance_ids': ['u1'], 'mapping_status': 'UNMAPPED'},
        {'id': 'c2', 'title': '진행 안내', 'utterance_ids': ['u2'], 'mapping_status': 'UNMAPPED'},
        {'id': 'c3', 'title': '혼합 논의', 'utterance_ids': ['u3', 'u4'], 'mapping_status': 'SYNTHESIS_ASSIGNED'},
    ]}}
    structure = {
        'topic_structure': {'source_brief_id': 'b1', 'consolidation_status': 'COMPLETED',
                            'revision_id': 'revision', 'source_hash': 'hash'},
        'topics': [{'id': 't1', 'title': '연결 쟁점'}],
        'live_topic_lineage': {'clusters': [
            {'id': 's1', 'source_cluster_id': 'c1', 'utterance_ids': ['u1'],
             'mapping_status': 'STRUCTURED_EVIDENCE', 'final_topic_ids': ['t1']},
            {'id': 's2', 'source_cluster_id': 'c2', 'utterance_ids': ['u2'],
             'mapping_status': 'PROCEDURAL', 'final_topic_ids': []},
            {'id': 's3', 'source_cluster_id': 'c3', 'utterance_ids': ['u3', 'u4'],
             'mapping_status': 'REVIEW_REQUIRED', 'final_topic_ids': ['t1'],
             'review_evidence_ids': ['u4']},
        ]},
        'structure_review_items': [
            {'id': 'r4', 'title': '확인 필요', 'summary': '모호한 원문', 'role': 'UNCERTAIN', 'evidence_ids': ['u4']},
            {'id': 'r2', 'title': '진행', 'summary': '진행 안내', 'role': 'PROCEDURE', 'evidence_ids': ['u2']},
        ],
    }
    return legacy, structure


def test_preserves_official_lineage_and_exposes_provisional_resolution():
    legacy, structure = fixture()
    before = deepcopy(legacy)
    result = build_live_topic_resolution(legacy, structure, 'b1')
    assert legacy == before
    assert result['authority_status'] == 'PROVISIONAL'
    assert result['legacy_pending_count'] == 2
    assert result['legacy_pending_linked_count'] == 1
    assert result['legacy_pending_procedural_count'] == 1
    assert result['legacy_pending_review_count'] == 0
    # A partial cluster that was formerly linked must still be visible.
    assert result['review_count'] == 1
    assert result['entries'][2]['review_evidence_ids'] == ['u4']
    assert result['entries'][2]['review_items'][0]['id'] == 'r4'


@pytest.mark.parametrize('damage', ['source', 'duplicate', 'missing_topic'])
def test_unverified_bridge_is_not_shown_as_resolved(damage):
    legacy, structure = fixture()
    first = structure['live_topic_lineage']['clusters'][0]
    if damage == 'source':
        first['utterance_ids'] = ['another-turn']
    elif damage == 'duplicate':
        structure['live_topic_lineage']['clusters'].append(deepcopy(first))
    else:
        first['final_topic_ids'] = ['absent-topic']
    result = build_live_topic_resolution(legacy, structure, 'b1')
    assert result['entries'][0]['status'] == 'UNRESOLVED'
    assert result['entries'][0]['topics'] == []
    assert result['legacy_pending_review_count'] == 1


@pytest.mark.parametrize('damage', ['brief', 'incomplete', 'revision'])
def test_stale_or_incomplete_structure_is_not_used(damage):
    legacy, structure = fixture()
    if damage == 'brief': structure['topic_structure']['source_brief_id'] = 'other'
    if damage == 'incomplete': structure['topic_structure']['consolidation_status'] = 'PENDING'
    if damage == 'revision': structure['topic_structure']['revision_id'] = ''
    assert build_live_topic_resolution(legacy, structure, 'b1') is None


def test_reviewed_source_fragments_are_not_queued_and_partial_links_are_counted():
    legacy, structure = fixture()
    before = deepcopy((legacy, structure))
    structure['structure_review_items'][0]['review_state'] = 'SOURCE_LIMITED'
    result = build_live_topic_resolution(legacy, structure, 'b1')
    assert result['entries'][2]['status'] == 'PARTIAL'
    assert result['entries'][2]['review_state'] == 'SOURCE_LIMITED'
    assert result['linked_cluster_count'] == 2
    assert result['source_limited_cluster_count'] == 1
    assert result['source_limited_evidence_count'] == 1
    assert result['pending_review_count'] == 0
    assert result['review_count'] == 1  # compatible historical mapping counter
    assert legacy == before[0]
    assert structure['topics'] == before[1]['topics']


@pytest.mark.parametrize('damage', ['missing_review', 'pending_review', 'failed_review', 'uncovered_evidence', 'stale_evidence'])
def test_unfinished_or_unverified_reviews_are_never_hidden_as_source_limited(damage):
    legacy, structure = fixture()
    review = structure['structure_review_items'][0]
    review['review_state'] = 'SOURCE_LIMITED'
    if damage == 'missing_review':
        structure['structure_review_items'] = []
    elif damage == 'pending_review':
        review['review_state'] = 'AUTO_PENDING'
    elif damage == 'failed_review':
        review['review_state'] = 'ANALYSIS_FAILED'
    elif damage == 'uncovered_evidence':
        structure['live_topic_lineage']['clusters'][2]['review_evidence_ids'].append('u3')
    else:
        structure['live_topic_lineage']['clusters'][2]['utterance_ids'] = ['changed']
    result = build_live_topic_resolution(legacy, structure, 'b1')
    assert result['pending_review_count'] == 1
    assert result['source_limited_cluster_count'] == 0
    assert result['entries'][2]['review_state'] == 'PENDING'


def test_source_limited_without_topic_is_preserved_and_not_claimed_linked():
    legacy, structure = fixture()
    structure['live_topic_lineage']['clusters'][2]['final_topic_ids'] = []
    structure['structure_review_items'][0]['review_state'] = 'REQUEST_SOURCE_LIMITED'
    result = build_live_topic_resolution(legacy, structure, 'b1')
    assert result['entries'][2]['topics'] == []
    assert result['entries'][2]['status'] == 'UNRESOLVED'
    assert result['linked_cluster_count'] == 1
    assert result['source_limited_cluster_count'] == 1
    assert result['pending_review_count'] == 0


def test_markdown_separates_current_review_from_historical_unmapped_counts():
    from app.main import _meeting_brief_markdown
    legacy, structure = fixture()
    structure['structure_review_items'][0]['review_state'] = 'SOURCE_LIMITED'
    resolution = build_live_topic_resolution(legacy, structure, 'b1')
    legacy['live_topic_lineage'].update(cluster_count=3, unmapped_cluster_count=2)
    legacy['report_summary'] = {'topics': []}
    text = _meeting_brief_markdown({'brief': legacy, 'live_topic_resolution': resolution})
    assert '쟁점 연결 2' in text
    assert '추가 연결 확인 0' in text
    assert '재검토 후 원문 불명확 1묶음 (1건)' in text
    assert '대조 당시 실시간 주제 연결 이력' in text
    assert '당시 상위 주제 연결 보류 항목 (보존 이력)' in text
