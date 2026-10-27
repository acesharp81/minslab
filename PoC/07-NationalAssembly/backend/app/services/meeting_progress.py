"""Small, persisted stage counters; never infer completion from elapsed time."""
from typing import Any

STAGES = ('ANALYZING', 'INTEGRATION', 'REVIEWING', 'ONTOLOGY', 'NARRATIVE', 'FINALIZING')


def stage_progress(state: dict[str, Any], structure: dict[str, Any] | None = None,
                   progress: dict[str, Any] | None = None,
                   ontology_pending: list | None = None) -> list[dict[str, Any]]:
    """Counts describe validated units, not requests sent or a time estimate."""
    progress = progress or {}
    phase = state.get('phase', 'STRUCTURING')
    active = 'INTEGRATION' if phase in {'STRUCTURING', 'CONSOLIDATING'} else phase
    position = STAGES.index(active) if active in STAGES else 1
    previous = {s['key']: s for s in state.get('stages', [])}
    result = []
    for index, key in enumerate(STAGES):
        status = ('COMPLETED' if state.get('status') == 'COMPLETED' or index < position
                  else ('WAITING' if state.get('status') in {'DEFERRED', 'FAILED'} else 'PROCESSING')
                  if index == position else 'PENDING')
        stage = {'key': key, 'status': status}
        stage.update({k: previous.get(key, {})[k] for k in ('completed', 'total', 'unit')
                      if k in previous.get(key, {})})
        result.append(stage)
    by_key = {s['key']: s for s in result}
    total = state.get('integration_batches_total')
    if total:
        by_key['INTEGRATION'].update(completed=min(state.get('integration_batches_done', 0), total), total=total, unit='묶음')
    if not structure:
        return result
    review = (structure.get('topic_structure') or {}).get('automatic_review') or {}
    # New counters use unique atoms; a reviewed atom pending a second check is
    # not counted as complete. Older snapshots simply omit unavailable counts.
    if 'total_atom_count' in review:
        by_key['REVIEWING'].update(completed=review['completed_atom_count'], total=review['total_atom_count'], unit='발언')
    if ontology_pending is not None:
        total = len(structure.get('topics', []))
        by_key['ONTOLOGY'].update(completed=max(0, total-len(ontology_pending)), total=total, unit='쟁점')
    narrative = structure.get('narrative_coverage') or {}
    if 'issue_count' in narrative:
        by_key['NARRATIVE'].update(completed=narrative.get('summarized_issue_count', 0), total=narrative['issue_count'], unit='쟁점')
    # These are authoritative persisted stage results, even if a worker has
    # briefly re-entered an earlier phase to check its cache.
    if progress.get('status') == 'COMPLETED':
        by_key['INTEGRATION']['status'] = 'COMPLETED'
    if review.get('status') == 'COMPLETED':
        by_key['REVIEWING']['status'] = 'COMPLETED'
    if ontology_pending == []:
        by_key['ONTOLOGY']['status'] = 'COMPLETED'
    if narrative.get('status') == 'COMPLETE':
        by_key['NARRATIVE']['status'] = 'COMPLETED'
    return result
