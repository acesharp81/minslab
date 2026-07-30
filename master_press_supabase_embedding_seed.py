from __future__ import annotations

"""Queue bounded historical article embeddings for the Master Press Supabase mirror."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "PoC" / "04-master-press"))

from master_press.config import Settings
from master_press.storage import Store
from master_press.supabase_mirror import SupabaseMirror


def queue_batch(store: Store, mirror: SupabaseMirror, size: int = 100) -> dict:
    cursor = store.get_setting("supabase_article_embedding_seed_cursor", "")
    with store.connect() as connection:
        rows = connection.execute("""SELECT ae.article_analysis_id,ae.model,ae.vector,ae.updated_at,aa.article_id,aa.organization_id
            FROM article_embeddings ae JOIN article_analyses aa ON aa.id=ae.article_analysis_id
            WHERE ae.status='completed' AND ae.dimensions=768 AND ae.article_analysis_id>? ORDER BY ae.article_analysis_id LIMIT ?""", (cursor, max(1, min(200, size)))).fetchall()
    queued = 0
    for row in rows:
        item = dict(row)
        vector = json.loads(item["vector"])
        analysis = {"id": item["article_analysis_id"], "organization_id": item.get("organization_id"), "updated_at": item.get("updated_at")}
        article = {"id": item["article_id"]}
        queued += int(mirror.article_embedding(analysis, article, vector, item["model"]))
    if rows and queued != len(rows):
        return {"selected": len(rows), "queued": queued, "cursor": cursor, "complete": False}
    if rows:
        store.set_setting("supabase_article_embedding_seed_cursor", str(rows[-1]["article_analysis_id"]))
    else:
        store.set_setting("supabase_article_embedding_seed_complete", "1")
    return {"selected": len(rows), "queued": queued, "cursor": cursor, "complete": not rows}


def main() -> int:
    settings = Settings.from_env()
    settings.ensure_directories()
    store = Store(settings.database_path, initialize=False)
    result = queue_batch(store, SupabaseMirror(settings, store))
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
