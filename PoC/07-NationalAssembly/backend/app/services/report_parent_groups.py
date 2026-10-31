"""Coalesce known policy parents, preserving every child and its source links.

This is a display projection: it never merges issues, rewrites summaries, or
changes role/task classification. Unrecognized parents keep their model title.
"""
from __future__ import annotations

import hashlib
import re
from copy import deepcopy
from typing import Any

PARENT_GROUPING_VERSION = "policy-parent-groups/2"


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", value)


def _target(title: str, has_future_fund: bool) -> tuple[str, str] | None:
    text = _compact(title)
    # Specific policy/institution anchors; generic ministry/police names are
    # intentionally not sufficient to combine unrelated cases.
    serious = "중대범죄수사청" in text or "중수청" in text
    prosecution = "공소청" in text
    if serious and prosecution:
        return "investigation-prosecution-cooperation", "중수청·공소청 수사·기소 협력"
    if serious:
        return "serious-crime-investigation-agency", "중대범죄수사청(중수청)"
    if prosecution:
        return "prosecution-agency", "공소청 운영·수사 협력"
    if "한강버스" in text:
        return "hangang-bus", "한강버스 사업"
    if "한동훈" in text and "딸" in text and "스펙" in text:
        return "han-daughter-credentials", "한동훈 딸 허위스펙 의혹 수사"
    if "부천" in text and "화재" in text:
        return "bucheon-fire", "부천 화재 대응·재발 방지"
    if any(word in text for word in ("소방관", "소방공무원")) and any(word in text for word in ("공상", "순직")):
        return "firefighter-injury-compensation", "소방공무원 공상·순직 보상"
    # A different named fund is never an alias merely because it is a fund.
    future = "미래대응기금" in text or (has_future_fund and "미래기금" in text)
    other_fund = re.search(r"[가-힣]{2,}기금", text.replace("미래대응기금", "").replace("미래기금", ""))
    if future and not other_fund:
        return "future-response-fund", "미래대응기금"
    if "기금" in text:
        return None
    if "반도체" in text and any(word in text for word in ("경기", "호황", "초과세수")) and any(
        word in text for word in ("재정", "세수", "예산", "국가채무")
    ):
        return "semiconductor-fiscal-cycle", "반도체 경기·초과세수와 재정 운용"
    if any(word in text for word in ("재정준칙", "국가채무", "국채상환", "국가재정전망")):
        return "national-fiscal-sustainability", "재정준칙·국가채무 관리"
    if "첨단산업" in text and any(word in text for word in ("투자", "연구개발", "재정지원")):
        return "advanced-industry-investment", "첨단산업 투자·연구개발"
    return None


def compact_report_parents(brief: dict[str, Any]) -> dict[str, Any]:
    """Return a separate projection, retaining order and exact child membership."""
    result = deepcopy(brief)
    groups = result.get("topic_groups") or []
    has_future_fund = any("미래대응기금" in _compact(g.get("title", "")) for g in groups)
    buckets: dict[str, list[dict[str, Any]]] = {}
    targets = {}
    for index, group in enumerate(groups):
        target = _target(group.get("title", ""), has_future_fund)
        key = target[0] if target else f"unmatched-{index}"
        buckets.setdefault(key, []).append(group)
        if target:
            targets[key] = target[1]
    if all(len(members) == 1 for members in buckets.values()):
        return result
    output = []
    for key, members in buckets.items():
        if len(members) == 1:
            output.append(members[0])
            continue
        merged = deepcopy(members[0])
        source_id = str(members[0].get("id", ""))
        namespace = "structured-" if source_id.startswith("structured-") else "summary-" if source_id.startswith("summary-") else ""
        merged.update(id=namespace + "policy-parent-" + hashlib.sha256(key.encode()).hexdigest()[:16],
                      title=targets[key])
        for field in ("topic_ids", "evidence_ids", "task_ids", "live_topic_cluster_ids"):
            if any(field in group for group in members):
                merged[field] = list(dict.fromkeys(value for group in members for value in group.get(field, [])))
        merged["source_groups"] = [original for group in members
                                   for original in group.get("source_groups", [deepcopy(group)])]
        merged["topic_count"] = len(merged.get("topic_ids", []))
        merged["summary"] = f"세부 쟁점 {merged['topic_count']}개"
        output.append(merged)
    result["topic_groups"] = output
    result["parent_grouping"] = {
        "version": PARENT_GROUPING_VERSION,
        "source_group_count": sum(len(g.get("source_groups", [g])) for g in output),
        "display_group_count": len(output),
        "method": "POLICY_TARGET_PARENT_ONLY",
    }
    if isinstance(result.get("topic_grouping"), dict):
        result["topic_grouping"]["group_count"] = len(output)
    if isinstance(result.get("topic_structure"), dict):
        result["topic_structure"]["parent_count"] = len(output)
    return result


PARENT_POLICY_INSTRUCTION = (
    "모든 분할은 동일한 policy_parent_catalogue의 제목만 parent로 사용한다. "
    "parent는 정책·사업·제도 대상이고, 재원 배분·적립·인출·국회 통제·찬반은 세부 issue다. "
    "미래대응기금의 배분·예산총계주의·국회 통제는 parent=미래대응기금을 공유한다. "
    "같은 parent 안에서도 다른 논점은 독립 canonical 번호로 보존한다. "
    "여러 분할에서 문구를 다르게 만들지 말고 동일한 정책에는 같은 목록 제목을 선택한다. "
)


def policy_parent_catalogue(items: list[dict[str, Any]]) -> list[str]:
    """One stable vocabulary from the whole input, never the current partition.

    Only reviewed policy aliases are normalized. Different/unknown targets
    retain their source titles. No external call or child-ID rewrite is needed.
    """
    titles = [str(item.get("parent") or "").strip() for item in items]
    has_future_fund = any("미래대응기금" in _compact(title) for title in titles)
    canonical = []
    for title in titles:
        match = _target(title, has_future_fund)
        canonical.append(match[1] if match else title)
    return list(dict.fromkeys(title for title in canonical if title))


def parent_title_schema(items: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {"type": "string", "maxLength": 80}
    titles = policy_parent_catalogue(items)
    if titles:
        result["enum"] = titles
    return result
