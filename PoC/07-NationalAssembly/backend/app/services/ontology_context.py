"""Conservative ontology fallback using a topic's own saved source spans."""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

from .official_brief_integration import semantic_tokens

Catalog = tuple[tuple[str, str, tuple[str, ...]], ...]
_NON_WORD = re.compile(r"[^0-9A-Za-z가-힣]")
_GENERIC = frozenset({
    '질의', '답변', '요청', '요구', '자료', '제출', '설명', '검토', '문제', '관련',
    '필요성', '확인', '현황', '위원', '위원장', '의원', '후보자', '장관', '국정감사',
    '정책', '정부', '국민', '기관', '운영', '추진', '강조', '지적', '사실', '입장',
    '문제점', '필요', '논란', '제도', '시스템', '구성', '보고', '사과', '발언',
    '강화', '마무리', '관심', '역할', '구체적', '적정성', '실효성', '이행',
    '노력', '현실', '방안', '관리', '개선', '책임', '기준', '대책', '사례',
})

# These phrases are only eligible with a matching saved source span; they do
# not broaden the legacy title-only matcher or repair uncertain ASR text.
CONTEXT_ALIASES: dict[str, tuple[str, ...]] = {
    'constitutional-order': (
        '헌법84조', '헌법제84조', '재판소원', '헌법불합치', '위헌법률심판', '권한쟁의', '헌법위임', '헌법주석서', '헌법전문', '불소추특권', '탄핵판결',
    ),
    'prosecution-judiciary': (
        '사법접근', '사법부신뢰', '법왜곡죄', '외부회생위원', '개인회생', '회생위원', '회생절차', '법관증원', '법관정원', '판결문공개', '재판지연',
        '검찰인사', '배당적정성', '사법지원', '공판검사', '국선변호', '법률구조', '변호사광고', '변호사시험', '로스쿨', '법왜곡', '판결문비실명화',
        '민사집행', '아동강제집행', '대법관제청', '재판독립', '사법독립', '법관기피', '법관회피', '판결문', '전자소송', '재판배당', '특별재판부',
        '법관인사',
    ),
    'criminal-case-procedure': (
        '압수수색', '추가영장', '공소시효', '사법경찰관', '수사종결', '증거능력', '공소유지', '항소포기', '영장발부', '실질심사', '증거보전',
        '부패재산몰수', '독직폭행', '불법수사', '수사권남용', '재심요건', '형사소송법', '집행유예', '양형불균형', '수사지휘', '수사정보유출', '변호인참여',
        '무죄추정', '전자영장', '공소분리',
    ),
    'correctional-services': (
        '교정행정', '교정공무원', '교도관', '교도소', '수용자처우', '수형자', '가석방', '전자감독', '무도실무관', '보호관찰', '영치금', '소년원',
        '치료감호', '전자발찌',
    ),
    'civil-service-personnel': (
        '공무원연금', '공무원복지', '공무원수당', '공무원채용', '공직윤리시스템', '공무원징계', '소청심사', '복수직급제', '경감급순환인사', '시간선택제공무원',
        '국가공무원법', '승진임용', '인사평가', '공무원정원', '공무원시험', '일반직전환', '공무원정년', '경찰승진', '경찰인사',
    ),
    'elections-public-opinion': (
        '선거범죄', '선거사무', '투표용지', '투표지보관', '선거망', '투표지인쇄', '비례대표제', '선거비용', '무투표당선', '허위사실공표죄', '선거공보',
    ),
    'police-investigation': (
        '경찰대학', '경찰수사역량', '경찰인력', '수사전문인력', '경찰독립성', '책임수사', '수사심의', '사건배당',
    ),
    'taxation': (
        '지방세', '지방소득세', '지방소비세', '법인세', '취득세', '재산세', '체납징수', '징수율', '주민세', '세제개편',
    ),
    'budget-public-finance': (
        '재정건전성', '재정위기', '재정비상', '세입구조', '세입부족', '세수부족', '도비매칭', '보조금삭감', '감액추경', '확장재정', '지방재정투자심사',
        '차등보조율', '보조금집행', '세수구조', '재정수요', '재정부담', '재정진단',
    ),
    'welfare-care-family': (
        '복지사각지대', '돌봄서비스', '통합돌봄', '기초생활수급', '생계급여', '복지지원', '자동지원복지', '복지패러다임', '신청주의', '복지급여', '돌봄로봇',
        '산후조리', '손주돌봄', '장기요양보험', '직권신청',
    ),
    'healthcare-medical-system': (
        '공공의료원', '의료공백', '의료접근', '빅5병원', '의료격차', '경찰병원', '소방병원', '응급센터', '공공의료', '의과대학',
    ),
    'public-safety-health': (
        '소방안전', '화재예방', '승강기사고', '운전면허적성검사', '화재대피', '소방장비', '심정지소생', '구급차도입', '구급차구조', '치매운전자',
        '화재경보기', '비화재경보', 'D급소화기', '자동확산소화기', '소방헬기', '소방로봇', '마약사범', '마약재활',
        '조건부면허', '운전면허취소',
    ),
    'children-digital-safety': (
        '스마트폰과의존', '청소년전용스마트폰', '학생스마트폰', '초등학생스마트폰',
    ),
    'sexual-violence-victim-protection': (
        '범죄피해자', '피해자지원금', '성추행', '성폭력피해', '2차피해', '성범죄',
    ),
    'education': (
        '특수학급', '특수학교', '장애학생', '사립학교', '대학입시', '특수교육', '초중등교육법', '대안교육', '서울런', '장애인특수교육',
    ),
    'transport-infrastructure': (
        'GTXA', 'GTXC', '철도인프라', '철도공단', '광역철도', '지하철', '대중교통', '교통통제', '똑버스', '교통비할인',
    ),
    'industry-semiconductors': (
        '반도체공급', '반도체생산', '반도체투자', '반도체경쟁력',
    ),
    'automotive-ev': (
        '자율주행자동차', '자율주행차',
    ),
    'government-operations': (
        '행정형벌', '적극행정', '법령정비', '행정혁신', '행정규칙', '정부입법', '행정법령', '법령정보서비스', '법률안제출계획',
    ),
    'privacy-communications': (
        '개인정보보호', '개인정보유출사고', 'DLP시스템', '정보보안', '지우개서비스', '털린내정보찾기',
    ),
    'ai-digital-infrastructure': (
        '공공데이터', '데이터개방', 'AI활용', 'AI교육',
    ),
    'public-discipline': (
        '출장보고서허위', '출장비부당', '공무원비위', '징계절차', '징계시효', '징계양정', '표적감사', '토착비리', '청렴의무', '고등징계위원회', '징계감경',
        '품위유지의무', '징계처분', '징계위원회', '외유성출장', '공익감사',
    ),
    'public-integrity-funds': (
        '채용비리', '금품수수', '인사청탁', '취업심사', '회전문인사',
    ),
    'public-appointments': (
        '후보자도덕성', '후보자자질', '후보자적격성', '청문회소명',
    ),
    'finance-investment': (
        '채무조정', '신용회복', '불법사금융', '불법대부', '서민금융', '소액생계비대출',
    ),
    'youth-employment': (
        '임금체불', '노동자대출', '근로자금융지원', '체불노동자', '학교급식노동자', '임금직접지급', '노동감독', '근로감독', '체불임금', '체불총액',
        '채불총액', '체불업체', '채불업체', '근로시간',
    ),
    'housing-real-estate': (
        '공공임대주택', '주거지원', '주택인허가', '주택착공', '주택시장', '건설경기', '주택가격', '신속통합기획', '청년안심주택', '도시정비법', '공공주택',
        '임대보증금',
    ),
    'balanced-development': (
        '지방소멸대응기금', '수도권과밀', '공장총량제', '수도권규제', '지방균형발전', '공공기관이전', '국토균형', '지방투자', '권역별투자',
    ),
    'environment-waste': (
        '직매립금지', '소각시설', '폐기물처리', '대기오염',
    ),
    'historical-justice': (
        '518보상', '518정신적손해배상', '민주화보상', '과거사정리위원회', '선감학원', '518특별법', '친일재산환수',
    ),
    'immigration-birth-registration': (
        '외국인보호소', '외국인보호위원회', '외국인정책위원회', '이민재단',
    ),
    'culture-tourism': (
        '라이브클럽', '야간경제', '문화진흥',
    ),
    'energy-electricity': (
        '송배전망', '전력계통', '원전증설', '원자력발전',
    ),
    'alliance-defense': (
        'UFS',
    ),
    'disability-care-services': (
        '시각장애인', '점자블록', '음향신호기', '장애인이동권', '장애인보행권',
    ),
    'water-resources-climate': (
        '정수장', '상수도관',
    ),
    'japan-relations': (
        '한일정상',
    ),
    'inter-korean-peace': (
        '정전상태', '남북한대화',
    ),
    'north-korea-nuclear': (
        '핵탄두', '핵반격',
    ),
    'defense-industry-capability': (
        '방공무기', '현무미사일',
    ),
    'military-facilities': (
        '미군공여지', '탄약고반환',
    ),
    'military-security': (
        '방첩활동', '방첩사',
    ),
    'military-justice': (
        '상관모욕죄',
    ),
    'national-security-strategy': (
        '국방백서', '주적개념',
    ),
    'international-cooperation': (
        '국빈방문', '정상회담', '유엔총회',
    ),
    'fair-trade-platform': (
        '공정거래법', '공정거래위반', '대금정산',
    ),
}


def _concept(left: str, right: str) -> re.Pattern[str]:
    return re.compile(rf'(?:{left}).{{0,12}}(?:{right})|(?:{right}).{{0,12}}(?:{left})', re.I)


# Local conjunctions, not independent keyword bags: the two policy concepts
# must occur within twelve characters in both the proposed topic and source.
CONTEXT_CONCEPTS = {
    'public-appointments': (
        ('후보자와 청문·검증', _concept('후보자', '청문|검증|자질|적격|도덕|눈높이')),
    ),
    'public-discipline': (
        ('출장과 허위·부당', _concept('출장', '허위|부당|위조')),
        ('공직자·공무원과 비위·징계', _concept('공직자|공무원', '비위|징계')),
    ),
    'civil-service-personnel': (
        ('공무원 인사·처우', _concept('공무원', '복장|수당|처우|연금|승진|채용(?!비리)|복리')),
    ),
    'budget-public-finance': (
        ('지방채·재정과 상환·편성', _concept('지방채|재정|기금|세입', '상환|이자|편성|삭감|고갈|매칭|집행')),
    ),
    'children-digital-safety': (
        ('아동·청소년 스마트폰', _concept('초등|학생|청소년', '스마트폰|휴대폰')),
    ),
    'youth-employment': (
        ('노동자·근로자 임금·금융지원', _concept('노동자|근로자', '임금|체불|채불|대출|금융지원')),
    ),
    'sexual-violence-victim-protection': (
        ('범죄 피해자 지원', _concept('범죄피해자|성폭력피해자', '지원|보호|열람')),
    ),
    'prosecution-judiciary': (
        ('개인회생 운영', _concept('회생', '수수료|채무자|위원|절차|통계')),
        ('법관·검사 인사·정원', _concept('법관|검사', '정원|증원|근무평정')),
        ('대법관·대법원장의 제청', _concept('대법관|대법원장', '제청|재제청|재청')),
    ),
    'public-safety-health': (
        ('소방 인력·장비', _concept('소방공무원|소방청|소방안전|소방시설', '인력|장비|안전관리|화재|정비')),
    ),
}


def _compact(value: str) -> str:
    return _NON_WORD.sub('', value).upper()


@lru_cache(maxsize=4)
def _terms(catalog: Catalog) -> tuple[tuple[str, str, tuple[tuple[str, str], ...]], ...]:
    # Short substrings (e.g. 전세 in 전세계) and generic institutions must not
    # become evidence for a new contextual assignment.
    return tuple((key, title, tuple(
        (_compact(word), word) for word in (*words, *CONTEXT_ALIASES.get(key, ()))
        if len(_compact(word)) >= 3
    )) for key, title, words in catalog)


def _hits(text: str, catalog: Catalog) -> dict[str, tuple[str, list[str]]]:
    compact = _compact(text)
    result = {}
    for key, title, terms in _terms(catalog):
        hits = [raw for normalized, raw in terms if normalized in compact]
        hits.extend(m.group() for _, pattern in CONTEXT_CONCEPTS.get(key, ())
                    if (m := pattern.search(compact)))
        if hits:
            result[key] = (title, list(dict.fromkeys(hits)))
    return result


def verified_topic_spans(topic: dict[str, Any]) -> list[dict[str, Any]]:
    if topic.get('coverage_origin') != 'EVIDENCE_STRUCTURE':
        return []
    evidence = set(topic.get('evidence_ids') or [])
    spans = []
    for point in topic.get('speaker_points') or []:
        span = point.get('evidence_span') or {}
        quote = span.get('quote')
        start, end = span.get('start'), span.get('end')
        if (not isinstance(quote, str) or not quote.strip()
            or point.get('summary') != quote
            or span.get('evidence_id') not in evidence
            or span.get('evidence_id') not in (point.get('evidence_ids') or [])
            or not isinstance(start, int) or not isinstance(end, int)
            or start < 0 or end - start != len(quote)
            or not span.get('content_hash') or not span.get('revision_ids')
            or span.get('role') in {'UNCERTAIN', 'PROCEDURE'}):
            continue
        spans.append(span)
    originals = list(spans)
    for span in topic.get('ontology_evidence_spans') or []:
        quote = span.get('quote')
        start, end = span.get('start'), span.get('end')
        if (isinstance(quote, str) and isinstance(start, int) and isinstance(end, int)
            and start >= 0 and end - start == len(quote)
            and span.get('context_origin') == 'SAME_UTTERANCE_TITLE_ANCHORS'
            and len(span.get('title_anchors', [])) >= 2
            and all(anchor in quote for anchor in span['title_anchors'])
            and any(o['evidence_id'] == span.get('evidence_id')
                    and o['content_hash'] == span.get('content_hash')
                    and o['revision_ids'] == span.get('revision_ids')
                    and o['start'] == span.get('original_start')
                    and o['end'] == span.get('original_end') for o in originals)):
            spans.append(span)
    return spans


def review_topic_context(topic: dict[str, Any], catalog: Catalog) -> dict[str, Any]:
    """Require a parent/issue policy target and a supporting source span.

    Never read sibling topics, neighbouring turns, or an entire speech. Multiple
    supported targets remain pending instead of winning by a longer keyword.
    """
    title = str(topic.get('title') or '')
    anchors = {t for t in semantic_tokens(title) - _GENERIC if len(t) >= 3}
    candidates: dict[str, dict[str, Any]] = {}
    spans = verified_topic_spans(topic)
    proposed_keys: set[str] = set()
    grounded_keys: set[str] = set()
    for span in spans:
        quote = span['quote']
        parent = str(span.get('parent') or '')
        proposed = _hits(parent, catalog)
        title_hits = _hits(title, catalog)
        # An explicit target in the issue itself is stronger than a broad parent.
        if title_hits:
            proposed = title_hits
        if span.get('context_origin') == 'SAME_UTTERANCE_TITLE_ANCHORS' and not title_hits:
            continue
        grounded = _hits(quote, catalog)
        proposed_keys.update(proposed)
        grounded_keys.update(proposed.keys() & grounded.keys())
        for key in proposed.keys() & grounded.keys():
            # A body's name alone does not turn its recruitment/disciplinary
            # controversy into that body's substantive policy area.
            if (not title_hits and re.search(r'징계|채용비리|청렴의무|허위.{0,8}출장|출장.{0,8}허위', title)
                and key not in {'public-discipline', 'public-integrity-funds', 'civil-service-personnel'}):
                continue
            label, parent_terms = proposed[key]
            source_terms = grounded[key][1]
            compact_quote = _compact(quote)
            supported_terms = []
            for term in source_terms:
                offset = compact_quote.find(_compact(term))
                nearby = compact_quote[max(0, offset - 65):offset + len(_compact(term)) + 65]
                shared = {a for a in anchors if _compact(a) in nearby}
                # A distinctive policy phrase can consist entirely of short
                # Korean words ("주택 가격", "세제 개편"). Require the same
                # curated phrase in both the issue title and its own source,
                # rather than dropping it because each token is <3 chars.
                exact_policy_phrase = (
                    len(_compact(term)) >= 4
                    and term in CONTEXT_ALIASES.get(key, ())
                    and _compact(term) in _compact(title)
                )
                if exact_policy_phrase or (title_hits and shared) or len(shared) >= 2 or any(len(_compact(a)) >= 5 for a in shared):
                    supported_terms.append(term)
            if not supported_terms:
                continue
            source_terms = supported_terms
            candidate = candidates.setdefault(key, {
                'key': key, 'title': label,
                'matched_keyword': max(source_terms, key=len),
                'matched_field': 'issue_and_evidence_span' if title_hits else 'parent_and_evidence_span', 'score': 0,
                'classification_method': 'ISSUE_AND_SOURCE_AGREEMENT' if title_hits else 'PARENT_AND_SOURCE_AGREEMENT',
                'supporting_spans': [],
            })
            candidate['supporting_spans'].append({
                'evidence_id': span['evidence_id'], 'start': span['start'], 'end': span['end'],
                'quote': quote, 'content_hash': span['content_hash'],
                'revision_ids': span['revision_ids'], 'parent_title': parent,
                'parent_keywords': parent_terms, 'source_keywords': source_terms,
                'context_origin': span.get('context_origin', 'ORIGINAL_STRUCTURED_QUOTE'),
                'original_start': span.get('original_start', span['start']),
                'original_end': span.get('original_end', span['end']),
            })
    if len(candidates) == 1:
        return {'match': next(iter(candidates.values())), 'reason': 'SOURCE_SUPPORTED'}
    reason = ('NO_VERIFIED_SOURCE_SPAN' if not spans
              else 'MULTIPLE_SUPPORTED_TARGETS' if candidates
              else 'NO_SPECIFIC_POLICY_TARGET' if not proposed_keys
              else 'SOURCE_TARGET_NOT_CONFIRMED' if not grounded_keys
              else 'ISSUE_SPAN_CONTEXT_WEAK')
    return {'match': None, 'reason': reason, 'candidate_keys': sorted(candidates)}


def match_topic_context(topic: dict[str, Any], catalog: Catalog) -> dict[str, Any] | None:
    return review_topic_context(topic, catalog)['match']
