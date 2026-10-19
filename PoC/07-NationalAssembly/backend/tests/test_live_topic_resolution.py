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
