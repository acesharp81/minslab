"""Three bounded workers; metadata polling does not rebuild the business inbox."""
import os,time,threading
from datetime import datetime,timedelta,timezone
import httpx
from fastapi import HTTPException,Request,Response
from functools import lru_cache
from pydantic import BaseModel,ConfigDict,Field
from .ai_collection_store import Store
from .ai_agent_catalog import ROLES,catalog
from .ai_agents_store import settings,configure,enqueue,economics
from .ai_agents_inbox import items,export_csv

_lock=threading.Lock()
_budget=(0,{})

def budget():
 global _budget
 with _lock:
  if time.monotonic()-_budget[0]<60:return _budget[1]
  try:
   with httpx.Client(timeout=3,trust_env=False) as client:
    response=client.get(os.environ['USAGE_GATEWAY_URL'].rstrip('/')+'/internal/status',headers={'x-minslab-meter-token':os.environ['USAGE_METER_TOKEN']})
    response.raise_for_status();value=response.json()
   result=dict(value['shared_budget']);result['models']=list(result.get('models',[]))
   tomorrow=(datetime.now(timezone.utc)+timedelta(days=1)).replace(hour=0,minute=0,second=0,microsecond=0)
   result['models'].append(dict(id='openrouter',label='Nemotron · OpenRouter 공용',unit='requests',
      limit=value['operational_limit'],official_limit=value['official_limit'],remaining=value['remaining'],
      used=value['operational_limit']-value['remaining'],reserved=0,unknown=0,expires_at=tomorrow.isoformat()))
  except (KeyError,ValueError,httpx.HTTPError):result=dict(models=[],error='공통 사용량 연결 확인 필요 · 한도를 임의 추정하지 않습니다')
  _budget=(time.monotonic(),result)
  return result

class AgentSettings(BaseModel):
 model_config=ConfigDict(extra='forbid')
 model:str=Field(max_length=100)
 review_model:str=Field(default='',max_length=100)
 enabled:bool=False
 hour_kst:int=Field(ge=1,le=4)
 version:int=Field(ge=0)


def install(app,service,authenticated,prefix):
 @lru_cache(maxsize=1)
 def store():return Store(service.data_dir)
 def check(role):
  if role not in ROLES:raise HTTPException(404,'지원하지 않는 에이전트')
 def auth(request):
  if not authenticated(request):raise HTTPException(401,'관리자 로그인이 필요합니다')
 @app.get(prefix+'/api/ai-agents')
 def status():
  s=store()
  return dict(s.status(include_events=False),agents=settings(s),roles=ROLES,models=catalog(),shared_budget=budget(),economics=economics(s),
   solar_unlimited=os.environ.get('SHARED_SOLAR_UNLIMITED','false').lower()=='true')
 @app.get(prefix+'/api/ai-agents/history')
 def history():return dict(runs=store().status()['runs'])
 @app.get(prefix+'/api/ai-agents/holds.csv')
 def csv_export(role:str='all'):
  if role not in ('all','collection','officer'):raise HTTPException(422,'지원하지 않는 CSV 범위')
  return Response(export_csv(service,store(),role),media_type='text/csv; charset=utf-8',headers={
   'Content-Disposition':f'attachment; filename="home-ai-{role}-holds.csv"','Cache-Control':'no-store'})
 @app.get(prefix+'/api/ai-agents/{role}/items')
 def inbox(role:str):
  check(role);data=items(service,store(),role)
  return dict(items=data,done=sum(r['state']=='DONE' for r in data),held=sum(r['state']=='HOLD' for r in data))
 @app.post(prefix+'/api/admin/ai-agents/{role}/settings')
 def save_settings(role:str,payload:AgentSettings,request:Request):
  auth(request);check(role)
  try:return configure(store(),role,payload.model_dump())
  except ValueError as error:raise HTTPException(422,str(error)) from None
 @app.post(prefix+'/api/admin/ai-agents/{role}/runs')
 def start(role:str,request:Request):
  auth(request);check(role);s=store()
  if not s.status(include_events=False)['worker_online']:raise HTTPException(409,'작업자 연결 확인 필요')
  try:result=enqueue(s,role)
  except ValueError as error:raise HTTPException(422,str(error)) from None
  if result.get('already_running'):raise HTTPException(409,'다른 작업을 포함해 이미 실행 중입니다. 완료 후 실행하세요')
  return result
