from __future__ import annotations

import json
import urllib.parse
import urllib.request

from .config import Settings


class SupabaseMirror:
    """Best-effort metadata mirror; operational work never depends on it."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.last_error = ""

    @property
    def enabled(self) -> bool:
        return bool(self.settings.supabase_url and self.settings.supabase_service_role_key)

    def upsert(self, table: str, rows: list[dict], on_conflict: str = "id") -> bool:
        if not self.enabled or not rows:
            return False
        query = urllib.parse.urlencode({"on_conflict": on_conflict})
        request = urllib.request.Request(
            f"{self.settings.supabase_url}/rest/v1/{table}?{query}",
            data=json.dumps(rows, ensure_ascii=False, default=str).encode("utf-8"),
            headers={
                "apikey": self.settings.supabase_service_role_key,
                "Authorization": f"Bearer {self.settings.supabase_service_role_key}",
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates,return=minimal",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.settings.request_timeout_seconds) as response:
                response.read()
            self.last_error = ""
            return True
        except Exception as error:
            self.last_error = str(error)
            return False

    def case(self, case: dict) -> bool:
        settings = {
            key: case.get(key)
            for key in (
                "include_terms", "required_terms", "exclude_terms", "synonym_terms", "urgent_terms",
                "include_publishers", "exclude_publishers", "rss_urls", "collection_mode",
                "collection_interval_minutes", "collection_times", "delivery_mode", "delivery_times",
                "relevance_threshold", "hold_threshold", "keyword_weight", "semantic_weight",
                "llm_weight", "max_articles_per_message",
            )
        }
        return self.upsert("master_press_cases", [{
            "id": case["id"], "name": case["name"], "topic_description": case.get("topic_description", ""),
            "settings": settings, "version": case.get("version", 1), "is_active": bool(case.get("is_active")),
            "next_collect_at": case.get("next_collect_at"), "last_collected_at": case.get("last_collected_at"),
            "created_at": case.get("created_at"), "updated_at": case.get("updated_at"),
        }])

    def article_score(self, article: dict, score: dict) -> bool:
        article_ok = self.upsert("master_press_articles", [{
            "id": article["id"], "canonical_url": article["canonical_url"], "original_url": article["original_url"],
            "title": article["title"], "publisher": article.get("publisher", ""), "published_at": article.get("published_at"),
            "snippet": article.get("snippet", ""), "source_type": article.get("source_type", "naver"),
            "first_seen_at": article.get("first_seen_at"), "updated_at": article.get("updated_at"),
        }])
        score_ok = self.upsert("master_press_scores", [{
            "id": score["id"], "article_id": score["article_id"], "case_id": score["case_id"],
            "case_version": score["case_version"], "keyword_score": score["keyword_score"],
            "semantic_score": score["semantic_score"], "llm_score": score["llm_score"],
            "final_score": score["final_score"], "summary": score.get("summary", ""),
            "reasons": json.loads(score.get("reasons") or "[]"),
            "low_score_categories": json.loads(score.get("low_score_categories") or "[]"),
            "decision": score["decision"], "created_at": score["created_at"], "updated_at": score["updated_at"],
        }])
        return article_ok and score_ok
