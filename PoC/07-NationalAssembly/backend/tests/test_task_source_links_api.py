from contextlib import contextmanager
from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.main import ended_live_broadcast_brief_evidence


def test_structured_task_endpoint_exposes_verified_direct_span():
    text = '소개합니다 업무 개선에 반영하겠습니다'
    start = text.index('업무')
    span = {'atom_id': 'a', 'evidence_id': 'u', 'start': start, 'end': len(text),
            'quote': text[start:], 'content_hash': 'hash', 'revision_ids': ['r']}
    task = {'id': 'structured-task-a', 'evidence_ids': ['u'], 'task_evidence_spans': [span]}
    structured = {'tasks': [task], 'topic_structure': {'revision_id': 'rev'}}
    snapshot = {'atoms': [{'id': 'a', 'evidence_id': 'u', 'text': text, 'offset': 0,
                          'content_hash': 'hash', 'revision_ids': ['r'], 'segment_ids': ['s']}]}
    @contextmanager
    def connection(_):
        yield MagicMock()
    with patch('app.main.connect', connection), patch('app.main.MeetingBriefRepository') as briefs, \
         patch('app.main.TopicStructureRepository') as structures, patch('app.main.LiveRepository') as live:
        briefs.return_value.latest.return_value = {'brief_id': uuid4(), 'brief': {}}
        briefs.return_value.evidence_ids.return_value = ['u']
        structures.return_value.ready_current.return_value = structured
        structures.return_value.snapshot.return_value = snapshot
        live.return_value.broadcast_official_context.return_value = None
        live.return_value.broadcast_official_material.return_value = {}
        result = ended_live_broadcast_brief_evidence(uuid4(), 'task', task['id'])
    assert result['source'] == 'LIVE_STRUCTURE_SNAPSHOT'
    assert result['direct_task_spans'] == [span]
    assert result['items'][0]['text'][start:] == span['quote']
