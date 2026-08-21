from __future__ import annotations

"""Flush bounded Supabase outbox batches with row isolation and FK ordering."""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
from master_press.config import Settings
from master_press.storage import Store
from master_press.supabase_mirror import SupabaseMirror


TABLE_PRIORITY = {
    "master_press_organizations": 10, "master_press_cases": 20,
    "master_press_articles": 30, "master_press_article_embeddings": 35,
    "master_press_scores": 40, "master_press_press_releases": 50,
    "master_press_press_release_chunks": 60, "master_press_article_press_matches": 70,
    "master_press_daily_metrics": 80, "master_press_daily_operations": 81,
    "master_press_daily_keyword_metrics": 82, "master_press_daily_model_metrics": 83,
}


class SupabaseOutboxFlusher:
    """Send good rows even when a neighboring row has a permanent conflict."""

    def __init__(self, store: Store, mirror: SupabaseMirror):
        self.store = store
        self.mirror = mirror
        self.stats = {"selected": 0, "completed": 0, "failed": 0,
                      "retryable_failed": 0, "blocked": 0, "isolated_requests": 0}

    @staticmethod
    def _payload(item: dict) -> dict:
        return json.loads(str(item["payload"]))

    def _prepare_row(self, table: str, payload: dict) -> dict:
        row = dict(payload)
        if table == "master_press_articles" and row.get("id"):
            row["id"] = self.store.supabase_remote_id("article", str(row["id"]))
            return row
        local_article_id = str(row.get("article_id") or "")
        if local_article_id:
            remote_article_id = self.store.supabase_remote_id("article", local_article_id)
            row["article_id"] = remote_article_id
            if table == "master_press_article_press_matches" and row.get("press_release_id"):
                row["id"] = f"{remote_article_id}:{row['press_release_id']}"
        return row

    def _dependency(self, table: str, payload: dict) -> str:
        article_id = str(payload.get("article_id") or "")
        if article_id and table != "master_press_articles":
            if self.store.supabase_remote_id("article", article_id) == article_id:
                event_id = f"master_press_articles:{article_id}"
                status = self.store.supabase_outbox_event_status(event_id)
                if status and status != "completed":
                    return event_id
        release_id = str(payload.get("press_release_id") or "")
        if release_id and table != "master_press_press_releases":
            event_id = f"master_press_press_releases:{release_id}"
            status = self.store.supabase_outbox_event_status(event_id)
            if status and status != "completed":
                return event_id
        return ""

    def _settle(self, item: dict, ok: bool, error: str = "", retryable: bool = True) -> None:
        settled = self.store.finish_supabase_outbox(
            str(item["id"]), ok, error, expected_payload=str(item["payload"]), retryable=retryable,
        )
        if not settled:
            return
        if ok:
            self.stats["completed"] += 1
            payload = self._payload(item)
            if item["table_name"] == "master_press_articles" and payload.get("id"):
                self.store.release_supabase_dependents("article", str(payload["id"]))
            elif item["table_name"] == "master_press_press_releases" and payload.get("id"):
                self.store.release_supabase_dependents("press_release", str(payload["id"]))
        else:
            self.stats["failed"] += 1
            self.stats["retryable_failed"] += int(retryable)

    def _reconcile_article(self, item: dict, payload: dict) -> bool:
        remote = self.mirror.find_article_by_canonical_url(str(payload.get("canonical_url") or ""))
        local_id = str(payload.get("id") or "")
        remote_id = str((remote or {}).get("id") or "")
        if not local_id or not remote_id or remote_id == local_id:
            return False
        mapped = dict(payload); mapped["id"] = remote_id
        if not self.mirror.upsert("master_press_articles", [mapped], "id"):
            return False
        self.store.save_supabase_identity_alias(
            "article", local_id, remote_id, str(payload.get("canonical_url") or ""),
        )
        self._settle(item, True)
        return True

    def _flush_items(self, table: str, conflict_key: str, items: list[dict]) -> None:
        if not items:
            return
        rows = [self._prepare_row(table, self._payload(item)) for item in items]
        if self.mirror.upsert(table, rows, conflict_key):
            for item in items:
                self._settle(item, True)
            return
        status = int(self.mirror.last_status or 0)
        error = str(self.mirror.last_error or f"supabase_http_{status}")
        if 400 <= status < 500 and len(items) > 1:
            self.stats["isolated_requests"] += 1
            midpoint = len(items) // 2
            self._flush_items(table, conflict_key, items[:midpoint])
            self._flush_items(table, conflict_key, items[midpoint:])
            return
        if table == "master_press_articles" and status == 409 and len(items) == 1:
            if self._reconcile_article(items[0], self._payload(items[0])):
                return
        retryable = not (400 <= status < 500)
        for item in items:
            self._settle(item, False, error, retryable=retryable)

    def run(self, limit: int = 100) -> dict:
        events = self.store.due_supabase_outbox(limit)
        self.stats["selected"] = len(events)
        grouped: dict[tuple[str, str], list[dict]] = {}
        for event in events:
            grouped.setdefault((event["table_name"], event["conflict_key"]), []).append(event)
        ordered = sorted(grouped.items(), key=lambda group: (TABLE_PRIORITY.get(group[0][0], 99), group[0]))
        for (table, conflict_key), items in ordered:
            ready = []
            for item in items:
                dependency = self._dependency(table, self._payload(item))
                if dependency:
                    if self.store.block_supabase_outbox(
                        str(item["id"]), dependency, expected_payload=str(item["payload"]),
                    ):
                        self.stats["blocked"] += 1
                    continue
                ready.append(item)
            self._flush_items(table, conflict_key, ready)
        return {**self.stats, "status": self.store.supabase_outbox_status()}


def main() -> int:
    settings = Settings.from_env(); settings.ensure_directories()
    store = Store(settings.database_path, initialize=False)
    result = SupabaseOutboxFlusher(store, SupabaseMirror(settings)).run(100)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if not int(result["retryable_failed"] or 0) else 1
    store.ensure_supabase_outbox_schema()


if __name__ == "__main__":
    raise SystemExit(main())
