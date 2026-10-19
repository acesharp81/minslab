"""Read-only source/classification audit; run in the backend environment."""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from app.config import get_settings
from app.db.connection import connect
from app.db.meeting_brief_repository import MeetingBriefRepository
from app.db.topic_structure_repository import TopicStructureRepository
from app.services.topic_structure import source_hash
from app.services.structure_review import review_candidates


def collect() -> dict[str, Any]:
    rows = []
    invalid = []
    spans_checked = 0
    with connect(get_settings().database_url) as c:
        repo = TopicStructureRepository(c)
        for item in MeetingBriefRepository(c).latest_all():
            brief = repo.current(item)
            if not brief:
                rows.append({'broadcast_id': str(item['broadcast_id']), 'progress': repo.progress(item)})
                continue
            meta = brief['topic_structure']
            sid = meta['revision_id']
            snapshot = repo.snapshot(sid)
            spans = [p['evidence_span'] for t in brief['topics'] for p in t['speaker_points']]
            spans += [s for f in spans for s in f.get('classification_context_spans', [])]
            spans += meta['uncertain'] + meta['procedure']
            for span in spans:
                spans_checked += 1
                if not any(a['evidence_id'] == span['evidence_id']
                           and a['offset'] <= span['start'] < span['end'] <= a['offset'] + len(a['text'])
                           and a['text'][span['start']-a['offset']:span['end']-a['offset']] == span['quote']
                           and a['content_hash'] == span['content_hash']
                           and a['revision_ids'] == span['revision_ids'] for a in snapshot['atoms']):
                    invalid.append({'broadcast_id': str(item['broadcast_id']), 'evidence_id': span['evidence_id']})
            lineage = brief['live_topic_lineage']
            rows.append({'broadcast_id': str(item['broadcast_id']), 'brief_id': str(item['brief_id']),
                'headline': brief.get('headline'), 'source_hash': source_hash(item['brief']),
                'source_hash_preserved': source_hash(item['brief']) == snapshot['source_hash'],
                'atoms': meta['source_atom_count'], 'topics': len(brief['topics']),
                'uncertain': len(meta['uncertain']), 'procedural': len(meta['procedure']),
                'failed': len(meta['rejected']), 'missing': len(meta['missing_evidence_ids']),
                'review_states': dict(Counter(i['review_state'] for i in brief['structure_review_items'])),
                'review': meta['automatic_review'],
                'eligible_review_atoms': len(review_candidates(brief, snapshot, repo.batches(sid))),
                'linked_clusters': lineage['mapped_cluster_count'], 'unresolved_clusters': lineage['unmapped_cluster_count'],
                'progress': repo.progress(item)})
    metrics = {k: sum(r.get(k, 0) for r in rows) for k in
               ['atoms', 'topics', 'uncertain', 'procedural', 'failed', 'missing', 'eligible_review_atoms',
                'linked_clusters', 'unresolved_clusters']}
    return {'checked_at': datetime.now(timezone.utc).isoformat(), 'report_count': len(rows),
            'metrics': metrics, 'source_spans_checked': spans_checked,
            'invalid_source_spans': invalid, 'reports': rows}


if __name__ == '__main__':
    print(json.dumps(collect(), ensure_ascii=False, default=str))
