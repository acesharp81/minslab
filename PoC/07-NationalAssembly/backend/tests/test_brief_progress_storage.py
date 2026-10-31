"""Content enrichment must not regress independently advancing progress."""
from copy import deepcopy

from app.db.meeting_brief_repository import MeetingBriefRepository


class RecordingConnection:
    def __init__(self):
        self.statements = []

    def execute(self, query, params=()):
        self.statements.append((query, params))
        return self

    def fetchone(self):
        return object()


def repository(monkeypatch):
    connection = RecordingConnection()
    repo = MeetingBriefRepository(connection)
    current = {'brief_id': 'b', 'brief': {
        'summary': '기존 요약', 'topics': [{'id': 't', 'evidence_ids': ['u']}],
        'finalization': {'status': 'COMPLETED', 'processed': 81},
    }}
    monkeypatch.setattr(repo, '_row', lambda _: deepcopy(current))
    return repo, connection, current


def test_late_enrichment_keeps_new_progress_and_archives_previous_content(monkeypatch):
    repo, connection, current = repository(monkeypatch)
    result = repo.update_brief('b', {**current['brief'], 'summary': '보완 요약',
                                   'finalization': {'status': 'PROCESSING', 'processed': 10}})
    assert result['brief']['summary'] == '보완 요약'
    assert result['brief']['finalization'] == current['brief']['finalization']
    assert result['brief']['topics'] == current['brief']['topics']
    assert not any('INSERT INTO meeting_brief_finalization_state' in q for q, _ in connection.statements)
    archives = [params[1].obj for q, params in connection.statements if q.startswith('INSERT INTO meeting_brief_revisions')]
    assert archives == [current['brief']]


def test_stale_progress_alone_creates_no_body_revision(monkeypatch):
    repo, connection, current = repository(monkeypatch)
    result = repo.update_brief('b', {**current['brief'], 'finalization': {'status': 'PROCESSING'}})
    assert result['brief'] == current['brief']
    assert not any(q.startswith(('INSERT', 'UPDATE')) for q, _ in connection.statements)
