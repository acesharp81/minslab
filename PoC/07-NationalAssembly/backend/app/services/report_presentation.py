"""Read-only presentation of stored AI summaries, separate from source excerpts."""
from __future__ import annotations

import re
from typing import Any

from .topic_structure import digest


def report_summary(brief: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    """Keep genuine stored summaries; never label a title fallback or quote as one."""
    topics = []
    source_to_summary = {}
    source_texts = [re.sub(r'\s+', '', a['text']) for a in snapshot['atoms']]
    if brief.get('result_kind') != 'DETERMINISTIC_FALLBACK':
        for topic in brief.get('topics', []):
            summary = str(topic.get('summary') or '').strip()
            origin = topic.get('summary_source')
            if not summary or origin in {'TITLE_FALLBACK', 'PRESERVED_LIVE_TOPIC'}:
                continue
            if topic.get('coverage_origin') == 'LIVE_TOPIC_SUPPLEMENT' and origin != 'CACHED_UTTERANCE_SUMMARY':
                continue
            compact = re.sub(r'\s+', '', summary)
            if any(compact in text for text in source_texts):
                continue
            points = []
            for point in topic.get('speaker_points', []):
                text = str(point.get('summary') or '').strip()
                if not text or point.get('summary_kind') == 'SOURCE_QUOTE':
                    continue
                if point.get('summary_verification') == 'OFFICIAL_SOURCE_EXCERPT':
                    continue
                if any(re.sub(r'\s+', '', text) in raw for raw in source_texts):
                    continue
                points.append({
                    'id': 'structured-summary-point-' + digest([topic['id'], point.get('id'), text])[:16],
                    'source_point_id': point.get('id'), 'summary': text,
                    'evidence_ids': list(point.get('evidence_ids') or []),
                    'authority_status': 'PROVISIONAL',
                })
            summary_id = 'structured-summary-' + digest([topic['id'], summary])[:16]
            source_to_summary[topic['id']] = summary_id
            topics.append({
                'id': summary_id, 'speaker_points': points,
                'source_topic_id': topic['id'], 'title': topic['title'], 'summary': summary,
                'evidence_ids': list(topic.get('evidence_ids') or []),
                'authority_status': 'PROVISIONAL',
            })
    # Restore the stored report hierarchy without reassigning source facets.
    groups = []
    grouped = set()
    for group in brief.get('topic_groups', []):
        ids = [source_to_summary[t] for t in group.get('topic_ids', [])
               if t in source_to_summary and source_to_summary[t] not in grouped]
        if not ids:
            continue
        groups.append({'id': 'summary-group-' + digest(group.get('id') or group['title'])[:16],
                       'title': group['title'], 'topic_ids': ids})
        grouped.update(ids)
    for topic in topics:
        if topic['id'] not in grouped:
            groups.append({'id': 'summary-group-' + digest(topic['id'])[:16],
                           'title': topic['title'], 'topic_ids': [topic['id']]})
    return {'topic_groups': groups, 'status': 'AVAILABLE' if topics else 'PENDING',
            'source': 'PRESERVED_AI_BRIEF', 'authority_status': 'PROVISIONAL', 'topics': topics}


def narrative_projection(brief: dict[str, Any]) -> dict[str, Any]:
    """One report layout for official-linked, provisional and structured views.

    Source authority stays on the underlying brief. A synopsis is still AI
    prose, even when its evidence links point to the official minutes.
    """
    from copy import deepcopy
    if brief.get('report_summary') is not None:
        result = deepcopy(brief['report_summary'])
        for topic in result.get('topics', []):
            topic.setdefault('evidence_type', 'summary_topic')
            for point in topic.get('speaker_points', []):
                point.setdefault('evidence_type', 'summary_speaker')
    else:
        topics = []
        for topic in brief.get('topics', []):
            if brief.get('result_kind') == 'DETERMINISTIC_FALLBACK':
                break
            if topic.get('summary_kind') == 'ROLE_COUNTS' or topic.get('coverage_origin') == 'EVIDENCE_STRUCTURE':
                continue
            if topic.get('summary_source') in {'TITLE_FALLBACK', 'PRESERVED_LIVE_TOPIC'}:
                continue
            summary = str(topic.get('summary') or '').strip()
            if not summary:
                continue
            points = []
            for point in [*topic.get('speaker_points', []), *topic.get('draft_only_speaker_points', [])]:
                is_quote = point.get('summary_verification') == 'OFFICIAL_SOURCE_EXCERPT'
                raw_text = point.get('provisional_summary') if is_quote else point.get('summary')
                text = str(raw_text or '').strip()
                if not text or point.get('summary_kind') == 'SOURCE_QUOTE':
                    continue
                if is_quote and text == str(point.get('summary') or '').strip():
                    continue
                points.append({'id': point['id'], 'summary': text,
                               'evidence_type': 'speaker',
                               'speaker_label': point.get('speaker_label') if point.get('speaker_official') else '화자 미확인',
                               'evidence_ids': list(point.get('evidence_ids') or []),
                               'official_evidence_ids': list(point.get('official_evidence_ids') or []),
                               'authority_status': 'PROVISIONAL'})
            topics.append({'id': topic['id'], 'title': topic.get('title') or '', 'summary': summary,
                           'evidence_type': 'topic', 'speaker_points': points,
                           'evidence_ids': list(topic.get('evidence_ids') or []),
                           '_official_diffs': deepcopy(topic.get('_official_diffs') or {}),
                           'authority_status': 'PROVISIONAL'})
        ids = {t['id'] for t in topics}
        groups = [{'id': 'summary-' + str(g.get('id') or digest(g['title'])[:16]),
                   'title': g['title'], 'topic_ids': [i for i in g.get('topic_ids', []) if i in ids]}
                  for g in brief.get('topic_groups', [])]
        groups = [g for g in groups if g['topic_ids']]
        grouped = {i for g in groups for i in g['topic_ids']}
        groups.extend({'id': 'summary-' + t['id'], 'title': t['title'], 'topic_ids': [t['id']]}
                      for t in topics if t['id'] not in grouped)
        result = {'topics': topics, 'topic_groups': groups,
                  'status': 'AVAILABLE' if topics else 'PENDING',
                  'source': 'STORED_AI_BRIEF', 'authority_status': 'PROVISIONAL'}
    attach_narrative_tasks(result, brief)
    result['presentation_version'] = 'meeting-summary/3'
    return result


def attach_narrative_tasks(narrative: dict[str, Any], brief: dict[str, Any]) -> None:
    """Attach tasks to display cards without changing canonical task/source links.

    Preserve original topic assignments. Newly extracted requests can be shown
    on a summary card only when their evidence identifies one unambiguous card.
    """
    topics = narrative.get('topics', [])
    for topic in topics:
        topic['task_ids'] = []
    for task in brief.get('tasks', []):
        if task.get('status') == 'RESOLVED':
            continue
        if brief.get('topic_structure'):
            candidates = [t for t in topics if
                          (task.get('source_topic_id') and task['source_topic_id'] == t.get('source_topic_id'))
                          or (task.get('source_task_id') and task.get('topic_title') == t.get('title'))]
        else:
            linked = set(task.get('related_topic_ids') or [])
            if task.get('topic_id'):
                linked.add(task['topic_id'])
            candidates = [t for t in topics if t['id'] in linked
                          or (not linked and task.get('topic_title') == t.get('title'))]
        if not candidates and brief.get('topic_structure') and task.get('related_topic_ids'):
            spans = [*task.get('task_evidence_spans', []), *task.get('request_spans', [])]
            evidence = {s.get('evidence_id') for s in spans if s.get('quote')}
            candidates = [t for t in topics if evidence and evidence.issubset(set(t.get('evidence_ids', [])))]
        # One task is not copied to every card sharing a long source turn.
        if len(candidates) == 1:
            candidates[0]['task_ids'].append(task['id'])
