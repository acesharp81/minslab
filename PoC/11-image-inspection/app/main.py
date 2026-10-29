import hashlib
import hmac
import io
import json
import secrets
import shutil
import time
import uuid
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field, ConfigDict
from .config import Settings, ROOT
from .storage import Store, now
from .engine import Engine
from . import rule_editor, checklist_report
from .rules import PACK, STEPS, rollup, redact
from .imaging import normalize, crop, cell_rect, labeled

PREFIX='/poc/image-inspection'

class RunInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    mode: str='live'
    vision_model: str='gpt-5.4'
    analysis_model: str='gpt-5.4-mini'
    text_sensitivity: str=Field(default='strict',pattern='^(standard|strict)$')
    rule_ids: list[str]=Field(default_factory=list,max_length=156)
    crop_id: str | None=None
    consent: bool=False
    force: bool=False
    reuse_observation_run_id: str | None=None
class RuleEditInput(BaseModel):
    markdown: str=Field(min_length=1,max_length=150000)
    base_version: str=Field(max_length=100)

class ReviewInput(BaseModel):
    finding_id: str
    status: str
    reason: str=Field(min_length=5,max_length=2000)
class CropInput(BaseModel):
    cell_ids: list[str]=Field(min_length=1,max_length=24)
class LoginInput(BaseModel):
    role: str
    password: str=Field(max_length=300)
class ReferenceInput(BaseModel):
    name: str=Field(min_length=2,max_length=150)
    kind: str
    issuer: str=Field(min_length=1,max_length=150)
    official_url: str=Field(max_length=1000)
    content: str=Field(min_length=5,max_length=12000)
    parent_ids: list[str]=Field(min_length=1,max_length=25)
    version: str=Field(min_length=1,max_length=80)
    effective_from: str=''
    effective_to: str=''


def create_app(settings=None):
    s=settings or Settings();store=Store(s.data/'inspection.sqlite3');engine=Engine(s,store)
    @asynccontextmanager
    async def lifespan(app):
        yield
        import asyncio
        await asyncio.to_thread(engine.pool.shutdown, wait=True)
    app=FastAPI(title='췤미! · PoC11 이미지 품질검수',docs_url=None,redoc_url=None,openapi_url=None,lifespan=lifespan)
    app.state.settings=s;app.state.store=store;app.state.engine=engine
    login_attempts={}

    @app.middleware('http')
    async def boundary(request,call_next):
        path=request.url.path
        if path.startswith(PREFIX):
            request.scope['path']=path[len(PREFIX):] or '/'
            request.scope['root_path']=PREFIX
        if request.method not in ('GET','HEAD','OPTIONS'):
            origin=request.headers.get('origin')
            if origin:
                from urllib.parse import urlsplit
                if urlsplit(origin).netloc!=request.headers.get('host'):return JSONResponse({'detail':'같은 사이트에서 요청하십시오.'},403)
            limit=(s.integer('MAX_UPLOAD_MB',20)+1)*1024*1024
            body=bytearray()
            async for part in request.stream():
                body.extend(part)
                if len(body)>limit:return JSONResponse({'detail':'업로드 용량 한도 초과'},413)
            request._body=bytes(body)
        response=await call_next(request)
        response.headers.update({'X-Content-Type-Options':'nosniff','Referrer-Policy':'same-origin','X-Frame-Options':'SAMEORIGIN',
          'Cache-Control':'no-store','Content-Security-Policy':"default-src 'self'; img-src 'self' blob: data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'self'; base-uri 'self'; form-action 'self'"})
        return response

    def actor(request,admin=False):
        sig=request.headers.get('x-inspection-admin','')
        secret=s.get('SESSION_SECRET')
        if secret and ':' in sig:
            stamp,digest=sig.split(':',1)
            signed_path=PREFIX+request.scope['path']
            expected=hmac.new(secret.encode(),f'{stamp}:{request.method}:{signed_path}'.encode(),hashlib.sha256).hexdigest()
            try:valid=abs(time.time()-int(stamp))<60 and hmac.compare_digest(expected,digest)
            except ValueError:valid=False
            if valid:return 'admin'
        token=request.cookies.get('poc11_session','')
        with store.connect() as c:row=c.execute('SELECT role FROM sessions WHERE id=? AND expires>?',(hashlib.sha256(token.encode()).hexdigest(),time.time())).fetchone()
        if not row:raise HTTPException(401,'검토자 또는 관리자 로그인이 필요합니다.')
        if admin and row['role']!='admin':raise HTTPException(403,'관리자 권한이 필요합니다.')
        return row['role']
    def getjob(jid):
        job=store.get(jid)
        if not job:raise HTTPException(404,'검사 자료를 찾을 수 없습니다.')
        return job
    def public_job(job):
        out={**job}
        if job['runs']:
            run=job['runs'][-1];out['parents']=rollup(run['results'],run['reviews'],run['rule_pack']);out['checklist_report']=checklist_report.build(run)
        else:out['parents']=rollup([])
        return out

    @app.get('/')
    def index():return FileResponse(ROOT/'web/index.html')
    @app.get('/assets/{name}')
    def assets(name):
        if name not in ('app.js','style.css'):raise HTTPException(404)
        return FileResponse(ROOT/'web'/name)
    @app.get('/health')
    def health():return {'status':'ok','service':'poc11','parents':len(PACK['parents']),'steps':len(STEPS)}
    @app.get('/api/config')
    def config(request:Request):
        try:role=actor(request)
        except HTTPException:role=None
        return {'role':role,'vision_models':['gpt-5.4','gpt-5.4-mini','gpt-6.1-sol','gpt-6-astra','nvidia/nemotron-3.5-super-vl:free'],'analysis_models':['solar-pro4','gpt-5.4','gpt-5.4-mini','gpt-6.1-sol','gpt-6-astra'],
          'openrouter_configured':bool(s.get('OPENROUTER_API_KEY')),'openai_configured':bool(s.get('OPENAI_API_KEY')),'upstage_configured':bool(s.get('UPSTAGE_API_KEY')),
          'external_enabled':s.flag('EXTERNAL_API_ENABLED',True),'rule_pack_version':rule_editor.current(store)['version'],'retention_days':s.integer('RETENTION_DAYS',30)}
    @app.get('/api/rules')
    def rules():return rule_editor.current(store)['pack']
    @app.get('/api/admin/rules')
    def edit_rules(request:Request):
        actor(request,True)
        return {**rule_editor.current(store),'history':rule_editor.history(store),'authoring_guide':(ROOT/'docs/rule-authoring-guide.md').read_text()}
    @app.get('/api/admin/rules/versions/{seq}')
    def rule_version(seq:int,request:Request):
        actor(request,True)
        with store.connect() as c:row=c.execute('SELECT version,markdown FROM rule_versions WHERE seq=?',(seq,)).fetchone()
        if not row:raise HTTPException(404,'규칙 버전을 찾을 수 없습니다.')
        return dict(row)
    @app.post('/api/admin/rules/validate')
    def validate_rules(data:RuleEditInput,request:Request):
        actor(request,True)
        try:preview=rule_editor.parse_markdown(data.markdown)
        except ValueError as exc:raise HTTPException(422,str(exc))
        before=rule_editor.current(store)['pack'];changes=[]
        for old,new in zip(before['parents']+before['steps'],preview['parents']+preview['steps']):
            key='original' if 'original' in old else 'objective'
            if old[key]!=new[key] or old['title']!=new['title']:changes.append(new.get('rule_id',new.get('id')))
        if before.get('guidance','')!=preview['guidance']:changes.insert(0,'공통 검수 지침')
        return {'valid':True,'changed':changes,'pack':preview,'warnings':rule_editor.compatibility_warnings(preview)}
    @app.put('/api/admin/rules')
    def save_rules(data:RuleEditInput,request:Request):
        who=actor(request,True)
        try:return rule_editor.save(store,data.markdown,data.base_version,who)
        except ValueError as exc:raise HTTPException(422,str(exc))
        except RuntimeError as exc:raise HTTPException(409,str(exc))
    @app.post('/api/login')
    def login(data:LoginInput,request:Request):
        ip=request.client.host if request.client else 'unknown';recent=[t for t in login_attempts.get(ip,[]) if time.time()-t<300]
        if len(recent)>=10:raise HTTPException(429,'5분 후 다시 시도하십시오.')
        login_attempts[ip]=recent+[time.time()]
        expected=s.get('ADMIN_PASSWORD' if data.role=='admin' else 'REVIEWER_PASSWORD')
        if data.role not in ('admin','reviewer') or not expected or not hmac.compare_digest(data.password,expected):raise HTTPException(401,'로그인 정보를 확인하십시오.')
        token=secrets.token_urlsafe(32)
        with store.connect() as c:
            c.execute('DELETE FROM sessions WHERE expires<?',(time.time(),))
            c.execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),data.role,time.time()+8*3600))
        response=JSONResponse({'role':data.role});response.set_cookie('poc11_session',token,httponly=True,secure=s.flag('COOKIE_SECURE'),samesite='strict',max_age=8*3600,path=request.scope.get('root_path') or '/')
        return response
    @app.post('/api/logout')
    def logout(request:Request):
        with store.connect() as c:c.execute('DELETE FROM sessions WHERE id=?',(hashlib.sha256(request.cookies.get('poc11_session','').encode()).hexdigest(),))
        response=JSONResponse({'ok':True});response.delete_cookie('poc11_session',path=request.scope.get('root_path') or '/');return response
    @app.get('/api/jobs')
    def jobs(request:Request):
        actor(request)
        return [{k:j[k] for k in ('id','metadata','created_at','state','demo')} for j in store.jobs()]
    def save_image(raw,filename,mime,metadata,demo=False):
        try:normalized,info=normalize(raw,filename,mime,s.integer('MAX_IMAGE_PIXELS',24000000))
        except ValueError as exc:raise HTTPException(400,str(exc))
        jid=uuid.uuid4().hex;directory=s.data/jid;directory.mkdir(mode=0o700)
        (directory/'image.png').write_bytes(normalized)
        job={'id':jid,'created_at':now(),'state':'READY','metadata':metadata,'image':info,'grid':{'id':'main-v1','rows':12,'cols':12},'runs':[],'crops':[],'demo':demo}
        store.save(job);return public_job(job)
    @app.post('/api/jobs')
    async def upload(request:Request,file:UploadFile=File(...),title:str=Form('제목 없음'),department:str=Form(''),media_type:str=Form('카드뉴스'),release_date:str=Form(''),context:str=Form('')):
        who=actor(request);raw=await file.read(s.integer('MAX_UPLOAD_MB',20)*1024*1024+1)
        if len(raw)>s.integer('MAX_UPLOAD_MB',20)*1024*1024:raise HTTPException(413,'파일 용량 초과')
        if any(len(x)>2000 for x in (title,department,media_type,release_date,context)):raise HTTPException(400,'입력 문구가 너무 깁니다.')
        job=save_image(raw,file.filename or '',file.content_type or '',dict(title=title,department=department,media_type=media_type,release_date=release_date,context=context))
        store.audit(who,'UPLOAD',job['id'],{'sha256':job['image']['original_sha256']});return job
    @app.post('/api/demo')
    def demo(request:Request):
        actor(request)
        return save_image((ROOT/'samples/demo.png').read_bytes(),'demo.png','image/png',{'title':'합성 샘플 · 지역 안전 캠페인','department':'시연 부서','media_type':'카드뉴스','release_date':'','context':'실제 판정이 아닌 고정된 기능 시연'},True)
    @app.get('/api/jobs/{jid}')
    def detail(jid:str,request:Request):actor(request);return public_job(getjob(jid))
    @app.get('/api/jobs/{jid}/image')
    def image(jid:str,request:Request):actor(request);getjob(jid);return FileResponse(s.data/jid/'image.png',media_type='image/png')
    @app.post('/api/jobs/{jid}/runs')
    def run(jid:str,data:RunInput,request:Request):
        who=actor(request);job=getjob(jid)
        if data.mode not in ('mock','live','blocked') or data.vision_model not in ('gpt-5.4','gpt-5.4-mini','gpt-6.1-sol','gpt-6-astra','nvidia/nemotron-3.5-super-vl:free') or data.analysis_model not in ('solar-pro4','gpt-5.4','gpt-5.4-mini','gpt-6.1-sol','gpt-6-astra',''):
            raise HTTPException(400,'지원하지 않는 실행 설정')
        if data.reuse_observation_run_id and (data.mode!='live' or data.crop_id):raise HTTPException(400,'관찰 재사용은 전체 이미지 실제 분석에서만 가능합니다.')
        if data.crop_id and data.crop_id not in {x['id'] for x in job['crops']}:raise HTTPException(400,'잘못된 확대 영역')
        if data.mode=='live':
            if not data.consent or not s.flag('EXTERNAL_API_ENABLED',True):raise HTTPException(400,'외부 전송 허용을 확인하십시오.')
            models=[data.analysis_model or data.vision_model]+([] if data.reuse_observation_run_id else [data.vision_model])
            for model in models:
                key='OPENROUTER_API_KEY' if model.endswith(':free') else 'UPSTAGE_API_KEY' if model=='solar-pro4' else 'OPENAI_API_KEY'
                if not s.get(key):raise HTTPException(400,f'{key} 설정이 필요합니다.')
        try:job=engine.submit(jid,data.model_dump())
        except ValueError as exc:raise HTTPException(409,str(exc))
        store.audit(who,'RUN',jid,data.model_dump());return public_job(job)
    @app.post('/api/jobs/{jid}/crops')
    def make_crop(jid:str,data:CropInput,request:Request):
        actor(request);job=getjob(jid)
        if job['state'] in ('QUEUED','RUNNING'):raise HTTPException(409,'현재 검사 완료 후 확대 영역을 만드십시오.')
        if len(job['crops'])>=20:raise HTTPException(400,'이미지당 확대 영역은 최대 20개입니다.')
        try:
            # Expand by one full main-grid cell on each side; preserve neighboring structure.
            rects=[cell_rect(x) for x in data.cell_ids];rows=[]
            for cell in data.cell_ids:
                r,c=int(cell[1:3]),int(cell[4:6])
                rows.extend(f'R{y:02}C{x:02}' for y in range(max(1,r-1),min(12,r+1)+1) for x in range(max(1,c-1),min(12,c+1)+1))
            raw,rect=crop((s.data/jid/'image.png').read_bytes(),sorted(set(rows)))
        except ValueError as exc:raise HTTPException(400,str(exc))
        cid='crop-'+uuid.uuid4().hex;info={'id':cid,'rect':rect,'selected_cells':data.cell_ids,'context_cells':sorted(set(rows)),'rows':8,'cols':8}
        (s.data/jid/(cid+'.png')).write_bytes(raw);job['crops'].append(info);store.save(job);return info
    @app.get('/api/jobs/{jid}/crops/{cid}')
    def crop_image(jid:str,cid:str,request:Request):
        actor(request);job=getjob(jid)
        if cid not in {x['id'] for x in job['crops']}:raise HTTPException(404)
        return FileResponse(s.data/jid/(cid+'.png'),media_type='image/png')
    @app.post('/api/jobs/{jid}/reviews')
    def review(jid:str,data:ReviewInput,request:Request):
        who=actor(request)
        if data.status not in ('PASS','FAIL','REVIEW','NOT_APPLICABLE'):raise HTTPException(400,'허용되지 않은 검토 상태')
        with engine.lock:
            job=getjob(jid)
            if job['state'] in ('QUEUED','RUNNING') or not job['runs']:raise HTTPException(409,'검사 완료 후 검토하십시오.')
            run=job['runs'][-1];finding=next((x for x in run['results'] if x.get('id')==data.finding_id),None)
            if not finding:raise HTTPException(404)
            item={**data.model_dump(),'reason':redact(data.reason),'reviewer':who,'at':now(),'previous_status':next((x['status'] for x in reversed(run['reviews']) if x['finding_id']==data.finding_id),finding['status'])}
            run['reviews'].append(item);store.save(job);store.audit(who,'REVIEW',jid,item)
        return public_job(job)
    @app.delete('/api/jobs/{jid}')
    def delete(jid:str,request:Request):
        who=actor(request,True)
        with engine.lock:
            job=getjob(jid)
            if job['state'] in ('RUNNING','QUEUED'):raise HTTPException(409,'진행 중인 검사는 삭제할 수 없습니다.')
            with store.connect() as c:c.execute('DELETE FROM jobs WHERE id=?',(jid,))
            shutil.rmtree(s.data/jid,ignore_errors=True)
            store.audit(who,'DELETE',jid,{'deleted':True})
        return {'deleted':True}
    @app.get('/api/jobs/{jid}/report')
    def report(jid:str,request:Request):
        actor(request);job=public_job(getjob(jid))
        return Response(json.dumps({'notice':'자동 검수는 최종 공개 승인이 아닙니다. FAIL은 오류 의심이며 사람 확인이 필요합니다.','exported_at':now(),**job},ensure_ascii=False,indent=2),media_type='application/json',headers={'Content-Disposition':f'attachment; filename="inspection-{jid}.json"'})
    @app.get('/api/usage')
    def usage(request:Request):actor(request);return engine.usage.summary()
    @app.get('/api/usage/remaining')
    def remaining_usage(request:Request):actor(request);return engine.usage.remaining()
    @app.post('/api/usage/sync')
    def sync(request:Request):actor(request,True);return {'synced':engine.usage.flush()}
    @app.get('/api/references')
    def references(request:Request):actor(request);return store.references()
    @app.post('/api/references')
    def add_reference(data:ReferenceInput,request:Request):
        who=actor(request,True)
        if not set(data.parent_ids)<={x['id'] for x in PACK['parents']}:raise HTTPException(400,'잘못된 원문 규칙')
        if not data.official_url.startswith('https://'):raise HTTPException(400,'출처는 HTTPS URL로 기록하십시오. 서버에서 자동 접속하지 않습니다.')
        if data.kind not in {'history','official-map','official-symbols','culture','official-emblems','policy','language','license','consent','source-data'}:raise HTTPException(400,'지원하지 않는 기준자료 종류')
        from datetime import date
        try:
            for d in (data.effective_from,data.effective_to):
                if d:date.fromisoformat(d)
            if data.effective_from and data.effective_to and data.effective_from>data.effective_to:raise ValueError()
        except ValueError:raise HTTPException(400,'유효 기간을 확인하십시오.')
        ref={**data.model_dump(),'id':'ref-'+uuid.uuid4().hex,'status':'DRAFT','retrieved_at':now(),'approved_by':None,'approved_at':None,'source_file_hash':hashlib.sha256(data.content.encode()).hexdigest(),'image_file':None}
        with store.connect() as c:c.execute('INSERT INTO references_registry VALUES(?,?)',(ref['id'],json.dumps(ref,ensure_ascii=False)))
        store.audit(who,'REFERENCE_CREATE',ref['id'],{'version':ref['version']});return ref
    @app.post('/api/references/{rid}/image')
    async def add_reference_image(rid:str,request:Request,file:UploadFile=File(...)):
        actor(request,True);ref=next((x for x in store.references() if x['id']==rid),None)
        if not ref or ref['status']!='DRAFT':raise HTTPException(409,'초안 자료에만 이미지를 첨부할 수 있습니다.')
        raw=await file.read(s.integer('MAX_UPLOAD_MB',20)*1024*1024+1)
        if len(raw)>s.integer('MAX_UPLOAD_MB',20)*1024*1024:raise HTTPException(413)
        try:raw,meta=normalize(raw,file.filename or '',file.content_type or '',s.integer('MAX_IMAGE_PIXELS',24000000))
        except ValueError as exc:raise HTTPException(400,str(exc))
        directory=s.data/'references';directory.mkdir(exist_ok=True,mode=0o700);name=rid+'-'+uuid.uuid4().hex+'.png';(directory/name).write_bytes(raw)
        ref.update(image_file=name,image_hash=meta['normalized_sha256'])
        with store.connect() as c:
            updated=c.execute("UPDATE references_registry SET body=? WHERE id=? AND json_extract(body,'$.status')='DRAFT'",(json.dumps(ref,ensure_ascii=False),rid))
            if updated.rowcount!=1:
                (directory/name).unlink(missing_ok=True)
                raise HTTPException(409,'자료가 승인되어 이미지 수정이 중단되었습니다.')
        return ref
    @app.get('/api/references/{rid}/image')
    def reference_image(rid:str,request:Request):
        actor(request);ref=next((x for x in store.references() if x['id']==rid),None)
        if not ref or not ref.get('image_file'):raise HTTPException(404)
        return FileResponse(s.data/'references'/ref['image_file'],media_type='image/png')
    @app.post('/api/references/{rid}/approve')
    def approve_reference(rid:str,request:Request):
        who=actor(request,True);ref=next((x for x in store.references() if x['id']==rid),None)
        if not ref or ref['status']!='DRAFT':raise HTTPException(409,'초안 자료만 승인할 수 있습니다.')
        if ref['kind'] in ('official-symbols','official-map','official-emblems') and not ref.get('image_file'):raise HTTPException(400,'공식 도안 비교에는 기준 이미지 첨부가 필요합니다.')
        ref.update(status='APPROVED',approved_by=who,approved_at=now())
        with store.connect() as c:c.execute('UPDATE references_registry SET body=? WHERE id=?',(json.dumps(ref,ensure_ascii=False),rid))
        store.audit(who,'REFERENCE_APPROVE',rid,{'version':ref['version']});return ref
    return app
