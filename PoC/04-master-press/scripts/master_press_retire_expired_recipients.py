from __future__ import annotations

"""Dry-run by default; retire only recipients with Kakao's definitive refresh-token error."""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from master_press.config import Settings
from master_press.storage import Store


TERMINAL_REFRESH_ERROR = "expired_or_invalid_refresh_token"


def candidates(store: Store) -> list[dict]:
    with store.connect() as connection:
        rows = connection.execute(
            """SELECT r.id,
                      (SELECT COUNT(*) FROM case_recipients cr WHERE cr.recipient_id=r.id) case_links,
                      (SELECT COUNT(*) FROM deliveries d
                        WHERE d.recipient_id=r.id AND d.status IN ('pending','retry')) article_waiting,
                      (SELECT COUNT(*) FROM magazine_deliveries md
                        WHERE md.recipient_id=r.id AND md.status IN ('pending','retry')) magazine_waiting
                 FROM recipients r
                WHERE r.status='reauthorize' AND r.last_error=?
                ORDER BY r.updated_at,r.id""",
            (TERMINAL_REFRESH_ERROR,),
        ).fetchall()
    return [dict(row) for row in rows]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Apply retirement; without this flag only report counts.")
    args = parser.parse_args()
    settings = Settings.from_env()
    store = Store(settings.database_path, initialize=False)
    selected = candidates(store)
    summary = {
        "mode": "apply" if args.apply else "dry_run",
        "recipients": len(selected),
        "case_links": sum(int(item["case_links"] or 0) for item in selected),
        "article_waiting": sum(int(item["article_waiting"] or 0) for item in selected),
        "magazine_waiting": sum(int(item["magazine_waiting"] or 0) for item in selected),
        "retired": 0,
        "cancelled_article_deliveries": 0,
        "cancelled_magazine_deliveries": 0,
    }
    if args.apply:
        for item in selected:
            result = store.retire_recipient(
                str(item["id"]), "auth_expired", TERMINAL_REFRESH_ERROR,
            )
            summary["retired"] += int(bool(result.get("deleted") and not result.get("already_deleted")))
            summary["cancelled_article_deliveries"] += int(result.get("cancelled_article_deliveries") or 0)
            summary["cancelled_magazine_deliveries"] += int(result.get("cancelled_magazine_deliveries") or 0)
    print(json.dumps(summary, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
