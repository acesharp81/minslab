from __future__ import annotations

import asyncio
import json
import os

os.environ["G2B_MODE"] = "mock"
os.environ["LLM_PROVIDER"] = "mock"
os.environ["STAGE2_PROVIDER"] = "mock"
os.environ["STAGE3_PRIMARY_PROVIDER"] = "mock"
os.environ["STAGE3_FALLBACK_PROVIDER"] = "mock"
os.environ["SUPABASE2_URL"] = ""
os.environ["SUPABASE2_SERVICE_ROLE_KEY"] = ""
os.environ["SUPABASE_URL"] = ""
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = ""

import _bootstrap  # noqa: E402,F401

from app.db import SessionLocal, init_db  # noqa: E402
from app.services.collector import run_collection  # noqa: E402


if __name__ == "__main__":
    init_db()
    with SessionLocal() as db:
        print(json.dumps(asyncio.run(run_collection(db, analyze=True)), ensure_ascii=False, indent=2))
