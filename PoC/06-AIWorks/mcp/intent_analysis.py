"""Intent Analysis MCP: deterministic intent signals for auditable routing."""

from __future__ import annotations


MANIFEST = {
    "id": "core.intent-analysis",
    "name": "의도 분석 MCP",
    "version": "0.1.0",
    "runtime": "local",
    "description": "사용자 요청을 외부 전송 없이 분석하여 모델 선택에 필요한 업무 유형과 근거를 반환합니다.",
    "inputs": {"text": {"type": "string"}},
    "outputs": {"intentAnalysis": {"type": "object"}},
    "permissions": [],
}


INTENT_RULES = [
    {
        "intentType": "complex_reasoning",
        "label": "복합 추론·계획",
        "keywords": [
            "계획",
            "검증",
            "분석",
            "비교",
            "근거",
            "예산",
            "산출",
            "계산",
            "현재 값",
            "최신 기준",
            "의존성",
            "단계",
        ],
        "complexity": "high",
    },
    {
        "intentType": "document_writing",
        "label": "문서 작성·변환",
        "keywords": [
            "요약",
            "공문체",
            "작성",
            "문장",
            "다듬",
            "번역",
            "축약",
            "두 줄",
            "2줄",
            "표현",
        ],
        "complexity": "low",
    },
]


def analyze(text: str) -> dict:
    normalized = " ".join(str(text or "").lower().split())
    if not normalized:
        raise ValueError("의도를 분석할 요청이 필요합니다.")
    scores = []
    for rule in INTENT_RULES:
        matched = [keyword for keyword in rule["keywords"] if keyword in normalized]
        scores.append((len(matched), rule, matched))
    scores.sort(key=lambda item: item[0], reverse=True)
    score, rule, matched = scores[0]
    if score == 0:
        rule = INTENT_RULES[1]
    confidence = min(0.98, 0.62 + max(score, 1) * 0.09)
    return {
        "intentType": rule["intentType"],
        "label": rule["label"],
        "complexity": rule["complexity"],
        "confidence": round(confidence, 2),
        "matchedSignals": matched,
        "analysisMode": "local-rule-audit",
        "externalTransfer": False,
    }
