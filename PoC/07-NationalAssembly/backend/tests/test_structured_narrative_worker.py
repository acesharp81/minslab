from contextlib import contextmanager
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest

from app.ingestion import structured_narrative_worker as worker
from app.services.structured_narrative import apply


@pytest.mark.parametrize('partial', [False, True])
@pytest.mark.parametrize('final_repair', [False, True])
def test_single_report_pool_preserves_lock_and_unique_batch_records(monkeypatch, partial, final_repair):
    from app.ingestion import narrative_jobs
    monkeypatch.setattr(narrative_jobs, 'background_defer_reason', lambda: None)
    rows, calls = [], []
    lock = {'held': False}
    brief = {'topic_structure': {'revision_id': 's'}, 'report_summary': {'topics': []},
             'topics': [{'id': f't{i}', 'title': '기관 협력', 'speaker_points': [
                 {'id': f'p{i}', 'role': 'REQUEST', 'evidence_span': {'evidence_id': f'u{i}',
                  'quote': '기관들이 협력하는 방안을 마련해 주시기 바랍니다.'}}]} for i in range(18)],
             'topic_groups': [{'id': 'g', 'title': '업무보고', 'topic_ids': [f't{i}' for i in range(18)]}]}

    class Connection:
        def execute(self, query, params=None):
            if 'pg_try_advisory_lock' in query:
                lock['held'] = True
                value = (True,)
            elif 'pg_advisory_unlock' in query:
                lock['held'] = False
                value = None
            else:
                value = ('ENDED',)
            return SimpleNamespace(fetchone=lambda: value)

    @contextmanager
    def connect(_):
        yield Connection()

    class Repository:
        def ready_current(self, item):
            return apply(deepcopy(brief), rows)
        def snapshot(self, sid):
            return {'atoms': []}
        def batches(self, sid):
            return []
        def record(self, sid, index, attempt, request, response, usage, error):
            assert lock['held']
            assert error is None or (partial and error == 'NARRATIVE_INVALID_SUMMARY')
            rows.append((index, request, response))

    class Client:
        provider, model = 'nvidia', 'fixture'
        def _post(self, prompt, schema, name):
            assert lock['held']
            calls.append(name)
            response = {key: {'summary': '관계기관 간 협력 방안을 마련해 달라는 요구가 제기됐다.',
                          'points': {pid: '기관 간 공동 대응 방안의 수립을 요청했다.'
                                     for pid in entry['properties']['points']['required']}}
                    for key, entry in schema['properties'].items()}
            if partial:
                response[next(iter(response))]['summary'] = '짧음'
            return response, {}

    class UnneededFallback:
        provider, model = 'openrouter', 'fixture'
        def _post(self, *args):
            pytest.fail('A partial batch must not resend already valid issues to another provider')

    monkeypatch.setattr(worker, 'connect', connect)
    monkeypatch.setattr(worker, 'get_settings', lambda: SimpleNamespace(database_url='fixture'))
    monkeypatch.setattr(worker, 'TopicStructureRepository', lambda c: Repository())
    monkeypatch.setattr(worker, 'MeetingBriefRepository', lambda c: SimpleNamespace(latest=lambda bid: {'brief_id': 'b'}))
    monkeypatch.setattr(worker, 'SummaryRepository', lambda c: MagicMock())
    routes = []
    def clients(*args):
        routes.append(args)
        return [Client(), UnneededFallback()]
    monkeypatch.setattr(worker, 'clients', clients)
    if final_repair:
        original_pending = worker.pending_batches
        def pending(*args):
            batches, blocked = original_pending(*args)
            return [{**r, 'repair_round': 4} for r in batches], blocked
        monkeypatch.setattr(worker, 'pending_batches', pending)
    monkeypatch.setattr(worker, 'pace_nim', lambda c: None)
    result = worker.process_one('authorized-report', batch_limit=3)
    assert result['status'] == ('PENDING' if partial else 'COMPLETE')
    assert result['coverage']['summarized_issue_count'] == (15 if partial else 18)
    assert len(calls) == 3
    assert len(rows) == len({row[0] for row in rows}) == (6 if partial else 3)
    assert set(routes) == ({('verification',)} if final_repair else {()})
    assert not lock['held']
