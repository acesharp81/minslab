"""Selection availability is separate from policy membership and review status."""
import math

def availability(program):
    values=program.get('profile') or {}
    targets=[value for key,value in values.items() if key=='target_units' or key.startswith(('annual:','region:'))]
    has_target=any(type(v) in (int,float) and math.isfinite(v) and v>=0 for v in targets)
    has_projects=(program.get('active_project_count') or 0)>0
    return dict(selection_enabled=has_target or has_projects,has_target_quantity=has_target,
                inactive_reason='' if has_target or has_projects else '목표수량·연결 사업 없음')
