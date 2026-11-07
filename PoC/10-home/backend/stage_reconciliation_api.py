"""Stage review reads use stored records only; reconciliation runs explicitly/nightly."""
from fastapi import Request, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from . import stage_reconciliation as stages

class Decision(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision_no:int=Field(ge=1)
    project_revision_no:int=Field(ge=1)
    profile_revision_no:int=Field(ge=0)
    mapping_revision_no:int|None=None
    action:str
    actor:str=Field(min_length=1,max_length=100)
    reason:str=Field(min_length=5,max_length=2000)
    checked:bool=False
    replace_confirmed:bool=False


def install(app,service,authenticated,prefix):
    @app.get(prefix+'/api/stage-reviews')
    def listing():
        from .publication_evidence import safe_value
        rows=stages.list_items(service)
        return safe_value(dict(items=rows,stages=stages.STAGES,pending=sum(r['status'] in stages.LIVE for r in rows),
            note='자료 연결과 단계 실적 승인은 별개입니다. 동일 사업·단계 누적값을 대체하며 기존 물량에 더하지 않습니다.'))

    @app.get(prefix+'/api/stage-reviews/export.csv')
    def download():
        return Response(stages.export_csv(service),media_type='text/csv; charset=utf-8',headers={
            'Content-Disposition':'attachment; filename="home-stage-review-pending.csv"','Cache-Control':'no-store'})

    @app.get(prefix+'/api/admin/stage-reviews/{proposal_id}/evidence')
    def evidence(proposal_id:str,request:Request):
        if not authenticated(request):raise HTTPException(401,'관리자 로그인이 필요합니다')
        from .hold_evidence_integrity import package,load_registry,references
        row=next((r for r in stages.list_items(service,include_proof=True) if r['id']==proposal_id),None)
        if not row:raise HTTPException(404,'검토 대상을 찾을 수 없습니다')
        record=dict(subject=row['id'],result=row,body_text=row['evidence_package']['body'],
            evidence=[v for k,v in row['quotes'].items() if k in ('date_quote','units_quote')],
            url=row['url'],cross_review=row.get('cross_review',{}),source_revision_no=row['source_ref']['revision_no'])
        import json
        return Response(json.dumps(package(record,[record],load_registry(service,references(row))),ensure_ascii=False),
            media_type='application/json',headers={'Cache-Control':'no-store','Content-Disposition':'attachment; filename="'+proposal_id+'-evidence.json"'})

    @app.post(prefix+'/api/admin/stage-reviews/refresh')
    def refresh(request:Request):
        if not authenticated(request):raise HTTPException(401,'관리자 로그인이 필요합니다')
        return stages.refresh(service,auto_apply=False)

    @app.post(prefix+'/api/admin/stage-reviews/{proposal_id}')
    def approve(proposal_id:str,payload:Decision,request:Request):
        if not authenticated(request):raise HTTPException(401,'관리자 로그인이 필요합니다')
        try:result=stages.decide(service,proposal_id,**payload.model_dump())
        except ValueError as error:raise HTTPException(422,str(error)) from None
        if result.get('conflict'):raise HTTPException(409,'원문·사업·검토 판본이 변경됐거나 이미 처리됐습니다. 새로고침 후 확인하세요.')
        return result
