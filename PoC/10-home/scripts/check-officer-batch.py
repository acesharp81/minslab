"""Exercise the full batch and graph projections inside a rolled-back transaction."""
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.db import engine_for,factory
from backend.service import HomeService
from backend.officer_completion import prepare,apply,STAGES
from backend.project_collection import collection_matrix
from backend.policy_delivery import build_delivery
from backend.api_samples import today
engine=engine_for()
with engine.connect() as connection:
    transaction=connection.begin()
    try:
        service=HomeService(engine);service.sessions=factory(connection)
        plan=prepare(service);result=apply(service,plan)
        assert result['applied']
        projects=service.projects(policy_id='POL_2025_0907')
        assert all(p['mapping']['status']=='CONFIRMED' for p in projects)
        profiles=service.rows('project_profile');schedules=service.rows('execution_schedule')
        print('CHECK_COUNTS',len(profiles),len(schedules),result,flush=True)
        assert len(profiles)==197 and len(schedules)==197*6
        assert all(all(s in p['progress'] or any(x['project_id']==p['project_id'] and x['stage']==s for x in schedules) for s in STAGES) for p in profiles)
        matrix=collection_matrix(service,policy_id='POL_2025_0907')
        graph=build_delivery(service,today(),include_portfolio_comparisons=False)
        assert graph['status']=='READY'
        manual_events=[e for c in graph['portfolio_cohorts'] for e in c['events'] if e.get('origin')=='MANUAL']
        assert manual_events and all(e['event_date']<=today().isoformat() for e in manual_events)
        assert apply(service,plan)=={'already_applied':True}
        print(json.dumps(dict(result=result,manual_events=len(manual_events),portfolio=len(graph['portfolio_cohorts']),matrix=matrix['total'],rollback=True),ensure_ascii=False))
    finally:transaction.rollback()
assert not HomeService(engine).rows('officer_completion')
