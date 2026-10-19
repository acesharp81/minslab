from contextlib import contextmanager
from copy import deepcopy
from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.main import ended_live_broadcast_brief, ended_live_broadcast_brief_markdown
from app.db.topic_structure_repository import TopicStructureRepository


def test_report_serves_completed_structure_and_preserves_original():
    broadcast, brief_id = uuid4(), uuid4()
    original = {'headline': '기존 제목', 'topics': [], 'tasks': []}
    structured = {'headline': '기존 제목', 'topics': [{'id': 'structured-topic-a', 'title': '새 쟁점'}],
                  'topic_structure': {'consolidation_status': 'COMPLETED'}}
    item = {'brief_id': brief_id, 'broadcast_id': broadcast, 'brief': original}
    @contextmanager
    def connection(_):
        c = MagicMock()
        c.execute.return_value.fetchone.return_value = ('EXECUTIVE',)
        yield c
    with patch('app.main.connect', connection), \
         patch('app.main.MeetingBriefRepository') as repository, \
         patch('app.main.TopicStructureRepository') as structures, \
         patch('app.main.LiveRepository') as live, \
         patch('app.main.OfficialIntegrationRepository') as integrations, \
         patch('app.main._public_meeting_brief', return_value=deepcopy(item)):
        repository.return_value.latest.return_value = item
        repository.return_value.progress.return_value = None
        structures.return_value.ready_current.return_value = structured
        live.return_value.broadcast_official_context.return_value = None
        integrations.return_value.latest_for_brief.return_value = None
        result = ended_live_broadcast_brief(broadcast)
    assert result['default_brief_view'] == 'STRUCTURED'
    assert result['brief'] is structured
    assert result['provisional_brief']['headline'] == original['headline']
    assert original == {'headline': '기존 제목', 'topics': [], 'tasks': []}


def test_markdown_structure_view_keeps_selected_grouping():
    structure = {'headline': '제목', 'summary': '', 'topic_structure': {'version': 'v'},
                 'topics': [{'id': 'structured-topic-a', 'title': '법원 안전',
                             'summary': '원문 근거', 'evidence_ids': ['u1']}],
                 'topic_groups': [{'title': '원문 기반 상위 주제', 'topic_ids': ['structured-topic-a']}],
                 'tasks': []}
    with patch('app.main.ended_live_broadcast_brief', return_value={
        'brief': {'headline': '공식 요약'}, 'structured_brief': structure,
        'authority_status': 'OFFICIAL',
    }):
        response = ended_live_broadcast_brief_markdown(uuid4(), view='structured')
    text = response.body.decode()
    assert '원문 기반 상위 주제' in text
    assert 'PROVISIONAL' in text
    assert 'OFFICIAL' not in text


def test_failed_structure_is_review_required_not_processing_forever():
    connection = MagicMock()
    connection.execute.return_value.fetchone.return_value = ('FAILED', 0, 0, 0)
    result = TopicStructureRepository(connection).progress({'brief_id': uuid4(), 'brief': {}})
    assert result['status'] == 'REVIEW_REQUIRED'
