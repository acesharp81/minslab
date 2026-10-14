"""Preview by default. --check rolls back; --apply appends audited manual targets."""
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.db import engine_for,factory
from backend.service import HomeService
from backend.officer_duration import prepare,apply
from backend.policy_delivery import build_delivery
from backend.api_samples import today
engine=engine_for()
if '--check' in sys.argv:
    with engine.connect() as connection:
        tx=connection.begin()
        try:
            s=HomeService(engine);s.sessions=factory(connection);plan=prepare(s);result=apply(s,plan)
            graph=build_delivery(s,today(),include_portfolio_comparisons=False)
            assert graph['status']=='READY'
            assert all(e['event_date']<=today().isoformat() for c in graph['portfolio_cohorts'] for e in c['events'] if e.get('origin')=='MANUAL')
            print(json.dumps(dict(result=result,graph='READY',rollback=True),ensure_ascii=False))
        finally:tx.rollback()
else:
    s=HomeService(engine);plan=prepare(s)
    out=Path('/app/data/runtime/officer-duration-preview.json') if Path('/app/data/runtime').exists() else Path('/tmp/officer-duration-preview.json')
    out.write_text(json.dumps(plan,ensure_ascii=False,indent=2));out.chmod(0o600)
    print(json.dumps(apply(s,plan) if '--apply' in sys.argv else dict(summary=plan['summary'],model={k:{a:b for a,b in v.items() if a!='samples'} for k,v in plan['model'].items()}),ensure_ascii=False))
