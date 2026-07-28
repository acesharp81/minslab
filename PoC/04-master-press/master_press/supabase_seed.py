from __future__ import annotations

"""Bounded, ordered initial metadata migration to the Supabase outbox."""

from datetime import datetime
from math import ceil

from .storage import KST, Store, now_iso


class SupabaseSeed:
    """Queue historical metadata in small dependency-safe batches.

    This class never performs remote I/O: the supplied mirror uses the local
    outbox. Article bodies, analysis rows, LLM responses and recipients are
    intentionally not read here.
    """

    BATCH_SIZE = 50
    WINDOW_START_HOUR = 1
    WINDOW_END_HOUR = 4
    ARTICLE_STAGES = (0.05, 0.20, 0.50, 1.00)
    PHASES = (
        ("organizations", "master_press_organizations"),
        ("cases", "master_press_cases"),
        ("articles", "master_press_articles"),
        ("scores", "master_press_scores"),
    )

    def __init__(self, store: Store, mirror):
        self.store = store
        self.mirror = mirror

    @staticmethod
    def _int(value: str, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _article_total(self) -> int:
        with self.store.connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM articles").fetchone()[0])

    def _article_queued(self) -> int:
        saved = self.store.get_setting("supabase_seed_article_queued", "")
        if saved:
            return self._int(saved)
        cursor = self.store.get_setting("supabase_seed_cursor", "")
        if not cursor:
            return 0
        with self.store.connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM articles WHERE id<=?", (cursor,)).fetchone()[0])

    def _article_stage_index(self, queued: int, total: int) -> int:
        saved = self.store.get_setting("supabase_seed_article_stage", "")
        if saved:
            return max(0, min(len(self.ARTICLE_STAGES) - 1, self._int(saved)))
        return next((index for index, ratio in enumerate(self.ARTICLE_STAGES) if queued < ceil(total * ratio)), len(self.ARTICLE_STAGES) - 1)

    def _article_status(self) -> dict:
        total = self._article_total()
        queued = min(total, self._article_queued())
        index = self._article_stage_index(queued, total)
        target = min(total, ceil(total * self.ARTICLE_STAGES[index]))
        paused = self.store.get_setting("supabase_seed_paused", "0") == "1"
        return {
            "total_articles": total,
            "article_queued": queued,
            "article_percent": round((queued / total * 100) if total else 100, 1),
            "stage_index": index + 1,
            "stage_count": len(self.ARTICLE_STAGES),
            "stage_target": target,
            "stage_target_percent": int(self.ARTICLE_STAGES[index] * 100),
            "paused": paused,
            "checkpoint": paused and self.store.get_setting("supabase_seed_phase", "organizations") == "articles",
        }

    def status(self) -> dict:
        phase = self.store.get_setting("supabase_seed_phase", "organizations")
        return {
            "enabled": bool(getattr(self.mirror, "enabled", False)),
            "phase": phase,
            "completed": phase == "complete",
            "batch_size": self.BATCH_SIZE,
            "start_hour": self.WINDOW_START_HOUR,
            "end_hour": self.WINDOW_END_HOUR,
            "queued_total": self._int(self.store.get_setting("supabase_seed_queued_total", "0")),
            "last_at": self.store.get_setting("supabase_seed_last_at", ""),
            "last_result": self.store.get_setting("supabase_seed_last_result", ""),
            **self._article_status(),
        }

    def _save_result(self, result: dict) -> dict:
        self.store.set_setting("supabase_seed_last_at", now_iso())
        self.store.set_setting("supabase_seed_last_result", str(result.get("status", ""))[:120])
        return result

    def pause(self) -> dict:
        self.store.set_setting("supabase_seed_paused", "1")
        return self.status()

    def continue_next_stage(self) -> dict:
        phase = self.store.get_setting("supabase_seed_phase", "organizations")
        if phase == "articles":
            article = self._article_status()
            if article["article_queued"] >= article["stage_target"]:
                if article["stage_index"] < article["stage_count"]:
                    self.store.set_setting("supabase_seed_article_stage", str(article["stage_index"]))
                else:
                    self.store.set_setting("supabase_seed_phase", "articles_wait")
                    self.store.set_setting("supabase_seed_cursor", "")
            self.store.set_setting("supabase_seed_paused", "0")
        else:
            self.store.set_setting("supabase_seed_paused", "0")
        return self.status()

    def _pending_for(self, table_name: str) -> int:
        return self.store.supabase_outbox_pending_for_tables([table_name])

    def _phase_index(self, name: str) -> int:
        return next((index for index, (phase, _table) in enumerate(self.PHASES) if phase == name), -1)

    def _advance_waiting_phase(self, phase: str) -> dict | None:
        base = phase.removesuffix("_wait")
        index = self._phase_index(base)
        if index < 0:
            self.store.set_setting("supabase_seed_phase", "organizations")
            self.store.set_setting("supabase_seed_cursor", "")
            return None
        table = self.PHASES[index][1]
        pending = self._pending_for(table)
        if pending:
            return self._save_result({"status": "waiting_remote", "phase": base, "pending": pending})
        next_phase = self.PHASES[index + 1][0] if index + 1 < len(self.PHASES) else "complete"
        self.store.set_setting("supabase_seed_phase", next_phase)
        self.store.set_setting("supabase_seed_cursor", "")
        return self._save_result({"status": "phase_advanced", "phase": next_phase})

    def _rows(self, phase: str, cursor: str, limit: int) -> list[dict]:
        table = {"organizations": "organizations", "cases": "cases", "articles": "articles", "scores": "article_scores"}[phase]
        with self.store.connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM {table} WHERE id>? ORDER BY id LIMIT ?", (cursor, max(1, min(self.BATCH_SIZE, limit)))
            ).fetchall()
        return [dict(row) for row in rows]

    def _queue_row(self, phase: str, row: dict) -> bool:
        if phase == "organizations":
            return self.mirror.organization(row)
        if phase == "cases":
            return self.mirror.case(row)
        if phase == "articles":
            return self.mirror.article(row)
        article = self.store.get_article(str(row.get("article_id") or ""))
        return bool(article) and self.mirror.article_score(article, row)

    def run_once(self, now: datetime | None = None) -> dict:
        current = now or datetime.now(KST)
        if not getattr(self.mirror, "enabled", False):
            return {"status": "disabled"}
        if not self.WINDOW_START_HOUR <= current.hour < self.WINDOW_END_HOUR:
            return {"status": "outside_window", "hour": current.hour}
        if self.store.get_setting("supabase_seed_paused", "0") == "1":
            return self._save_result({"status": "paused", "phase": self.store.get_setting("supabase_seed_phase", "organizations")})

        phase = self.store.get_setting("supabase_seed_phase", "organizations")
        if phase == "complete":
            return self._save_result({"status": "complete"})
        if phase.endswith("_wait"):
            return self._advance_waiting_phase(phase) or self.run_once(current)

        if self._phase_index(phase) < 0:
            self.store.set_setting("supabase_seed_phase", "organizations")
            self.store.set_setting("supabase_seed_cursor", "")
            phase = "organizations"
        cursor = self.store.get_setting("supabase_seed_cursor", "")
        limit = self.BATCH_SIZE
        article = None
        if phase == "articles":
            article = self._article_status()
            remaining = article["stage_target"] - article["article_queued"]
            if remaining <= 0:
                self.store.set_setting("supabase_seed_paused", "1")
                return self._save_result({"status": "checkpoint", "phase": "articles", **article})
            limit = min(limit, remaining)
        rows = self._rows(phase, cursor, limit)
        if not rows:
            self.store.set_setting("supabase_seed_phase", f"{phase}_wait")
            return self._advance_waiting_phase(f"{phase}_wait") or self._save_result({"status": "waiting_remote", "phase": phase})

        queued = 0
        for row in rows:
            if not self._queue_row(phase, row):
                return self._save_result({"status": "queue_failed", "phase": phase, "queued": queued, "error": str(getattr(self.mirror, "last_error", ""))[:300]})
            queued += 1
        self.store.set_setting("supabase_seed_cursor", str(rows[-1]["id"]))
        total = self._int(self.store.get_setting("supabase_seed_queued_total", "0")) + queued
        self.store.set_setting("supabase_seed_queued_total", str(total))
        if phase == "articles":
            current_count = article["article_queued"] + queued if article else self._article_queued() + queued
            self.store.set_setting("supabase_seed_article_queued", str(current_count))
            if current_count >= article["stage_target"]:
                self.store.set_setting("supabase_seed_paused", "1")
                return self._save_result({"status": "checkpoint", "phase": phase, "queued": queued, "queued_total": total, **self._article_status()})
        return self._save_result({"status": "queued", "phase": phase, "queued": queued, "queued_total": total})
