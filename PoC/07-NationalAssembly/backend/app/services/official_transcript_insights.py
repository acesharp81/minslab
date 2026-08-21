from __future__ import annotations


GENERATOR_VERSION = "official-keyword-insight/2.0"
CLASSIFICATION_METHOD = "DETERMINISTIC_KEYWORD_RULE"

INSTITUTION_NAMES: tuple[str, ...] = (
    "행정안전위원회", "예산결산특별위원회", "법제사법위원회",
    "행안위", "예결위", "법사위",
)

TOPIC_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("재난·안전", ("재난", "호우", "복구", "피해", "안전", "소방")),
    ("재정·예산", ("예산", "재정", "재원", "결산", "추경", "세입", "세출")),
    ("법무·사법", ("법률", "법무", "법원", "검찰", "수사", "사법", "특별검사")),
    ("선거·참정권", ("선거", "투표", "참정권", "선관위")),
    ("지방·행정", ("행정", "지방", "자치", "공무원", "정부조직")),
    ("절차·의결", ("개의", "개회", "산회", "상정", "의결", "가결", "토론", "의사일정")),
)

MINISTRY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("행정안전부", ("재난", "안전", "소방", "행정", "지방", "자치", "공무원", "선거", "투표", "선관위")),
    ("기획재정부", ("예산", "재정", "재원", "결산", "추경", "세입", "세출")),
    ("법무부", ("법률", "법무", "검찰", "수사", "사법", "특별검사")),
)


def _mask_institution_names(text: str) -> str:
    for name in INSTITUTION_NAMES:
        text = text.replace(name, " ")
    return text


def _matches(
    text: str, rules: tuple[tuple[str, tuple[str, ...]], ...]
) -> list[dict[str, object]]:
    result = []
    for label, keywords in rules:
        matched = [keyword for keyword in keywords if keyword in text]
        if matched:
            result.append({"label": label, "keywords": matched})
    return result


def classify_official_utterance(text: str) -> dict[str, object]:
    evidence_text = _mask_institution_names(text)
    topic_links = _matches(evidence_text, TOPIC_RULES)
    ministry_links = _matches(evidence_text, MINISTRY_RULES)
    policy_topics = [
        item for item in topic_links if item["label"] not in {"절차·의결"}
    ]
    utterance_kind = "POLICY" if policy_topics else (
        "PROCEDURAL" if topic_links else "OTHER"
    )
    if not topic_links:
        topic_links = [{"label": "기타 발언", "keywords": []}]
    evidence_keywords = sorted({
        keyword
        for item in [*topic_links, *ministry_links]
        for keyword in item["keywords"]
    })
    return {
        "utterance_kind": utterance_kind,
        "topics": [str(item["label"]) for item in topic_links],
        "ministries": [str(item["label"]) for item in ministry_links],
        "topic_links": topic_links,
        "ministry_links": [
            {**item, "relation": "RELATED"} for item in ministry_links
        ],
        "evidence_keywords": evidence_keywords,
    }
