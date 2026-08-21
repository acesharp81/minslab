from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


class AdapterError(RuntimeError):
    """A source response cannot be accepted without inventing data."""


@dataclass(frozen=True, slots=True)
class SourcePayload:
    source_key: str
    content: bytes
    content_type: str
    retrieved_at: datetime
    source_url: str
    http_status: int


class SourceAdapter(Protocol):
    source_key: str
    parser_version: str

    def parse(self, payload: SourcePayload) -> list[dict[str, str | None]]:
        """Parse a preserved source payload without performing network I/O."""
        ...
