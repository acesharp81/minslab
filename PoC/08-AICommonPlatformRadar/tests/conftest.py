from __future__ import annotations

import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("G2B_MODE", "mock")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("STAGE2_PROVIDER", "mock")
os.environ.setdefault("STAGE3_PRIMARY_PROVIDER", "mock")
os.environ.setdefault("STAGE3_FALLBACK_PROVIDER", "mock")
os.environ.setdefault("AUTO_SEED_SAMPLE", "false")
os.environ.setdefault("SUPABASE2_URL", "")
os.environ.setdefault("SUPABASE2_SERVICE_ROLE_KEY", "")
