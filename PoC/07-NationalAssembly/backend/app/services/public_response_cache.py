"""Short-lived, bounded, single-flight cache for public JSON projections only."""
from __future__ import annotations

from collections import OrderedDict
from threading import Event, Lock
from time import monotonic
from typing import Callable, Hashable


class PublicResponseCache:
    def __init__(self, *, max_entries: int = 8, max_bytes: int = 32 * 1024 * 1024,
                 clock: Callable[[], float] = monotonic) -> None:
        self.max_entries = max_entries
        self.max_bytes = max_bytes
        self.clock = clock
        self._entries: OrderedDict[Hashable, tuple[float, bytes]] = OrderedDict()
        self._flights: dict[Hashable, Event] = {}
        self._lock = Lock()

    def get(self, key: Hashable, build: Callable[[], bytes], *, ttl: float) -> bytes:
        while True:
            with self._lock:
                now = self.clock()
                for expired in [k for k, (until, _) in self._entries.items() if until <= now]:
                    self._entries.pop(expired)
                if key in self._entries:
                    self._entries.move_to_end(key)
                    return self._entries[key][1]
                event = self._flights.get(key)
                if event is None:
                    event = self._flights[key] = Event()
                    break
            event.wait()
        try:
            value = build()
            with self._lock:
                if len(value) <= self.max_bytes:
                    self._entries[key] = (self.clock() + ttl, value)
                    while (len(self._entries) > self.max_entries
                           or sum(len(v) for _, v in self._entries.values()) > self.max_bytes):
                        self._entries.popitem(last=False)
            return value
        finally:
            with self._lock:
                self._flights.pop(key)
                event.set()
