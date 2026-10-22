"""Selection availability is separate from policy membership and review status."""
import math

def availability(program):
    values=program.get('profile') or {}
    targets=[value for key,value in values.items() if key=='target_units' or key.startswith(('annual:','region:'))]
    has_target=any(type(v) in (int,float) and math.isfinite(v) and v>0 for v in targets)
    has_projects=(program.get('active_project_count') or 0)>0
    units=program.get('linked_project_units')
    has_collected_units=type(units) in (int,float) and math.isfinite(units) and units>0
    visible=has_projects or has_collected_units
    return dict(selection_enabled=visible,has_target_quantity=has_target,has_collected_units=has_collected_units,
                inactive_reason='' if visible else '연결 사업·확보 호수 없음')
