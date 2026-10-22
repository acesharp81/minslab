"""Coverage of persisted evidence, separate from the generated narrative's authority."""
from __future__ import annotations

from typing import Any


def topic_report_coverage(report: dict[str, Any], evidence: list[dict[str, Any]]) -> dict[str, Any]:
    ids = {str(item['id']) for item in evidence if item.get('id')}
    section_ids = {str(value) for section in report.get('sections') or []
                   for value in section.get('evidence_ids') or []}
    cited_ids = {str(value) for kind in ('policy_implications', 'sections', 'tasks', 'timeline')
                 for row in report.get(kind) or [] for value in row.get('evidence_ids') or []}
    return {
        'evidence_count': len(ids),
        'narrative_cited_count': len(ids & section_ids),
        'report_cited_count': len(ids & cited_ids),
        'narrative_uncited_ids': sorted(ids - section_ids),
        'report_uncited_ids': sorted(ids - cited_ids),
        'source_task_count': sum(len(item.get('tasks') or []) for item in evidence),
        'detail_evidence_count': len(evidence),
        'basis': 'SAVED_EVIDENCE_SNAPSHOT',
        'semantic_completeness_verified': False,
    }
