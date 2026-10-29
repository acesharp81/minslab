"""CLOVA OCR V2 adapter + atomic application-side monthly request cap.
No retry on uncertain outcomes. Reservations count against the cap even after crashes.
"""
import base64
from datetime import datetime, timezone
import hashlib
import json
import math
from urllib.parse import urlparse
import uuid
from zoneinfo import ZoneInfo
import httpx
from .storage import now
from .rules import redact


def month_period(at=None):
    at=(at or datetime.now(timezone.utc)).astimezone(ZoneInfo('Asia/Seoul'))
    y,m=(at.year+1,1) if at.month==12 else (at.year,at.month+1)
    return at.strftime('%Y-%m'),datetime(y,m,1,tzinfo=ZoneInfo('Asia/Seoul')).isoformat()


def initialize(store):
    with store.connect() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS naver_ocr_requests (
            id TEXT PRIMARY KEY, period TEXT NOT NULL, account TEXT NOT NULL,
            state TEXT NOT NULL, at TEXT NOT NULL, http_status INTEGER, detail TEXT NOT NULL DEFAULT '')''')


def account(settings):
    return hashlib.sha256(settings.get('NAVER_OCR_API_KEY').encode()).hexdigest()[:24]


def snapshot(settings,store,at=None):
    initialize(store);period,reset=month_period(at);cap=max(0,min(100,settings.integer('NAVER_OCR_MONTHLY_LIMIT',100)))
    offset=max(0,settings.integer('NAVER_OCR_MONTHLY_USED_OFFSET',0))
    with store.connect() as c:
        states=dict(c.execute('SELECT state,count(*) FROM naver_ocr_requests WHERE period=? GROUP BY state',(period,)).fetchall())
    used=sum(states.values())+offset
    configured=bool(settings.get('NAVER_OCR_API_KEY') and settings.get('NAVER_OCR_API_URL'))
    return {'id':'naver-ocr','label':'NAVER CLOVA OCR','unit':'requests','period':'month','scope':'POC11_NAVER_MONTHLY',
        'limit':cap,'remaining':max(0,cap-used),'used':used,'reserved':states.get('RESERVED',0),'unknown':states.get('UNKNOWN',0),
        'status':'AVAILABLE' if configured else 'UNAVAILABLE','expires_at':reset,'month':period,
        'note':'월 100회 앱 호출 상한 · 한국시간 매월 1일 갱신 · 예약·실패·미확정 호출 포함. 다른 앱/콘솔 사용은 자동 조회되지 않습니다.'+(' 키/Invoke URL 설정 필요.' if not configured else '')}


def reserve(settings,store):
    initialize(store);period,_=month_period();cap=max(0,min(100,settings.integer('NAVER_OCR_MONTHLY_LIMIT',100)))
    offset=max(0,settings.integer('NAVER_OCR_MONTHLY_USED_OFFSET',0));eid='naver-'+uuid.uuid4().hex
    with store.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        used=c.execute('SELECT count(*) FROM naver_ocr_requests WHERE period=?',(period,)).fetchone()[0]
        if used+offset>=cap:raise RuntimeError('NAVER OCR 월 호출 한도 소진 · 추가 호출 차단')
        c.execute('INSERT INTO naver_ocr_requests(id,period,account,state,at) VALUES(?,?,?,?,?)',(eid,period,account(settings),'RESERVED',now()))
    return eid


def call(settings,store,raw):
    key=settings.get('NAVER_OCR_API_KEY');url=settings.get('NAVER_OCR_API_URL')
    if not key or not url:raise RuntimeError('NAVER OCR 키 또는 Invoke URL 미설정')
    parsed=urlparse(url)
    if parsed.scheme!='https' or not parsed.hostname or not (parsed.hostname.endswith(('.apigw.ntruss.com','.apigw.gov-ntruss.com','.apigw.fin-ntruss.com')) or parsed.hostname=='clovaocr-api-kr.ncloud.com') or parsed.username or parsed.password:
        raise RuntimeError('NAVER OCR 공식 HTTPS API Gateway Invoke URL을 설정하십시오.')
    if not settings.flag('EXTERNAL_API_ENABLED',True):raise RuntimeError('외부 전송 차단 모드')
    # Admission is durable BEFORE transmitting a single image.
    eid=reserve(settings,store);state='UNKNOWN';status=0;detail='응답 미확정'
    try:
        with httpx.Client(timeout=45,follow_redirects=False) as client:
            response=client.post(url,headers={'X-OCR-SECRET':key},json={'version':'V2','requestId':eid,'timestamp':int(datetime.now(timezone.utc).timestamp()*1000),
                'lang':'ko','images':[{'format':'png','name':'inspection','data':base64.b64encode(raw).decode()}]})
        status=response.status_code
        if status!=200:
            # Keep only documented codes, never echo provider bodies (may contain secrets).
            reasons={'0001':'호출 URL 오류','0002':'Secret key 검증 실패','0011':'요청 본문 오류',
                     '0021':'프로토콜 버전 오류','0022':'OCR 도메인 오류','0023':'공급자 호출 한도 소진',
                     '0025':'공급자 요청 속도 제한','0028':'표 추출 설정 오류'}
            try:code=str(response.json().get('code',''))
            except (ValueError,AttributeError):code=''
            state='FAILED';detail='공급자 HTTP '+str(status)
            if code in reasons:detail+=' · '+code+' '+reasons[code]
            raise RuntimeError(detail)
        images=response.json().get('images',[])
        if len(images)!=1 or images[0].get('inferResult')!='SUCCESS':
            state='FAILED';detail='OCR 인식 응답 미완료';raise RuntimeError(detail)
        fields=[]
        for field in images[0].get('fields',[]):
            vertices=field.get('boundingPoly',{}).get('vertices',[])
            if len(vertices)!=4:continue
            xs=[float(v['x']) for v in vertices];ys=[float(v['y']) for v in vertices]
            if not all(math.isfinite(v) for v in xs+ys):continue
            fields.append({'text':redact(str(field.get('inferText','')))[:2000],'score':float(field.get('inferConfidence',0)),
                           'rect_px':[min(xs),min(ys),max(xs),max(ys)]})
        state='COMPLETED';detail='문자 영역 '+str(len(fields))+'개'
        return {'engine':'NAVER CLOVA OCR V2','fields':fields,'event_id':eid,'status':state}
    except httpx.HTTPError as exc:
        raise RuntimeError('NAVER OCR 네트워크 오류 · 한도 예약 유지') from exc
    except (ValueError,KeyError,TypeError) as exc:
        detail='OCR 응답 형식 오류';raise RuntimeError(detail) from exc
    finally:
        with store.connect() as c:c.execute('UPDATE naver_ocr_requests SET state=?,http_status=?,detail=? WHERE id=?',(state,status,detail,eid))


def history(store):
    initialize(store)
    with store.connect() as c:return [dict(r) for r in c.execute('SELECT id,period,state,at,http_status,detail FROM naver_ocr_requests ORDER BY at DESC LIMIT 200')]
