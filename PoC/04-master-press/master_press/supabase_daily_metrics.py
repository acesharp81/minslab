from __future__ import annotations

"""Build a compact, non-operational Supabase read model for score history."""

from collections import Counter
from datetime import datetime, timedelta

from .storage import KST, Store, now_iso


class SupabaseDailyMetrics:
    """Queue only daily score aggregates; never queue article bodies or LLM output."""

    LOOKBACK_DAYS = 35
    ENABLED_KEY = "supabase_daily_metrics_enabled"

    def __init__(self, store: Store, mirror):
        self.store = store
        self.mirror = mirror

    @staticmethod
    def _top(counter: Counter, limit: int = 10) -> list[dict]:
        return [
            {"label": label, "value": count}
            for label, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))[:limit]
        ]

    def rows(self, days: int | None = None, reference: datetime | None = None) -> list[dict]:
        lookback = max(1, min(365, int(days or self.LOOKBACK_DAYS)))
        current = (reference or datetime.now(KST)).astimezone(KST)
        cutoff = (current - timedelta(days=lookback - 1)).replace(hour=0, minute=0, second=0, microsecond=0).isoformat(timespec="seconds")
        with self.store.connect() as connection:
            source_rows = connection.execute(
                """SELECT substr(s.created_at,1,10) metric_date,c.organization_id,s.case_id,s.article_id,
                          s.decision,s.final_score,s.article_type,s.created_at,s.updated_at,a.publisher
                   FROM article_scores s
                   JOIN cases c ON c.id=s.case_id
                   JOIN articles a ON a.id=s.article_id
                   WHERE s.created_at>=?
                   ORDER BY s.created_at ASC""",
                (cutoff,),
            ).fetchall()
        grouped: dict[tuple[str, str, str], dict] = {}
        for row in source_rows:
            item = dict(row)
            metric_date = str(item.get("metric_date") or "")
            organization_id = str(item.get("organization_id") or "")
            case_id = str(item.get("case_id") or "")
            if not metric_date or not organization_id or not case_id:
                continue
            key = (metric_date, organization_id, case_id)
            metric = grouped.setdefault(key, {
                "article_ids": set(), "score_count": 0, "sent_count": 0, "hold_count": 0, "low_count": 0,
                "score_sum": 0.0, "publishers": Counter(), "topics": Counter(),
                "created_at": str(item.get("created_at") or ""), "updated_at": str(item.get("updated_at") or ""),
            })
            metric["article_ids"].add(str(item.get("article_id") or ""))
            metric["score_count"] += 1
            decision = str(item.get("decision") or "")
            if decision == "send":
                metric["sent_count"] += 1
            elif decision == "hold":
                metric["hold_count"] += 1
            elif decision == "low":
                metric["low_count"] += 1
            metric["score_sum"] += float(item.get("final_score") or 0)
            publisher = str(item.get("publisher") or "미확인").strip() or "미확인"
            topic = str(item.get("article_type") or "기타").strip() or "기타"
            metric["publishers"][publisher] += 1
            metric["topics"][topic] += 1
            created_at = str(item.get("created_at") or "")
            updated_at = str(item.get("updated_at") or "")
            if created_at and (not metric["created_at"] or created_at < metric["created_at"]):
                metric["created_at"] = created_at
            if updated_at and updated_at > metric["updated_at"]:
                metric["updated_at"] = updated_at
        result = []
        for (metric_date, organization_id, case_id), metric in sorted(grouped.items(), reverse=True):
            score_count = int(metric["score_count"])
            result.append({
                "id": f"score-history:{metric_date}:{organization_id}:{case_id}",
                "metric_date": metric_date,
                "organization_id": organization_id,
                "case_id": case_id,
                "score_count": score_count,
                "article_count": len(metric["article_ids"]),
                "sent_count": int(metric["sent_count"]),
                "hold_count": int(metric["hold_count"]),
                "low_count": int(metric["low_count"]),
                "average_score": round(float(metric["score_sum"]) / score_count, 2) if score_count else 0.0,
                "top_publishers": self._top(metric["publishers"]),
                "top_topics": self._top(metric["topics"]),
                "created_at": metric["created_at"] or now_iso(),
                "updated_at": metric["updated_at"] or now_iso(),
            })
        return result

    def status(self) -> dict:
        return {
            "enabled": self.store.get_setting(self.ENABLED_KEY, "0") == "1",
            "lookback_days": self.LOOKBACK_DAYS,
            "last_at": self.store.get_setting("supabase_daily_metrics_last_at", ""),
            "last_result": self.store.get_setting("supabase_daily_metrics_last_result", ""),
            "last_rows": int(self.store.get_setting("supabase_daily_metrics_last_rows", "0") or 0),
            "shadow_status": self.store.get_setting("supabase_daily_metrics_shadow_status", "not_run"),
            "shadow_last_at": self.store.get_setting("supabase_daily_metrics_shadow_last_at", ""),
            "shadow_mismatches": int(self.store.get_setting("supabase_daily_metrics_shadow_mismatches", "0") or 0),
        }

    @staticmethod
    def _comparison_value(row: dict) -> dict:
        return {
            "metric_date": str(row.get("metric_date") or ""),
            "organization_id": str(row.get("organization_id") or ""),
            "case_id": str(row.get("case_id") or ""),
            "score_count": int(row.get("score_count") or 0),
            "article_count": int(row.get("article_count") or 0),
            "sent_count": int(row.get("sent_count") or 0),
            "hold_count": int(row.get("hold_count") or 0),
            "low_count": int(row.get("low_count") or 0),
            "average_score": round(float(row.get("average_score") or 0), 2),
            "top_publishers": list(row.get("top_publishers") or []),
            "top_topics": list(row.get("top_topics") or []),
        }

    def shadow_compare(self, days: int | None = None, reference: datetime | None = None) -> dict:
        """Compare local summary rows with Supabase without changing either source."""
        if not getattr(self.mirror, "enabled", False):
            result = {"status": "disabled", "reason": "supabase_unavailable"}
        elif self.store.get_setting(self.ENABLED_KEY, "0") != "1":
            result = {"status": "disabled", "reason": "not_enabled"}
        else:
            local_rows = self.rows(days, reference)
            remote_rows = self.mirror.daily_metrics_history(max(500, len(local_rows) + 20))
            if remote_rows is None:
                result = {"status": "unavailable", "error": str(getattr(self.mirror, "last_error", ""))[:300]}
            else:
                local = {str(row["id"]): self._comparison_value(row) for row in local_rows}
                remote = {str(row.get("id") or ""): self._comparison_value(row) for row in remote_rows}
                missing_remote = sorted(set(local) - set(remote))
                mismatched = sorted(key for key in set(local) & set(remote) if local[key] != remote[key])
                result = {
                    "status": "ready" if not missing_remote and not mismatched else "mismatch",
                    "local_rows": len(local), "remote_rows": len(remote),
                    "missing_remote": missing_remote[:20], "mismatched": mismatched[:20],
                }
        self.store.set_setting("supabase_daily_metrics_shadow_status", str(result["status"]))
        self.store.set_setting("supabase_daily_metrics_shadow_last_at", now_iso())
        self.store.set_setting("supabase_daily_metrics_shadow_mismatches", str(len(result.get("missing_remote", [])) + len(result.get("mismatched", []))))
        return result

    def run_once(self, days: int | None = None, reference: datetime | None = None) -> dict:
        if not getattr(self.mirror, "enabled", False):
            return {"status": "disabled", "reason": "supabase_unavailable"}
        if self.store.get_setting(self.ENABLED_KEY, "0") != "1":
            return {"status": "disabled", "reason": "not_enabled"}
        rows = self.rows(days, reference)
        queued = bool(not rows or self.mirror.daily_metrics(rows))
        result = {"status": "queued" if queued else "queue_failed", "rows": len(rows)}
        if not queued:
            result["error"] = str(getattr(self.mirror, "last_error", ""))[:300]
        self.store.set_setting("supabase_daily_metrics_last_at", now_iso())
        self.store.set_setting("supabase_daily_metrics_last_result", result["status"])
        self.store.set_setting("supabase_daily_metrics_last_rows", str(len(rows)))
        return result
