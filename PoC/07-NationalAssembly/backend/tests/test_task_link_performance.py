from copy import deepcopy
from unittest.mock import patch

from app.services import meeting_brief


def test_large_report_reuses_topic_features_and_prioritizes_evidence():
    brief = {
        'topics': [{'id': f't-{i}', 'title': f'주택 공급 계획 {i}',
                    'evidence_ids': [f'e-{i}']} for i in range(200)],
        'tasks': [{'id': f'a-{i}', 'title': '자료 제출',
                   'topic_title': '주택 공급 계획 199',
                   'evidence_ids': [f'e-{i}']} for i in range(20)],
    }
    original = deepcopy(brief)
    with patch.object(meeting_brief, '_topic_tokens', wraps=meeting_brief._topic_tokens) as tokens, \
         patch.object(meeting_brief, 'SequenceMatcher', wraps=meeting_brief.SequenceMatcher) as ratios:
        result = meeting_brief.link_tasks_to_topics(brief)
    assert [t['topic_id'] for t in result['tasks']] == [f't-{i}' for i in range(20)]
    assert tokens.call_count <= 220
    assert ratios.call_count == 20
    assert brief == original


def test_similarity_tie_keeps_stable_first_topic():
    result = meeting_brief.link_tasks_to_topics({
        'topics': [{'id': 'a', 'title': '주택 공급'}, {'id': 'b', 'title': '주택 공급'}],
        'tasks': [{'title': '확인 요청', 'topic_title': '주택 공급'}],
    })
    assert result['tasks'][0]['topic_id'] == 'a'
