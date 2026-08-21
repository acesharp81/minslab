"""Model Management MCP: low-latency primary routing with safe fallbacks."""

from __future__ import annotations

from copy import deepcopy
import os


MANIFEST = {
    "id": "core.model-management",
    "name": "모델 관리 MCP",
    "version": "0.1.0",
    "runtime": "local",
    "description": "응답속도·한국어 품질·데이터 정책을 관리하고 기본 모델과 대체 모델을 선택합니다.",
    "inputs": {"intentAnalysis": {"type": "object"}},
    "outputs": {"route": {"type": "object"}},
    "permissions": [
        {"scope": "model.invoke", "reason": "선택된 모델 호출", "required": True},
        {"scope": "network.send", "reason": "승인된 Upstage Solar endpoint 호출", "required": True},
    ],
}


MODELS = [
    {
        "id": "upstage:solar-pro3-fast",
        "apiModel": "solar-pro3",
        "reasoningEffort": None,
        "label": "Upstage · Solar Pro 3 Fast",
        "provider": "upstage",
        "price": {"input": 0, "output": 0},
        "contextTokens": 128_000,
        "personality": "fast-korean-generalist",
        "strengths": ["information_query", "quick_answer", "simple_summary", "simple_edit"],
        "description": "추론 확장 없이 빠르게 답하는 기본 모드입니다. 단순 조회·확인·짧은 요약에 사용합니다.",
        "dataPolicy": {"externalTransfer": True, "allowClassifications": ["public", "internal"], "requiresMasking": True},
        "default": True,
        "speedClass": "fast",
        "routingRole": "fast",
        "source": "https://api.upstage.ai/v1/models",
    },
    {
        "id": "upstage:solar-pro3",
        "apiModel": "solar-pro3",
        "reasoningEffort": "medium",
        "label": "Upstage · Solar Pro 3",
        "provider": "upstage",
        "price": {"input": 0, "output": 0},
        "contextTokens": 128_000,
        "personality": "document-specialist",
        "strengths": ["document_writing", "summarization", "official_tone", "structured_output", "retrieval_synthesis"],
        "description": "보고서 작성·문장 편집·RAG 근거 종합과 구조화된 응답에 사용하는 표준 모드입니다.",
        "dataPolicy": {"externalTransfer": True, "allowClassifications": ["public", "internal"], "requiresMasking": True},
        "default": False,
        "speedClass": "balanced",
        "routingRole": "balanced",
        "source": "https://api.upstage.ai/v1/models",
    },
    {
        "id": "upstage:solar-pro4",
        "apiModel": "solar-pro4",
        "reasoningEffort": "medium",
        "label": "Upstage · Solar Pro 4",
        "provider": "upstage",
        "price": {"input": 0, "output": 0},
        "contextTokens": 128_000,
        "personality": "reasoning-agent",
        "strengths": ["complex_reasoning", "multi_step_planning", "calculation", "policy_validation", "cross_document_analysis"],
        "description": "복합 비교·계산·정책 검증·다문서 분석처럼 깊은 추론이 필요한 업무에 사용합니다.",
        "dataPolicy": {"externalTransfer": True, "allowClassifications": ["public", "internal"], "requiresMasking": True},
        "default": False,
        "speedClass": "deep",
        "routingRole": "deep",
        "source": "https://api.upstage.ai/v1/models",
    },
]


def validate_registry() -> None:
    if not MODELS:
        raise ValueError("사용 가능한 모델이 하나 이상 필요합니다.")
    ids = set()
    for model in MODELS:
        if model["id"] in ids:
            raise ValueError("중복 모델 ID가 있습니다.")
        ids.add(model["id"])
        price = model.get("price") or {}
        if float(price.get("input", -1)) < 0 or float(price.get("output", -1)) < 0:
            raise ValueError("모델 가격은 0 이상이어야 합니다.")
    if sum(bool(model.get("default")) for model in MODELS) != 1:
        raise ValueError("기본 모델은 정확히 하나여야 합니다.")


def list_models() -> list[dict]:
    validate_registry()
    return deepcopy(MODELS)


def select_model(intent_analysis: dict, classification: str = "internal") -> dict:
    validate_registry()
    intent_type = str(intent_analysis.get("intentType") or "document_writing")
    signals = {str(item) for item in intent_analysis.get("matchedSignals") or []}
    roles = {model["routingRole"]: model for model in MODELS}
    deep_signals = {"비교", "검증", "산출", "계산", "시사점", "정책", "법률", "의존성", "단계"}
    if intent_type == "complex_reasoning" and (len(signals) >= 2 or signals & deep_signals):
        selected = roles["deep"]
        reason = "복합 비교·검증·계산 신호를 감지하여 Solar Pro 4 선택"
    elif intent_type in {"document_writing", "complex_reasoning"}:
        selected = roles["balanced"]
        reason = "문서 작성 또는 단일 분석 요청으로 Solar Pro 3 선택"
    else:
        selected = roles["fast"]
        reason = "단순 조회·확인 요청으로 Solar Pro 3 Fast 선택"
    preferred_id = str(intent_analysis.get("preferredModelId") or "")
    preferred = next((model for model in MODELS if model["id"] == preferred_id), None)
    if preferred:
        selected = preferred
        reason = str(intent_analysis.get("modelPolicyReason") or "의도분석 MCP 환경설정 적용")
    if os.getenv("AIWORKS_MODEL_ROUTING_MODE", "auto").strip().lower() == "manual":
        configured_id = os.getenv("AIWORKS_DEFAULT_MODEL", "").strip()
        selected = next((model for model in MODELS if model["id"] == configured_id), selected)
        reason = "운영자 수동 고정 모델 선택"
    fallback_role = {"fast": "balanced", "balanced": "deep", "deep": "balanced"}[selected["routingRole"]]
    fallback = roles[fallback_role]
    allowed = classification in selected["dataPolicy"]["allowClassifications"]
    return {
        "model": deepcopy(selected),
        "reason": reason,
        "externalTransfer": True,
        "classificationAllowed": allowed,
        "requiredPermissions": ["model.invoke", "network.send"],
        "fallbackModelId": fallback["id"],
    }
