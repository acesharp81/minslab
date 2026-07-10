"""MinsLab 포트폴리오에서 보고서 처리 코어를 홈페이지 API에 연결하는 서비스 어댑터."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
REPORT_CORE_PATH = BASE_DIR / "report_core.py"
DEFAULT_TIMEOUT = 120
DEFAULT_SYSTEM_PROMPT = (
    "너는 지방자치단체 민원 담당자의 초안 작성 보조자입니다. "
    "반드시 유효한 JSON 객체만 반환하세요. 마크다운, 코드블록, 설명 문장을 쓰지 마세요. "
    "JSON 키는 lines 하나만 사용하고, lines 값은 4~5개의 한국어 문장 배열이어야 합니다."
)
MAX_SYSTEM_PROMPT_CHARS = 4000

_REPORT_CORE = None


def load_report_core():
    """보고서 처리 코어 report_core.py를 재사용 가능한 모듈로 읽는다."""
    global _REPORT_CORE
    if _REPORT_CORE is not None:
        return _REPORT_CORE

    spec = importlib.util.spec_from_file_location("report_draft_core", REPORT_CORE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("보고서 처리 report_core.py를 불러오지 못했습니다.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    _REPORT_CORE = module
    return module


def _number(value, default, minimum, maximum, *, integer=False):
    try:
        parsed = int(value) if integer else float(value)
    except (TypeError, ValueError):
        parsed = default
    parsed = max(minimum, min(maximum, parsed))
    return int(parsed) if integer else round(float(parsed), 2)


def runtime_settings():
    """모델 선택창과 옵션창에서 사용할 기본값과 범위를 반환한다."""
    source = load_report_core()
    config = source.load_config()
    default_model = (
        os.environ.get("OLLAMA_MODEL")
        or config.get("recommended_model")
        or source.DEFAULT_MODEL
    )
    recommended = [
        str(item).strip()
        for item in config.get("recommended_models", [])
        if str(item).strip()
    ]
    if default_model not in recommended:
        recommended.insert(0, default_model)

    return {
        "default_model": default_model,
        "recommended_models": recommended,
        "temperature": _number(config.get("temperature"), 0.3, 0.0, 2.0),
        "num_predict": _number(config.get("num_predict"), 500, 500, 4096, integer=True),
        "num_ctx": _number(config.get("num_ctx"), 2048, 512, 32768, integer=True),
        "system_prompt": DEFAULT_SYSTEM_PROMPT,
        "limits": {
            "temperature": {"min": 0.0, "max": 2.0, "step": 0.1},
            "num_predict": {"min": 500, "max": 4096, "step": 100},
            "num_ctx": {"min": 512, "max": 32768, "step": 256},
        },
    }



def normalize_system_prompt(value):
    """사용자 시스템 프롬프트를 검증하고 빈 값이면 기본값을 사용한다."""
    prompt = str(value or "").strip()
    if not prompt:
        return DEFAULT_SYSTEM_PROMPT
    if len(prompt) > MAX_SYSTEM_PROMPT_CHARS:
        raise ValueError(
            f"시스템 프롬프트는 {MAX_SYSTEM_PROMPT_CHARS:,}자 이하로 입력하세요."
        )
    return prompt


def normalize_options(options=None):
    """브라우저가 보낸 생성 옵션을 안전한 범위로 제한한다."""
    defaults = runtime_settings()
    options = options if isinstance(options, dict) else {}
    return {
        "temperature": _number(
            options.get("temperature"), defaults["temperature"], 0.0, 2.0
        ),
        "num_predict": _number(
            options.get("num_predict"),
            defaults["num_predict"],
            500,
            4096,
            integer=True,
        ),
        "num_ctx": _number(
            options.get("num_ctx"), defaults["num_ctx"], 512, 32768, integer=True
        ),
    }


def _is_chat_model(model):
    name = str(model.get("name") or "").lower()
    details = model.get("details") if isinstance(model.get("details"), dict) else {}
    family = str(details.get("family") or "").lower()
    families = [str(item).lower() for item in details.get("families", []) if item]
    if not name or "embed" in name or "embedding" in name:
        return False
    return "bert" not in family and not any("bert" in item for item in families)


def _ollama_base_url():
    source = load_report_core()
    config = source.load_config()
    return os.environ.get(
        "OLLAMA_BASE_URL", config.get("ollama_base_url", "http://127.0.0.1:11434")
    ).rstrip("/")


def installed_models():
    """서버에 설치된 로컬 대화 모델 목록을 Ollama에서 조회한다."""
    request = urllib.request.Request(f"{_ollama_base_url()}/api/tags", method="GET")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Ollama 모델 목록 조회 실패: {error}") from error

    return [
        {
            "value": model["name"],
            "name": model["name"],
            "label": f"Ollama · {model['name']}",
            "size": model.get("size", 0),
            "modified_at": model.get("modified_at", ""),
            "details": model.get("details", {}),
            "installed": True,
        }
        for model in data.get("models", [])
        if model.get("name") and _is_chat_model(model)
    ]


def model_options():
    """설치 모델과 옵션 기본값을 포트폴리오 UI 형식으로 반환한다."""
    settings = runtime_settings()
    warning = ""
    try:
        models = installed_models()
    except RuntimeError as error:
        models = []
        warning = str(error)

    installed_names = {item["name"] for item in models}
    default_model = settings["default_model"]
    if models and default_model not in installed_names:
        default_model = models[0]["name"]
    if not models:
        models = [
            {
                "value": default_model,
                "name": default_model,
                "label": f"Ollama · {default_model} (설정값)",
                "size": 0,
                "details": {},
                "installed": False,
            }
        ]

    return {
        "models": models,
        "default": default_model,
        "settings": settings,
        "warning": warning,
    }


def _selected_model(value):
    model = str(value or "").strip()
    if not model:
        model = runtime_settings()["default_model"]
    if len(model) > 200 or any(char in model for char in "\r\n\0"):
        raise ValueError("모델 이름이 올바르지 않습니다.")
    return model


def call_ollama(prompt, model, options, system_prompt):
    """선택된 모델, 생성 옵션, 시스템 프롬프트로 로컬 Ollama를 호출한다."""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "format": "json",
        "options": options,
    }
    request = urllib.request.Request(
        f"{_ollama_base_url()}/api/chat",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Ollama 생성 실패: {error}") from error
    if data.get("error"):
        raise RuntimeError(f"Ollama 오류: {data['error']}")
    return data.get("message", {}).get("content") or data.get("response", "")


def generate(payload):
    """요청과 관련된 XML 사례를 선택해 검토 가능한 초안을 생성한다."""
    source = load_report_core()
    request_text = str(payload.get("request") or "").strip()
    if not request_text:
        raise ValueError("요청 내용을 입력하세요.")
    if len(request_text) > 8000:
        raise ValueError("요청 내용은 8,000자 이하로 입력하세요.")

    model = _selected_model(payload.get("model"))
    request_options = payload.get("options") if isinstance(payload.get("options"), dict) else {}
    options = normalize_options(request_options)
    system_prompt = normalize_system_prompt(request_options.get("system_prompt"))
    style_guide, cases = source.load_materials()
    selected_case = source.select_best_case(request_text, cases)
    prompt = source.build_prompt(request_text, style_guide, selected_case)

    started = time.perf_counter()
    raw_answer = call_ollama(prompt, model, options, system_prompt)
    answer = source.finalize_answer(source.extract_answer(raw_answer), selected_case)
    return {
        "answer": answer,
        "model": model,
        "options": options,
        "system_prompt_customized": system_prompt != DEFAULT_SYSTEM_PROMPT,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "case": {
            "id": selected_case["id"],
            "title": selected_case["title"],
            "reply_type": selected_case["reply_type"],
            "department": selected_case["department"],
            "contact": selected_case["contact"],
            "review_note": selected_case["review_note"],
        },
        "review_notice": style_guide.get(
            "review_notice",
            "생성 초안은 담당자가 사실관계와 법령 근거를 확인한 뒤 사용한다.",
        ),
    }
