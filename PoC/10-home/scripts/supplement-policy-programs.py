#!/usr/bin/env python3
"""Run inside the HOME container: default read-only preview; --apply persists reviewed evidence."""
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.service import HomeService
from backend.db import engine_for
from backend.program_catalog import apply
print(json.dumps(apply(HomeService(engine_for()),dry_run='--apply' not in sys.argv),ensure_ascii=False,indent=2))
