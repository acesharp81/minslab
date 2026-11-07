from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock
from app.ingestion import official_integration_worker as worker


def test_timeout_projection_retries_and_does_not_complete_job(monkeypatch):
    repo = Mock()
    job = {'job_id': 'j', 'broadcast_id': 'b', 'official_document_id': 'd',
           'meeting_brief_id': 'm', 'last_error': 'ReadTimeout: old gateway', 'attempt_count': 2}
    repo.claim.return_value = job
    @contextmanager
    def connection(_):
        yield Mock()
    monkeypatch.setattr(worker, 'connect', connection)
    monkeypatch.setattr(worker, 'get_settings', lambda: SimpleNamespace(database_url='test'))
    monkeypatch.setattr(worker, 'OfficialIntegrationJobRepository', lambda _: repo)
    generate = Mock(return_value={'status': 'RETRY_WAIT', 'api_requests': 1})
    monkeypatch.setattr(worker, 'generate_one', generate)
    worker.process_available(limit=1)
    repo.retry.assert_called_once_with('j', 'OFFICIAL_COMPARISON_PENDING')
    repo.complete.assert_not_called()
    # A previous timeout must actually retry comparison, not request source-only mode.
    assert 'source_only_due_to_prior_failure' not in generate.call_args.kwargs
