"""Keep follow-up tasks grounded in the target turn, not adjacent dialogue."""
from __future__ import annotations

import re
from typing import Any

VERSION = 'direct-follow-up/1'
_ACTION = re.compile(r'제출|송부|제공|공개|검토|개선|반영|마련|조치|확보|추진|시정|보완|보고|이행|점검|협의|조사|정비|설치|수립|고발|개정|철회|확인|수사|지원|비교|분석|청구|도입|기록|파악|밝히|살피|살펴|진행|감사|처리|정리|설명|준비|검증|해소|협력|확대|통과|연구|규명|환수|중단|개편|협조|차단|선언|청취')
_DIRECTIVE = re.compile(r'(?:해|하여|해\s*|하|해\s*주|하여\s*주|해주|하셔|하시|해주시|하여주시).{0,10}(?:바랍|주십시오|주세요|주시|주십|겠|해야|도록|필요|부탁)|(?:제출|검토|개선|조치|보고|확인|고발|개정|철회|수사|지원).{0,16}(?:바랍|주십시오|주세요|주시|주십|하겠|요청|요구|해야|부탁)|(?:요청|요구|부탁|촉구)(?:드립|합|하겠)')
_END = re.compile(r'(?:습니다|습니까|합니다|합니까|주세요|주십시오|바랍니다|하겠다|해야\s*한다)(?=\s|[.!?]|$)[.!?]?|[.!?]\s*')
_IMMEDIATE = re.compile(r'즉시\s*답변|동의\s*여부|질문$|질의\s*진행|발언\s*(?:시간|허용)|감사\s*중지|영상.*(?:재생|투영)|슬라이드|인사말')
_NEGATIVE = re.compile(r'하지\s*(?:마|말)|해서는\s*안|할\s*수\s*없|요구한\s*적.*없|요청한\s*적.*없')
_STOP = {'관련', '대한', '요구', '요청', '과제', '후속', '조치', '검토', '제출', '확인', '보고', '진행', '필요', '방안', '대해', '자료'}
_FOLLOW_UP_END = re.compile(r'하겠|해\s*보겠|하셔야|해\s*주시|하시기|하십시오|해\s*주시면|하시고|해\s*보도록|해야|보완해야|비교해서\s*보세요|기록해\s*놓겠|고발할\s*테니|살피도록|살펴보도록|밝혀\s*주십시오|청구가\s*돼야|고민을\s*해야')
_DIRECT_REQUEST = re.compile(r'주실\s*것|주셨으면|주셔|주시|주세요|내놔야|내놓아야|내주세요|달라|가지세요|끝내야|협의하셔|청구할\s*것을\s*제안|하도록\s*하겠|하도록\s*해')


def _actions(text: str) -> set[str]:
    # Korean paraphrases should not erase genuine document requests.
    text = re.sub(r'보내|내놓|내놔|내주|내줘|내달라', '제출', text)
    text = text.replace('밝혀', '밝히')
    text = re.sub(r'도와|돕', '협조', text)
    text = re.sub(r'막으|막아', '차단', text)
    text = re.sub(r'살펴보|살피|다시\s*생각', '검토', text)
    return set(_ACTION.findall(text))


def task_needs_review(insight: dict[str, Any] | None) -> bool:
    insight = insight or {}
    return bool(insight.get('task') and (not insight.get('task_evidence_quote')
        or insight.get('task_validation') != VERSION))


def _clauses(text: str) -> list[str]:
    ends = [0, *(m.end() for m in _END.finditer(text)), len(text)]
    return [text[a:b].strip() for a, b in zip(ends, ends[1:]) if text[a:b].strip()]


def _supported(title: str, quote: str) -> bool:
    """A matching subject alone cannot turn a question into a commitment."""
    if not (_DIRECTIVE.search(quote) or _FOLLOW_UP_END.search(quote)
            or _DIRECT_REQUEST.search(quote)) or _NEGATIVE.search(quote):
        return False
    if re.search(r'하도록\s*(?:되어|돼|되었)', quote) and not _DIRECT_REQUEST.search(quote):
        return False
    actions = _actions(title)
    if not actions or not actions.intersection(_actions(quote)):
        return False
    # Exclude a title whose only action is an immediate oral response/check.
    if actions <= {'확인'} and not re.search(r'확인.{0,15}(?:하겠|해\s*보겠|해\s*주|하여\s*주|후|해서|하여)', quote):
        return False
    tokens = set(re.findall(r'[가-힣A-Za-z0-9]{2,}', title)) - _STOP
    compact = re.sub(r'\s+', '', quote)
    return bool((tokens and any(t in compact for t in tokens)) or len(quote) < 50)


def grounded_task(insight: dict[str, Any], source: str | None, *,
                  require_quote: bool = False) -> dict[str, Any]:
    """Return a projection; never modify the stored AI output or source text.

    Legacy tasks use explicit request/commitment clauses. New model output must
    additionally supply its own exact quote and classify the kind of follow-up.
    An invalid task does not remove the question/answer summary.
    """
    result = dict(insight)
    title = str(result.get('task') or '').strip()
    if not title:
        return result
    quote = str(result.get('task_evidence_quote') or '').strip()
    reason = 'NO_DIRECT_FOLLOW_UP'
    matched = ''
    if source and not _IMMEDIATE.search(title):
        if quote:
            if (quote in source and len(quote) <= 600
                    and result.get('task_kind') in {'FOLLOW_UP_REQUEST', 'COMMITMENT'}
                    and _supported(title, quote)):
                matched = quote
            else:
                reason = 'INVALID_TARGET_EVIDENCE'
        elif not require_quote:
            matched = next((q for q in _clauses(source) if len(q) <= 600
                            and _supported(title, q)), '')
        else:
            reason = 'MISSING_TARGET_EVIDENCE'
    if matched:
        result.update(task_evidence_quote=matched, task_validation=VERSION,
                      task_evidence_start=source.index(matched),
                      task_evidence_end=source.index(matched) + len(matched))
    else:
        result.update(task=None, task_validation=reason,
                      task_candidate=title)
    return result
