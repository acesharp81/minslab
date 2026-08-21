"""Template MCP v2: bind presentation rules to a canonical Report Document."""

from __future__ import annotations

from copy import deepcopy


MANIFEST = {
    "id": "template.report-style",
    "name": "보고서 양식 적용 MCP v2",
    "version": "0.1.0",
    "runtime": "local",
    "description": "보고서의 사실·본문을 바꾸지 않고 문체, 글머리표, 문단 스타일과 출력 프리셋을 연결합니다.",
    "inputs": {"reportDocument": {"type": "object"}, "intent": {"type": "string"}},
    "outputs": {"reportDocument": {"type": "object"}, "template": {"type": "object"}},
    "permissions": [],
}


TEMPLATES = {
    "standard-report.v2": {
        "id": "standard-report.v2",
        "name": "표준 보고서",
        "version": "2.0",
        "styleProfile": "standard",
        "rendererProfile": "standard",
        "rendererOptions": {"preset": "보고서"},
        "listStyle": {"level1": "-", "embeddedMarker": False},
        "contentPolicy": "preserve-semantic-blocks",
    },
    "central-government-outline.v2": {
        "id": "central-government-outline.v2",
        "name": "중앙부처 개조식 보고서",
        "version": "2.0",
        "styleProfile": "central-government-outline",
        "rendererProfile": "mois-internal",
        "rendererOptions": {"preset": "개조식"},
        "listStyle": {"level1": "-", "embeddedMarker": False},
        "contentPolicy": "preserve-facts-normalize-outline",
    },
}


def select(intent: str = "", requested: str = "") -> dict:
    if requested in TEMPLATES:
        return deepcopy(TEMPLATES[requested])
    normalized = " ".join(str(intent or "").lower().split())
    if any(term in normalized for term in ("중앙부처", "개조식", "항목식", "행안부", "행정안전부")):
        return deepcopy(TEMPLATES["central-government-outline.v2"])
    return deepcopy(TEMPLATES["standard-report.v2"])


def apply(report_document: dict, template: dict, fact_snapshot: dict | None = None) -> dict:
    document = deepcopy(report_document)
    selected = deepcopy(template)
    document["template"] = selected
    document["factSnapshot"] = {
        "projectId": (fact_snapshot or {}).get("projectId"),
        "asOf": (fact_snapshot or {}).get("asOf"),
        "valueIds": list((fact_snapshot or {}).get("valueIds") or []),
        "facts": deepcopy((fact_snapshot or {}).get("facts") or {}),
    }
    document["presentation"] = {
        "rendererProfile": selected.get("rendererProfile") or "standard",
        "rendererOptions": deepcopy(selected.get("rendererOptions") or {}),
        "listStyle": deepcopy(selected.get("listStyle") or {}),
        "markerOwnership": "renderer",
    }
    return document
