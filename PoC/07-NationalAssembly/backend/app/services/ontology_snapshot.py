"""Non-blocking, single-flight cache for the ontology's expensive read projection."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import logging
from threading import Lock, Thread
from time import monotonic
from typing import Any, Callable

logger = logging.getLogger(__name__)


class OntologySnapshotCache:
    def __init__(self, ttl_seconds: float = 120, retry_seconds: float = 30):
        self.ttl_seconds = ttl_seconds
        self.retry_seconds = retry_seconds
        self._lock = Lock()
        self._payload: dict[str, Any] | None = None
        self._taxonomy: dict[str, Any] | None = None
        self._generated_at: str | None = None
        self._completed_at = float('-inf')
        self._attempted_at = float('-inf')
        self._running = False
        self._failed = False

    def get(self, build: Callable[[], dict[str, Any]],
            taxonomy: Callable[[], dict[str, Any]], *, refresh: bool = False) -> dict[str, Any]:
        launch = False
        with self._lock:
            now = monotonic()
            needs_refresh = (self._payload is None or self._failed or refresh
                             or now - self._completed_at >= self.ttl_seconds)
            if needs_refresh and not self._running and now - self._attempted_at >= self.retry_seconds:
                self._running = True
                self._attempted_at = now
                launch = True
            if self._payload is None and self._taxonomy is None:
                self._taxonomy = taxonomy()
            result = deepcopy(self._payload if self._payload is not None else self._taxonomy)
            status = ('REFRESHING' if self._payload is not None else 'LOADING') if self._running else (
                ('STALE' if self._payload is not None else 'FAILED') if self._failed else 'READY')
            result['snapshot'] = {
                'status': status,
                'generated_at': self._generated_at,
                'refresh_in_progress': self._running,
                'max_age_seconds': self.ttl_seconds,
                'retry_after_seconds': max(0, round(self.retry_seconds - (now - self._attempted_at))),
            }
            result['additional_llm_calls'] = 0
        if launch:
            Thread(target=self._refresh, args=(build,), name='ontology-snapshot', daemon=True).start()
        return result

    def _refresh(self, build: Callable[[], dict[str, Any]]) -> None:
        try:
            payload = build()
        except Exception as exc:
            logger.warning('Ontology snapshot refresh failed (%s)', type(exc).__name__)
            with self._lock:
                self._failed = True
                self._running = False
            return
        with self._lock:
            self._payload = payload
            self._generated_at = datetime.now(timezone.utc).isoformat()
            self._completed_at = monotonic()
            self._failed = False
            self._running = False
