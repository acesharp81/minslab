from backend.ai_officer_decisions import Check

def officer_response(result,cid='offline'):
 def respond(*args,**kwargs):
  return (Check(accept=True,reason='독립 검증 자료와 동일 사업·범위·인용을 확인했습니다',issues=[]),cid+'-check') if kwargs.get('schema')==Check else (result,cid)
 return respond
