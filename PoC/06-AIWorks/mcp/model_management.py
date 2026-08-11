"""Model Management MCP: free-only model registry and capability routing."""

from __future__ import annotations

from copy import deepcopy


MANIFEST = {
    "id": "core.model-management",
    "name": "모델 관리 MCP",
    "version": "0.1.0",
    "runtime": "local",
    "description": "무료 모델의 가격·능력·데이터 정책을 관리하고 의도 분석 결과에 맞는 모델을 선택합니다.",
    "inputs": {"intentAnalysis": {"type": "object"}},
    "outputs": {"route": {"type": "object"}},
    "permissions": [
        {"scope": "model.invoke", "reason": "선택된 모델 호출", "required": True},
        {"scope": "network.send", "reason": "OpenRouter 무료 endpoint 호출", "required": True},
    ],
}


MODELS = [
    {
        "id": "google/gemma-4-26b-a4b-it:free",
        "label": "Google · Gemma 4 26B A4B (무료)",
        "provider": "openrouter",
        "price": {"input": 0, "output": 0},
        "contextTokens": 262_000,
        "personality": "document-specialist",
        "strengths": [
            "document_writing",
            "summarization",
            "official_tone",
            "translation",
            "structured_output",
        ],
        "description": "빠른 지시 이행과 자연스러운 문서 작성·요약·문체 변경에 우선 사용합니다.",
        "dataPolicy": {
            "externalTransfer": True,
            "allowClassifications": ["public", "internal"],
            "requiresMasking": True,
        },
        "freeOnly": True,
        "source": "https://openrouter.ai/google/gemma-4-26b-a4b-it:free",
    },
    {
        "id": "openai/gpt-oss-20b:free",
        "label": "OpenAI · gpt-oss-20b (무료)",
        "provider": "openrouter",
        "price": {"input": 0, "output": 0},
        "contextTokens": 131_000,
        "personality": "reasoning-agent",
        "strengths": [
            "complex_reasoning",
            "multi_step_planning",
            "calculation",
            "policy_validation",
            "cross_document_analysis",
        ],
        "description": "복합 추론, 단계별 계획, 계산·근거 검증과 구조화된 도구 작업에 우선 사용합니다.",
        "dataPolicy": {
            "externalTransfer": True,
            "allowClassifications": ["public", "internal"],
            "requiresMasking": True,
        },
        "freeOnly": True,
        "source": "https://openrouter.ai/openai/gpt-oss-20b:free",
    },
]


def validate_registry() -> None:
    if len(MODELS) != 2:
        raise ValueError("테스트 모델은 정확히 2개만 등록해야 합니다.")
    ids = set()
    for model in MODELS:
        if model["id"] in ids:
            raise ValueError("중복 모델 ID가 있습니다.")
        ids.add(model["id"])
        if not model["id"].endswith(":free") or not model.get("freeOnly"):
            raise ValueError("무료 variant가 아닌 모델은 등록할 수 없습니다.")
        price = model.get("price") or {}
        if float(price.get("input", -1)) != 0 or float(price.get("output", -1)) != 0:
            raise ValueError("입력·출력 가격이 모두 0인 모델만 등록할 수 있습니다.")


def list_models() -> list[dict]:
    validate_registry()
    return deepcopy(MODELS)


def select_model(intent_analysis: dict, classification: str = "internal") -> dict:
    validate_registry()
    intent_type = str(intent_analysis.get("intentType") or "document_writing")
    candidates = [model for model in MODELS if intent_type in model["strengths"]]
    selected = candidates[0] if candidates else MODELS[0]
    allowed = classification in selected["dataPolicy"]["allowClassifications"]
    return {
        "model": deepcopy(selected),
        "reason": (
            f"{intent_type} 의도와 {selected['personality']} 성격이 일치하여 선택"
            if candidates
            else "일반 문서 업무 기본 모델로 선택"
        ),
        "externalTransfer": True,
        "classificationAllowed": allowed,
        "requiredPermissions": ["model.invoke", "network.send"],
        "fallbackModelId": next(model["id"] for model in MODELS if model["id"] != selected["id"]),
    }
