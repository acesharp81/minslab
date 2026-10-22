"""Additive, source-grounded vocabulary from the October 2026 audit reports.

Run only after legacy title, context and verified semantic assignments. These
phrases add coverage within existing targets; no report nodes or sources change.
"""
from functools import lru_cache
from typing import Any

from .ontology_context import Catalog, review_topic_context, verified_topic_spans, _compact

EXTENSION_VERSION = "report-vocabulary/2026-10-22"
EXTENSION_ALIASES: dict[str, tuple[str, ...]] = {
    "prosecution-judiciary": (
        "양형적정성", "양형의적정성", "양형의부당", "양형부당", "양형조사관", "양형조사", "감형내역", "항소심", "재심신청", "재심사유", "재심개시", "재심절차",
        "민사사건", "민형사가사", "가사사건", "사건처리기간", "미제사건처리", "인가결정", "법인회생", "회생법원",
        "법관스마트워크", "지역법관", "향판", "법관판단", "시범재판", "집행관", "인도소송", "국제상사", "집행정지",
        "아동최우선이익", "아동최우선원칙", "헤이그국제사법회의", "강제집행과정",
    ),
    "criminal-case-procedure": (
        "증거위조", "증거를위조", "증거를왜곡", "증거왜곡", "디지털포렌식", "포렌식검색어", "수사의뢰서", "수사지휘권한", "구속사건", "형집행", "형의집행",
        "수사공소기관", "공정수사", "피의자전환", "불송치결정", "수사공백",
    ),
    "historical-justice": (
        "518유공자", "518피해자", "518왜곡", "518폄훼", "518손해배상", "전두환회고록", "국가상대배상", "국가상대보상",
        "고문사건", "43사건", "형사보상청구",
    ),
    "public-discipline": ("성매매판사", "판사성매매", "부장판사뇌물", "허위보고", "공무원비위", "감사청구", "허위출장"),
    "elections-public-opinion": ("선관위법", "선관위상임위원", "선관위의상임위원", "개표조작", "선관위원장겸직", "선거법위반", "선거관리위원장"),
    "children-digital-safety": ("아동학대", "아동보호위탁", "아동트라우마", "학대아동보호"),
    "sexual-violence-victim-protection": ("성폭행", "가정폭력", "스토킹", "피해자유족진술", "접근금지", "피해자배상"),
    "civil-service-personnel": ("신규주무관", "소방관처우", "소방관인력", "공무원초과근무"),
    "local-council-autonomy": ("행정통합", "통합특별법", "고향사랑기부", "고향사랑기부세"),
    "balanced-development": ("지역활성화투자펀드", "공공기관본사이전", "지방소멸", "지역균형성장"),
    "environment-waste": ("석포제련소", "제련소이전", "환경오염책임"),
    "forest-disaster": ("산불피해", "야간진화", "헬기진화", "산불진화", "야간헬기진화", "소나무재선충", "산불임시주택"),
    "healthcare-medical-system": (
        "공중보건의", "공보의", "입원환자", "의대설립", "의료원설립", "울산의료원", "청주의료원", "의료기관관리", "치료가능사망률",
        "반구대병원", "환자전원", "병원폐원", "입원환경", "비질환자입원", "전원보호지원단",
    ),
    "education": ("폐교활용", "공동캠퍼스", "교육현장이념중립"),
    "housing-real-estate": ("청산연금방지법",),
    "culture-tourism": ("문화관광산업", "관광단지", "유교랜드", "관광산업", "세종문화회관", "남산케이블카", "마라톤대회"),
    "transport-infrastructure": ("민간전용활주로", "공항개발", "울릉도여객선", "삼성역공사", "철근누락", "GTXA"),
    "military-facilities": ("공항소음", "전투비행단", "군공항소음", "소음피해보상"),
    "disability-care-services": ("장애인권익옹호", "교통약자이동", "자립지원법", "권리중심일자리"),
    "welfare-care-family": ("청년국민연금", "국민연금보험료", "국민연금첫보험료", "청년연금", "AI돌봄", "인공지능돌봄", "중장년기본법", "사회서비스원"),
    "budget-public-finance": ("지출구조조정", "재정사업", "채무증가", "지방채관리", "도비매칭", "재정손실"),
    "public-assets": ("도청사업사이클링", "당산벙커", "청사이전", "공공시설위탁"),
    "media-public-communication": ("지역신문홍보비", "정부광고비", "언론통제", "옥외광고물", "자유표시구역", "자율표시구역"),
    "youth-employment": ("초과근무수당", "대체휴무", "인턴십지원", "인턴십경력", "외국인인력"),
    "space-program": ("우주센터", "다목적발사장"),
    "public-safety-health": ("재난대응", "재난예방", "재난사고", "임시주택", "임시숙소앵커", "앵커볼트", "군중밀집", "서소문고가붕괴", "궁평지하차도", "산업재해", "안전시설투자"),
}


@lru_cache(maxsize=1)
def extension_catalog(catalog: Catalog) -> Catalog:
    if set(EXTENSION_ALIASES) - {key for key, _, _ in catalog}:
        raise ValueError("extension must use an existing ontology target")
    return tuple((key, title, (*words, *EXTENSION_ALIASES.get(key, ())))
                 for key, title, words in catalog)


def match_topic_extension(topic: dict[str, Any], catalog: Catalog) -> dict[str, Any] | None:
    # An ambiguous existing classification must not be resolved by extra words.
    if review_topic_context(topic, catalog)["reason"] == "MULTIPLE_SUPPORTED_TARGETS":
        return None
    review = review_topic_context(topic, extension_catalog(catalog))
    match = review["match"]
    if match:
        return {**match, "classification_method": "REPORT_VOCABULARY_SOURCE_AGREEMENT"}
    if review["reason"] == "MULTIPLE_SUPPORTED_TARGETS":
        return None
    # As in legacy contextual aliases, a distinctive phrase present in both
    # title and saved quote is enough even when its short tokens are stopwords.
    # Only these explicit particle variants are equivalent; never normalize
    # names or infer the target from a neighbouring turn.
    equivalents = {"양형의적정성": "양형적정성", "양형의부당": "양형부당",
                   "증거를위조": "증거위조", "증거를왜곡": "증거왜곡",
                   "선관위의상임위원": "선관위상임위원"}
    title = _compact(str(topic.get("title") or ""))
    candidates: dict[str, dict[str, Any]] = {}
    labels = {key: label for key, label, _ in catalog}
    for key, words in EXTENSION_ALIASES.items():
        canonical = lambda word: equivalents.get(word, word)
        title_terms = {canonical(word) for word in words if len(word) >= 4 and word in title}
        if not title_terms:
            continue
        for span in verified_topic_spans(topic):
            quote = _compact(span["quote"])
            matches = [word for word in words if len(word) >= 4 and word in quote
                       and canonical(word) in title_terms]
            if not matches:
                continue
            match = candidates.setdefault(key, {
                "key": key, "title": labels[key], "score": 0,
                "matched_keyword": max(matches, key=len),
                "matched_field": "issue_and_evidence_span",
                "classification_method": "REPORT_VOCABULARY_SOURCE_AGREEMENT",
                "supporting_spans": [],
            })
            match["supporting_spans"].append({**span, "source_keywords": matches,
                                             "parent_title": span.get("parent", "")})
    if len(candidates) == 1:
        return next(iter(candidates.values()))
    return None
