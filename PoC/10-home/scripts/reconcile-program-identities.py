"""Run a review preview by default; --apply saves reversible aliases and audits."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.db import engine_for
from backend.service import HomeService
from backend.program_identity import apply
p=argparse.ArgumentParser();p.add_argument('--apply',action='store_true');args=p.parse_args()
print(json.dumps(apply(HomeService(engine_for()),not args.apply),ensure_ascii=False,indent=2))
