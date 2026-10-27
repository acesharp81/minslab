"""Language checks for generated Korean text, never a source-text rewriter."""
from __future__ import annotations

import re
from typing import Any

_FOREIGN_SCRIPT = re.compile(r'[\u3400-\u9fff\uf900-\ufaff\U00020000-\U0002fa1f\u3040-\u30ff\u0400-\u04ff]')
_LATIN = re.compile(r'[A-Za-z]{3,}')
_BROKEN_WORD = re.compile(r'[가-힣]_[a-z]{3,}|[가-힣][a-z]{5,}(?=[가-힣]|\b)')


def language_error(text: str, source: str | None = None) -> str | None:
    if _FOREIGN_SCRIPT.search(text):
        return 'NON_KOREAN_SCRIPT'
    # A read-time check can reject obvious corruption without guessing a name.
    if source is None:
        return 'BROKEN_MIXED_WORD' if _BROKEN_WORD.search(text) else None
    if set(_LATIN.findall(text.casefold())) - set(_LATIN.findall(source.casefold())):
        return 'UNSUPPORTED_LATIN'
    return None


def summary_language_error(summary: str, insight: dict[str, Any] | None,
                           source: str | None = None) -> str | None:
    insight = insight or {}
    texts = [summary, *(str(insight.get(k) or '') for k in ('topic', 'topic_key', 'task')),
             *(str(o) for o in insight.get('owners', []))]
    # Scan the (potentially 12k-character) source once per turn, not per field.
    if source is None:
        return next((error for text in texts if (error := language_error(text))), None)
    allowed = set(_LATIN.findall(source.casefold()))
    for text in texts:
        if _FOREIGN_SCRIPT.search(text):
            return 'NON_KOREAN_SCRIPT'
        if set(_LATIN.findall(text.casefold())) - allowed:
            return 'UNSUPPORTED_LATIN'
    return None


def utterance_sources(utterances: list[dict[str, Any]]) -> dict[tuple[Any, str], str]:
    """Recheck old caches against raw same-broadcast context, never AI text."""
    from .summary_contract import add_conversation_context
    groups: dict[Any, list[dict[str, Any]]] = {}
    for u in utterances:
        groups.setdefault(u.get('broadcast_id'), []).append(u)
    return {(u.get('broadcast_id'), u['content_hash']): ' '.join(
        c['text'] for c in u['conversation_context'])
        for group in groups.values() for u in add_conversation_context(group)}
