from __future__ import annotations

import unittest
import uuid
from datetime import datetime, timedelta, timezone

from app.db.watch_repository import WatchRepository, _allows_kakao_delivery


class _Result:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None


class _DigestConnection:
    def __init__(self, rows):
        self.rows = rows
        self.sessions = {row[0] for row in rows}
        self.notified_sessions = set()

    def execute(self, sql, params=None):
        if "SELECT session.id" in sql:
            return _Result(self.rows)
        if "INSERT INTO watch_notifications" in sql:
            session_id = params[2]
            if session_id not in self.sessions:
                raise ValueError("digest session was pruned before insertion")
            self.notified_sessions.add(session_id)
            return _Result([(params[0],)])
        return _Result([])


class _DigestRepository(WatchRepository):
    def __init__(self, connection):
        super().__init__(connection)
        self.prune_calls = []
        self.outbox_kakao = []

    def _enqueue_outbox(self, subscriber_id, notification_id, *, kakao_enabled):
        self.outbox_kakao.append(kakao_enabled)

    def prune_notification_history(self, subscriber_id, keep=50):
        self.prune_calls.append(subscriber_id)
        self.connection.sessions.intersection_update(self.connection.notified_sessions)


class WatchDigestRecoveryTests(unittest.TestCase):
    def test_all_fetched_digest_sessions_are_inserted_before_pruning(self):
        subscriber_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        rows = [
            (uuid.uuid4(), subscriber_id, uuid.uuid4(), uuid.uuid4(),
             "종료 회의", 2, "관심 규칙", True, True, "assembly.webcast.go.kr",
             now - timedelta(days=2), 1)
            for _ in range(2)
        ]
        connection = _DigestConnection(rows)
        repository = _DigestRepository(connection)

        result = repository.finalize_ended_sessions()

        self.assertEqual({"sessions_ended": 2, "digests_created": 2}, result)
        self.assertEqual({row[0] for row in rows}, connection.notified_sessions)
        self.assertEqual([subscriber_id], repository.prune_calls)
        self.assertEqual([False, False], repository.outbox_kakao)

    def test_stale_kakao_delivery_is_suppressed(self):
        now = datetime(2026, 10, 2, 4, tzinfo=timezone.utc)
        self.assertFalse(_allows_kakao_delivery(
            "assembly.webcast.go.kr", now - timedelta(hours=7), now=now,
        ))
        self.assertTrue(_allows_kakao_delivery(
            "assembly.webcast.go.kr", now - timedelta(minutes=5), now=now,
        ))
        self.assertFalse(_allows_kakao_delivery(
            "poc07.replay.local", now - timedelta(minutes=5), now=now,
        ))
