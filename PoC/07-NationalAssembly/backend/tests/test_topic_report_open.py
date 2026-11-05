from copy import deepcopy
from contextlib import contextmanager
from datetime import date, datetime, timezone
from unittest import TestCase
from unittest.mock import Mock, patch
from uuid import UUID

from fastapi import BackgroundTasks, FastAPI
import asyncio
import json
from types import SimpleNamespace
from app import topic_report_api as api

RID = UUID('3485a374-2ae2-450e-98f9-fa921d3ffc84')


def saved():
    return {'report_id': RID, 'subscriber_id': 'private', 'usage_metadata': {'private': True},
            'status': 'READY', 'provider': 'openai', 'model': 'stored-model', 'ministry': '행정안전부', 'topic': '',
            'period_start': date(2026, 10, 1), 'period_end': date(2026, 10, 31),
            'updated_at': datetime(2026, 11, 5, tzinfo=timezone.utc),
            'report': {'title': '저장 보고서', 'sections': []}, 'evidence': [{'id': 'saved'}]}


def http_get(app, path):
    sent = []
    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}
    async def send(message):
        sent.append(message)
    asyncio.run(app({"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
                     "method": "GET", "scheme": "http", "path": path, "raw_path": path.encode(),
                     "query_string": b"", "root_path": "", "headers": [],
                     "client": ("test", 123), "server": ("test", 80)}, receive, send))
    status = next(message["status"] for message in sent if message["type"] == "http.response.start")
    body = b"".join(message.get("body", b"") for message in sent if message["type"] == "http.response.body")
    return SimpleNamespace(status_code=status, json=lambda: json.loads(body))


class SavedReportOpenTests(TestCase):
    def setUp(self):
        api._scope_cache.clear()
        with api._scope_lock:
            api._scope_pending.clear()

    def test_cold_saved_read_schedules_once_without_running_search_or_mutating_snapshot(self):
        item = saved(); original = deepcopy(item)
        tasks = BackgroundTasks()
        first = api._cached_scope(item, tasks)
        second = api._cached_scope(item, tasks)
        self.assertEqual(len(tasks.tasks), 1)
        self.assertEqual(first['report'], original['report'])
        self.assertEqual(first['evidence'], original['evidence'])
        self.assertEqual(first['evidence_scope']['status'], 'PENDING')
        self.assertEqual(first, second)
        self.assertEqual(item, original)

    def test_cached_supplements_and_updated_report_invalidation(self):
        item = saved()
        api._scope_cache.put(api._scope_key(item), {'supplementary_evidence': [{'id':'new'}], 'evidence_scope': {'additional_count':1}})
        tasks = BackgroundTasks()
        self.assertEqual(api._cached_scope(item, tasks)['supplementary_evidence'], [{'id':'new'}])
        self.assertEqual(len(tasks.tasks), 0)
        item['updated_at'] = 'changed'
        self.assertEqual(api._cached_scope(item, tasks)['evidence_scope']['status'], 'PENDING')
        self.assertEqual(len(tasks.tasks), 1)

    def test_bounded_parallel_work_and_failed_scope_keeps_original(self):
        for i in range(3):
            item = {**saved(), 'report_id': str(i)}
            tasks = BackgroundTasks();api._cached_scope(item, tasks)
            self.assertEqual(len(tasks.tasks), 1 if i < 2 else 0)
        item = saved(); key = api._scope_key(item)
        with patch.object(api, 'connect', side_effect=RuntimeError('offline')):
            api._refresh_scope(item, key)
        result = api._cached_scope(item, BackgroundTasks())
        self.assertEqual(result['evidence_scope']['status'], 'UNAVAILABLE')
        self.assertEqual(result['report'], item['report'])
        self.assertEqual(result['evidence'], item['evidence'])

    def test_http_detail_and_scope_do_not_search_on_request_path_or_expose_private_metadata(self):
        app = FastAPI();app.include_router(api.router)
        @contextmanager
        def connection(_):
            yield Mock()
        repository = Mock();repository.get_visible.return_value = saved()
        with patch.object(api, 'connect', connection), patch.object(api, 'TopicReportRepository', return_value=repository), \
             patch.object(api, '_refresh_scope') as background:
            response = http_get(app, f'/api/topic-reports/{RID}')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['report']['title'], '저장 보고서')
            self.assertNotIn('subscriber_id', response.json())
            self.assertNotIn('usage_metadata', response.json())
            repository.search.assert_not_called()
            background.assert_called_once()
            scope = http_get(app, f'/api/topic-reports/{RID}/scope')
            self.assertEqual(scope.status_code, 200)
            self.assertNotIn('report', scope.json())
            self.assertNotIn('evidence', scope.json())
            repository.search.assert_not_called()
            repository.markdown.return_value = '# 저장 보고서'
            md = http_get(app, f'/api/topic-reports/{RID}/report.md')
            self.assertEqual(md.status_code, 200)
            repository.search.assert_not_called()

    def test_pending_markdown_preserves_saved_body_and_discloses_scope_check(self):
        item = api._cached_scope(saved(), BackgroundTasks())
        from app.db.topic_report_repository import TopicReportRepository
        text = TopicReportRepository.markdown(item)
        self.assertIn('# 저장 보고서', text)
        self.assertIn('추가 자료 확인은 진행 중', text)
        self.assertIn('saved', text)

    def test_unknown_scope_report_is_404_and_does_not_schedule(self):
        with patch.object(api, 'connect') as connection, patch.object(api, 'TopicReportRepository') as repository:
            repository.return_value.get_visible.return_value = None
            tasks = BackgroundTasks()
            from fastapi import HTTPException
            with self.assertRaises(HTTPException) as error:
                api.topic_report_scope(RID, tasks, None)
            self.assertEqual(error.exception.status_code, 404)
            self.assertEqual(len(tasks.tasks), 0)
