from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any


_SPACE_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^0-9a-zA-Z가-힣\s]")
_HANGUL_RE = re.compile(r"[가-힣]")


def normalize_watch_text(value: str) -> str:
    """Normalize harmless spacing/case differences without changing Korean meaning."""
    normalized = unicodedata.normalize("NFKC", str(value or "")).casefold()
    normalized = _PUNCT_RE.sub(" ", normalized)
    return _SPACE_RE.sub(" ", normalized).strip()


def _contains_term(normalized_text: str, normalized_term: str) -> bool:
    if not normalized_term:
        return False
    if _HANGUL_RE.search(normalized_term):
        return normalized_term.replace(" ", "") in normalized_text.replace(" ", "")
    if normalized_term.isalnum() and len(normalized_term) <= 5:
        return re.search(rf"(?<![0-9a-z]){re.escape(normalized_term)}(?![0-9a-z])", normalized_text) is not None
    return normalized_term in normalized_text


@dataclass(frozen=True, slots=True)
class WatchMatch:
    term: str
    excerpt: str


def match_watch_rule(text: str, rule: dict[str, Any]) -> WatchMatch | None:
    normalized = normalize_watch_text(text)
    if not normalized:
        return None
    excludes = [normalize_watch_text(term) for term in rule.get("exclude_terms") or []]
    if any(_contains_term(normalized, term) for term in excludes):
        return None
    for raw_term in rule.get("include_terms") or []:
        term = normalize_watch_text(raw_term)
        if _contains_term(normalized, term):
            return WatchMatch(term=str(raw_term).strip(), excerpt=_excerpt(text, term))
    return None


def _excerpt(text: str, normalized_term: str, radius: int = 90) -> str:
    compact = _SPACE_RE.sub(" ", str(text or "")).strip()
    folded = compact.casefold()
    index = folded.find(normalized_term)
    if index < 0 or len(compact) <= radius * 2:
        return compact[: radius * 2].strip()
    start = max(0, index - radius)
    end = min(len(compact), index + len(normalized_term) + radius)
    return f"{'…' if start else ''}{compact[start:end].strip()}{'…' if end < len(compact) else ''}"
