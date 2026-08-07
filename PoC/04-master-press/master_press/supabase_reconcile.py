from __future__ import annotations

"""Read-only consistency checks for the Master Press Supabase replica."""

import json
import re
import urllib.request

from .storage import Store, now_iso


class SupabaseReconciler:
    TABLES = (
        ("organizations", "master_press_organizations", "SELECT COUNT(*) FROM organizations"),
        ("cases", "master_press_cases", "SELECT COUNT(*) FROM cases"),
        ("articles", "master_press_articles", "SELECT COUNT(*) FROM articles"),
        ("scores", "master_press_scores", "SELECT COUNT(*) FROM article_scores"),
        ("press_releases", "master_press_press_releases", "SELECT COUNT(*) FROM press_releases WHERE embedding_status='completed'"),
        ("press_release_chunks", "master_press_press_release_chunks", "SELECT COUNT(*) FROM press_release_chunks"),
        ("article_press_matches", "master_press_article_press_matches", "SELECT COUNT(*) FROM article_press_release_matches WHERE is_related=1"),
    )

    def __init__(self, settings, store: Store):
        self.settings = settings
        self.store = store

    @property
    def enabled(self) -> bool:
        return bool(self.settings.supabase_url and self.settings.supabase_service_role_key)

    def status(self) -> dict:
        raw = self.store.get_setting("supabase_reconcile_details", "{}")
        try:
            details = json.loads(raw)
        except (TypeError, ValueError):
            details = {}
        return {
            "enabled": self.enabled,
            "last_at": self.store.get_setting("supabase_reconcile_last_at", ""),
            "status": self.store.get_setting("supabase_reconcile_status", "not_run"),
            "details": details,
        }

    def _remote_count(self, table_name: str) -> int:
        request = urllib.request.Request(
            f"{self.settings.supabase_url}/rest/v1/{table_name}?select=id",
            headers={
                "apikey": self.settings.supabase_service_role_key,
                "Authorization": f"Bearer {self.settings.supabase_service_role_key}",
                "Range": "0-0",
                "Prefer": "count=exact",
            },
        )
        with urllib.request.urlopen(request, timeout=min(8, self.settings.request_timeout_seconds)) as response:
            content_range = response.headers.get("Content-Range", "")
        match = re.search(r"/(\d+)$", content_range)
        if not match:
            raise ValueError(f"count_missing:{table_name}")
        return int(match.group(1))

    def run(self) -> dict:
        if not self.enabled:
            result = {"status": "disabled", "details": {}}
        else:
            details, errors = {}, []
            with self.store.connect() as connection:
                for label, remote_table, local_query in self.TABLES:
                    local_count = int(connection.execute(local_query).fetchone()[0])
                    try:
                        remote_count = self._remote_count(remote_table)
                        # Operational rows expire locally after 7/8 days while
                        # the remote replica is retained longer. A remote
                        # superset is therefore expected; only a remote deficit
                        # indicates that mirroring has fallen behind.
                        ok = remote_count >= local_count
                        details[label] = {
                            "local": local_count, "remote": remote_count,
                            "remote_only": max(0, remote_count - local_count),
                            "mode": "remote_superset", "ok": ok,
                        }
                        if not ok:
                            errors.append(label)
                    except Exception as error:
                        details[label] = {"local": local_count, "remote": None, "ok": False, "error": type(error).__name__}
                        errors.append(label)
            result = {"status": "ready" if not errors else "mismatch", "details": details, "errors": errors}
        self.store.set_setting("supabase_reconcile_last_at", now_iso())
        self.store.set_setting("supabase_reconcile_status", result["status"])
        self.store.set_setting("supabase_reconcile_details", json.dumps(result.get("details", {}), ensure_ascii=False, separators=(",", ":")))
        return result
