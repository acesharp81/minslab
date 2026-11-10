"""Demo personas, not institutional authentication. Legacy cases keep their report names."""
ARCHIVED_DEMOS={'employee-ring-v1-2-completed','employee-ring-v1-4-completed'}
EMPLOYEES = {f"employee{i}":f"직원 {i}" for i in range(1,5)}
def employee_from(request):
    return request.headers.get("x-employee") or request.cookies.get("handover_employee")
def memberships(store, case_id):
    row=store.one("SELECT predecessor_id,successor_id FROM case_members WHERE case_id=?",(case_id,))
    return {**(row or {"predecessor_id":"employee1","successor_id":"employee2"}),"legacy_assignment":not bool(row),"archived":not bool(row) or case_id in ARCHIVED_DEMOS}
def member_role(store,case_id,employee):
    m=memberships(store,case_id)
    return "predecessor" if employee==m["predecessor_id"] else "successor" if employee==m["successor_id"] else None
