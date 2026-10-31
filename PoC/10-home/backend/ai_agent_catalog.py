"""Fixed model/role allowlist; selection never supplies URLs, secrets or code."""
import os
NEMO='nvidia/nemotron-3.5-super-vl:free'
MODELS={
 'solar-pro4':dict(label='Solar Pro 4',provider='SOLAR',pool='solar-pro4',roles=['algorithm','collection','officer']),
 NEMO:dict(label='OpenRouter · Nemotron 3.5 Super VL',provider='OPENROUTER',pool='openrouter',roles=['collection']),
 'gpt-5.4-mini':dict(label='GPT-5.4 mini',provider='OPENAI',pool='gpt-5.4-mini',roles=['collection']),
 'gpt-5.4':dict(label='GPT-5.4',provider='OPENAI',pool='gpt-5.4',roles=['algorithm','collection','officer']),
 'gpt-6.1-terra':dict(label='GPT-6.1 Terra',provider='OPENAI',pool='openai-shared',roles=['algorithm','collection','officer']),
}
ROLES={'algorithm':'알고리즘 에이전트','collection':'수집 에이전트','officer':'업무담당자 에이전트'}

def configured(model):
 p=MODELS[model]['provider']
 if p=='SOLAR':return bool(os.getenv('UPSTAGE_SECRET_KEY'))
 if p=='OPENROUTER':return bool(os.getenv('USAGE_GATEWAY_URL') and os.getenv('USAGE_METER_TOKEN'))
 return bool(os.getenv('OPENAI_API_KEY') or os.getenv('OpenAI_API_KEY'))

def validate(role,model):
 if role not in ROLES or model not in MODELS or role not in MODELS[model]['roles']:
  raise ValueError('해당 역할에 허용되지 않은 모델입니다')
 if not configured(model):raise ValueError('선택한 모델의 연결 설정이 없습니다')
 return MODELS[model]

def catalog():return [dict(id=k,**v,configured=configured(k)) for k,v in MODELS.items()]
