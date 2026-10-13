"""Register the 16 reviewed 9.7/follow-up sites; default is a read-only preview."""
import argparse
import json
from pathlib import Path
from backend.db import engine_for
from backend.service import HomeService
from backend.policy_project_registry import register_reviewed_sites

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--data-dir', default='/app/data')
    args = parser.parse_args()
    service = HomeService(engine_for(),args.data_dir)
    result = register_reviewed_sites(service,args.apply)
    if args.apply:
        out=Path(args.data_dir)/'audits/POLICY_SCOPE_REGISTRATION_20261013.json'
        # Keep the first applied additions as the permanent registration receipt.
        if result['added'] or not out.exists():
            out.parent.mkdir(parents=True,exist_ok=True)
            out.write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False))
