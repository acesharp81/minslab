"""Collect official living context with normal raw evidence, batch and revision history."""
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.service import HomeService
from backend.db import engine_for
from backend.sources import SOURCES
s=HomeService(engine_for())
result=s.collect_one(next(r for r in SOURCES if r['id']=='kosis_living'))
print(json.dumps(result,ensure_ascii=False))
