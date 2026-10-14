"""Dry run by default; --apply commits a version-pinned audited batch exactly once."""
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.db import engine_for
from backend.service import HomeService
from backend.officer_completion import prepare,apply
s=HomeService(engine_for());plan=prepare(s)
out=Path('/app/data/runtime/officer-completion-preview.json') if Path('/app/data/runtime').exists() else Path('/tmp/officer-completion-preview.json')
out.write_text(json.dumps(plan,ensure_ascii=False,indent=2));out.chmod(0o600)
print(json.dumps(apply(s,plan) if '--apply' in sys.argv else plan['summary'],ensure_ascii=False))
