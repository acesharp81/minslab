"""Source-preserving automatic second pass for unclassified discussion facets."""
from __future__ import annotations

from copy import deepcopy
from typing import Any
import json

from .topic_structure import build_prompt, digest, response_schema, validate_response, placeholder_label
from .structure_retry import retry_allowance, review_retry_history

PROFILE = 'discussion-context-review/3'
DOCUMENT_PROFILE = 'discussion-request-context/2'
VERIFY_PROFILE = 'discussion-uncertain-check/1'
LABEL_PROFILE = 'discussion-placeholder-review/1'
READ_PROFILES = {'discussion-context-review/1', 'discussion-context-review/2', PROFILE, 'discussion-request-context/1', DOCUMENT_PROFILE, VERIFY_PROFILE, LABEL_PROFILE}
BATCH_START = 400000


def facet_key(facet: dict[str, Any]) -> tuple[str, int, str]:
    return facet['atom_id'], facet['start'], facet['issue']


def placeholder_facets(brief: dict[str, Any]) -> list[dict[str, Any]]:
    return [point['evidence_span'] for topic in brief.get('topics', [])
            for point in topic.get('speaker_points', []) if point.get('evidence_span')
            and any(placeholder_label(point['evidence_span'].get(k)) for k in ('parent', 'issue'))]


def review_candidates(brief: dict[str, Any], snapshot: dict[str, Any],
                      history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for facet in brief['topic_structure']['uncertain']:
        groups.setdefault(facet['atom_id'], []).append(facet)
    documents: dict[str, list[dict[str, Any]]] = {}
    for request in brief['topic_structure'].get('document_requests', []):
        if not request['related_topic_ids']:
            documents.setdefault(request['atom_id'], []).append({
                **request, 'issue': request['source_issue'], 'parent': request['source_parent'],
                'replacement_kind': 'DOCUMENT_REQUEST'})
    atoms = {a['id']: a for a in snapshot['atoms']}
    pending = []
    candidates = [(VERIFY_PROFILE if any(
        f.get('automatic_review') and len(f.get('quote', '').strip()) >= 80
        for f in targets) else PROFILE, atom_id, targets) for atom_id, targets in groups.items()]
    candidates += [(DOCUMENT_PROFILE, atom_id, targets) for atom_id, targets in documents.items()]
    labels: dict[str, list[dict[str, Any]]] = {}
    for facet in placeholder_facets(brief):
        labels.setdefault(facet['atom_id'], []).append(facet)
    candidates += [(LABEL_PROFILE, atom_id, targets) for atom_id, targets in labels.items()]
    for profile, atom_id, targets in candidates:
        if profile == DOCUMENT_PROFILE and any(p['atom']['id'] == atom_id for p in pending):
            continue
        attempts = [h for h in history if h['request'].get('profile') == profile
                    and atom_id in [a['id'] for a in h['request'].get('atoms', [])]]
        if any(h['status'] == 'READY' for h in attempts) or not retry_allowance(review_retry_history(attempts)):
            continue
        atom = deepcopy(atoms[atom_id])
        atom['context_spans'] = []
        for field, delta in [('before', -1), ('after', 1)]:
            nearby = sorted((a for a in snapshot['atoms'] if a['sequence'] == atom['sequence'] + delta),
                            key=lambda a: a['offset'])
            if nearby:
                context = ' '.join(a['text'] for a in nearby)
                atom[field] = context[-1200:] if delta < 0 else context[:1200]
                neighbor = nearby[-1] if delta < 0 else nearby[0]
                start = max(0, len(neighbor['text']) - 1200) if delta < 0 else 0
                quote = neighbor['text'][start:start + 1200]
                atom['context_spans'].append({
                    'evidence_id': neighbor['evidence_id'], 'start': neighbor['offset'] + start,
                    'end': neighbor['offset'] + start + len(quote), 'quote': quote,
                    'content_hash': neighbor['content_hash'], 'revision_ids': neighbor['revision_ids'],
                    'segment_ids': neighbor['segment_ids']})
        pending.append({'atom': atom, 'targets': targets, 'profile': profile})
    return pending


def review_schema(atoms: list[dict[str, Any]]) -> dict[str, Any]:
    result = response_schema(atoms)
    result['properties']['reasons'] = {'type': 'object', 'additionalProperties': False,
        'properties': {a['id']: {'type': 'string', 'minLength': 1, 'maxLength': 200} for a in atoms},
        'required': [a['id'] for a in atoms]}
    result['required'].append('reasons')
    return result


def review_prompt(request: dict[str, Any]) -> str:
    # Rejected catalog titles and old cluster hints anchor the model to the same mistake.
    # Reclassify from source first; retain previous targets only in the audit record.
    atoms = [{**a, 'hints': []} for a in request['atoms']]
    targets = [{k: f[k] for k in ('atom_id', 'start', 'end', 'quote') if k in f}
               for f in request['targets']]
    source_prompt = build_prompt(atoms, request.get('context_catalog', []))
    source_prompt = source_prompt.replace(
        'context_before/context_after는 맥락용이며 해당 발언의 근거로 사용하지 마라.',
        'context_before/context_after는 저장 원문의 앞뒤 발언이다. 생략된 대상과 주제를 판별할 때 사용하되 '
        'span_index와 직접 인용은 해당 source_spans에서만 선택하라. 앞뒤 발언자의 주장을 현재 화자의 발언으로 옮기지 마라.')
    return (source_prompt + '\n'
            '이번 작업은 자동 재분류다. 이전 판단 보류는 정답이 아니다. 아래 대상 쟁점만 다시 판단하라. '
            '앞뒤 문답에서 생략된 대상이 명확하면 같은 쟁점으로 연결하되 원문에 없는 사실이나 인명은 만들지 마라. '
            '기존 쟁점과 다르면 독립된 구체 주제를 만들라. 자료 제출 요구는 해당 주제의 REQUEST로 분류하라. '
            '위원장의 발언이라도 자료·서면 답변 제출을 지시하면 단순 진행과 구분하여 REQUEST로 남겨라. '
            '예: 아이폰 모바일 신분증 문제를 답변한 직후 해당 사안을 서면 답변하라고 하면 그 문제의 후속 요구다. '
            '직전의 구체적 인건비 자료 요구를 받아 신속 제출을 지시하면 같은 인건비 주제의 REQUEST다. '
            '반면 자료 요구를 먼저 받겠다는 발언 순서 안내는 PROCEDURE다. 회의 말미 전체 기관에 한 '
            '일괄 서면 답변 지시는 특정 정책 주제로 억지 연결하지 말고 공통 회의 후속 절차로 둬라. '
            '대상 원문 안에 여러 요구가 있으면 각각의 원문 구간을 선택해 분리하라. '
            '인식 오류가 일부 있어도 정책 대상과 논점이 명확하면 중립적 표현으로 분류하라. '
            '진행·인사·단순 호응은 PROCEDURE, 실제 대상을 알 수 없는 끊긴 원문만 UNCERTAIN으로 둔다. '
            '사건의 정확한 법률명·목적·배경을 모르는 것과 논의 주제를 모르는 것은 다르다. '
            '구체적 대상과 행위가 보이면 원문 범위의 중립적인 주제로 분류하라. '
            '예: 격려금인지 불명확해도 대법관에게 정기 현금 지급을 비판한 발언은 대법관 정기 현금 지급의 적정성이라는 주제다. '
            '답변 거부나 선택적 답변에 관한 질의도 국정감사 답변 태도라는 쟁점으로 분류할 수 있다. '
            '발언 내용의 진위를 확정하는 것이 아니라 발언자의 질문·주장·요구를 분류하는 작업이다. '
            '이미 분류된 다른 논점을 반복하거나 주제명을 문맥보다 넓게 붙이지 마라. '
            '중요: 기존 쟁점 제목은 후보일 뿐이며 재사용을 강제하지 않는다. 제목 중 일부만 해당하면 원문에 맞는 새 제목을 만들어라. '
            '예: 대법관 증원만 언급했으면 제청 지연을 제목에 추가하지 않는다. 영장 발부율만 나오면 선관위 영장을 붙이지 않는다. '
            '예: 현금 지급 문맥이지만 격려금인지 확인할 수 없으면 대법관 현금 지급 방식으로 중립적으로 표현한다. '
            '공직선거법, 헌법 84조, 선관위, 개인회생, 격려금, 제청 같은 용어는 해당 원문 또는 제공된 앞뒤 원문에 근거가 있어야 한다. '
            '이전 uncertainty_reason이 ISSUE_SOURCE_MISMATCH이면 같은 제목을 반복하지 말고 실제 근거에 맞게 좁혀라. '
            '인식 오류가 난 법률용어는 그대로 주제로 삼지 말고 확인 가능한 사실과 논점으로 표현하라. '
            'reasons에는 각 발언의 분류 근거 또는 원문 부족 사유를 한국어 한 문장으로 적어라. '
            '사용자에게 판단·확인·검토를 요청하지 마라.\n'
            + json.dumps(targets, ensure_ascii=False)
            + '\n직전 검증에서 원문과 일치하지 않은 제목: '
            + json.dumps(request.get('validation_feedback', []), ensure_ascii=False))


def validated_review(request: dict[str, Any], response: dict[str, Any]) -> list[dict[str, Any]]:
    facets = validate_response(response, request['atoms'], strict_labels=request.get('profile') == LABEL_PROFILE)
    reasons = response.get('reasons', {})
    if set(reasons) != {a['id'] for a in request['atoms']} or any(
        not isinstance(v, str) or not v.strip() or len(v) > 200 for v in reasons.values()
    ):
        raise ValueError('INVALID_REVIEW_REASON')
    for facet in facets:
        facet['automatic_review'] = request.get('profile', PROFILE)
        facet['classification_reason'] = reasons[facet['atom_id']]
        atom = next(a for a in request['atoms'] if a['id'] == facet['atom_id'])
        facet['classification_context_spans'] = atom.get('context_spans', [])
    return facets


def apply_reviews(facets: list[dict[str, Any]], rows: list[tuple[Any, Any, Any]]) -> tuple[list[dict[str, Any]], set[str]]:
    result = deepcopy(facets)
    reviewed: set[str] = set()
    for _, request, response in rows:
        if request.get('profile') not in READ_PROFILES:
            continue
        replacement = validated_review(request, response)
        keys = {facet_key(f) for f in request['targets']}
        # Only the previously unclassified facets are replaced; other claims survive.
        document_keys = {(f['atom_id'], f['issue']) for f in request['targets']
                         if f.get('replacement_kind') == 'DOCUMENT_REQUEST'}
        result = [f for f in result if facet_key(f) not in keys and not (
            (f['atom_id'], f['issue']) in document_keys and f['role'] in {'REQUEST', 'PROCEDURE', 'UNCERTAIN'})]
        result.extend(replacement)
        reviewed.update(a['id'] for a in request['atoms'])
    return result, reviewed


def annotate_review_state(brief: dict[str, Any], reviewed: set[str],
                          reviewed_documents: set[str] | None = None,
                          verified_atoms: set[str] | None = None) -> None:
    meta = brief['topic_structure']
    pending_atoms = {f['atom_id'] for f in meta['uncertain']
                     if f['atom_id'] not in reviewed or f.get('uncertainty_reason')}
    pending_atoms.update(f['atom_id'] for f in meta['uncertain']
                         if f.get('automatic_review') and len(f.get('quote', '').strip()) >= 80
                         and f['atom_id'] not in (verified_atoms or set()))
    request_atoms = {r['atom_id'] for r in meta.get('document_requests', []) if not r['related_topic_ids']}
    pending_requests = request_atoms - (reviewed_documents or set())
    invalid_label_ids = {f['atom_id'] for f in placeholder_facets(brief)}
    pending_ids = pending_atoms | pending_requests | invalid_label_ids | {f['atom_id'] for f in meta['rejected']}
    total_ids = reviewed | (reviewed_documents or set()) | (verified_atoms or set()) | pending_ids
    meta['automatic_review'] = {'profile': PROFILE, 'reviewed_atom_count': len(reviewed),
        'completed_atom_count': len(total_ids - pending_ids), 'total_atom_count': len(total_ids),
        'pending_atom_count': len(pending_atoms | pending_requests | invalid_label_ids),
        'invalid_label_atom_count': len(invalid_label_ids),
        'pending_request_atom_count': len(pending_requests), 'unresolved_request_atom_count': len(request_atoms),
        'failed_atom_count': len(meta['rejected']),
        'status': 'PENDING' if pending_atoms or pending_requests or invalid_label_ids or meta['rejected'] else 'COMPLETED'}
    by_id = {digest([f['atom_id'], f.get('role'), f.get('start')])[:16]: f
             for f in meta['uncertain']}
    for item in brief['structure_review_items']:
        if item.get('request_atom_id'):
            done = item['request_atom_id'] in (reviewed_documents or set())
            item['review_state'] = 'REQUEST_SOURCE_LIMITED' if done else 'AUTO_PENDING'
            if not done:
                item['reason'] = '제출 요구의 대상과 앞뒤 문맥을 자동 분석합니다.'
            elif not item.get('reason'):
                item['reason'] = '재분석 후에도 특정 주제로 연결할 근거가 부족해 요구 원문을 보존합니다.'
            continue
        facet = by_id.get(item['id'].removeprefix('structured-review-'))
        if facet:
            item['review_state'] = 'SOURCE_LIMITED' if facet['atom_id'] in reviewed and facet['atom_id'] not in pending_atoms else 'AUTO_PENDING'
            item['reason'] = (facet.get('classification_reason') if item['review_state'] == 'SOURCE_LIMITED'
                              else '앞뒤 발언을 포함해 원문에 맞는 주제로 자동 재분류합니다.')


def valid_review_subset(request: dict[str, Any], response: dict[str, Any],
                        snapshot: dict[str, Any], pending_ids: set[str]):
    """Recover only complete, source-validated atoms from a rejected review."""
    from .topic_structure import materialize
    facets = validated_review(request, response)
    probe = materialize({'topics': [], 'tasks': []}, snapshot, facets, [], 'review-subset')
    bad = {f['atom_id'] for f in probe['topic_structure']['uncertain'] if f.get('uncertainty_reason')}
    good = {a['id'] for a in request['atoms']} & pending_ids - bad
    if not good:
        return None
    subset_request = {**request, 'atoms': [a for a in request['atoms'] if a['id'] in good],
                      'targets': [f for f in request['targets'] if f['atom_id'] in good]}
    assignments = response['assignments']
    subset_response = {'reasons': {k: v for k, v in response['reasons'].items() if k in good},
        'assignments': ({k: v for k, v in assignments.items() if k in good} if isinstance(assignments, dict)
                        else [a for a in assignments if a['atom_id'] in good])}
    validated_review(subset_request, subset_response)
    return subset_request, subset_response
