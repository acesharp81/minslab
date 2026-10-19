"""Read-only audit. Run inside the backend environment and redirect stdout to JSON."""
import json, time
from collections import Counter
from app.config import get_settings
from app.db.connection import connect
from app.db.meeting_brief_repository import MeetingBriefRepository
from app.db.topic_structure_repository import TopicStructureRepository
from app.db.live_repository import LiveRepository
from app.db.official_integration_repository import OfficialIntegrationRepository
from app.services.ontology_sources import select_current_ontology_brief
from app.services.meeting_topic_groups import build_meeting_topic_ontology, attach_meeting_topic_groups, _ontology_match, _is_report_artifact
from app.services.ontology_context import review_topic_context
from app.services.ontology_semantic import review_input, PROFILE, semantic_match
from app.services.meeting_topic_groups import TARGET_ONTOLOGY
from app.services.topic_structure import source_hash
from app.ingestion.ontology_review_worker import pending_items

def collect_audit() -> dict[str, object]:
    start = time.monotonic()
    rows = []
    snapshots = {}
    originals = 0
    queue = 0
    calls = Counter()
    attempts = Counter()
    seen_calls = set()
    with connect(get_settings().database_url) as c:
        for item in MeetingBriefRepository(c).latest_all():
            context = LiveRepository(c).broadcast_official_context(item['broadcast_id'])
            doc = (context or {}).get('official_document_id')
            integ = OfficialIntegrationRepository(c).latest_for_brief_document(item['brief_id'], doc) if doc else None
            brief, source = select_current_ontology_brief(item, integ, doc)
            row = c.execute("SELECT source_hash,source_snapshot FROM meeting_topic_structures WHERE meeting_brief_id=%s AND status='READY' ORDER BY created_at DESC LIMIT 1", (item['brief_id'],)).fetchone()
            if row:
                assert row[0] == source_hash(item['brief'])
                originals += 1
                snapshots[str(item['brief_id'])] = row[1]
            if source == 'PROVISIONAL':
                brief = TopicStructureRepository(c).ready_current(item) or brief
                if brief.get('topic_structure'):
                    queue += len(pending_items(brief, TopicStructureRepository(c).batches(brief['topic_structure']['revision_id'])))
            rows.append({'broadcast_id': str(item['broadcast_id']), 'source': source, 'brief': brief})
        for request, response, metadata, status, structure_id, batch_index, attempt in c.execute('SELECT request_snapshot,response,usage_metadata,status,structure_id,batch_index,attempt FROM meeting_topic_structure_batches WHERE batch_index>=200000').fetchall():
            profile = request.get('profile')
            attempts[profile, status] += 1
            for stage in ('proposals', 'verification'):
                if stage in response:
                    call_key = (metadata.get('provider'), (metadata.get(stage) or {}).get('request_id') or (str(structure_id), batch_index, (attempt + 1) // 2), stage)
                    if call_key not in seen_calls:
                        calls[profile, metadata.get('provider'), stage] += 1
                        seen_calls.add(call_key)
    result = build_meeting_topic_ontology([r['brief'] for r in rows])
    assignments = []
    pending = []
    checked = 0
    for r in rows:
        b = r['brief']
        grouped = attach_meeting_topic_groups(b)
        mapped = {}
        for g in grouped['topic_groups']:
            for e in g['classification_evidence']:
                mapped[e['topic_id']] = g['key']
                if e['supporting_spans']:
                    assignments.append({'broadcast_id': r['broadcast_id'], 'key': g['key'], 'target': g['title'], **e})
                    snapshot = snapshots[b['topic_structure']['source_brief_id']]
                    for s in e['supporting_spans']:
                        assert any((a['evidence_id'] == s['evidence_id'] and a['content_hash'] == s['content_hash'] and (a['revision_ids'] == s['revision_ids']) and (a['offset'] <= s['start']) and (a['offset'] + len(a['text']) >= s['end']) and (a['text'][s['start'] - a['offset']:s['end'] - a['offset']] == s['quote']) for a in snapshot['atoms']))
                        checked += 1
        for t in b.get('topics', []):
            if t['id'] in mapped or _is_report_artifact(t):
                continue
            review = t.get('ontology_semantic_review')
            item = review_input(t, TARGET_ONTOLOGY)
            reason = 'SEMANTIC_REJECTED_OR_UNRESOLVED' if review and (not review['verification']['approve'] or review['proposal']['target'] == 'UNRESOLVED' or review['verification'].get('target') != review['proposal']['target']) else 'SEMANTIC_SUPPORT_QUOTE_INVALID' if review else 'SOURCE_TOO_WEAK_FOR_SEMANTIC_REVIEW' if not item else 'SEMANTIC_QUEUE_PENDING'
            pending.append({'broadcast_id': r['broadcast_id'], 'topic_id': t['id'], 'title': t.get('title'), 'source': r['source'], 'reason': reason, 'context_reason': review_topic_context(t, TARGET_ONTOLOGY)['reason'], 'review': review, 'source_points': t.get('speaker_points', [])})
    output = {'version': result['version'], 'metrics': result['metrics'], 'source_counts': dict(Counter((r['source'] for r in rows))), 'original_reports_unchanged': originals, 'source_spans_checked': checked, 'invalid_source_spans': 0, 'queued_semantic_topics': queue, 'assignments': assignments, 'pending': pending, 'pending_reasons': dict(Counter((p['reason'] for p in pending))), 'model_calls': [{'profile': k[0], 'provider': k[1], 'stage': k[2], 'count': v} for k, v in calls.items()], 'attempts': [{'profile': k[0], 'status': k[1], 'count': v} for k, v in attempts.items()], 'elapsed_seconds': round(time.monotonic() - start, 3), 'source_briefs': {r['broadcast_id']: r['brief'].get('topic_structure', {}).get('source_brief_id') for r in rows}}
    return output
if __name__ == '__main__':
    print(json.dumps(collect_audit(), ensure_ascii=False))
