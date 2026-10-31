"""Authenticated configuration/run controls; read-only execution visibility."""
from typing import Literal
from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from .ai_collection_store import Store
from .ai_collection_fetch import canonical
from .ai_collection_models import availability
from .ai_collection_budget import status as shared_status


class Settings(BaseModel):
    model_config=ConfigDict(extra='forbid')
    enabled: bool=False
    profile: Literal['OPENAI','SOLAR']='OPENAI'
    hour_kst: int=Field(default=7,ge=0,le=23)
    max_documents: int=Field(default=20,ge=1,le=100)
    daily_usd: float=Field(default=2,gt=0,le=20,allow_inf_nan=False)
    monthly_usd: float=Field(default=30,gt=0,le=100,allow_inf_nan=False)
    solar_total_usd: float=Field(default=110,gt=0,le=110,allow_inf_nan=False)
    mini_tokens: int=Field(default=9_000_000,ge=1000,le=10_000_000)
    large_tokens: int=Field(default=900_000,ge=1000,le=1_000_000)
    search_enabled: bool=True
    queries: list[str]=Field(default_factory=list,max_length=5)
    seed_urls: list[str]=Field(default_factory=list,max_length=20)
    sample_every: int=Field(default=5,ge=1,le=20)
    version: int=Field(default=0,ge=0)


def install(app,service,authenticated,prefix):
    from .ai_agents_api import install as install_agents
    install_agents(app,service,authenticated,prefix)
    def store(): return Store(service.data_dir)
    @app.get(prefix+'/api/ai-collection')
    def status(): return dict(store().status(),providers=availability(),shared_budget=shared_status())

    @app.post(prefix+'/api/admin/ai-collection/settings')
    def settings(payload:Settings,request:Request):
        if not authenticated(request): raise HTTPException(401,'관리자 로그인이 필요합니다')
        config=payload.model_dump()
        if any(not q.strip() or len(q)>150 for q in config['queries']): raise HTTPException(422,'검색어는 1~150자입니다')
        try: config['seed_urls']=[canonical(u) for u in config['seed_urls']]
        except ValueError as error: raise HTTPException(422,str(error)) from None
        if config['enabled'] and not availability()[config['profile']]: raise HTTPException(422,'선택한 제공사의 API 키가 없습니다')
        try: return store().configure(config)
        except ValueError as error: raise HTTPException(409,str(error)) from None

    @app.post(prefix+'/api/admin/ai-collection/runs')
    def run(request:Request):
        if not authenticated(request): raise HTTPException(401,'관리자 로그인이 필요합니다')
        s=store()
        if not availability()[s.settings()['profile']]: raise HTTPException(422,'선택한 제공사의 API 키가 없습니다')
        if not s.status()['worker_online']: raise HTTPException(409,'AI 수집 worker가 오프라인입니다. 유지관리자에게 실행을 요청하세요')
        return s.enqueue()

    @app.post(prefix+'/api/admin/ai-collection/runs/{rid}/stop')
    def stop(rid:str,request:Request):
        if not authenticated(request): raise HTTPException(401,'관리자 로그인이 필요합니다')
        return store().stop(rid)
