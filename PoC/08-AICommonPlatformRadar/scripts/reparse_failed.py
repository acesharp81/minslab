from __future__ import annotations

import json

import _bootstrap  # noqa: F401

from app.db import SessionLocal, init_db
from app.services.collector import reparse_failed


if __name__ == "__main__":
    init_db()
    with SessionLocal() as db:
        print(json.dumps(reparse_failed(db), ensure_ascii=False, indent=2))

