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
    "configuration": {
        "version": "1.0",
        "properties": {
            "initialDocumentModel": {
                "type": "string",
                "title": "최초 문서 생성 모델",
                "description": "새 보고서·계획서·초안을 처음 생성할 때 품질 우선으로 사용할 모델입니다.",
                "enum": ["upstage:solar-pro4", "upstage:solar-pro3", "upstage:solar-pro3-fast", "auto"],
                "enumLabels": {
                    "upstage:solar-pro4": "Solar Pro 4 · 최고 품질",
                    "upstage:solar-pro3": "Solar Pro 3 · 균형",
                    "upstage:solar-pro3-fast": "Solar Pro 3 Fast · 속도",
                    "auto": "자동 판단",
                },
                "default": "upstage:solar-pro4",
            },
        },
        "required": ["initialDocumentModel"],
    },
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
            "시사점",
            "정책",
            "법률",
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
    {
        "intentType": "information_query",
        "label": "빠른 정보 조회",
        "keywords": ["조회", "검색", "확인", "찾아", "알려", "현황", "무엇", "얼마"],
        "complexity": "low",
    },
]


def analyze(text: str, context: dict | None = None, configuration: dict | None = None) -> dict:
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
    context = context or {}
    configuration = configuration or {}
    creates_document = (
        not bool(context.get("has_selection") or context.get("selection_text"))
        and any(
            phrase in normalized
            for phrase in (
                "보고서로 작성",
                "보고서 작성",
                "보고서로 만들어",
                "보고서로 생성",
                "보고서를 생성",
                "보고서 생성",
                "계획서로 작성",
                "계획서 작성",
                "계획서로 만들어",
                "문서로 작성",
                "문서로 만들어",
                "초안 작성",
                "초안을 만들어",
                "작성해줘",
                "작성해주세요",
                "작성 해줘",
            )
        )
    )
    preferred_model = str(configuration.get("initialDocumentModel") or "upstage:solar-pro4") if creates_document else ""
    return {
        "intentType": rule["intentType"],
        "label": rule["label"],
        "complexity": rule["complexity"],
        "confidence": round(confidence, 2),
        "matchedSignals": matched,
        "analysisMode": "local-rule-audit",
        "externalTransfer": False,
        "createsInitialDocument": creates_document,
        "preferredModelId": "" if preferred_model == "auto" else preferred_model,
        "modelPolicyReason": "최초 문서 생성 품질 우선 설정" if creates_document and preferred_model != "auto" else "의도 기반 자동 선택",
    }
