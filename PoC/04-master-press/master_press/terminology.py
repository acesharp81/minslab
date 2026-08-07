from __future__ import annotations

import re


# Aliases normalize names, but do not by themselves assert that two articles
# describe the same event.
EDITORIAL_TERM_ALIASES = {
    "중대본": "중앙재난안전대책본부",
    "중앙재난대책본부": "중앙재난안전대책본부",
    "중앙재난안전대책본부": "중앙재난안전대책본부",
}

EVENT_CONCEPT_PREFIX = "사건·"


def canonical_editorial_term(value: object) -> str:
    clean = str(value or "").strip()
    compact = re.sub(r"[\s·._-]+", "", clean).casefold()
    return EDITORIAL_TERM_ALIASES.get(compact, clean)


def inferred_editorial_events(article_text: object) -> list[str]:
    """Return precise event signatures; broad subjects are excluded."""
    normalized = re.sub(r"\s+", " ", str(article_text or "")).casefold().strip()
    compact = re.sub(r"\s+", "", normalized)
    heatwave = "폭염" in compact or "무더위" in compact
    emergency_hq = "중대본" in compact or "중앙재난안전대책본부" in compact
    if not heatwave:
        return []
    events: list[str] = []
    if emergency_hq and "2단계" in compact and any(term in compact for term in ("격상", "가동", "발령", "범정부대응")):
        events.append(EVENT_CONCEPT_PREFIX + "폭염 중대본 2단계")
    meeting = any(term in compact for term in ("점검회의", "상황점검", "추진상황점검", "긴급점검"))
    highest_response = emergency_hq and "최고수준" in compact and any(term in compact for term in ("대응", "태세", "유지"))
    if (meeting or highest_response) and not events:
        events.append(EVENT_CONCEPT_PREFIX + "폭염 중대본 대응 점검회의")
    return events
