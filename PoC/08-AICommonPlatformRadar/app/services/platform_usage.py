from __future__ import annotations

import re
from typing import Any


# 조달 문서에는 정식 명칭 외에 "범정부 AI 플랫폼"이 자주 사용된다.
# 일반적인 "AI 플랫폼"까지 포함하면 다른 상용·기관 플랫폼을 오인하므로
# 반드시 "범정부"가 함께 있는 별칭만 공통기반으로 인정한다.
COMMON_PLATFORM_TERM = (
    r"(?:(?:범정부\s*)?(?:인공지능|AI)\s*공통기반|"
    r"범정부\s*(?:인공지능|AI)\s*플랫폼)"
)
COMMON_PLATFORM_MENTION = re.compile(COMMON_PLATFORM_TERM, re.IGNORECASE)
COMMON_PLATFORM_USAGE = re.compile(
    COMMON_PLATFORM_TERM
    + r".{0,40}(?:활용(?:한다|하여|할\s*예정|\s*계획)|"
      r"사용(?:한다|하여|할\s*예정|\s*계획)|"
      r"연계(?:한다|하여|할\s*예정)|적용(?:한다|하여|할\s*예정)|"
      r"이용(?:한다|하여|할\s*예정))",
    re.IGNORECASE,
)
COMMON_PLATFORM_NON_USE = re.compile(
    rf"(?:{COMMON_PLATFORM_TERM}.{{0,40}}(?:사용|활용|연계|적용)하지\s*않|"
    rf"{COMMON_PLATFORM_TERM}.{{0,30}}미사용|미사용.{{0,30}}{COMMON_PLATFORM_TERM})",
    re.IGNORECASE,
)

# 공통기반을 실제 채택한 문구가 아니라 여러 대안 중 하나로 병렬 제시한 경우다.
# 이 상태는 최종 2유형을 유지하되, 단순한 "사용 문구 없음"과 구분한다.
OPTIONAL_PLATFORM_USAGE = re.compile(
    rf"(?:{COMMON_PLATFORM_TERM}.{{0,120}}(?:등|또는|선택|대안).{{0,120}}"
    rf"(?:방안|검토|제시|선정)|"
    rf"(?:대안|선택지|방안).{{0,120}}{COMMON_PLATFORM_TERM})",
    re.IGNORECASE | re.DOTALL,
)

OPTIONAL_USAGE_LABEL = "선택적 범정부 AI 공통기반 활용 명시"
OPTIONAL_USAGE_REASON = (
    "범정부 AI 공통기반이 다른 인프라 대안과 함께 선택적으로 제시되어 있으며, "
    "우선 검토 여부와 실제 채택 여부는 확인되지 않았습니다."
)


def is_optional_platform_usage_text(text: str | None) -> bool:
    return bool(text and OPTIONAL_PLATFORM_USAGE.search(text))


def _evidence_quotes(result: dict[str, Any]) -> list[str]:
    quotes: list[str] = []
    for field in ("platform_usage_evidence", "evidence"):
        items = result.get(field)
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict):
                quote = str(item.get("quote") or "").strip()
                if quote:
                    quotes.append(quote)
    return quotes


def has_optional_platform_usage(result: dict[str, Any]) -> bool:
    """Detect optional use in grounded evidence, including stored analyses."""
    if str(result.get("platform_usage") or "") in {"uses", "not_used"}:
        return False
    return any(is_optional_platform_usage_text(quote) for quote in _evidence_quotes(result))


def with_usage_presentation(result: dict[str, Any]) -> dict[str, Any]:
    presented = dict(result)
    optional = has_optional_platform_usage(presented)
    presented["optional_platform_usage"] = optional
    if optional:
        presented["platform_usage_display_label"] = OPTIONAL_USAGE_LABEL
        presented["platform_usage_display_reason"] = OPTIONAL_USAGE_REASON
    else:
        presented["platform_usage_display_label"] = ""
        presented["platform_usage_display_reason"] = ""
    return presented
