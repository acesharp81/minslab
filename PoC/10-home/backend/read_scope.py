"""Reuse row reads only inside one read-only projection build."""
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from functools import wraps

_scope = ContextVar('home_projection_reads', default=None)
_RAW = {'permit', 'general_permit', 'register', 'register_recap', 'permit_dong', 'permit_parcel'}

@contextmanager
def projection_reads():
    # Nested read-only builders share this request, never another request.
    if _scope.get() is not None:
        yield
        return
    token = _scope.set({})
    try:
        yield
    finally:
        _scope.reset(token)

def reuse_rows(method):
    @wraps(method)
    def read(self, kind, as_of=None, entity_ids=None, known_at=None):
        cache = _scope.get()
        if cache is None or kind in _RAW or entity_ids is not None:
            return method(self, kind, as_of, entity_ids, known_at)
        key = (id(self), kind, as_of, known_at, self.known_at)
        if key not in cache:
            cache[key] = method(self, kind, as_of, entity_ids, known_at)
        # Callers enrich nested project rows. Never share those mutations with
        # another consumer, request or historical projection.
        return deepcopy(cache[key])
    return read
