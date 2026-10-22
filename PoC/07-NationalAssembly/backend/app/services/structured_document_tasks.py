"""Recover document follow-ups and route them to substantive issues, without I/O."""
from __future__ import annotations

import re
from typing import Any

from .live_topic_mapping import _meaningful_tokens

_GENERIC = {'자료제출요구', '자료제출', '서면답변요구', '답변서제출요구', '공통후속과제'}
_STOP = {'자료', '제출', '요구', '요청', '서면', '답변', '보고', '내용', '공개', '열람',
         '절차', '국정감사', '위원회', '위원장', '의원', '위원', '국회', '감사원', '서울시',
         '기관', '운영', '적정성', '적절성', '개선', '확보', '실태', '관련', '질의', '확인',
         '공방', '의혹', '가능', '여부', '인사청문회', '도덕성', '후보자', '주요', '결과',
         '진행', '시작', '안내', '협조', '태도', '시장', '위원님', '공무원', '불성실',
         '준비', '시간', '주질의', '보충질의', '국정감사장', '자료제출', '자료제공',
         '요청사항', '기회', '발언', '행정안전위원회', '사실관계', '의사진행발언', '말씀',
         '서면질의', '보도자료', '종합', '국감', '업무보고', '전반', '시정', '다음',
         '확인서', '보고서', '내역', '회계서류', '지급회계서류', '원장', '감사원장',
         '감사', '공직생활', '초대', '중수청장후보', '준비단', '중수청장', '수사', '사건'}
_OBJECT = r'(?:자료|서류|문서|보고서|답변서|내역|현황|확인서|계획서|대책안|방안|영수증|서면질의|서면)'
_ACTION = r'(?:제출|송부|보내|제공|공개|열람|보고)'
_DIRECTIVE = r'(?:주시|주십|주세요|주셔|주도록|바랍|부탁|요청드|요구합|요구드|하시겠|하십|하겠|할수있겠|해줄수)'
_REQUEST = re.compile(_OBJECT + r'.{0,70}?' + _ACTION + r'.{0,8}?' + _DIRECTIVE
                      + r'|' + _OBJECT + r'.{0,25}?(?:주십시오|주세요|주시기|주시겠|주실|주도록)')
_ELLIPTICAL = re.compile(r'(?:제출|송부|보내).{0,15}(?:주시|주십|주세요|주도록|하시|하겠|해주|주셔)')


def _reference_only(value: str) -> bool:
    """Reading already distributed material is not a new document request."""
    return bool(re.search(r'참고|참조', value)) and not bool(
        re.search(r'제출|송부|보내|제공|공개|열람', value)
    )


def generic_document_issue(value: str) -> bool:
    return re.sub(r'\s+', '', value) in _GENERIC


def _span(atom: dict[str, Any], start: int, end: int) -> dict[str, Any]:
    return {'atom_id': atom['id'], 'evidence_id': atom['evidence_id'],
            'start': atom['offset'] + start, 'end': atom['offset'] + end,
            'quote': atom['text'][start:end], 'content_hash': atom.get('content_hash'),
            'revision_ids': atom.get('revision_ids', []), 'segment_ids': atom.get('segment_ids', [])}


def document_request_span(atom: dict[str, Any], facet: dict[str, Any]) -> dict[str, Any] | None:
    """Require a source request or an existing REQUEST facet; reject procedural PPT cues."""
    text = atom.get('text', '')
    positions = [i for i, char in enumerate(text) if not char.isspace()]
    compact = ''.join(text[i] for i in positions)
    matches = [m for m in _REQUEST.finditer(compact)
               if not _reference_only(m.group())
               and not re.search(r'띄워|넘겨|화면.*보여|발언(?:기회)?|질의해|질의하|의사진행|의결|상정', m.group())]
    if not matches and (generic_document_issue(facet['issue']) or '제출' in facet['issue']):
        matches = [m for m in _ELLIPTICAL.finditer(compact)
                   if not re.search(r'발언|질의|관련|하고있|하도록되어', m.group())]
    if not matches and facet['role'] == 'REQUEST':
        # Existing source-grounded REQUESTs also include reported/past demands.
        matches = [m for m in re.finditer(_OBJECT + r'.{0,45}?' + _ACTION, compact)
                   if not _reference_only(m.group())
                   and not re.search(r'발언|질의해|질의하|관련된', m.group())]
    if not matches:
        return None
    anchor = max(0, facet['start'] - atom['offset'])
    match = min(matches, key=lambda m: abs(positions[m.start()] - anchor))
    begin, finish = positions[match.start()], positions[match.end() - 1] + 1
    # A distant directive belongs to a different facet of a long turn.
    if not generic_document_issue(facet['issue']) and (finish < anchor or begin > anchor + len(facet['quote']) + 80):
        return None
    tail = re.match(r'[^\s.!?]{0,12}', text[finish:]).group()
    start, end = max(0, begin - 220), finish + len(tail)
    if facet['role'] == 'REQUEST':
        end = min(len(text), max(end, min(anchor + len(facet['quote']), begin + 320)))
    # Lists often name their objects after "자료를 요구합니다. 첫째 ...".
    if re.match(r'[\s.!?]*(?:첫째|첫\s*번째|두\s*가지|최근|사고\s*전)', text[end:]):
        end = min(len(text), end + 320)
    return _span(atom, start, end)


def restore_document_parents(facets: list[dict[str, Any]]) -> None:
    """Undo the old consolidation's catch-all parent while retaining topic identity."""
    parents: dict[str, set[str]] = {}
    for facet in facets:
        if not generic_document_issue(facet['parent']):
            parents.setdefault(facet.get('source_parent', facet['parent']), set()).add(facet['parent'])
    for facet in facets:
        if not generic_document_issue(facet['parent']) or generic_document_issue(facet['issue']):
            continue
        source_parent = facet.get('source_parent') or ''
        if not source_parent or generic_document_issue(source_parent):
            from .meeting_topic_groups import _ontology_match
            match = _ontology_match({'title': facet['issue']})
            source_parent = match['title'] if match else facet['issue']
        candidates = parents.get(source_parent, set())
        issue = re.sub(r'\s+', '', facet['issue'])
        scored = sorted(((sum(len(t) for t in _tokens(p) if t in issue), p) for p in candidates), reverse=True)
        parent = source_parent
        if len(candidates) == 1:
            parent = next(iter(candidates))
        elif scored and scored[0][0] >= 4 and (len(scored) == 1 or scored[0][0] > scored[1][0]):
            parent = scored[0][1]
        facet['topic_identity_parent'] = facet['parent']
        facet['parent'] = parent


def extract_document_requests(facets: list[dict[str, Any]], snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    atoms = {a['id']: a for a in snapshot['atoms']}
    requests = []
    seen = set()
    for facet in facets:
        atom = atoms.get(facet['atom_id'])
        if not atom:
            continue
        span = document_request_span(atom, facet)
        generic = generic_document_issue(facet['issue'])
        if not span:
            continue
        if facet['role'] not in ('REQUEST', 'PROCEDURE', 'UNCERTAIN') and not generic:
            continue
        request = {**span, 'source_role': facet['role'], 'source_issue': facet['issue'],
                   'source_parent': facet['parent'], 'role': 'REQUEST',
                   'classification_reason': facet.get('classification_reason', '')}
        key = (span['evidence_id'], span['start'], span['end'])
        if key not in seen:
            requests.append(request)
            seen.add(key)
        if generic or facet['role'] in ('PROCEDURE', 'UNCERTAIN'):
            facet.update(source_role=facet['role'], role='REQUEST', task_only=True,
                         classification_review='DOCUMENT_REQUEST_RECOVERED')
    return requests


def _tokens(value: str) -> set[str]:
    return {t for t in _meaningful_tokens(value) - _STOP if len(t) >= 2
            and not re.fullmatch(r'(?:자료|제출|요구|요청|협조|답변|열람|공개|서면|확인|사실관계|가능|여부|질의|제공)+', t)}


def route_document_requests(requests: list[dict[str, Any]], topics: dict[str, dict[str, Any]],
                            groups: dict[str, dict[str, Any]], snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Use named subjects and verified shared evidence; never assign by cluster ID alone."""
    parent_by_topic = {tid: g['title'] for g in groups.values() for tid in g['topic_ids']}
    atoms = {a['id']: a for a in snapshot['atoms']}
    output = []
    for request in requests:
        quote = re.sub(r'\s+', '', request['quote'])
        ranked = []
        for tid, topic in topics.items():
            title_tokens = _tokens(topic['title'])
            parent_tokens = _tokens(parent_by_topic.get(tid, ''))
            hits = {t for t in title_tokens | parent_tokens if t in quote}
            meaningful = (len(hits) >= 2 and any(len(t) >= 3 for t in hits)) or any(len(t) >= 4 for t in hits)
            if not meaningful:
                continue
            score = sum(min(len(t), 6) for t in hits) + 2 * len(hits & title_tokens) + 4 * len(hits & parent_tokens)
            if request['evidence_id'] in topic['evidence_ids']:
                score += 5
            ranked.append((score, tid))
        ranked.sort(reverse=True)
        ids: list[str] = []
        method = 'TOPIC_UNCONFIRMED'
        exact = [tid for tid, topic in topics.items()
                 if topic['title'] == request['source_issue']
                 and parent_by_topic[tid] == request['source_parent']
                 and request['evidence_id'] in topic['evidence_ids']]
        if exact:
            ids = exact
            method = 'EXISTING_ISSUE_REQUEST_SOURCE'
        if ranked and not ids:
            best, tid = ranked[0]
            competing = [other for score, other in ranked if score >= best - 1
                         and parent_by_topic[other] != parent_by_topic[tid]]
            if not competing:
                ids = [other for score, other in ranked if score == best
                       and parent_by_topic[other] == parent_by_topic[tid]]
                method = 'REQUEST_SOURCE_SUBJECT'
        # Short "submit it" continuations may inherit only a verified, uniquely named
        # issue in the immediately previous turn; retain that source separately.
        context_spans = []
        atom = atoms[request['atom_id']]
        if not ids and len(atom['text']) < 100 and re.search(r'제출|송부|보내', atom['text']):
            preceding = [a for a in snapshot['atoms'] if 0 < atom['sequence'] - a['sequence'] <= 2]
            nearest = max((a['sequence'] for a in preceding), default=-1)
            prior = [a for a in preceding if a['sequence'] == nearest]
            # A skipped turn must be a short acknowledgement, not another discussion.
            if nearest == atom['sequence'] - 2 and len(atom.get('before', '').strip()) > 12:
                prior = []
            context = re.sub(r'\s+', '', ' '.join(a['text'] for a in prior)).replace('결제', '결재')
            matches = []
            issue_tokens = _tokens(request['source_issue'])
            grounded = {t for t in issue_tokens if t in context}
            if len(grounded) >= 2 and any(len(t) >= 3 for t in grounded):
                for tid, topic in topics.items():
                    if any(a['evidence_id'] in topic['evidence_ids'] for a in prior):
                        shared = grounded & _tokens(topic['title'] + ' ' + parent_by_topic.get(tid, ''))
                        if len(shared) >= 2:
                            matches.append((len(shared), tid))
                if matches:
                    high = max(s for s, _ in matches)
                    selected = [tid for s, tid in matches if s == high]
                    if len({parent_by_topic[t] for t in selected}) == 1:
                        ids = selected
                        method = 'REQUEST_AND_PREVIOUS_SOURCE_SUBJECT'
                        context_spans = [_span(a, 0, len(a['text'])) for a in prior]
        output.append({**request, 'related_topic_ids': ids,
                       'topic_link_method': method, 'context_spans': context_spans})
    return output
