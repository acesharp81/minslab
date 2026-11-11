"""Exact function copy from 국정온 task_source_links.py; source SHA in manifest."""
from typing import Any

def verified_task_spans(task: dict[str, Any], utterances: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Only expose offsets that exactly match the source returned by the evidence API."""
    sources = {u['utterance_id']: u for u in utterances}
    spans = []
    seen = set()
    for span in [*task.get('task_evidence_spans', []), *task.get('request_spans', [])]:
        source = sources.get(span.get('evidence_id'))
        start, end = (span.get('start'), span.get('end'))
        if not source or not isinstance(start, int) or (not isinstance(end, int)) or (start < 0) or (end <= start) or (end > len(source['text'])) or (source['text'][start:end] != span.get('quote')) or (source.get('content_hash') != span.get('content_hash')) or (not set(span.get('revision_ids', [])).issubset(source.get('revision_ids', []))):
            continue
        key = (span['evidence_id'], start, end)
        if key not in seen:
            spans.append(span)
            seen.add(key)
    return spans
