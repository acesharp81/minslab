from __future__ import annotations

import argparse
import json

from ..config import get_settings
from ..db.connection import connect
from ..db.watch_operations_repository import WatchOperationsRepository


def main() -> None:
    parser = argparse.ArgumentParser(description="실방송 자막·재연결·공식전환 회귀 점검")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--include-test", action="store_true")
    args = parser.parse_args()
    with connect(get_settings().database_url) as connection:
        items = WatchOperationsRepository(connection).audit_recent(
            limit=max(1, min(args.limit, 100)), include_test=args.include_test,
        )
    print(json.dumps({"items": items, "count": len(items)}, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
