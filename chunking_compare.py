"""문서 청킹, Supabase 임베딩, RAG 비교 실습 유틸."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import math
import os
import re
import time
import uuid
import zipfile
from typing import Any
from urllib import error, parse, request
from xml.etree import ElementTree

from env_utils import env_first, load_project_env


CHUCKING_TABLES = ("chucking_test1", "chucking_test2", "chucking_test3")
LEGACY_TABLE_ALIASES = {
    "chucking_test1": ("chucking_test1", "chucnkig_test1"),
    "chucking_test2": ("chucking_test2", "chucnkig_test2"),
    "chucking_test3": ("chucking_test3", "chucnkig_test3"),
}
_ALLOWED_TABLES = set(CHUCKING_TABLES) | {name for aliases in LEGACY_TABLE_ALIASES.values() for name in aliases}
_resolved_tables: dict[str, str] = {}
DEFAULT_CHAT_MODEL = "openai/gpt-4o-mini"
DEFAULT_EMBEDDING_MODEL = "openai/text-embedding-3-small"
DEFAULT_RERANK_MODEL = "rerank-v4.0-fast"
RAG_MODE_LABELS = {"naive": "Naive RAG", "advanced": "Advanced RAG"}
LOCAL_EMBEDDING_DIM = 1536
TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣_]+")

STRATEGIES: dict[str, dict[str, Any]] = {
    "fixed": {
        "label": "고정 길이 청킹",
        "short_label": "Fixed",
        "description": "문서를 일정한 글자 수와 겹침 구간으로 자릅니다. 구현이 단순하고 결과 크기가 예측 가능합니다.",
        "pros": ["처리 속도가 빠름", "청크 크기가 균일함", "임베딩 비용 예측이 쉬움"],
        "cons": ["문장이나 문단 중간이 끊길 수 있음", "문맥 경계 보존이 약함"],
    },
    "recursive": {
        "label": "문단 우선 재귀 청킹",
        "short_label": "Recursive",
        "description": "문단, 문장, 길이 순서로 경계를 낮춰가며 자릅니다. 원문 구조를 최대한 보존합니다.",
        "pros": ["문단 단위 의미가 잘 보존됨", "긴 문단도 자동 분할됨", "근거 문맥이 자연스러움"],
        "cons": ["청크 길이가 들쭉날쭉할 수 있음", "문서 형식 품질에 영향을 받음"],
    },
    "semantic": {
        "label": "문장 윈도우 의미 청킹",
        "short_label": "Semantic Window",
        "description": "여러 문장을 겹치는 윈도우로 묶어 주변 의미를 함께 보존합니다.",
        "pros": ["질문 주변 맥락 검색에 강함", "짧은 문서에서도 비교 근거가 풍부함", "중요 문장이 여러 청크에 노출됨"],
        "cons": ["중복 청크가 생김", "임베딩 저장량이 늘 수 있음"],
    },
}

_embedding_disabled_reason: str | None = None


load_project_env()


def _supabase_base_url() -> str:
    value = env_first("SUPABASE2_URL", "SUPABASE_URL")
    if not value:
        raise RuntimeError("SUPABASE2_URL 또는 SUPABASE_URL이 설정되지 않았습니다.")
    return value.rstrip("/")


def _supabase_key() -> str:
    value = env_first("SUPABASE2_SERVICE_ROLE_KEY", "SUPABASE_SERVICE_ROLE_KEY")
    if not value:
        raise RuntimeError("SUPABASE2_SERVICE_ROLE_KEY 또는 SUPABASE_SERVICE_ROLE_KEY가 설정되지 않았습니다.")
    return value


def _openrouter_api_key() -> str:
    value = env_first("OPENROUTER_API_KEY", "openrouter_api_key")
    if not value:
        raise RuntimeError("OPENROUTER_API_KEY가 설정되지 않았습니다.")
    return value


def _cohere_api_key() -> str:
    value = env_first("COHERE_API_KEY", "cohere_api_key")
    if not value:
        raise RuntimeError("cohere_api_key 또는 COHERE_API_KEY가 설정되지 않았습니다.")
    return value


def _rest_url() -> str:
    base = _supabase_base_url()
    return base if base.endswith("/rest/v1") else f"{base}/rest/v1"


def _table_candidates(table: str) -> tuple[str, ...]:
    if table in LEGACY_TABLE_ALIASES:
        return LEGACY_TABLE_ALIASES[table]
    if table in _ALLOWED_TABLES:
        return (table,)
    raise ValueError("허용되지 않은 Supabase 테이블입니다.")


def _raw_supabase_request(method: str, table: str, query: str = "", payload: Any = None, prefer: str | None = None) -> Any:
    headers = {
        "apikey": _supabase_key(),
        "Authorization": f"Bearer {_supabase_key()}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    suffix = f"?{query}" if query else ""
    req = request.Request(f"{_rest_url()}/{table}{suffix}", data=body, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=30) as response:
            data = response.read()
            return json.loads(data.decode("utf-8")) if data else None
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{table} 요청 실패 · {exc.code} {detail}") from exc
    except TimeoutError as exc:
        raise RuntimeError(f"{table} 요청 시간이 초과되었습니다. 잠시 후 다시 시도하세요.") from exc
    except error.URLError as exc:
        raise RuntimeError(f"{table} 연결 실패 · {exc.reason}") from exc


def _is_missing_table_error(exc: RuntimeError) -> bool:
    message = str(exc)
    return "PGRST205" in message or "Could not find the table" in message


def _resolve_table(table: str) -> str:
    if table in _resolved_tables:
        return _resolved_tables[table]
    last_error: RuntimeError | None = None
    for candidate in _table_candidates(table):
        try:
            _raw_supabase_request("GET", candidate, "select=id&limit=1")
            _resolved_tables[table] = candidate
            return candidate
        except RuntimeError as exc:
            last_error = exc
            if _is_missing_table_error(exc):
                continue
            raise
    if last_error:
        raise last_error
    raise RuntimeError(f"{table} 테이블을 찾을 수 없습니다.")


def _supabase_request(method: str, table: str, query: str = "", payload: Any = None, prefer: str | None = None) -> Any:
    actual_table = _resolve_table(table)
    return _raw_supabase_request(method, actual_table, query=query, payload=payload, prefer=prefer)


def _normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text.strip()


def _split_sentences(text: str) -> list[str]:
    compact = re.sub(r"\s+", " ", text.strip())
    if not compact:
        return []
    pieces = re.split(r"(?<=[.!?。！？])\s+|(?<=[다요죠음임함됨])\s+", compact)
    sentences = [piece.strip() for piece in pieces if piece.strip()]
    return sentences or [compact]


def _fixed_chunks(text: str, size: int = 900, overlap: int = 120) -> list[str]:
    chunks = []
    start = 0
    text_length = len(text)
    while start < text_length:
        end = min(start + size, text_length)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= text_length:
            break
        start = max(end - overlap, start + 1)
    return chunks


def _group_units(units: list[str], max_chars: int, overlap_units: int = 0) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for unit in units:
        unit_len = len(unit)
        if current and current_len + unit_len + 1 > max_chars:
            chunks.append("\n\n".join(current).strip())
            current = current[-overlap_units:] if overlap_units else []
            current_len = sum(len(item) + 2 for item in current)
        current.append(unit)
        current_len += unit_len + 2
    if current:
        chunks.append("\n\n".join(current).strip())
    return [chunk for chunk in chunks if chunk]


def _recursive_chunks(text: str, max_chars: int = 1100) -> list[str]:
    paragraphs = [part.strip() for part in re.split(r"\n{2,}", text) if part.strip()]
    units: list[str] = []
    for paragraph in paragraphs:
        if len(paragraph) <= max_chars:
            units.append(paragraph)
            continue
        sentences = _split_sentences(paragraph)
        units.extend(_group_units(sentences, max_chars=max_chars, overlap_units=1))
    return _group_units(units, max_chars=max_chars, overlap_units=1)


def _semantic_window_chunks(text: str, window_size: int = 5, stride: int = 3) -> list[str]:
    sentences = _split_sentences(text)
    if len(sentences) <= window_size:
        return [" ".join(sentences).strip()] if sentences else []
    chunks = []
    seen = set()
    for start in range(0, len(sentences), stride):
        window = " ".join(sentences[start:start + window_size]).strip()
        if not window or window in seen:
            continue
        seen.add(window)
        chunks.append(window)
        if start + window_size >= len(sentences):
            break
    return chunks


def _build_chunk_items(chunks: list[str], max_chunks: int = 30) -> list[dict[str, Any]]:
    items = []
    for index, content in enumerate(chunks[:max_chunks], start=1):
        tokens = TOKEN_RE.findall(content)
        items.append({
            "rank": index,
            "content": content,
            "char_count": len(content),
            "token_count": len(tokens),
            "preview": content[:260],
        })
    return items


def chunk_document(text: str, strategies: list[str] | None = None) -> dict[str, Any]:
    text = _normalize_text(text or "")
    if not text:
        raise ValueError("청킹할 문서 내용을 입력하거나 첨부하세요.")
    if len(text) > 150_000:
        text = text[:150_000]
    selected = strategies or ["fixed", "recursive", "semantic"]
    selected = [strategy for strategy in selected if strategy in STRATEGIES]
    if not selected:
        raise ValueError("청킹 알고리즘을 하나 이상 선택하세요.")
    if len(selected) > 3:
        raise ValueError("청킹 알고리즘은 최대 3개까지 선택할 수 있습니다.")

    plan_items = []
    for slot, strategy in enumerate(selected, start=1):
        if strategy == "fixed":
            raw_chunks = _fixed_chunks(text)
        elif strategy == "recursive":
            raw_chunks = _recursive_chunks(text)
        else:
            raw_chunks = _semantic_window_chunks(text)
        definition = STRATEGIES[strategy]
        chunks = _build_chunk_items(raw_chunks)
        avg_chars = round(sum(item["char_count"] for item in chunks) / len(chunks)) if chunks else 0
        plan_items.append({
            "slot": slot,
            "table": CHUCKING_TABLES[slot - 1],
            "strategy": strategy,
            "label": definition["label"],
            "short_label": definition["short_label"],
            "description": definition["description"],
            "pros": definition["pros"],
            "cons": definition["cons"],
            "chunks": chunks,
            "summary": f"{len(chunks)}개 청크 · 평균 {avg_chars}자",
        })
    return {
        "document": {"char_count": len(text), "token_count": len(TOKEN_RE.findall(text))},
        "plans": plan_items,
    }


def _local_hash_embedding(text: str, dim: int = LOCAL_EMBEDDING_DIM) -> list[float]:
    vector = [0.0] * dim
    tokens = TOKEN_RE.findall(text.lower())
    if not tokens:
        tokens = [text[:80] or "empty"]
    for token in tokens:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=12).digest()
        index = int.from_bytes(digest[:4], "big") % dim
        sign = 1.0 if digest[4] % 2 else -1.0
        weight = 1.0 + min(len(token), 12) / 12
        vector[index] += sign * weight
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [round(value / norm, 6) for value in vector]


def _openrouter_embedding(text: str) -> list[float]:
    model = os.getenv("OPENROUTER_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)
    payload = {"model": model, "input": text[:8000]}
    req = request.Request(
        "https://openrouter.ai/api/v1/embeddings",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {_openrouter_api_key()}",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=45) as response:
            body = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenRouter 임베딩 실패 · {exc.code} {detail}") from exc
    except TimeoutError as exc:
        raise RuntimeError("OpenRouter 임베딩 요청 시간이 초과되었습니다. 로컬 fallback 임베딩으로 전환합니다.") from exc
    except error.URLError as exc:
        raise RuntimeError(f"OpenRouter 임베딩 연결 실패 · {exc.reason}") from exc
    embedding = (body.get("data") or [{}])[0].get("embedding")
    if not isinstance(embedding, list) or not embedding:
        raise RuntimeError("OpenRouter 임베딩 응답이 비어 있습니다.")
    return [float(value) for value in embedding]


def _embedding_for_text(text: str) -> tuple[list[float], str, str | None]:
    global _embedding_disabled_reason
    model = os.getenv("OPENROUTER_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)
    if not _embedding_disabled_reason:
        try:
            return _openrouter_embedding(text), f"openrouter:{model}", None
        except RuntimeError as exc:
            _embedding_disabled_reason = str(exc)
    return _local_hash_embedding(text), "local-hash-fallback", _embedding_disabled_reason


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{value:.6f}" for value in vector) + "]"


def embed_plan(plan: dict[str, Any]) -> dict[str, Any]:
    slot = int(plan.get("slot") or 0)
    if slot < 1 or slot > len(CHUCKING_TABLES):
        raise ValueError("임베딩 대상 방식 번호가 올바르지 않습니다.")
    chunks = plan.get("chunks")
    if not isinstance(chunks, list) or not chunks:
        raise ValueError("임베딩할 청크가 없습니다.")
    table = CHUCKING_TABLES[slot - 1]
    run_id = str(uuid.uuid4())
    embedded_at = int(time.time())
    rows = []
    provider = ""
    warning = None
    for index, chunk in enumerate(chunks, start=1):
        content = str(chunk.get("content") or "").strip()
        if not content:
            continue
        vector, provider, warning = _embedding_for_text(content)
        rows.append({
            "id": index,
            "content": content,
            "metadata": {
                "run_id": run_id,
                "slot": slot,
                "strategy": plan.get("strategy"),
                "strategy_label": plan.get("label"),
                "rank": index,
                "char_count": len(content),
                "token_count": len(TOKEN_RE.findall(content)),
                "embedded_at": embedded_at,
                "embedding_provider": provider,
            },
            "embedding": _vector_literal(vector),
        })
    if not rows:
        raise ValueError("비어 있지 않은 청크가 없습니다.")
    _supabase_request("DELETE", table, "id=gte.0", prefer="return=minimal")
    _supabase_request("POST", table, payload=rows, prefer="return=representation")
    return {
        "ok": True,
        "table": table,
        "actual_table": _resolved_tables.get(table, table),
        "slot": slot,
        "strategy": plan.get("strategy"),
        "strategy_label": plan.get("label"),
        "run_id": run_id,
        "embedded_count": len(rows),
        "embedding_provider": provider,
        "warning": warning,
    }


def _parse_vector(value: Any) -> list[float]:
    if isinstance(value, list):
        return [float(item) for item in value]
    if isinstance(value, str):
        raw = value.strip()
        if raw.startswith("[") and raw.endswith("]"):
            raw = raw[1:-1]
        if not raw:
            return []
        return [float(item) for item in raw.split(",") if item.strip()]
    return []


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    size = min(len(left), len(right))
    dot = sum(left[index] * right[index] for index in range(size))
    left_norm = math.sqrt(sum(value * value for value in left[:size])) or 1.0
    right_norm = math.sqrt(sum(value * value for value in right[:size])) or 1.0
    return dot / (left_norm * right_norm)


def _request_rows(table: str, limit: int = 300) -> list[dict[str, Any]]:
    query = parse.urlencode({
        "select": "id,content,metadata,embedding",
        "order": "id.asc",
        "limit": str(limit),
    })
    return _supabase_request("GET", table, query=query) or []



def _keyword_terms(text: str, limit: int = 12) -> list[str]:
    stopwords = {"이", "그", "저", "것", "수", "등", "및", "또는", "그리고", "대한", "대해", "문서", "내용", "핵심", "요약", "알려줘"}
    terms: list[str] = []
    for token in TOKEN_RE.findall((text or "").lower()):
        if len(token) <= 1 or token in stopwords:
            continue
        if token not in terms:
            terms.append(token)
        if len(terms) >= limit:
            break
    return terms


def _advanced_query_variants(prompt: str) -> list[str]:
    terms = _keyword_terms(prompt, limit=8)
    variants = [prompt]
    if terms:
        variants.append(" ".join(terms))
        variants.append(f"{prompt}\n관련 핵심어: {' '.join(terms)}")
    return list(dict.fromkeys(variant.strip() for variant in variants if variant.strip()))[:3]


def _compress_content_for_prompt(prompt: str, content: str, max_chars: int = 900) -> str:
    content = str(content or "").strip()
    if len(content) <= max_chars:
        return content
    terms = set(_keyword_terms(prompt, limit=16))
    sentences = _split_sentences(content)
    if not sentences:
        return content[:max_chars].strip()
    ranked = []
    for index, sentence in enumerate(sentences):
        sentence_terms = set(_keyword_terms(sentence, limit=30))
        overlap = len(terms & sentence_terms)
        ranked.append((overlap, -index, sentence))
    selected = [item[2] for item in sorted(ranked, reverse=True) if item[0] > 0][:5]
    if not selected:
        selected = sentences[:4]
    compressed = " ".join(selected).strip()
    if len(compressed) > max_chars:
        compressed = compressed[:max_chars].strip()
    return compressed or content[:max_chars].strip()


def _rows_for_answer(prompt: str, top: list[dict[str, Any]], rag_mode: str) -> list[dict[str, Any]]:
    rows = []
    for index, item in enumerate(top, start=1):
        raw = dict(item.get("raw") or {})
        raw["citation"] = f"검색 조각 {index}"
        if rag_mode == "advanced":
            original = str(raw.get("content") or item.get("content") or "")
            raw["content"] = _compress_content_for_prompt(prompt, original)
            metadata = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
            raw["metadata"] = {**metadata, "context_compressed": len(raw["content"]) < len(original)}
        rows.append(raw)
    return rows


def _normalize_rag_mode(value: Any) -> str:
    mode = str(value or "naive").strip().lower()
    return mode if mode in RAG_MODE_LABELS else "naive"

def _build_context_prompt(prompt: str, rows: list[dict[str, Any]]) -> str:
    context_blocks = []
    for index, row in enumerate(rows[:10], start=1):
        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        label = metadata.get("strategy_label") or "청킹 결과"
        content = str(row.get("content") or "").strip()
        citation = row.get("citation") or f"검색 조각 {index}"
        context_blocks.append(f"[{citation}] {label} / score {row.get('score', 0):.4f}\n{content}")
    return (
        "아래 검색 조각만 근거로 한국어 답변을 작성하세요. "
        "근거에 없는 내용은 없다고 말하고, 중요한 문장 끝에는 반드시 [검색 조각 번호] 형식의 근거를 붙이세요. "
        "여러 근거가 있으면 [검색 조각 1][검색 조각 3]처럼 붙이고, 청킹/RAG 방식 차이가 보이면 짧게 언급하세요.\n\n"
        f"질문:\n{prompt}\n\n검색 조각:\n" + "\n\n".join(context_blocks)
    )


def _ollama_request(payload: dict[str, Any]) -> dict[str, Any]:
    base_url = env_first("OLLAMA_BASE_URL", default="http://127.0.0.1:11434").rstrip("/")
    try:
        from analytics_store import increment_local_llm_calls
        increment_local_llm_calls()
    except Exception:
        pass
    req = request.Request(
        f"{base_url}/api/chat",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Ollama 호출 실패 · {exc.code} {detail}") from exc
    except TimeoutError as exc:
        raise RuntimeError("Ollama 응답 시간이 초과되었습니다. 모델이 문서를 처리하는 데 너무 오래 걸렸습니다.") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Ollama 연결 실패 · {exc.reason}") from exc


def _call_openrouter(model: str, prompt: str, rows: list[dict[str, Any]], temperature: float = 0.2) -> str:
    if not rows:
        return "검색된 청크가 없어 답변 생성을 생략했습니다."
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "항상 자연스러운 한국어로만 답변하세요. 검색 문맥에 없는 내용은 추측하지 마세요."},
            {"role": "user", "content": _build_context_prompt(prompt, rows)},
        ],
        "temperature": temperature,
        "max_tokens": 700,
    }
    req = request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {_openrouter_api_key()}",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=60) as response:
            body = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenRouter 호출 실패 · {exc.code} {detail}") from exc
    except TimeoutError as exc:
        raise RuntimeError("OpenRouter 답변 생성 시간이 초과되었습니다. 문서/Top-K를 줄이거나 다시 시도하세요.") from exc
    except error.URLError as exc:
        raise RuntimeError(f"OpenRouter 연결 실패 · {exc.reason}") from exc
    choices = body.get("choices") or []
    if not choices:
        raise RuntimeError("OpenRouter 응답에 choices가 없습니다.")
    answer = choices[0].get("message", {}).get("content", "").strip()
    if not answer:
        raise RuntimeError("OpenRouter 응답 텍스트가 비어 있습니다.")
    return answer


def _call_ollama(model: str, prompt: str, rows: list[dict[str, Any]], temperature: float = 0.2, top_k: int = 40) -> str:
    if not rows:
        return "검색된 청크가 없어 답변 생성을 생략했습니다."
    body = _ollama_request({
        "model": model,
        "stream": False,
        "messages": [
            {"role": "system", "content": "항상 자연스러운 한국어로만 답변하세요. 검색 문맥에 없는 내용은 추측하지 마세요."},
            {"role": "user", "content": _build_context_prompt(prompt, rows)},
        ],
        "options": {"temperature": temperature, "num_predict": 700, "top_p": 0.9, "top_k": top_k},
    })
    answer = body.get("message", {}).get("content", "").strip()
    if not answer:
        raise RuntimeError("Ollama 응답 텍스트가 비어 있습니다.")
    return answer


def _normalize_chat_model(model: str | None) -> tuple[str, str]:
    value = (model or DEFAULT_CHAT_MODEL).strip()
    if value.startswith("ollama:"):
        local_model = value.split(":", 1)[1].strip()
        if not local_model:
            raise ValueError("Ollama 모델명이 비어 있습니다.")
        return "ollama", local_model
    if value.startswith("openrouter:"):
        return "openrouter", value.split(":", 1)[1].strip() or DEFAULT_CHAT_MODEL
    if "/" not in value:
        return "ollama", value
    return "openrouter", value or DEFAULT_CHAT_MODEL


def _call_selected_model(model: str, prompt: str, rows: list[dict[str, Any]], temperature: float = 0.2, top_k: int = 40) -> str:
    provider, model_name = _normalize_chat_model(model)
    if provider == "ollama":
        return _call_ollama(model_name, prompt, rows, temperature=temperature, top_k=top_k)
    return _call_openrouter(model_name, prompt, rows, temperature=temperature)


def _clamp_float(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    if math.isnan(number) or math.isinf(number):
        number = default
    return max(minimum, min(maximum, number))


def _clamp_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))


def _call_cohere_rerank(
    prompt: str,
    candidates: list[dict[str, Any]],
    top_k: int,
    rerank_model: str | None = None,
) -> list[dict[str, Any]]:
    if not candidates:
        return []
    model = (rerank_model or os.getenv("COHERE_RERANK_MODEL") or DEFAULT_RERANK_MODEL).strip()
    documents = [str(item.get("content") or item.get("preview") or "")[:4000] for item in candidates]
    payload = {
        "model": model,
        "query": prompt,
        "documents": documents,
        "top_n": min(top_k, len(candidates)),
    }
    req = request.Request(
        "https://api.cohere.com/v2/rerank",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {_cohere_api_key()}",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=45) as response:
            body = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Cohere reranking 실패 · {exc.code} {detail}") from exc
    except TimeoutError as exc:
        raise RuntimeError("Cohere reranking 요청 시간이 초과되었습니다. Reranking을 끄고 다시 시도하세요.") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Cohere reranking 연결 실패 · {exc.reason}") from exc

    reranked: list[dict[str, Any]] = []
    for result in body.get("results") or []:
        index = result.get("index")
        if not isinstance(index, int) or index < 0 or index >= len(candidates):
            continue
        item = dict(candidates[index])
        score = result.get("relevance_score")
        if isinstance(score, (int, float)):
            item["rerank_score"] = float(score)
            raw = dict(item.get("raw") or {})
            raw["rerank_score"] = float(score)
            item["raw"] = raw
        reranked.append(item)
    return reranked or candidates[:top_k]


def _query_embedding(prompt: str, rows: list[dict[str, Any]]) -> tuple[list[float], str, str | None]:
    providers = {
        row.get("metadata", {}).get("embedding_provider")
        for row in rows
        if isinstance(row.get("metadata"), dict)
    }
    non_empty_providers = {str(provider) for provider in providers if provider}
    if non_empty_providers and all(provider.startswith("local-hash") for provider in non_empty_providers):
        return _local_hash_embedding(prompt), "local-hash-fallback", None
    return _embedding_for_text(prompt)


def _selected_chucking_tables(tables: list[str] | tuple[str, ...] | None = None) -> list[str]:
    if not tables:
        return list(CHUCKING_TABLES)
    selected = []
    for table in tables:
        if table not in CHUCKING_TABLES:
            raise ValueError("허용되지 않은 청킹 테이블입니다.")
        if table not in selected:
            selected.append(table)
    if not selected:
        raise ValueError("질문을 수행할 청킹 테이블이 없습니다.")
    return selected


def compare_tables(
    prompt: str,
    model: str = DEFAULT_CHAT_MODEL,
    tables: list[str] | tuple[str, ...] | None = None,
    temperature: float = 0.2,
    top_k: int = 5,
    reranking: bool = False,
    rerank_model: str | None = None,
    rag_mode: str = "naive",
) -> dict[str, Any]:
    prompt = (prompt or "").strip()
    if not prompt:
        raise ValueError("질문을 입력하세요.")
    temperature = _clamp_float(temperature, 0.2, 0.0, 1.5)
    top_k = _clamp_int(top_k, 5, 1, 10)
    if isinstance(reranking, str):
        reranking = reranking.strip().lower() in {"1", "true", "yes", "on"}
    else:
        reranking = bool(reranking)
    rag_mode = _normalize_rag_mode(rag_mode)
    advanced = rag_mode == "advanced"
    rerank_model_value = (rerank_model or os.getenv("COHERE_RERANK_MODEL") or DEFAULT_RERANK_MODEL).strip()
    selected_tables = _selected_chucking_tables(tables)
    panels = []
    for table in selected_tables:
        slot = CHUCKING_TABLES.index(table) + 1
        panel_started = time.perf_counter()
        try:
            rows = _request_rows(table)
            if not rows:
                panels.append({
                    "slot": slot,
                    "label": f"청킹 방식 {slot}",
                    "table": table,
                    "actual_table": _resolved_tables.get(table, table),
                    "model": model,
                    "temperature": temperature,
                    "top_k": top_k,
                    "rag_mode": rag_mode,
                    "rag_label": RAG_MODE_LABELS[rag_mode],
                    "reranking": reranking or advanced,
                    "rerank_model": rerank_model_value if (reranking or advanced) else None,
                    "status": "ok",
                    "summary": "임베딩된 청크가 없습니다.",
                    "meta": {"total_rows": 0, "top_count": 0, "top_score": 0, "avg_score": 0, "candidate_count": 0, "elapsed_ms": round((time.perf_counter() - panel_started) * 1000)},
                    "answer": "먼저 해당 방식의 임베딩 버튼을 눌러 Supabase에 청크를 저장하세요.",
                    "results": [],
                })
                continue

            query_variants = _advanced_query_variants(prompt) if advanced else [prompt]
            scored_by_id: dict[str, dict[str, Any]] = {}
            provider = ""
            warning = None
            for query_text in query_variants:
                query_vector, provider, warning = _query_embedding(query_text, rows)
                for row in rows:
                    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
                    content = str(row.get("content") or "")
                    score = _cosine_similarity(query_vector, _parse_vector(row.get("embedding")))
                    key = str(row.get("id") or hashlib.sha1(content.encode("utf-8")).hexdigest())
                    existing = scored_by_id.get(key)
                    if existing and existing["score"] >= score:
                        existing.setdefault("matched_queries", []).append(query_text)
                        continue
                    scored_by_id[key] = {
                        "score": score,
                        "title": f"Chunk {row.get('id', '?')}",
                        "content": content,
                        "preview": content[:360],
                        "metadata": metadata,
                        "matched_queries": [query_text],
                        "raw": {**row, "score": score},
                    }
            scored = list(scored_by_id.values())
            scored.sort(key=lambda item: item["score"], reverse=True)
            candidate_count = min(len(scored), max(top_k * (4 if advanced else 3), top_k))
            candidate_pool = scored[:candidate_count]
            rerank_used = reranking or advanced
            rerank_warning = None
            if rerank_used:
                try:
                    top = _call_cohere_rerank(prompt, candidate_pool, top_k, rerank_model_value)
                except RuntimeError as exc:
                    if not advanced:
                        raise
                    rerank_warning = str(exc)
                    top = scored[:top_k]
            else:
                top = scored[:top_k]
            strategy_label = next(
                (item["metadata"].get("strategy_label") for item in scored if item["metadata"].get("strategy_label")),
                f"청킹 방식 {slot}",
            )
            top_scores = [item["score"] for item in top]
            if advanced:
                summary = f"Advanced · 질의 {len(query_variants)}개 · 후보 {candidate_count}개 · 최종 {len(top)}개 비교"
                if rerank_warning:
                    summary += " · rerank fallback"
            elif reranking:
                summary = f"Naive · 총 {len(rows)}개 중 후보 {candidate_count}개 rerank · 최종 {len(top)}개 비교"
            else:
                summary = f"Naive · 총 {len(rows)}개 중 상위 {len(top)}개 비교"
            result_items = []
            for index, item in enumerate(top):
                result = {
                    "rank": index + 1,
                    "score": round(item["score"], 4),
                    "title": item["title"],
                    "preview": item["preview"],
                    "content": item["content"],
                    "metadata": item["metadata"],
                    "matched_queries": item.get("matched_queries", [])[:3],
                    "citation": f"검색 조각 {index + 1}",
                }
                if isinstance(item.get("rerank_score"), (int, float)):
                    result["rerank_score"] = round(float(item["rerank_score"]), 4)
                result_items.append(result)
            answer_rows = _rows_for_answer(prompt, top, rag_mode)
            answer_text = _call_selected_model(model, prompt, answer_rows, temperature=temperature, top_k=top_k)
            elapsed_ms = round((time.perf_counter() - panel_started) * 1000)
            cited_chunks = sorted({int(match) for match in re.findall(r"\[검색 조각 (\d+)\]", answer_text)})
            panels.append({
                "slot": slot,
                "label": strategy_label,
                "table": table,
                "actual_table": _resolved_tables.get(table, table),
                "model": model,
                "temperature": temperature,
                "top_k": top_k,
                "rag_mode": rag_mode,
                "rag_label": RAG_MODE_LABELS[rag_mode],
                "query_variants": query_variants,
                "advanced_steps": ["multi-query retrieval", "best-effort rerank", "context compression"] if advanced else ["single-query vector search"],
                "reranking": rerank_used,
                "rerank_model": rerank_model_value if rerank_used else None,
                "status": "ok",
                "summary": summary,
                "embedding_provider": provider,
                "warning": warning or rerank_warning,
                "meta": {
                    "total_rows": len(rows),
                    "top_count": len(top),
                    "top_score": round(max(top_scores), 4) if top_scores else 0,
                    "avg_score": round(sum(top_scores) / len(top_scores), 4) if top_scores else 0,
                    "candidate_count": candidate_count,
                    "reranking": rerank_used,
                    "query_count": len(query_variants),
                    "context_compression": advanced,
                    "elapsed_ms": elapsed_ms,
                    "answer_chars": len(answer_text),
                    "citation_count": len(cited_chunks),
                },
                "citations": [f"검색 조각 {number}" for number in cited_chunks],
                "answer": answer_text,
                "results": result_items,
            })
        except (RuntimeError, ValueError) as exc:
            panels.append({
                "slot": slot,
                "label": f"청킹 방식 {slot}",
                "table": table,
                "actual_table": _resolved_tables.get(table, table),
                "model": model,
                "temperature": temperature,
                "top_k": top_k,
                "rag_mode": rag_mode,
                "rag_label": RAG_MODE_LABELS[rag_mode],
                "reranking": reranking or advanced,
                "rerank_model": rerank_model_value if (reranking or advanced) else None,
                "status": "error",
                "summary": "검색 또는 답변 생성 실패",
                "answer": str(exc),
                "meta": {"elapsed_ms": round((time.perf_counter() - panel_started) * 1000)},
                "results": [],
            })
    return {
        "prompt": prompt,
        "model": model,
        "temperature": temperature,
        "top_k": top_k,
        "rag_mode": rag_mode,
        "rag_label": RAG_MODE_LABELS[rag_mode],
        "reranking": reranking or advanced,
        "rerank_model": rerank_model_value if (reranking or advanced) else None,
        "panels": panels,
    }


LEGACY_COMPARE_TABLES = (("일반 청킹", "documents"), ("전처리 청킹", "documents_test"))
TITLE_KEYS = ("title", "name", "source", "document_title", "filename", "file_name", "heading")
CONTENT_KEYS = ("content", "text", "chunk", "body", "document", "page_content", "summary", "description")


def _request_legacy_table(table: str, limit: int = 50) -> list[dict[str, Any]]:
    if table not in {name for _, name in LEGACY_COMPARE_TABLES}:
        raise ValueError("허용되지 않은 비교 테이블입니다.")
    query = parse.urlencode({"select": "*", "limit": str(limit)})
    return _raw_supabase_request("GET", table, query=query) or []


def _tokens(value: str) -> set[str]:
    return {token.lower() for token in TOKEN_RE.findall(value) if len(token) > 1}


def _pick_first(row: dict[str, Any], candidates: tuple[str, ...]) -> str:
    for key in candidates:
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _row_preview(row: dict[str, Any]) -> tuple[str, str]:
    title = _pick_first(row, TITLE_KEYS)
    content = _pick_first(row, CONTENT_KEYS)
    if not content:
        parts = []
        for value in row.values():
            if isinstance(value, str) and value.strip():
                parts.append(value.strip())
            elif isinstance(value, (int, float)):
                parts.append(str(value))
        content = " ".join(parts)
    if not title:
        title = row.get("id") and f"Row {row['id']}" or "문서 조각"
    return title, content[:1200]


def _score_legacy_row(prompt_tokens: set[str], row: dict[str, Any]) -> tuple[int, str, str]:
    title, preview = _row_preview(row)
    haystack = f"{title} {preview}"
    hay_tokens = _tokens(haystack)
    overlap = prompt_tokens & hay_tokens
    score = len(overlap)
    normalized = haystack.lower()
    for token in prompt_tokens:
        if token and token in normalized:
            score += 2
    return score, title, preview


def compare_legacy_tables(prompt: str, model: str = DEFAULT_CHAT_MODEL) -> dict[str, Any]:
    """04 청킹 실습용: 기존 documents/documents_test 비교를 유지한다."""
    prompt = (prompt or "").strip()
    if not prompt:
        raise ValueError("프롬프트를 입력하세요.")
    prompt_tokens = _tokens(prompt)
    panels = []
    for label, table in LEGACY_COMPARE_TABLES:
        panel_started = time.perf_counter()
        try:
            rows = _request_legacy_table(table, limit=50)
            scored = []
            for row in rows:
                score, title, preview = _score_legacy_row(prompt_tokens, row)
                scored.append({"score": score, "title": title, "preview": preview, "raw": row})
            scored.sort(key=lambda item: item["score"], reverse=True)
            top = scored[:5]
            context_rows = [
                {
                    "content": item["preview"],
                    "metadata": {"strategy_label": label, "source_table": table, "title": item["title"]},
                    "score": item["score"],
                }
                for item in top
            ]
            panels.append({
                "label": label,
                "table": table,
                "model": model,
                "status": "ok",
                "summary": f"총 {len(rows)}건 중 상위 {len(top)}건 비교",
                "meta": {
                    "total_rows": len(rows),
                    "top_count": len(top),
                    "top_score": top[0]["score"] if top else 0,
                    "avg_score": round(sum(item["score"] for item in top) / len(top), 1) if top else 0,
                },
                "answer": _call_selected_model(model, prompt, context_rows),
                "results": [
                    {
                        "rank": index + 1,
                        "score": item["score"],
                        "title": item["title"],
                        "preview": item["preview"][:500],
                    }
                    for index, item in enumerate(top)
                ],
            })
        except RuntimeError as exc:
            panels.append({
                "label": label,
                "table": table,
                "model": model,
                "status": "error",
                "summary": "테이블 조회 실패",
                "answer": str(exc),
                "meta": {"elapsed_ms": round((time.perf_counter() - panel_started) * 1000)},
                "results": [],
            })
    return {"prompt": prompt, "model": model, "panels": panels}


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _sort_section_name(name: str) -> tuple[int, str]:
    match = re.search(r"section(\d+)\.xml$", name)
    return (int(match.group(1)) if match else 9999, name)


def _paragraph_text(paragraph: ElementTree.Element) -> str:
    parts: list[str] = []

    def walk(element: ElementTree.Element) -> None:
        local = _local_name(element.tag)
        if local in {"t", "text"} and element.text:
            parts.append(element.text)
        elif local in {"lineBreak", "br"}:
            parts.append("\n")
        elif local == "tab":
            parts.append("\t")
        for child in list(element):
            walk(child)
            if child.tail:
                parts.append(child.tail)

    walk(paragraph)
    text = "".join(parts)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def extract_hwpx_text(file_bytes: bytes) -> dict[str, Any]:
    if len(file_bytes) > 30 * 1024 * 1024:
        raise ValueError("30MB 이하의 .hwpx 파일만 처리할 수 있습니다.")
    stream = io.BytesIO(file_bytes)
    if not zipfile.is_zipfile(stream):
        raise ValueError(".hwpx ZIP 구조를 읽을 수 없습니다.")
    paragraphs: list[str] = []
    with zipfile.ZipFile(stream) as archive:
        infos = archive.infolist()
        total_uncompressed = sum(info.file_size for info in infos)
        if total_uncompressed > 80 * 1024 * 1024:
            raise ValueError("압축 해제 크기가 너무 큽니다.")
        section_names = [
            info.filename
            for info in infos
            if re.match(r"^Contents/section\d+\.xml$", info.filename)
        ]
        if not section_names:
            section_names = [
                info.filename
                for info in infos
                if info.filename.startswith("Contents/") and "section" in info.filename and info.filename.endswith(".xml")
            ]
        if not section_names:
            raise ValueError("Contents/section*.xml 본문 파일을 찾지 못했습니다.")
        for name in sorted(section_names, key=_sort_section_name):
            raw_xml = archive.read(name)
            try:
                root = ElementTree.fromstring(raw_xml)
            except ElementTree.ParseError:
                continue
            for element in root.iter():
                if _local_name(element.tag) == "p":
                    paragraph = _paragraph_text(element)
                    if paragraph:
                        paragraphs.append(paragraph)
    text = _normalize_text("\n\n".join(paragraphs))
    if not text:
        raise ValueError(".hwpx 본문 텍스트를 추출하지 못했습니다.")
    return {
        "text": text,
        "char_count": len(text),
        "paragraph_count": len(paragraphs),
        "section_count": len(section_names),
    }


def extract_hwpx_payload(filename: str, data_base64: str) -> dict[str, Any]:
    filename = filename or "document.hwpx"
    if not filename.lower().endswith(".hwpx"):
        raise ValueError(".hwpx 파일만 이 추출 API에서 처리합니다.")
    raw = data_base64.split(",", 1)[-1].strip()
    if not raw:
        raise ValueError("파일 데이터가 비어 있습니다.")
    try:
        file_bytes = base64.b64decode(raw, validate=True)
    except ValueError as exc:
        raise ValueError("base64 파일 데이터를 해석할 수 없습니다.") from exc
    result = extract_hwpx_text(file_bytes)
    result["filename"] = filename
    return result
