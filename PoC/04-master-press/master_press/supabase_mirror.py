from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
import time

from .config import Settings


class SupabaseMirror:
    """Best-effort metadata mirror; operational work never depends on it."""

    HISTORY_CACHE_TTL_SECONDS = 45
    HISTORY_FAILURE_LIMIT = 3
    HISTORY_CIRCUIT_SECONDS = 300

    def __init__(self, settings: Settings, outbox_store=None):
        self.settings = settings
        self.outbox_store = outbox_store
        self.last_error = ""
        self.last_status = 0
        self.last_duration_ms = 0
        self._history_cache: dict[str, tuple[float, list[dict]]] = {}
        self._history_failures = 0
        self._history_disabled_until = 0.0
        self.last_history_source = "not_requested"

    @property
    def enabled(self) -> bool:
        return bool(self.settings.supabase_url and self.settings.supabase_service_role_key)

    @staticmethod
    def _http_error_text(error: urllib.error.HTTPError) -> str:
        """Preserve PostgREST's actionable error body without leaking headers."""
        raw = error.read().decode("utf-8", "replace")[:4000]
        try:
            detail = json.loads(raw)
        except (TypeError, ValueError):
            detail = {}
        if not isinstance(detail, dict):
            detail = {}
        record = {
            "http_status": int(error.code or 0),
            "code": str(detail.get("code") or "")[:80],
            "message": str(detail.get("message") or raw or error.reason or "")[:600],
            "details": str(detail.get("details") or "")[:600],
            "hint": str(detail.get("hint") or "")[:300],
        }
        return json.dumps(
            {key: value for key, value in record.items() if value not in (None, "")},
            ensure_ascii=False, separators=(",", ":"),
        )

    def find_article_by_canonical_url(self, canonical_url: str) -> dict | None:
        """Return the authoritative remote article identity for reconciliation."""
        if not self.enabled or not str(canonical_url or "").strip():
            return None
        query = urllib.parse.urlencode({
            "select": "id,canonical_url", "canonical_url": f"eq.{canonical_url}", "limit": 1,
        })
        request = urllib.request.Request(
            f"{self.settings.supabase_url}/rest/v1/master_press_articles?{query}",
            headers={
                "apikey": self.settings.supabase_service_role_key,
                "Authorization": f"Bearer {self.settings.supabase_service_role_key}",
                "Accept": "application/json",
            }, method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.settings.request_timeout_seconds) as response:
                rows = json.loads(response.read().decode("utf-8"))
            return dict(rows[0]) if isinstance(rows, list) and rows else None
        except Exception:
            return None

    def upsert(self, table: str, rows: list[dict], on_conflict: str = "id") -> bool:
        if not self.enabled or not rows:
            return False
        if self.outbox_store is not None:
            queued = self.outbox_store.queue_supabase_outbox(table, rows, on_conflict)
            self.last_error = "" if queued == len(rows) else "outbox_enqueue_incomplete"
            self.last_status = 0
            return queued == len(rows)
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
            self.last_status = 0
            return True
        except urllib.error.HTTPError as error:
            self.last_error = self._http_error_text(error)
            self.last_status = int(error.code or 0)
            return False
        except Exception as error:
            self.last_error = f"{type(error).__name__}: {error}"[:1000]
            self.last_status = int(getattr(error, "code", 0) or 0)
            return False

    def organization(self, organization: dict) -> bool:
        search_metadata = {
            key: organization.get(key)
            for key in ("abbreviations", "former_names", "people", "exclude_terms", "domains", "rss_urls")
        }
        collection_settings = {
            key: organization.get(key)
            for key in (
                "collection_mode", "collection_interval_minutes", "collection_times",
                "max_search_queries", "max_articles_per_run",
            )
        }
        return self.upsert("master_press_organizations", [{
            "id": organization["id"], "name": organization["name"],
            "search_metadata": search_metadata, "collection_settings": collection_settings,
            "is_active": bool(organization.get("is_active")),
            "next_collect_at": organization.get("next_collect_at"),
            "last_collected_at": organization.get("last_collected_at"),
            "archived_at": organization.get("archived_at"),
            "created_at": organization.get("created_at"), "updated_at": organization.get("updated_at"),
        }])


    def case(self, case: dict) -> bool:
        settings = {
            key: case.get(key)
            for key in (
                "include_terms", "required_terms", "exclude_terms", "synonym_terms", "urgent_terms",
                "include_publishers", "exclude_publishers", "rss_urls", "collection_mode",
                "collection_interval_minutes", "collection_times", "delivery_mode", "delivery_times",
                "send_relevant_immediately", "relevance_threshold", "hold_threshold", "keyword_weight", "semantic_weight",
                "llm_weight", "max_articles_per_message",
            )
        }
        return self.upsert("master_press_cases", [{
            "id": case["id"], "name": case["name"], "topic_description": case.get("topic_description", ""),
            "organization_id": case.get("organization_id"),
            "settings": settings, "version": case.get("version", 1), "is_active": bool(case.get("is_active")),
            "next_collect_at": case.get("next_collect_at"), "last_collected_at": case.get("last_collected_at"),
            "created_at": case.get("created_at"), "updated_at": case.get("updated_at"),
        }])

    def recent_score_history(self, limit: int = 20, case_id: str = "") -> list[dict] | None:
        """Read compact score history with a bounded remote-read safety layer.

        SQLite remains the fallback. Successful remote results are cached briefly;
        after repeated remote errors the circuit opens and callers fall back without
        waiting for more network timeouts.
        """
        if not self.enabled:
            self.last_history_source = "disabled"
            return None
        safe_limit = max(1, min(100, int(limit)))
        clean_case_id = str(case_id or "").strip()
        cache_key = f"{safe_limit}:{clean_case_id}"
        now = time.monotonic()
        cached = self._history_cache.get(cache_key)
        if cached and now - cached[0] < self.HISTORY_CACHE_TTL_SECONDS:
            self.last_history_source = "cache"
            self.last_duration_ms = 0
            self.last_error = ""
            return [dict(item) for item in cached[1]]
        if now < self._history_disabled_until:
            self.last_history_source = "circuit_open"
            self.last_duration_ms = 0
            self.last_error = "history_circuit_open"
            return None
        params = {
            "select": "id,article_id,case_id,final_score,summary,organization_tag,article_type,decision,created_at,article:master_press_articles(title,publisher,published_at,original_url)",
            "order": "created_at.desc",
            "limit": safe_limit,
        }
        if clean_case_id:
            params["case_id"] = f"eq.{clean_case_id}"
        request = urllib.request.Request(
            f"{self.settings.supabase_url}/rest/v1/master_press_scores?{urllib.parse.urlencode(params)}",
            headers={
                "apikey": self.settings.supabase_service_role_key,
                "Authorization": f"Bearer {self.settings.supabase_service_role_key}",
            },
        )
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=min(5, self.settings.request_timeout_seconds)) as response:
                rows = json.loads(response.read().decode("utf-8"))
            self.last_duration_ms = round((time.perf_counter() - started) * 1000, 1)
            self.last_error = ""
            self.last_history_source = "remote"
            self._history_failures = 0
            self._history_disabled_until = 0.0
            items = [dict(item) for item in rows if isinstance(item, dict)]
            self._history_cache[cache_key] = (now, items)
            return [dict(item) for item in items]
        except Exception as error:
            self.last_duration_ms = round((time.perf_counter() - started) * 1000, 1)
            self.last_error = str(error)
            self.last_history_source = "error"
            self._history_failures += 1
            if self._history_failures >= self.HISTORY_FAILURE_LIMIT:
                self._history_disabled_until = time.monotonic() + self.HISTORY_CIRCUIT_SECONDS
            return None

    def history_read_status(self) -> dict:
        now = time.monotonic()
        return {
            "source": self.last_history_source,
            "consecutive_failures": self._history_failures,
            "circuit_open": now < self._history_disabled_until,
            "cache_entries": len(self._history_cache),
        }

    def match_press_release_chunks(self, query_vector: list[float], organization_id: str = "", limit: int = 12) -> list[dict]:
        """Read-only pgvector lookup for the press-RAG candidate fast path.

        Failures deliberately return an empty list: local candidate generation
        remains the source of truth and continues without a remote dependency.
        """
        if not self.enabled or not query_vector:
            return []
        started = time.perf_counter()
        try:
            payload = {
                "query_embedding": "[" + ",".join(str(float(value)) for value in query_vector) + "]",
                "match_count": max(1, min(50, int(limit))),
                "target_organization": organization_id or None,
            }
            request = urllib.request.Request(
                f"{self.settings.supabase_url}/rest/v1/rpc/match_master_press_release_chunks",
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers={
                    "apikey": self.settings.supabase_service_role_key,
                    "Authorization": f"Bearer {self.settings.supabase_service_role_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=min(5, self.settings.request_timeout_seconds)) as response:
                rows = json.loads(response.read().decode("utf-8"))
            self.last_error = ""
            self.last_duration_ms = round((time.perf_counter() - started) * 1000, 1)
            return [dict(item) for item in rows if isinstance(item, dict)]
        except Exception as error:
            self.last_error = str(error)
            self.last_duration_ms = round((time.perf_counter() - started) * 1000, 1)
            return []

    def article(self, article: dict) -> bool:
        return self.upsert("master_press_articles", [{
            "id": article["id"], "canonical_url": article["canonical_url"], "original_url": article["original_url"],
            "title": article["title"], "publisher": article.get("publisher", ""), "published_at": article.get("published_at"),
            "snippet": article.get("snippet", ""), "source_type": article.get("source_type", "naver"),
            "first_seen_at": article.get("first_seen_at"), "updated_at": article.get("updated_at"),
        }])

    def article_embedding(self, analysis: dict, article: dict, vector: list[float], model: str) -> bool:
        if len(vector) != 768:
            return False
        # The embedding has a foreign key to the article in Supabase. Queue the
        # parent first so the outbox priority can satisfy that dependency.
        article_ok = self.article(article)
        embedding_ok = self.upsert("master_press_article_embeddings", [{
            "analysis_id": analysis["id"], "article_id": article["id"], "organization_id": analysis.get("organization_id"),
            "embedding_model": str(model)[:120], "dimensions": len(vector),
            "embedding": "[" + ",".join(str(float(value)) for value in vector) + ",]".replace(",]", "]"),
            "updated_at": analysis.get("updated_at"),
        }], "analysis_id")

        return bool(article_ok and embedding_ok)
    def article_score(self, article: dict, score: dict) -> bool:
        article_ok = self.article(article)
        score_ok = self.upsert("master_press_scores", [{
            "id": score["id"], "article_id": score["article_id"], "case_id": score["case_id"],
            "case_version": score["case_version"], "keyword_score": score["keyword_score"],
            "semantic_score": score["semantic_score"], "llm_score": score["llm_score"],
            "final_score": score["final_score"], "summary": score.get("summary", ""),
            "organization_tag": score.get("organization_tag", ""),
            "article_type": score.get("article_type", "기타"),
            "classification_tags": json.loads(score.get("classification_tags") or "[]"),
            "reasons": json.loads(score.get("reasons") or "[]"),
            "low_score_categories": json.loads(score.get("low_score_categories") or "[]"),
            "decision": score["decision"], "created_at": score["created_at"], "updated_at": score["updated_at"],
        }])
        return article_ok and score_ok


    def daily_metrics(self, rows: list[dict]) -> bool:
        """Queue compact daily score aggregates for the remote read model."""
        return self.upsert("master_press_daily_metrics", rows)

    def history_operations(self, rows: list[dict]) -> bool:
        return self.upsert("master_press_daily_operations", rows)

    def history_keywords(self, rows: list[dict]) -> bool:
        return self.upsert("master_press_daily_keyword_metrics", rows)

    def history_models(self, rows: list[dict]) -> bool:
        return self.upsert("master_press_daily_model_metrics", rows)

    def daily_metrics_history(self, limit: int = 500) -> list[dict] | None:
        """Read only the compact daily score read model for shadow comparison."""
        if not self.enabled:
            return None
        params = {
            "select": "id,metric_date,organization_id,case_id,score_count,article_count,sent_count,hold_count,low_count,average_score,top_publishers,top_topics,created_at,updated_at",
            "order": "metric_date.desc",
            "limit": max(1, min(1000, int(limit))),
        }
        request = urllib.request.Request(
            f"{self.settings.supabase_url}/rest/v1/master_press_daily_metrics?{urllib.parse.urlencode(params)}",
            headers={
                "apikey": self.settings.supabase_service_role_key,
                "Authorization": f"Bearer {self.settings.supabase_service_role_key}",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=min(5, self.settings.request_timeout_seconds)) as response:
                rows = json.loads(response.read().decode("utf-8"))
            self.last_error = ""
            return [dict(item) for item in rows if isinstance(item, dict)]
        except Exception as error:
            self.last_error = str(error)
            return None

    def press_release(self, release: dict, markdown: str) -> bool:
        return self.upsert("master_press_press_releases", [{
            "id": release["id"], "organization_id": release["organization_id"],
            "source": release.get("source", "mois"), "external_id": release.get("external_id", ""),
            "canonical_url": release["canonical_url"], "title": release["title"],
            "department": release.get("department", ""), "contact_name": release.get("contact_name", ""),
            "contact_phone": release.get("contact_phone", ""), "published_at": release.get("published_at"),
            "summary": release.get("summary", ""), "markdown": markdown,
            "content_hash": release.get("content_hash", ""),
            "document_fingerprint": release.get("document_fingerprint", ""),
            "embedding_model": release.get("embedding_model", ""),
            "created_at": release.get("created_at"), "updated_at": release.get("updated_at"),
        }])

    def press_release_chunks(self, chunks: list[dict]) -> bool:
        rows = [{
            "id": item["id"], "press_release_id": item["press_release_id"],
            "chunk_index": item["chunk_index"], "content": item["content"],
            "content_hash": item["content_hash"], "embedding_model": item["embedding_model"],
            "dimensions": item["dimensions"],
            "embedding": "[" + ",".join(str(float(value)) for value in item["vector"]) + "]",
            "created_at": item["created_at"], "updated_at": item["updated_at"],
        } for item in chunks]
        return self.upsert("master_press_press_release_chunks", rows)

    def press_release_match(self, match: dict) -> bool:
        return self.press_release_matches([match])

    def press_release_matches(self, matches: list[dict]) -> bool:
        rows = []
        if self.outbox_store is not None:
            for article_id in dict.fromkeys(str(match.get("article_id") or "") for match in matches):
                article = self.outbox_store.get_article(article_id) if article_id else None
                if article:
                    self.article(article)
        for match in matches:
            rows.append({
                "id": f'{match["article_id"]}:{match["press_release_id"]}',
                "article_id": match["article_id"], "press_release_id": match["press_release_id"],
                "semantic_score": match.get("semantic_score", 0), "lexical_score": match.get("lexical_score", 0),
                "similarity_score": match.get("similarity_score", 0), "matcher_version": match.get("matcher_version", ""),
                "matched_at": match.get("matched_at"),
            })
        return self.upsert("master_press_article_press_matches", rows)
