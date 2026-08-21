from __future__ import annotations

from enum import StrEnum


class LifecycleStatus(StrEnum):
    SCHEDULED = "SCHEDULED"
    LIVE = "LIVE"
    ENDED = "ENDED"
    CANCELED = "CANCELED"


class AuthorityStatus(StrEnum):
    LIVE = "LIVE"
    PROVISIONAL = "PROVISIONAL"
    OFFICIAL = "OFFICIAL"


class ReconciliationStatus(StrEnum):
    MATCHED = "MATCHED"
    UNRESOLVED = "UNRESOLVED"
    CONFLICT = "CONFLICT"
