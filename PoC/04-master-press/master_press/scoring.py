from __future__ import annotations

import json
import math
import re
import urllib.error
import urllib.request
from dataclasses import dataclass

from .config import Settings


JSON_OBJECT_RE = re.compile(r"\{.*\}", re.S)


def clamp(value: float, low: float = 0, high: float = 100) -> float:
    return max(low, min(high, float(value)))


def normalized_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").casefold()).strip()


def keyword_relevance(case: dict, article: dict) -> dict:
    title = normalized_text(article.get("title", ""))
    snippet = normalized_text(article.get("snippet", ""))
    body = normalized_text(article.get("body", ""))
    weighted_texts = ((title, 3.0), (snippet, 1.5), (body, 1.0))
    included = [normalized_text(term) for term in case.get("include_terms", []) if normalized_text(term)]
    required = [normalized_text(term) for term in case.get("required_terms", []) if normalized_text(term)]
    excluded = [normalized_text(term) for term in case.get("exclude_terms", []) if normalized_text(term)]
    synonyms = case.get("synonym_terms") if isinstance(case.get("synonym_terms"), dict) else {}

    expanded: dict[str, list[str]] = {}
    for term in [*included, *required]:
        variants = [term]
        for value in synonyms.get(term, []):
            if normalized_text(value):
                variants.append(normalized_text(value))
        expanded[term] = list(dict.fromkeys(variants))

    matched_terms: list[str] = []
    title_matches: set[str] = set()
    coverage_points = 0.0
    maximum_points = 0.0
    for term in [*required, *included]:
        variants = expanded.get(term, [term])
        maximum_points += 3.0
        best = 0.0
        for field_text, weight in weighted_texts:
            if any(variant in field_text for variant in variants):
                best = max(best, weight)
        if best:
            matched_terms.append(term)
            coverage_points += best
            if any(variant in title for variant in variants):
                title_matches.add(term)

    if not required and not included:
        score = 50.0 if case.get("topic_description") else 0.0
    else:
        score = 100.0 * coverage_points / max(1.0, maximum_points)

    missing_required = [term for term in required if term not in matched_terms]
    excluded_hits = [term for term in excluded if any(term in text for text, _weight in weighted_texts)]
    categories = []
    reasons = []
    if missing_required:
        score = min(score, 35)
        categories.append("required_term_missing")
        reasons.append(f"필수 키워드 누락: {', '.join(missing_required[:5])}")
    if excluded_hits:
        score = max(0, score - 70)
        categories.append("excluded_term")
        reasons.append(f"제외 키워드 일치: {', '.join(excluded_hits[:5])}")
    if matched_terms and set(matched_terms) == title_matches and not any(term in body for term in matched_terms):
        score = min(score, 55)
        categories.append("title_only_match")
        reasons.append("키워드가 제목에만 집중되어 있습니다.")
    if not body:
        categories.append("body_unavailable")
        reasons.append("본문을 확인하지 못해 제목과 검색 요약문만 사용했습니다.")
    if matched_terms:
        reasons.append(f"일치 키워드: {', '.join(matched_terms[:8])}")
    return {
        "score": round(clamp(score), 1),
        "matched_terms": matched_terms,
        "categories": list(dict.fromkeys(categories)),
        "reasons": reasons,
        "urgent": any(normalized_text(term) in f"{title} {snippet} {body}" for term in case.get("urgent_terms", [])),
    }


class OllamaClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    def request(self, path: str, payload: dict) -> dict:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"{self.settings.ollama_base_url}{path}",
            data=data,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=max(30, self.settings.request_timeout_seconds * 6)) as response:
            return json.loads(response.read().decode("utf-8"))

    def embeddings(self, values: list[str]) -> list[list[float]]:
        try:
            response = self.request("/api/embed", {"model": self.settings.embedding_model, "input": values, "truncate": True})
            embeddings = response.get("embeddings") or []
            if len(embeddings) == len(values):
                return embeddings
        except Exception:
            pass
        results = []
        for value in values:
            response = self.request("/api/embeddings", {"model": self.settings.embedding_model, "prompt": value})
            results.append(response.get("embedding") or [])
        return results

    def classify_and_summarize(self, case: dict, article: dict) -> dict:
        content = (article.get("body") or article.get("snippet") or "")[:8000]
        prompt = f"""당신은 한국어 뉴스 모니터링 분류기입니다.
설정 주제와 기사의 실제 관련성을 0~100점으로 평가하고 2~3문장으로 요약하세요.
제목에 키워드가 있어도 본문 맥락이 다르면 낮은 점수를 주세요.
반드시 JSON 객체만 반환하세요.

설정명: {case.get('name', '')}
주제 설명: {case.get('topic_description', '')}
포함 키워드: {', '.join(case.get('include_terms', []))}
필수 키워드: {', '.join(case.get('required_terms', []))}
제외 키워드: {', '.join(case.get('exclude_terms', []))}

기사 제목: {article.get('title', '')}
언론사: {article.get('publisher', '')}
기사 내용:
{content}

JSON 형식:
{{"score": 0, "summary": "요약", "reasons": ["근거"], "low_score_categories": ["동음이의어|단순언급|주제불일치|본문부족 중 해당값"]}}"""
        response = self.request("/api/chat", {
            "model": self.settings.llm_model,
            "stream": False,
            "format": "json",
            "messages": [{"role": "user", "content": prompt}],
            "options": {"temperature": 0.1, "num_predict": 320, "num_ctx": 8192},
            "keep_alive": "5m",
        })
        raw = response.get("message", {}).get("content", "")
        match = JSON_OBJECT_RE.search(raw)
        data = json.loads(match.group(0) if match else raw)
        return {
            "score": clamp(float(data.get("score", 0))),
            "summary": str(data.get("summary", "")).strip()[:1200],
            "reasons": [str(item)[:300] for item in data.get("reasons", [])][:8],
            "categories": [str(item)[:80] for item in data.get("low_score_categories", [])][:8],
        }


def cosine_similarity(first: list[float], second: list[float]) -> float:
    if not first or not second or len(first) != len(second):
        return 0.0
    numerator = sum(a * b for a, b in zip(first, second))
    denominator = math.sqrt(sum(a * a for a in first)) * math.sqrt(sum(b * b for b in second))
    return numerator / denominator if denominator else 0.0


def semantic_relevance(client: OllamaClient, case: dict, article: dict) -> float:
    topic = " ".join([
        str(case.get("topic_description") or ""),
        " ".join(case.get("required_terms", [])),
        " ".join(case.get("include_terms", [])),
    ]).strip()
    article_text = " ".join([
        str(article.get("title") or ""),
        str(article.get("snippet") or ""),
        str(article.get("body") or "")[:5000],
    ]).strip()
    if not topic or not article_text:
        return 0.0
    first, second = client.embeddings([f"search_query: {topic}", f"search_document: {article_text}"])
    similarity = cosine_similarity(first, second)
    return round(clamp(similarity * 100), 1)


@dataclass
class RelevanceEngine:
    settings: Settings

    def __post_init__(self):
        self.ollama = OllamaClient(self.settings)

    def evaluate(self, case: dict, article: dict) -> dict:
        keyword = keyword_relevance(case, article)
        semantic_score = 0.0
        llm = {"score": 0.0, "summary": "", "reasons": [], "categories": []}
        semantic_error = ""
        llm_error = ""
        try:
            semantic_score = semantic_relevance(self.ollama, case, article)
        except Exception as error:
            semantic_error = type(error).__name__
        try:
            llm = self.ollama.classify_and_summarize(case, article)
        except Exception as error:
            llm_error = type(error).__name__

        components = [
            (keyword["score"], float(case.get("keyword_weight", 0.3)), True),
            (semantic_score, float(case.get("semantic_weight", 0.4)), not semantic_error),
            (llm["score"], float(case.get("llm_weight", 0.3)), not llm_error),
        ]
        available_weight = sum(weight for _score, weight, available in components if available)
        final_score = sum(score * weight for score, weight, available in components if available) / max(available_weight, 0.001)
        reasons = [*keyword["reasons"], *llm["reasons"]]
        categories = [*keyword["categories"], *llm["categories"]]
        if semantic_score < 45 and not semantic_error:
            categories.append("low_semantic_similarity")
            reasons.append("주제와 기사 본문의 의미 유사도가 낮습니다.")
        if semantic_error:
            reasons.append(f"임베딩 평가 생략: {semantic_error}")
        if llm_error:
            reasons.append(f"LLM 평가 생략: {llm_error}")

        threshold = float(case.get("relevance_threshold", 75))
        hold_threshold = float(case.get("hold_threshold", 55))
        decision = "send" if final_score >= threshold or keyword["urgent"] else ("hold" if final_score >= hold_threshold else "low")
        summary = llm["summary"] or str(article.get("snippet") or article.get("title") or "")[:500]
        return {
            "keyword_score": round(keyword["score"], 1),
            "semantic_score": round(semantic_score, 1),
            "llm_score": round(llm["score"], 1),
            "final_score": round(clamp(final_score), 1),
            "summary": summary,
            "reasons": list(dict.fromkeys(reasons)),
            "matched_terms": keyword["matched_terms"],
            "low_score_categories": list(dict.fromkeys(categories)),
            "decision": decision,
            "urgent": keyword["urgent"],
        }
