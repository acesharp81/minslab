"""Bounded response cache, checked against committed DB changes on every read."""
from collections import OrderedDict
from concurrent.futures import Future
import json
from threading import RLock
from time import monotonic
from sqlalchemy import select, func
from .db import Revision, Mapping, ProgramMapping, Audit, Batch


def projection_version(service):
    def scalar(value):
        return select(value).scalar_subquery()
    # Every source/goal edit appends an immutable revision. Mapping edits bump
    # revision_no and append Audit. Finished collections change source coverage.
    query = select(scalar(func.max(Revision.recorded_at)),
                   scalar(func.sum(Mapping.revision_no)), scalar(func.count(Mapping.id)),
                   scalar(func.sum(ProgramMapping.revision_no)), scalar(func.count(ProgramMapping.id)),
                   scalar(func.max(Audit.recorded_at)), scalar(func.max(Batch.finished_at)))
    with service.sessions() as session:
        return tuple(session.execute(query).one())


class ProjectionCache:
    def __init__(self, version, max_entries=8, ttl=1800, max_bytes=32 * 1024 * 1024):
        self.version = version
        self.max_entries = max_entries
        self.ttl = ttl
        self.max_bytes = max_bytes
        self.entries = OrderedDict()
        self.inflight = {}
        self.lock = RLock()

    def get(self, key, build):
        # DB validation stays synchronous: officer edits must be visible on the
        # next request. A slow miss must not hold the lock over unrelated hits.
        version = self.version()
        flight_key = (key, version)
        with self.lock:
            item = self.entries.get(key)
            if item and item[0] == version and monotonic() - item[1] < self.ttl:
                self.entries.move_to_end(key)
                return item[2], 'HIT'
            flight = self.inflight.get(flight_key)
            owner = flight is None
            if owner:
                flight = self.inflight[flight_key] = Future()
        if not owner:
            return flight.result(), 'COALESCED'
        try:
            body = json.dumps(build(), ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()
            if self.version() == version:
                with self.lock:
                    self.entries[key] = (version, monotonic(), body)
                    self.entries.move_to_end(key)
                    while len(self.entries) > self.max_entries or sum(len(v[2]) for v in self.entries.values()) > self.max_bytes:
                        self.entries.popitem(last=False)
            flight.set_result(body)
            return body, 'MISS'
        except BaseException as error:
            flight.set_exception(error)
            raise
        finally:
            with self.lock:
                self.inflight.pop(flight_key, None)
