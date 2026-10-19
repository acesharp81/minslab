"""Locate supplemental excerpts within the same immutable source utterance."""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
import re
from typing import Any

from .ontology_context import _GENERIC, verified_topic_spans
from .official_brief_integration import semantic_tokens

_EXCERPT_CHARS = 300


def attach_ontology_source_context(
    brief: dict[str, Any], snapshot: dict[str, Any], topic_ids: set[str],
) -> dict[str, Any]:
    """Keep original citations; add at most three independently located spans.

    Search only atoms belonging to an existing verified citation's utterance.
    An excerpt needs two distinctive title anchors (at least six characters in
    total), not a parent label or an institution name alone.
    """
    result = deepcopy(brief)
    by_evidence: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for atom in snapshot.get('atoms', []):
        by_evidence[atom['evidence_id']].append(atom)
    for topic in result.get('topics', []):
        if topic['id'] not in topic_ids:
            continue
        anchors = {t for t in semantic_tokens(topic.get('title', '')) - _GENERIC
                   if len(t) >= 3 and not re.fullmatch(r'[0-9.%년개월]+', t)}
        if len(anchors) < 2:
            continue
        candidates = []
        for origin in verified_topic_spans(topic):
            for atom in by_evidence.get(origin['evidence_id'], []):
                # Restrict to the source revision of the original evidence.
                if atom.get('content_hash') != origin.get('content_hash'):
                    continue
                text = atom['text']
                starts = {0, max(0, len(text) - _EXCERPT_CHARS)}
                for token in anchors:
                    starts.update(max(0, m.start() - 80) for m in re.finditer(re.escape(token), text))
                for start in sorted(starts):
                    quote = text[start:start + _EXCERPT_CHARS]
                    hits = sorted(t for t in anchors if t in quote)
                    if len(hits) < 2 or sum(map(len, hits)) < 6:
                        continue
                    absolute = atom['offset'] + start
                    if absolute == origin['start'] and quote == origin['quote']:
                        continue
                    span = {**origin, 'start': absolute, 'end': absolute + len(quote),
                            'quote': quote, 'revision_ids': atom['revision_ids'],
                            'segment_ids': atom['segment_ids'], 'atom_id': atom['id'],
                            'context_origin': 'SAME_UTTERANCE_TITLE_ANCHORS',
                            'original_start': origin['start'], 'original_end': origin['end'],
                            'title_anchors': hits}
                    candidates.append((len(hits), sum(map(len, hits)), span))
        selected = []
        for _, _, span in sorted(candidates, key=lambda v: (-v[0], -v[1], v[2]['evidence_id'], v[2]['start'])):
            if any(s['evidence_id'] == span['evidence_id']
                   and abs(s['start'] - span['start']) < _EXCERPT_CHARS // 2 for s in selected):
                continue
            selected.append(span)
            if len(selected) == 3:
                break
        if selected:
            topic['ontology_evidence_spans'] = selected
    return result
