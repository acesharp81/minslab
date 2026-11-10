"""Project current detailed AI notes beside preserved official comparison edits.

This is a read model: no new LLM request, source rewrite or claim that an AI
paraphrase is an official quotation. Unique source quotes and existing revision/part matches with a substantial
verbatim anchor add official references. Partial links do not attribute a summary. Corrections made by the saved comparison remain visible.
"""
from __future__ import annotations

from copy import deepcopy
from difflib import SequenceMatcher
import re
from typing import Any, Iterable

from .report_presentation import narrative_projection


def _exact_text(value: Any) -> str:
    text = str(value or '').casefold()
    # Ignore spacing and sentence punctuation, but keep decimal points,
    # percentage signs and signed values distinct (1.5 != 15, -5 != 5).
    text = re.sub(r'(?<!\d)\.|\.(?!\d)', '', text)
    return re.sub(r'[^가-힣a-z0-9.%+\-−]', '', text)


def exact_official_sources(quote: str, rows: Iterable[dict[str, Any]]) -> list[str]:
    """Do not attribute short, ambiguous or merely similar source fragments."""
    text = _exact_text(quote)
    if len(text) < 24:
        return []
    matches = [str(r['utterance_id']) for r in rows
               if text in r['_compact_text']]
    return matches if len(matches) == 1 else []


def reconciled_atom_sources(
    atoms: dict[str, dict[str, Any]], matches: list[dict[str, Any]],
    sources: list[dict[str, Any]],
) -> dict[str, list[str]]:
    """Restrict saved matches to the same revision, speaker piece and source text."""
    source_ids = {str(r['utterance_id']) for r in sources}
    by_segment = {}
    for part in matches:
        match = part.get('official_reconciliation') or {}
        official_id = str(match.get('official_utterance_id') or '')
        if match.get('status') == 'MATCHED' and official_id in source_ids:
            by_segment.setdefault(str(part['segment_id']), []).append((part, official_id))
    result = {}
    for atom in atoms.values():
        text = _exact_text(atom['text'])
        revisions = {str(i) for i in atom.get('revision_ids', [])}
        refs = []
        for segment_id in atom.get('segment_ids', []):
            for part, official_id in by_segment.get(str(segment_id), []):
                raw = _exact_text(part.get('text'))
                if (str(part.get('revision_id')) in revisions and min(len(raw), len(text)) >= 24
                    and (raw in text or text in raw)):
                    refs.append(official_id)
        result[atom['id']] = list(dict.fromkeys(refs))
    return result


def supported_reconciled_sources(
    quote: str, candidate_ids: list[str], sources: list[dict[str, Any]],
) -> tuple[list[str], bool]:
    """Keep a source link only with a substantial verbatim anchor in the quote.

    Partial anchors support navigation, not attribution of the entire summary.
    Names require near-complete coverage; numerical/negation changes do not
    acquire a speaker label merely through text similarity.
    """
    text = _exact_text(quote)
    if len(text) < 24:
        return [], False
    by_id = {str(r['utterance_id']): r for r in sources}
    covered = set()
    refs = []
    safe = True
    for key in candidate_ids:
        source = by_id[key]['_compact_text']
        blocks = SequenceMatcher(None, text, source, autojunk=False).get_matching_blocks()
        if max(b.size for b in blocks) < 24:
            continue
        refs.append(key)
        for block in blocks:
            if block.size >= 4:
                covered.update(range(block.a, block.a + block.size))
        # Compare edited spans between the first and last shared text, avoiding
        # unrelated numbers elsewhere in a long official turn.
        first, last = blocks[0], blocks[-2]
        left, right = text[first.a:last.a + last.size], source[first.b:last.b + last.size]
        markers = r'[+−-]?\d+(?:\.\d+)?%?|않|못|아니|없'
        if re.findall(markers, left) != re.findall(markers, right):
            safe = False
    return refs, bool(refs and safe and len(covered) / len(text) >= .94)


def official_structured_view(
    official: dict[str, Any], structured: dict[str, Any], brief_id: Any,
    rows: Iterable[dict[str, Any]], changes: list[dict[str, Any]],
    snapshot: dict[str, Any] | None = None,
    source_matches: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    meta = structured.get('topic_structure') or {}
    narrative = structured.get('report_summary') or {}
    if (str(meta.get('source_brief_id')) != str(brief_id)
        or meta.get('consolidation_status') != 'COMPLETED'
        or not meta.get('revision_id') or not meta.get('source_hash')
        or not narrative.get('topics')):
        return official
    sources = [{**r, '_compact_text': _exact_text(r.get('text'))} for r in rows
               if r.get('utterance_id') and r.get('text')]
    names = {str(r['utterance_id']): r.get('speaker_name') for r in sources}
    atoms = {a['id']: a for a in (snapshot or {}).get('atoms', [])} if (
        snapshot and str(snapshot.get('brief_id')) == str(brief_id)
        and snapshot.get('source_hash') == meta.get('source_hash')
    ) else {}
    reconciled = reconciled_atom_sources(atoms, source_matches or [], sources)
    atom_matches = {}
    result = deepcopy(structured)
    for field in ('headline', 'summary', 'meeting_sessions', 'meeting_session_count',
                  'meeting_session_version', '_official_diffs'):
        if field in official:
            result[field] = deepcopy(official[field])
    point_sources = {}
    named_points = set()
    for topic in result.get('topics', []):
        for point in topic.get('speaker_points', []):
            span = point.get('evidence_span') or {}
            ids = exact_official_sources(span.get('quote') or '', sources)
            named = bool(ids)
            atom = atoms.get(span.get('atom_id'))
            if not ids and atom:
                start = int(span.get('start', -1)) - atom['offset']
                end = int(span.get('end', -1)) - atom['offset']
                if (atom.get('content_hash') and atom['content_hash'] == span.get('content_hash')
                    and atom['evidence_id'] == span.get('evidence_id')
                    and 0 <= start < end <= len(atom['text'])
                    and atom['text'][start:end] == span.get('quote')):
                    if atom['id'] not in atom_matches:
                        atom_matches[atom['id']] = exact_official_sources(atom['text'], sources)
                    ids = atom_matches[atom['id']]
                    named = bool(ids)
                    if not ids:
                        ids, named = supported_reconciled_sources(
                            span.get('quote') or '', reconciled.get(atom['id'], []), sources)
            point['official_evidence_ids'] = ids
            point['speaker_official'] = bool(named and ids and all(names.get(i) for i in ids))
            if point['speaker_official']:
                named_points.add(point['id'])
                point['speaker_label'] = ' · '.join(dict.fromkeys(names[i] for i in ids))
            point_sources[point['id']] = ids
        topic['official_evidence_ids'] = list(dict.fromkeys(
            i for p in topic.get('speaker_points', []) for i in p['official_evidence_ids']))
    detailed = result['report_summary']
    linked = 0
    for topic in detailed['topics']:
        ids = []
        for point in topic.get('speaker_points', []):
            source_ids = point.get('source_point_ids') or []
            refs = list(dict.fromkeys(i for p in source_ids for i in point_sources.get(p, [])))
            point['official_evidence_ids'] = refs
            point['speaker_label'] = '화자 미확인'
            point['speaker_official'] = False
            # Names require attributed matches for every source facet; partial
            # references support navigation only. The prose stays AI-generated.
            speakers = {names.get(i) for i in refs}
            if source_ids and all(p in named_points for p in source_ids) and speakers and all(speakers):
                point['speaker_label'] = ' · '.join(dict.fromkeys(names[i] for i in refs))
                point['speaker_official'] = True
                point['speaker_match_status'] = 'MATCHED' if len(speakers) == 1 else 'MULTIPLE_SPEAKERS'
            else:
                point['speaker_match_status'] = 'PARTIAL' if refs else 'UNMATCHED'
            point['authority_status'] = 'PROVISIONAL'
            ids.extend(refs)
        topic['official_evidence_ids'] = list(dict.fromkeys(ids))
        topic['summary_verification'] = 'OFFICIAL_SOURCE_LINKED' if ids else 'LIVE_SOURCE_ONLY'
        topic['authority_status'] = 'PROVISIONAL'
        linked += bool(ids)
    official_tasks = {t['id']: t for t in official.get('tasks', [])}
    inherited = set()
    for task in result.get('tasks', []):
        original = official_tasks.get(task.get('source_task_id'))
        if original:
            inherited.add(original['id'])
            for field in ('title', 'description', 'ministries', 'owner_basis', 'official_evidence_ids', '_official_diffs'):
                if field in original:
                    task[field] = deepcopy(original[field])
    extra_tasks = [deepcopy(t) for t in official_tasks.values() if t['id'] not in inherited]
    # Preserve official additions/corrections and tasks that the earlier LIVE
    # structure could not contain. Never assign them to a new issue by title.
    preserved_ids = {str(c.get('entity_id')) for c in changes
                     if c.get('entity_type') == 'topic' and c.get('operation') in {'ADD', 'UPDATE'}}
    official_narrative = narrative_projection(official)
    supplements = [deepcopy(t) for t in official_narrative['topics'] if str(t['id']) in preserved_ids]
    result['topics'].extend(deepcopy(t) for t in official.get('topics', []) if str(t['id']) in preserved_ids)
    result['tasks'].extend(extra_tasks)
    if extra_tasks:
        task_topic_id = 'structured-official-task-additions'
        task_topic = {
            'id': task_topic_id, 'title': '공식 자료에서 추가된 과제',
            'summary': '공식 회의록 대조에서 확인한 추가 요구사항입니다. 각 과제의 원문을 확인할 수 있습니다.',
            'evidence_ids': list(dict.fromkeys(i for t in extra_tasks for i in t.get('evidence_ids', []))),
            'official_evidence_ids': list(dict.fromkeys(i for t in extra_tasks for i in t.get('official_evidence_ids', []))),
            'speaker_points': [], 'authority_status': 'PROVISIONAL',
        }
        # Older ADD records sometimes defaulted to the first broad topic.
        # Preserve that historical link, but do not propagate it as a new,
        # asserted relation to unrelated detailed issues.
        for task in extra_tasks:
            task['comparison_topic_id'] = task.get('topic_id')
            task['topic_id'] = task_topic_id
            task['related_topic_ids'] = [task_topic_id]
            task['topic_title'] = task_topic['title']
        result['topics'].append(deepcopy(task_topic))
        supplements.append({**task_topic, 'source_structured_topic_id': task_topic_id,
                            'evidence_type': 'topic', 'retained_task_ids': [t['id'] for t in extra_tasks]})
    if supplements:
        group = {'id': 'structured-official-supplements', 'title': '공식 대조 보완 내용',
                 'topic_ids': [t['id'] for t in supplements]}
        detailed['topics'].extend(supplements)
        detailed['topic_groups'].append(deepcopy(group))
        result['topic_groups'].append({**group, 'evidence_ids': list(dict.fromkeys(
            i for t in supplements for i in t.get('evidence_ids', []))), 'topic_count': len(supplements)})
    result['official_detail_presentation'] = {
        'version': 'official-structured-view/1.2', 'source_revision_id': meta['revision_id'],
        'detail_topic_count': len(narrative['topics']), 'official_linked_topic_count': linked,
        'live_only_topic_count': len(narrative['topics']) - linked,
        'supplement_topic_count': len(supplements), 'additional_llm_calls': 0,
    }
    result['authority_status'] = 'PROVISIONAL'
    return result


def present_structured_source_speakers(
    items: list[dict[str, Any]], rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Label a LIVE source only when the complete text matches one official turn."""
    sources = [{**r, '_compact_text': _exact_text(r.get('text'))} for r in rows
               if r.get('utterance_id') and r.get('text')]
    by_id = {str(r['utterance_id']): r for r in sources}
    result = deepcopy(items)
    for item in result:
        ids = exact_official_sources(item.get('text') or '', sources)
        if ids and by_id[ids[0]].get('speaker_name'):
            item['speaker_label'] = by_id[ids[0]]['speaker_name']
            item['speaker_official'] = True
            item['official_evidence_ids'] = ids
    return result


def structured_official_comparisons(
    items: list[dict[str, Any]], matches: list[dict[str, Any]],
    rows: list[dict[str, Any]], official_ids: list[str], *,
    publication_stage: str, authority_status: str,
) -> list[dict[str, Any]]:
    """Restore official-first diffs using only the selected saved LIVE evidence.

    A complete single-turn baseline includes continuation captions. Mixed turns
    use verified revision/part matches, never the entire mixed text per speaker.
    Unpaired sources remain OFFICIAL_ONLY instead of showing invented edits.
    """
    from .official_evidence_presentation import build_official_evidence_presentations
    selected = set(map(str, official_ids))
    sources = [{**r, '_compact_text': _exact_text(r.get('text'))} for r in rows
               if str(r.get('utterance_id')) in selected]
    by_id = {str(r['utterance_id']): r for r in sources}
    atoms = {str(item['utterance_id']): {**item, 'id': str(item['utterance_id'])} for item in items}
    refs = reconciled_atom_sources(atoms, matches, sources)
    baselines: dict[str, list[str]] = {}
    seen = set()
    complete_turn_ids = set()
    for item in items:
        key = str(item['utterance_id'])
        text = str(item.get('text') or '')
        normalized = _exact_text(text)
        ids = refs[key] or exact_official_sources(text, sources)
        # A source turn may be split across caption revisions. Use the entire
        # saved turn when it has one linked official speaker and close wording.
        if len(ids) == 1 and SequenceMatcher(
            None, normalized, by_id[ids[0]]['_compact_text'], autojunk=False,
        ).ratio() >= .75:
            complete_turn_ids.add(ids[0])
            baselines.setdefault(ids[0], []).append(text)
            continue
        revisions = set(map(str, item.get('revision_ids', [])))
        segment_order = {str(value): index for index, value in enumerate(item.get('segment_ids', []))}
        segments = set(segment_order)
        for part in sorted(matches, key=lambda p: segment_order.get(str(p.get('segment_id')), len(segments))):
            match = part.get('official_reconciliation') or {}
            official_id = str(match.get('official_utterance_id') or '')
            revision_id, segment_id = str(part.get('revision_id')), str(part.get('segment_id'))
            raw = str(part.get('text') or '')
            compact = _exact_text(raw)
            identity = (official_id, revision_id, segment_id)
            if (official_id not in ids or revision_id not in revisions or segment_id not in segments
                or not compact or compact not in normalized or identity in seen):
                continue
            seen.add(identity)
            baselines.setdefault(official_id, []).append(raw)
    paired = [{'utterance_id': 'saved-baseline-' + key, 'text': ' '.join(texts),
               'segment_count': len(texts), 'official_reconciliation': {
                   'status': 'MATCHED', 'official_utterance_id': key}}
              for key, texts in baselines.items()]
    result = build_official_evidence_presentations(
        paired, sources, official_ids, publication_stage=publication_stage,
        authority_status=authority_status,
    )
    for row in result:
        if not row['live_text'] or row['utterance_id'] in complete_turn_ids:
            continue
        before, after = _exact_text(row['live_text']), _exact_text(row['text'])
        common = sum(block.size for block in SequenceMatcher(None, before, after, autojunk=False).get_matching_blocks())
        if min(common / max(1, len(before)), common / max(1, len(after))) < .9:
            row.update(comparison_status='PARTIAL_BASELINE', change_count=0,
                       diff_spans=[{'kind': 'equal', 'text': row['text']}], live_only_fragments=[])
    return result
