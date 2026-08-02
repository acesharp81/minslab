from __future__ import annotations

import uuid
from typing import Any

from .storage import Store, kst_day_start_iso, now_iso


class ShadowCaseStore:
    """Low-priority GPT comparison jobs kept separate from delivery decisions."""

    def __init__(self, store: Store):
        self.store = store

    def queue(self, evaluation: dict[str, Any]) -> bool:
        now = now_iso()
        with self.store.connect() as connection:
            cursor = connection.execute(
                """INSERT OR IGNORE INTO shadow_case_evaluations(
                       id,case_evaluation_id,status,queued_at,primary_model,primary_decision,
                       primary_final_score,primary_llm_score
                   ) VALUES(?,?, 'pending',?,?,?,?,?)""",
                (
                    str(uuid.uuid4()), str(evaluation["id"]), now,
                    str(evaluation.get("model") or "")[:120],
                    str(evaluation.get("decision") or "")[:20],
                    float(evaluation.get("final_score") or 0),
                    float(evaluation.get("llm_score") or 0),
                ),
            )
        return bool(cursor.rowcount)

    def next_job(self) -> dict[str, Any] | None:
        now = now_iso()
        with self.store._lock, self.store.connect() as connection:
            row = connection.execute(
                """SELECT s.*,ce.article_id,ce.case_id,ce.article_analysis_id
                   FROM shadow_case_evaluations s
                   JOIN case_evaluations ce ON ce.id=s.case_evaluation_id
                   WHERE s.status='pending'
                   ORDER BY s.queued_at,s.rowid LIMIT 1"""
            ).fetchone()
            if not row:
                return None
            cursor = connection.execute(
                """UPDATE shadow_case_evaluations
                   SET status='processing',started_at=?,attempts=attempts+1,error=NULL
                   WHERE id=? AND status='pending'""",
                (now, row["id"]),
            )
            if not cursor.rowcount:
                return None
        return dict(row)

    def finish(self, job_id: str, result: dict[str, Any] | None = None, error: str = "", duration_ms: int = 0) -> None:
        now = now_iso()
        result = result or {}
        report = result.get("analysis_report") or {}
        usage = report.get("usage") or {}
        with self.store.connect() as connection:
            row = connection.execute(
                "SELECT primary_decision FROM shadow_case_evaluations WHERE id=?", (job_id,)
            ).fetchone()
            decision = str(result.get("decision") or "")
            match = None if error or not decision or not row else int(decision == str(row["primary_decision"] or ""))
            connection.execute(
                """UPDATE shadow_case_evaluations
                   SET status=?,completed_at=?,duration_ms=?,shadow_model=?,shadow_decision=?,
                       shadow_final_score=?,shadow_llm_score=?,decision_match=?,
                       input_tokens=?,output_tokens=?,error=?
                   WHERE id=?""",
                (
                    "failed" if error else "completed", now, max(0, int(duration_ms)),
                    str(report.get("model") or "")[:120], decision[:20],
                    float(result.get("final_score") or 0), float(result.get("llm_score") or 0),
                    match, max(0, int(usage.get("prompt_tokens") or 0)),
                    max(0, int(usage.get("completion_tokens") or 0)), str(error)[:1000] or None, job_id,
                ),
            )

    def status(self, daily_limit: int) -> dict[str, Any]:
        today = kst_day_start_iso()
        with self.store.connect() as connection:
            row = connection.execute(
                """SELECT
                     COUNT(*) requested,
                     SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) pending,
                     SUM(CASE WHEN status='processing' THEN 1 ELSE 0 END) processing,
                     SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) completed,
                     SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) failed,
                     SUM(CASE WHEN status='completed' AND decision_match=1 THEN 1 ELSE 0 END) matching,
                     SUM(CASE WHEN status='completed' AND decision_match=0 THEN 1 ELSE 0 END) different,
                     COALESCE(SUM(input_tokens),0) input_tokens,
                     COALESCE(SUM(output_tokens),0) output_tokens,
                     COALESCE(AVG(CASE WHEN status='completed' THEN duration_ms END),0) avg_duration_ms
                   FROM shadow_case_evaluations WHERE queued_at>=?""",
                (today,),
            ).fetchone()
            depth = connection.execute(
                "SELECT COUNT(*) value FROM shadow_case_evaluations WHERE status IN ('pending','processing')"
            ).fetchone()
        requested = int(row["requested"] or 0)
        completed = int(row["completed"] or 0)
        matching = int(row["matching"] or 0)
        return {
            "model": "gpt-5.4-mini",
            "daily_limit": max(1, int(daily_limit)),
            "requested": requested,
            "pending": int(row["pending"] or 0),
            "processing": int(row["processing"] or 0),
            "completed": completed,
            "failed": int(row["failed"] or 0),
            "matching": matching,
            "different": int(row["different"] or 0),
            "agreement_rate": round(matching * 100 / completed, 1) if completed else 0.0,
            "input_tokens": int(row["input_tokens"] or 0),
            "output_tokens": int(row["output_tokens"] or 0),
            "tokens": int(row["input_tokens"] or 0) + int(row["output_tokens"] or 0),
            "average_seconds": round(float(row["avg_duration_ms"] or 0) / 1000, 2),
            "queue_depth": int(depth["value"] or 0),
            "remaining": max(0, max(1, int(daily_limit)) - requested),
            "day_start": today,
        }
