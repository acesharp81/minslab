from fastapi import Request,HTTPException
from functools import lru_cache
from pydantic import BaseModel,ConfigDict,Field
from typing import Literal
from .ai_collection_store import Store
from . import algorithm_review as review
from .publication_evidence import safe_value

class Validation(BaseModel):
 model_config=ConfigDict(extra='forbid')
 result_id:str=Field(max_length=100)
 selector:str=Field(min_length=1,max_length=200)
 scope:Literal['URL','PATH']='URL'
 expected_quote:str=Field(min_length=10,max_length=500)

class Decision(BaseModel):
 model_config=ConfigDict(extra='forbid')
 result_id:str=Field(max_length=100)
 version:int=Field(ge=0)
 action:Literal['APPLY','IGNORE','RETRY','DISABLE']
 actor:str=Field(min_length=1,max_length=100)
 reason:str=Field(min_length=5,max_length=2000)
 validation_id:str=Field(default='',max_length=100)
 checked:bool=False


def install(app,service,authenticated,prefix):
 @lru_cache(maxsize=1)
 def store():return Store(service.data_dir)
 def auth(request):
  if not authenticated(request):raise HTTPException(401,'관리자 로그인이 필요합니다')
 def perform(fn):
  try:return safe_value(fn())
  except review.Conflict as error:raise HTTPException(409,str(error)) from None
  except ValueError as error:raise HTTPException(422,str(error)) from None
 @app.get(prefix+'/api/algorithm-review/{subject}')
 def detail(subject:str):return perform(lambda:review.detail(service,store(),subject))
 @app.post(prefix+'/api/admin/algorithm-review/{subject}/validate')
 def validate(subject:str,payload:Validation,request:Request):
  auth(request)
  return perform(lambda:review.validate(service,store(),subject,**payload.model_dump()))
 @app.post(prefix+'/api/admin/algorithm-review/{subject}/decision')
 def decide(subject:str,payload:Decision,request:Request):
  auth(request)
  return perform(lambda:review.decide(service,store(),subject,**payload.model_dump()))
