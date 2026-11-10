import asyncio,json,threading
import uvicorn
from fastapi import FastAPI,Request
from fastapi.responses import StreamingResponse
from app.main import create_app
fake=FastAPI()
@fake.post('/v1/chat/completions')
async def chat(request:Request):
 body=await request.json();data=json.loads(body['messages'][1]['content']);invalid='오류' in data['question'];ref=data['confirmed_facts'][0]['id']
 text='보조금 정산 승인부터 확인하세요. 기한이 지난 업무의 누락 영수증을 요청하고, 담당자와 승인 일정을 협의하는 것이 좋겠습니다. 이 문장은 실제 수신 중 표시 여부를 확인하는 합성 테스트입니다.'
 raw=json.dumps({'paragraphs':[{'text':text,'fact_ids':['F999999' if invalid else ref],'background_ids':[]}]},ensure_ascii=False)
 async def events():
  for pos in range(0,len(raw),8):
   yield 'data: '+json.dumps({'choices':[{'delta':{'content':raw[pos:pos+8]}}]},ensure_ascii=False)+'\n\n'
   await asyncio.sleep(.06)
  await asyncio.sleep(1.5)
  yield 'data: '+json.dumps({'choices':[{'delta':{},'finish_reason':'stop'}]})+'\n\n'
  yield 'data: '+json.dumps({'usage':{'prompt_tokens':10,'completion_tokens':10},'choices':[]})+'\n\n'
  yield 'data: [DONE]\n\n'
 return StreamingResponse(events(),media_type='text/event-stream')
threading.Thread(target=lambda:uvicorn.run(fake,host='127.0.0.1',port=18132,log_level='warning'),daemon=True).start()
app=create_app(data_dir='test-results/practice/workspace',model_config={'url':'http://127.0.0.1:18132/v1','key':'synthetic-only','model':'solar-pro4'})
uvicorn.run(app,host='127.0.0.1',port=18131,log_level='warning')
