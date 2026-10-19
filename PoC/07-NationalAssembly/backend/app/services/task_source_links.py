"""Match follow-up tasks to direct request/commitment spans in saved source text."""
from __future__ import annotations

import re
from typing import Any

from .live_topic_mapping import _meaningful_tokens

_END = re.compile(r'(?:겠습니다|합니다|습니다|습니까|바랍니다|주세요|주십시오|됩니다|주시고요|주시면)(?=\s|[.!?]|$)[.!?]?')
_ACTION = re.compile(r'검토|개선|반영|제출|제공|송부|공개|마련|조치|확보|추진|시정|보완|보고|이행|요구|요청|점검|협의|논의|지원|확인|조사|해결|정비|설치|수립|보고|배포|채택')
_INTENT = re.compile(r'겠|바랍|주세요|주십시오|주시|요구|요청|필요|해야|하도록|해\s*주|추진|계획|당부|부탁|약속')
_STOP = {'관련', '대한', '국정감사', '후속', '과제', '요구', '요청', '필요', '추가', '사항', '검토요구'}


def _tokens(value: str) -> set[str]:
    # Unlike topic similarity, task matching needs action words such as 검토/반영.
    raw = set(re.findall(r'[가-힣A-Za-z0-9]{2,}', value))
    return (_meaningful_tokens(value) | raw) - _STOP


def direct_task_source_links(task: dict[str, Any], topics: dict[str, dict[str, Any]],
                             snapshot: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]]]:
    evidence = set(task.get('evidence_ids', []))
    tokens = _tokens(task.get('title', ''))
    candidates = []
    for atom in snapshot['atoms']:
        if atom['evidence_id'] not in evidence:
            continue
        text = atom['text']
        boundaries = [0, *(m.end() for m in _END.finditer(text))]
        if boundaries[-1] != len(text):
            boundaries.append(len(text))
        for start, end in zip(boundaries, boundaries[1:]):
            while start < end and text[start].isspace():
                start += 1
            quote = text[start:end]
            compact = re.sub(r'\s+', '', quote)
            hits = {token for token in tokens if token in compact}
            if len(hits) < 2 or not _ACTION.search(compact) or not _INTENT.search(compact):
                continue
            score = sum(min(len(t), 6) for t in hits)
            candidates.append((score, atom, start, end, quote))
    if not candidates:
        return [], []
    best = max(c[0] for c in candidates)
    spans = []
    seen = set()
    linked = set()
    for score, atom, start, end, quote in sorted(candidates, key=lambda c: -c[0]):
        if score < best or len(spans) >= 3:
            continue
        absolute_start, absolute_end = atom['offset'] + start, atom['offset'] + end
        key = (atom['evidence_id'], absolute_start, absolute_end)
        if key in seen:
            continue
        seen.add(key)
        compact = re.sub(r'\s+', '', quote)
        ranked = []
        for tid, topic in topics.items():
            if atom['evidence_id'] not in topic.get('evidence_ids', []):
                continue
            shared = {t for t in _tokens(topic['title']) if t in compact}
            overlap = False
            for point in topic.get('speaker_points', []):
                span = point.get('evidence_span') or {}
                if (span.get('evidence_id') == atom['evidence_id']
                    and span.get('start', 0) < absolute_end and span.get('end', 0) > absolute_start):
                    overlap = True
            if len(shared) < 2 and not (overlap and any(len(t) >= 3 for t in shared)):
                continue
            title_agreement = _tokens(topic['title']) & tokens
            ranked.append((sum(min(len(t), 6) for t in shared) + 2 * len(title_agreement) + int(overlap), tid))
        top = max((s for s, _ in ranked), default=0)
        ids = sorted(tid for s, tid in ranked if s == top)
        linked.update(ids)
        spans.append({'atom_id': atom['id'], 'evidence_id': atom['evidence_id'],
                      'start': absolute_start, 'end': absolute_end, 'quote': quote,
                      'content_hash': atom.get('content_hash'), 'revision_ids': atom.get('revision_ids', []),
                      'segment_ids': atom.get('segment_ids', []), 'topic_ids': ids,
                      'method': 'DIRECT_TASK_REQUEST_OR_COMMITMENT'})
    return sorted(linked), spans


def verified_task_spans(task: dict[str, Any], utterances: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Only expose offsets that exactly match the source returned by the evidence API."""
    sources = {u['utterance_id']: u for u in utterances}
    spans = []
    seen = set()
    for span in [*task.get('task_evidence_spans', []), *task.get('request_spans', [])]:
        source = sources.get(span.get('evidence_id'))
        start, end = span.get('start'), span.get('end')
        if (not source or not isinstance(start, int) or not isinstance(end, int)
            or start < 0 or end <= start or end > len(source['text'])
            or source['text'][start:end] != span.get('quote')
            or source.get('content_hash') != span.get('content_hash')
            or not set(span.get('revision_ids', [])).issubset(source.get('revision_ids', []))):
            continue
        key = (span['evidence_id'], start, end)
        if key not in seen:
            spans.append(span)
            seen.add(key)
    return spans
