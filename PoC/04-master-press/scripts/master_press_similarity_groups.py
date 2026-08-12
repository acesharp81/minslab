from __future__ import annotations

"""Rebuild the Master Press persisted related-article map outside web workers."""

import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from master_press.config import Settings
from master_press.storage import Store, now_iso


def main() -> int:
    settings = Settings.from_env()
    settings.ensure_directories()
    store = Store(settings.database_path, initialize=False)
    try:
        if not store.similarity_groups_stale():
            result = {"status": "fresh", "articles": 0}
        else:
            started = time.perf_counter()
            articles = store.rebuild_article_similarity_groups()
            result = {"status": "rebuilt", "articles": articles, "duration_ms": round((time.perf_counter() - started) * 1000, 1)}
            store.set_setting("similarity_groups_last_status", "rebuilt")
            store.set_setting("similarity_groups_last_at", now_iso())
            store.set_setting("similarity_groups_last_articles", str(articles))
            store.set_setting("similarity_groups_last_duration_ms", str(result["duration_ms"]))
            store.set_setting("similarity_groups_last_error", "")
    except Exception as exc:
        store.set_setting("similarity_groups_last_status", "error")
        store.set_setting("similarity_groups_last_at", now_iso())
        store.set_setting("similarity_groups_last_error", f"{type(exc).__name__}: {exc}"[:500])
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
