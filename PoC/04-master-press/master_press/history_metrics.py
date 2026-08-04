from __future__ import annotations

"""Compact long-term operational and keyword history for Master Press.

The rows built here deliberately exclude article bodies, embeddings, prompts and
LLM responses. They can outlive the short operational retention window and
remain suitable for trend charts in Supabase.
"""

from collections import Counter, defaultdict
from datetime import datetime, timedelta
import json
import re

from .storage import KST, Store, json_value, now_iso


TOKEN_RE = re.compile(r"[가-힣A-Za-z0-9]{2,40}")
EXCLUDED_TERMS = {
    "기사", "보도", "자료", "관련", "대한", "통해", "위해", "이번", "정부", "기관",
    "정책", "발표", "지원", "추진", "확대", "강화", "현장", "오늘", "최근", "내용",
    "위한", "함께", "지난", "있다", "따르면", "밝혔다", "조사", "결과", "실시", "찾아", "만나",
}


class SupabaseHistoryMetrics:
    """Build bounded, idempotent history rows before operational data expires."""

    KEYWORD_LIMIT = 200
    EXTRACTOR_VERSION = "daily-keyword-v1"

    def __init__(self, store: Store, mirror):
        self.store = store
        self.mirror = mirror

    @staticmethod
    def _date(value: str) -> str:
        return str(value or "")[:10]

    @staticmethod
    def _organization(value: object) -> str:
        return str(value or "").strip()

    @classmethod
    def _terms(cls, *values: object, excluded: set[str] | None = None) -> set[str]:
        terms: set[str] = set()
        dynamic_excluded = {str(value).strip().casefold() for value in (excluded or set()) if str(value).strip()}
        for value in values:
            items = json_value(value, []) if isinstance(value, str) and value.lstrip().startswith(("[", "{")) else value
            if not isinstance(items, list):
                items = [items]
            for item in items:
                for token in TOKEN_RE.findall(str(item or "")):
                    normalized = re.sub(r"\s+", " ", token).strip().casefold()
                    if normalized and normalized not in EXCLUDED_TERMS and normalized not in dynamic_excluded and not re.fullmatch(r"\d{1,4}(년|월|일)", normalized):
                        terms.add(normalized)
        return terms

    def operation_rows(self, days: int = 14, reference: datetime | None = None, dataset: str = "production") -> list[dict]:
        current = (reference or datetime.now(KST)).astimezone(KST)
        cutoff = (current - timedelta(days=max(1, int(days)) - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
        cutoff_iso = cutoff.isoformat(timespec="seconds")
        metrics: dict[tuple[str, str], Counter] = defaultdict(Counter)
        with self.store.connect() as connection:
            article_rows = connection.execute(
                """SELECT substr(a.first_seen_at,1,10) day,COALESCE(aa.organization_id,'') organization_id,
                          COUNT(DISTINCT a.id) article_count,
                          COUNT(DISTINCT CASE WHEN aa.status='completed' THEN a.id END) analyzed_count,
                          COUNT(DISTINCT CASE WHEN aa.status='failed' THEN a.id END) analysis_failed_count
                   FROM articles a LEFT JOIN article_processing_flags apf ON apf.article_id=a.id
                   LEFT JOIN article_analyses aa ON aa.id=apf.analysis_id
                   WHERE a.first_seen_at>=? GROUP BY day,organization_id""", (cutoff_iso,)
            ).fetchall()
            press_rows = connection.execute(
                """SELECT substr(COALESCE(published_at,created_at),1,10) day,COALESCE(organization_id,'') organization_id,
                          COUNT(*) press_release_count
                   FROM press_releases WHERE COALESCE(published_at,created_at)>=? GROUP BY day,organization_id""", (cutoff_iso,)
            ).fetchall()
            match_rows = connection.execute(
                """SELECT substr(m.matched_at,1,10) day,COALESCE(aa.organization_id,'') organization_id,
                          COUNT(*) related_match_count
                   FROM article_press_release_matches m
                   JOIN article_processing_flags apf ON apf.article_id=m.article_id
                   JOIN article_analyses aa ON aa.id=apf.analysis_id
                   WHERE m.is_related=1 AND m.matched_at>=? GROUP BY day,organization_id""", (cutoff_iso,)
            ).fetchall()
            score_rows = connection.execute(
                """SELECT substr(e.created_at,1,10) day,COALESCE(c.organization_id,'') organization_id,
                          COUNT(*) score_count,
                          SUM(CASE WHEN e.decision='send' THEN 1 ELSE 0 END) sent_count,
                          SUM(CASE WHEN e.decision='hold' THEN 1 ELSE 0 END) hold_count,
                          SUM(CASE WHEN e.decision='low' THEN 1 ELSE 0 END) low_count
                   FROM case_evaluations e JOIN cases c ON c.id=e.case_id
                   WHERE e.created_at>=? GROUP BY day,organization_id""", (cutoff_iso,)
            ).fetchall()
            run_rows = connection.execute(
                """SELECT substr(started_at,1,10) day,COALESCE(organization_id,'') organization_id,
                          COUNT(*) collection_run_count,
                          SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) collection_failed_count
                   FROM collection_runs WHERE started_at>=? GROUP BY day,organization_id""", (cutoff_iso,)
            ).fetchall()
        for rows in (article_rows, press_rows, match_rows, score_rows, run_rows):
            for row in rows:
                item = dict(row)
                key = (self._date(item.pop("day")), self._organization(item.pop("organization_id")))
                metrics[key].update({name: int(value or 0) for name, value in item.items()})
        now = now_iso()
        fields = (
            "article_count", "analyzed_count", "analysis_failed_count", "press_release_count", "related_match_count",
            "score_count", "sent_count", "hold_count", "low_count", "collection_run_count", "collection_failed_count",
        )
        return [
            {"id": f"history:{dataset}:operations:{day}:{organization_id or 'all'}", "dataset": dataset,
             "metric_date": day, "organization_id": organization_id or None,
             **{name: int(values.get(name, 0)) for name in fields}, "created_at": now, "updated_at": now}
            for (day, organization_id), values in sorted(metrics.items(), reverse=True) if day
        ]

    def keyword_rows(self, days: int = 14, reference: datetime | None = None, dataset: str = "production") -> list[dict]:
        current = (reference or datetime.now(KST)).astimezone(KST)
        cutoff = (current - timedelta(days=max(1, int(days)) - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
        cutoff_iso = cutoff.isoformat(timespec="seconds")
        documents: dict[tuple[str, str, str], set[str]] = defaultdict(set)
        terms: dict[tuple[str, str, str], Counter] = defaultdict(Counter)
        with self.store.connect() as connection:
            article_rows = connection.execute(
                """SELECT a.id,substr(COALESCE(a.published_at,a.first_seen_at),1,10) day,COALESCE(aa.organization_id,'') organization_id,
                          COALESCE(o.name,'') organization_name,a.title,a.snippet,aa.entities,aa.topic_concepts
                   FROM articles a JOIN article_processing_flags apf ON apf.article_id=a.id
                   JOIN article_analyses aa ON aa.id=apf.analysis_id AND aa.status='completed'
                   LEFT JOIN organizations o ON o.id=aa.organization_id
                   WHERE COALESCE(a.published_at,a.first_seen_at)>=?""", (cutoff_iso,)
            ).fetchall()
            press_rows = connection.execute(
                """SELECT pr.id,substr(COALESCE(pr.published_at,pr.created_at),1,10) day,COALESCE(pr.organization_id,'') organization_id,
                          COALESCE(o.name,'') organization_name,pr.title,pr.summary
                   FROM press_releases pr LEFT JOIN organizations o ON o.id=pr.organization_id
                   WHERE COALESCE(pr.published_at,pr.created_at)>=?""", (cutoff_iso,)
            ).fetchall()
        for row in article_rows:
            item = dict(row); bucket = (self._date(item["day"]), self._organization(item["organization_id"]), "article")
            if not bucket[0]:
                continue
            documents[bucket].add(str(item["id"]))
            # Common analysis already supplies entities and topic concepts; using
            # every title token would make grammatical filler dominate the trend.
            for term in self._terms(item["entities"], item["topic_concepts"], excluded=self._terms(item["organization_name"])):
                terms[bucket][term] += 1
        for row in press_rows:
            item = dict(row); bucket = (self._date(item["day"]), self._organization(item["organization_id"]), "press_release")
            if not bucket[0]:
                continue
            documents[bucket].add(str(item["id"]))
            for term in self._terms(item["title"], item["summary"], excluded=self._terms(item["organization_name"])):
                terms[bucket][term] += 1
        now = now_iso(); result: list[dict] = []
        for (day, organization_id, source_kind), counts in sorted(terms.items(), reverse=True):
            total = len(documents[(day, organization_id, source_kind)])
            for rank, (keyword, count) in enumerate(sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:self.KEYWORD_LIMIT], start=1):
                result.append({
                    "id": f"history:{dataset}:keyword:{day}:{organization_id or 'all'}:{source_kind}:{keyword}",
                    "dataset": dataset, "metric_date": day, "organization_id": organization_id or None,
                    "source_kind": source_kind, "keyword": keyword, "document_count": int(count), "document_total": total,
                    "coverage_pct": round(count / max(1, total) * 100, 2), "rank": rank,
                    "extractor_version": self.EXTRACTOR_VERSION, "created_at": now, "updated_at": now,
                })
        return result

    def model_rows(self, days: int = 14, reference: datetime | None = None, dataset: str = "production") -> list[dict]:
        current = (reference or datetime.now(KST)).astimezone(KST)
        cutoff = (current - timedelta(days=max(1, int(days)) - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
        with self.store.connect() as connection:
            rows = connection.execute(
                """SELECT substr(created_at,1,10) day,provider,stage,model,COUNT(*) request_count,
                          SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) completed_count,
                          SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) failed_count,
                          SUM(input_tokens) input_tokens,SUM(output_tokens) output_tokens,SUM(usage_units) usage_units,
                          ROUND(AVG(duration_ms),1) average_duration_ms
                   FROM llm_api_calls WHERE created_at>=? GROUP BY day,provider,stage,model""", (cutoff.isoformat(timespec="seconds"),)
            ).fetchall()
        now = now_iso(); result = []
        for row in rows:
            item = dict(row); day = self._date(item.pop("day"))
            provider, stage, model = (str(item.pop(name) or "") for name in ("provider", "stage", "model"))
            if day:
                result.append({"id": f"history:{dataset}:model:{day}:{provider}:{stage}:{model}", "dataset": dataset,
                               "metric_date": day, "provider": provider, "stage": stage, "model": model,
                               **{name: int(item.get(name) or 0) for name in ("request_count", "completed_count", "failed_count", "input_tokens", "output_tokens", "usage_units")},
                               "average_duration_ms": float(item.get("average_duration_ms") or 0), "created_at": now, "updated_at": now})
        return result

    def payload(self, days: int = 14, reference: datetime | None = None, dataset: str = "production") -> dict[str, list[dict]]:
        return {"operations": self.operation_rows(days, reference, dataset), "keywords": self.keyword_rows(days, reference, dataset), "models": self.model_rows(days, reference, dataset)}

    def trial(self, days: int = 14, reference: datetime | None = None, queue: bool = False) -> dict:
        payload = self.payload(days, reference, dataset="trial")
        counts = {name: len(rows) for name, rows in payload.items()}
        if not queue:
            return {"status": "preview", "days": days, "counts": counts, "payload": payload}
        if not getattr(self.mirror, "enabled", False):
            return {"status": "disabled", "days": days, "counts": counts}
        outcomes = {
            "operations": self.mirror.history_operations(payload["operations"]),
            "keywords": self.mirror.history_keywords(payload["keywords"]),
            "models": self.mirror.history_models(payload["models"]),
        }
        return {"status": "queued" if all(outcomes.values()) else "queue_failed", "days": days, "counts": counts, "outcomes": outcomes}

    def run(self, days: int = 2, reference: datetime | None = None) -> dict:
        """Queue production aggregates; callers run this only in the quiet window."""
        payload = self.payload(days, reference, dataset="production")
        counts = {name: len(rows) for name, rows in payload.items()}
        if not getattr(self.mirror, "enabled", False):
            return {"status": "disabled", "days": days, "counts": counts}
        outcomes = {
            "operations": self.mirror.history_operations(payload["operations"]),
            "keywords": self.mirror.history_keywords(payload["keywords"]),
            "models": self.mirror.history_models(payload["models"]),
        }
        status = "queued" if all(outcomes.values()) else "queue_failed"
        if status == "queued":
            snapshot = {
                "ids": {name: [str(row["id"]) for row in rows] for name, rows in payload.items()},
                "updated_at": {name: str(rows[0].get("updated_at") or "") if rows else "" for name, rows in payload.items()},
            }
            self.store.set_setting("supabase_history_last_snapshot_at", now_iso())
            self.store.set_setting("supabase_history_last_snapshot_days", str(days))
            self.store.set_setting("supabase_history_last_snapshot", json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")))
        return {"status": status, "days": days, "counts": counts, "outcomes": outcomes}
