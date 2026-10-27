"""Incremental AI issue IDs, independent of per-turn summaries and tasks."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import re
from typing import Any
from uuid import NAMESPACE_URL, uuid5

PROFILE = 'live-discussion-classification/1.0'
BATCH_SIZE = 80


def procedure_conflict(task: Any, title: str) -> bool:
    return bool(task and re.search(r'개회|회의\s*진행|질의\s*순서|정회\s*안내', title))


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


def fingerprint(turn: dict[str, Any]) -> str:
    insight = turn.get('live_insight') or {}
    return digest([turn.get('content_hash'), turn.get('summary'), insight.get('topic'), insight.get('topic_key')])


def classification_request(turns: list[dict[str, Any]], state: dict[str, Any]) -> dict[str, Any]:
    assignments = state.get('assignments', {})
    eligible = [u for u in sorted(turns, key=lambda u: int(u.get('first_cursor') or 0))
                if u.get('is_final') and u.get('live_insight') and u.get('summary_kind') == 'AI_CACHED']
    pending = [i for i, u in enumerate(eligible)
               if assignments.get(str(u['utterance_id']), {}).get('fingerprint') != fingerprint(u)
               or procedure_conflict(u['live_insight'].get('task'), state.get('groups',{}).get(assignments.get(str(u['utterance_id']),{}).get('group_id'),{}).get('title',''))][:BATCH_SIZE]
    targets = set(pending)
    indices = sorted(targets | {j for i in pending for j in range(max(0, i-3), min(len(eligible), i+3))})
    rows = []
    for i in indices:
        u = eligible[i]; insight = u['live_insight']; old = assignments.get(str(u['utterance_id']), {})
        rows.append({'id': f'u{i}', 'target': i in targets, 'utterance_id': str(u['utterance_id']),
                     'fingerprint': fingerprint(u), 'content_hash': u['content_hash'],
                     'first_cursor': u.get('first_cursor'), 'last_cursor': u.get('last_cursor'),
                     'segment_ids':[str(v) for v in u.get('segment_ids',[])], 'revision_ids':[str(v) for v in u.get('revision_ids',[])],
                     'summary': u['summary'], 'topic': insight.get('topic'), 'role': insight.get('role'),
                     'task': insight.get('task'), 'previous_group_id': old.get('group_id')})
    return {'profile': PROFILE, 'catalog': state.get('groups', {}), 'turns': rows}


def build_prompt(request: dict[str, Any]) -> str:
    visible = [{k:v for k,v in row.items() if k not in {'utterance_id','fingerprint','content_hash','first_cursor','last_cursor','segment_ids','revision_ids'}} for row in request['turns']]
    return ('국회 실시간 발언 요약을 같은 정책 사안의 논의 단위로 분류하라. 발언마다 새 주제를 만들지 마라. '
            '같은 사건·정책에 관한 질의, 답변, 반박, 통계 설명, 자료 요구, 후속 과제는 표현이 달라도 한 주제다. '
            '예: 정신질환 수용자 증가/치료감호 청구율/치료시설 확충 질의와 답변은 정신질환 범죄자 치료·관리 제도라는 한 논의다. '
            '여론조사 사건의 자금 흐름/증거 판단/상소/판결문 비교 요구도 같은 사건 논의다. '
            '단, 같은 기관이란 이유로 서로 다른 사건·정책을 합치지 마라. 국감 개회에 중수청 수사·선관위·소방 논의를 합치면 안 된다. '
            '앞뒤 순서와 문맥을 읽고 짧은 동의·부인·이어진 답변도 해당 사안에 연결하라. '
            '순수 개회·선서·질의순서·정회 안내는 중립적인 회의 진행 주제로 분류하되 실제 자료요구는 해당 정책사안에 둬라. '
            'task가 있는 발언은 개회·회의 진행·질의순서 안내 주제에 배정하면 안 된다. 투표지 검증 요청은 선거 검증 사안에 연결한다. '
            '기존 catalog에 같은 사안이 있으면 반드시 그 id를 재사용하라. 새 사안만 new-1,new-2 등의 id로 만든다. '
            'title은 발언 한 문장의 제목이 아닌 공통 사안의 중립적인 한국어 제목, scope는 그 사안의 포함 범위다. '
            '기존 id의 title/scope는 변경하지 말고 그대로 반환하라. 기존 사안의 질의·답변을 새 세부 제목으로 분리하지 마라. '
            'target=true인 id를 정확히 한 번씩 모든 groups의 utterance_ids에 배정하라. target=false는 문맥용이며 배정하면 안 된다. '
            '입력에 없는 주제·사실·과제를 만들거나 발언을 생략하지 마라. 적절한 주제 수를 미리 정하지 마라. '
            '출력은 groups 배열만 포함한 JSON이다.\n' + json.dumps({'catalog':request['catalog'], 'context_only':[r for r in visible if not r['target']], 'targets':[r for r in visible if r['target']]},ensure_ascii=False))


def response_schema() -> dict[str, Any]:
    props = {'id':{'type':'string'}, 'title':{'type':'string','minLength':1,'maxLength':100},
             'scope':{'type':'string','minLength':1,'maxLength':240},
             'utterance_ids':{'type':'array','items':{'type':'string'},'minItems':1}}
    return {'type':'object','additionalProperties':False,'required':['groups'], 'properties':{'groups':{
        'type':'array','items':{'type':'object','additionalProperties':False,'properties':props,'required':list(props)}}}}


def apply_classification(broadcast_id: str, state: dict[str, Any], request: dict[str, Any], response: dict[str, Any]) -> dict[str, Any]:
    expected = {r['id']:r for r in request['turns'] if r['target']}
    context_ids = {r['id'] for r in request['turns'] if not r['target']}
    result = deepcopy(state or {'groups':{},'assignments':{}})
    groups = result.setdefault('groups', {}); assignments = result.setdefault('assignments', {})
    seen: set[str] = set(); group_ids: set[str] = set()
    if not isinstance(response.get('groups'), list):
        raise ValueError('INVALID_GROUPS')
    for group in response['groups']:
        ids = group.get('utterance_ids')
        if not isinstance(ids, list) or not ids:
            raise ValueError('EMPTY_GROUP')
        if any(uid not in expected and uid not in context_ids for uid in ids):
            raise ValueError('UNKNOWN_OR_DUPLICATE_TURN')
        # Some providers echo context-only rows. They must never change earlier assignments.
        ids = [uid for uid in ids if uid in expected]
        if not ids:
            continue
        gid = str(group.get('id') or ''); title = str(group.get('title') or '').strip(); scope = str(group.get('scope') or '').strip()
        if gid in group_ids or not title or len(title)>100 or not scope or len(scope)>240 or re.search(r'[\u3400-\u9fff]',title+scope):
            raise ValueError('INVALID_GROUP')
        group_ids.add(gid)
        if gid in groups:
            # Stable title and scope cannot drift to absorb unrelated subjects.
            canonical = gid
        elif re.fullmatch(r'new-[1-9][0-9]*', gid):
            canonical = str(uuid5(NAMESPACE_URL, f'{PROFILE}:{broadcast_id}:{title}:{scope}'))
            groups.setdefault(canonical, {'title':title,'scope':scope})
        else:
            raise ValueError('UNKNOWN_GROUP_ID')
        for uid in ids:
            if uid not in expected or uid in seen:
                raise ValueError('UNKNOWN_OR_DUPLICATE_TURN')
            seen.add(uid); row=expected[uid]
            if procedure_conflict(row.get('task'),groups[canonical]['title']):
                raise ValueError('SUBSTANTIVE_TASK_IN_PROCEDURE')
            assignments[row['utterance_id']] = {'group_id':canonical,'fingerprint':row['fingerprint'],
                'content_hash':row['content_hash'],'first_cursor':row['first_cursor'],'last_cursor':row['last_cursor']}
    if seen != set(expected):
        raise ValueError('MISSING_TURN')
    # Unused groups can remain in the catalog for stable future reuse.
    return result


def project_classification(turns: list[dict[str, Any]], state: dict[str, Any]) -> None:
    for u in turns:
        if (u.get('live_insight') or {}).get('discussion_group'):
            u['live_insight'] = {k:v for k,v in u['live_insight'].items() if k != 'discussion_group'}
        match = state.get('assignments',{}).get(str(u.get('utterance_id')), {})
        group = state.get('groups',{}).get(match.get('group_id'))
        if group and match.get('fingerprint') == fingerprint(u) and u.get('live_insight') and not procedure_conflict(u['live_insight'].get('task'),group['title']):
            u['live_insight'] = {**u['live_insight'], 'discussion_group': {
                'id':match['group_id'],'title':group['title'],'scope':group['scope'],
                'profile':PROFILE,'authority_status':'PROVISIONAL'}}


def validated_partial_response(request: dict[str, Any], response: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Keep only unambiguous source assignments; leave other turns pending.

    Never pick the first of conflicting assignments or fabricate missing IDs.
    The full raw response and request are retained by the repository caller.
    """
    expected = {r['id'] for r in request['turns'] if r['target']}
    targets = {r['id']:r for r in request['turns'] if r['target']}
    if not isinstance(response.get('groups'), list):
        raise ValueError('INVALID_GROUPS')
    claims: dict[str, set[str]] = {}; merged: dict[str, dict[str, Any]] = {}; conflicts: set[str] = set()
    for group in response['groups']:
        gid=str(group.get('id') or '')
        if not isinstance(group.get('utterance_ids'),list):
            raise ValueError('INVALID_GROUP')
        if gid in merged and (group.get('title'),group.get('scope')) != (merged[gid].get('title'),merged[gid].get('scope')):
            conflicts.add(gid)
        merged.setdefault(gid,{**group,'utterance_ids':[]})
        for uid in group['utterance_ids']:
            title = request.get('catalog',{}).get(gid,{}).get('title',str(group.get('title') or ''))
            if uid in expected and not procedure_conflict(targets[uid].get('task'),title):
                claims.setdefault(uid,set()).add(gid)
                if uid not in merged[gid]['utterance_ids']:
                    merged[gid]['utterance_ids'].append(uid)
    accepted={uid for uid,gids in claims.items() if len(gids)==1 and not (gids & conflicts)}
    if not accepted:
        raise ValueError('NO_UNAMBIGUOUS_ASSIGNMENTS')
    cleaned={'groups':[{**g,'utterance_ids':[uid for uid in g['utterance_ids'] if uid in accepted]}
                       for g in merged.values() if any(uid in accepted for uid in g['utterance_ids'])]}
    subset={**request,'turns':[{**r,'target':r['target'] and r['id'] in accepted} for r in request['turns']]}
    return subset,cleaned,{'accepted_turns':len(accepted),'pending_turn_ids':sorted(expected-accepted)}
