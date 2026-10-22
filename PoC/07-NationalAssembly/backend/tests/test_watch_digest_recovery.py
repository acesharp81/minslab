from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from app.db.watch_repository import _allows_kakao_delivery


class WatchDigestRecoveryTests(unittest.TestCase):
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
