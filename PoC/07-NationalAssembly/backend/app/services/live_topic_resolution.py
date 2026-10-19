"""Expose current provisional structure alongside preserved legacy lineage."""
from __future__ import annotations

from collections import Counter
from typing import Any

PENDING_STATUSES = frozenset({
    'UNMAPPED', 'LEXICAL_CANDIDATE', 'AMBIGUOUS',
    'MULTIPLE_FINAL_TOPICS', 'REVIEW_REQUIRED',
})


def build_live_topic_resolution(
    legacy: dict[str, Any], structured: dict[str, Any], brief_id: Any,
) -> dict[str, Any] | None:
    meta = structured.get('topic_structure') or {}
    if (str(meta.get('source_brief_id')) != str(brief_id)
        or meta.get('consolidation_status') != 'COMPLETED'
        or not meta.get('revision_id') or not meta.get('source_hash')):
        return None
    topics = {str(t['id']): t for t in structured.get('topics', [])}
    candidates: dict[str, list[dict[str, Any]]] = {}
    for cluster in (structured.get('live_topic_lineage') or {}).get('clusters', []):
        candidates.setdefault(str(cluster.get('source_cluster_id')), []).append(cluster)
    entries = []
    for original in (legacy.get('live_topic_lineage') or {}).get('clusters', []):
        source_id = str(original['id'])
        matches = candidates.get(source_id, [])
        current = matches[0] if len(matches) == 1 else {}
        # IDs alone are insufficient: the source utterance membership must agree.
        evidence = set(original.get('utterance_ids') or [])
        valid = bool(evidence and evidence == set(current.get('utterance_ids') or []))
        ids = list(current.get('final_topic_ids') or []) if valid else []
        valid = valid and all(t in topics for t in ids)
        state = current.get('mapping_status') if valid else None
        status = ('LINKED' if state in {'STRUCTURED_EVIDENCE', 'STRUCTURED_MULTI_ISSUE'} and ids
                  else 'PROCEDURAL' if state == 'PROCEDURAL' and not ids
                  else 'PARTIAL' if state == 'REVIEW_REQUIRED' and ids
                  else 'UNRESOLVED')
        review_ids = set(current.get('review_evidence_ids') or evidence) if valid else evidence
        reviews = [
            {'id': r['id'], 'title': r['title'], 'summary': r.get('summary', ''),
             'evidence_ids': r.get('evidence_ids', []),
             'review_state': r.get('review_state'), 'reason': r.get('reason', '')}
            for r in structured.get('structure_review_items', [])
            if r.get('role') != 'PROCEDURE' and review_ids.intersection(r.get('evidence_ids') or [])
        ] if status in {'PARTIAL', 'UNRESOLVED'} and valid else []
        entries.append({
            'source_cluster_id': source_id, 'title': original.get('title', ''),
            'legacy_status': original.get('mapping_status'),
            'legacy_pending': original.get('mapping_status') in PENDING_STATUSES,
            'status': status, 'authority_status': 'PROVISIONAL',
            'structured_cluster_id': current.get('id') if valid else None,
            'topics': [{'id': t, 'title': topics[t]['title']} for t in ids] if valid else [],
            'review_items': reviews,
            'review_evidence_ids': sorted(review_ids) if status in {'PARTIAL', 'UNRESOLVED'} else [],
        })
    totals = Counter(e['status'] for e in entries)
    pending = Counter(e['status'] for e in entries if e['legacy_pending'])
    return {
        'version': 'live-topic-resolution/1.0', 'authority_status': 'PROVISIONAL',
        'source_brief_id': str(brief_id), 'revision_id': meta['revision_id'],
        'source_hash': meta['source_hash'], 'entries': entries,
        'cluster_count': len(entries), 'linked_count': totals['LINKED'],
        'procedural_count': totals['PROCEDURAL'],
        'review_count': totals['PARTIAL'] + totals['UNRESOLVED'],
        'legacy_pending_count': sum(pending.values()),
        'legacy_pending_linked_count': pending['LINKED'],
        'legacy_pending_procedural_count': pending['PROCEDURAL'],
        'legacy_pending_review_count': pending['PARTIAL'] + pending['UNRESOLVED'],
    }
