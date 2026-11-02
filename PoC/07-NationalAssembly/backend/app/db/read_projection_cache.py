"""Bounded JSON copies of derived reads; source/model responses stay in DB."""
from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable, Hashable
import json
from threading import RLock
from time import monotonic
from typing import Any
import zlib


class ProjectionCache:
    def __init__(
        self, max_bytes: int = 32 * 1024 * 1024, max_entries: int = 256,
        ttl: float = 300, clock: Callable[[], float] = monotonic,
    ) -> None:
        self.max_bytes = max_bytes
        self.max_entries = max_entries
        self.ttl = ttl
        self.clock = clock
        self.rows: OrderedDict[Hashable, tuple[float, int, bytes]] = OrderedDict()
        self.bytes = 0
        self.lock = RLock()
        self.hits = 0
        self.misses = 0

    def get(self, key: Hashable) -> dict[str, Any] | None:
        with self.lock:
            row = self.rows.get(key)
            if row is None:
                self.misses += 1
                return None
            stamp, size, payload = row
            if self.clock() - stamp >= self.ttl:
                self.rows.pop(key)
                self.bytes -= size
                self.misses += 1
                return None
            self.rows.move_to_end(key)
            self.hits += 1
        # JSON loading cannot execute Python code and gives every caller a copy.
        return json.loads(zlib.decompress(payload))

    def put(self, key: Hashable, value: dict[str, Any]) -> None:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        payload = zlib.compress(encoded.encode("utf-8"), level=1)
        size = len(payload)
        if size > self.max_bytes:
            return
        with self.lock:
            previous = self.rows.pop(key, None)
            if previous:
                self.bytes -= previous[1]
            while self.rows and (self.bytes + size > self.max_bytes or len(self.rows) >= self.max_entries):
                _, (_, removed, _) = self.rows.popitem(last=False)
                self.bytes -= removed
            self.rows[key] = (self.clock(), size, payload)
            self.bytes += size

    def clear(self) -> None:
        with self.lock:
            self.rows.clear()
            self.bytes = 0


projection_cache = ProjectionCache()
