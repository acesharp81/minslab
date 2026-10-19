"""On-demand public facility information with explicit matching and provenance."""
import re
import json
import hashlib
import httpx
import time
import threading
from urllib.parse import urljoin
from xml.etree import ElementTree as ET
from bs4 import BeautifulSoup
from .collectors import Fetcher
from .api_samples import today
from .infrastructure import distance_metres, mart_name

KML = {'bus':'https://topis.seoul.go.kr/map/busKml.do', 'subway':'https://topis.seoul.go.kr/map/subwayKml.do'}
SCHOOL_LIST='https://www.schoolinfo.go.kr/ei/ss/pneiss_a08_s0.do'
SCHOOL_PROFILE='https://www.schoolinfo.go.kr/ei/ss/Pneiss_b01_s0.do'
CHILD_LIST='https://iseoul.seoul.go.kr/portal/info/preSchoolList.do'
EMART_LIST='https://emartapp.emart.com/branch/list.do'
TOPIS='https://topis.seoul.go.kr'
BUS='https://bus.go.kr'
KINDS={'school','childcare','bus','subway','hospital','mart'}


def compact(value):
    return re.sub(r'\s+', '', str(value or '')).replace('서울특별시','서울').replace('경기도','경기').replace('인천광역시','인천')


def field(label,value):
    if value is None or value=='':return None
    return {'label':label,'value':str(value)}


def same_address(actual,expected):
    """Require the same road and building number; never join names alone."""
    provinces={'서울특별시','서울','경기도','경기','인천광역시','인천'}
    district=lambda s:set(re.findall(r'(?:^|\s)([가-힣]+[시군구])(?=\s|$)',s))-provinces
    ad,bd=district(actual),district(expected)
    if ad and bd and not (ad<=bd or bd<=ad):return False
    road=lambda s:re.findall(r'([가-힣0-9]+(?:대로|로|길))\s*(\d+(?:-\d+)?)',s)
    a,b=road(actual),road(expected)
    if a and b:return bool(set(a)&set(b)) and compact(actual)[:2]==compact(expected)[:2]
    # Parcel addresses are only accepted with the same district/dong/number.
    parcel=lambda s:re.findall(r'([가-힣]+[동리읍면])\s*(\d+(?:-\d+)?)',s)
    a,b=parcel(actual),parcel(expected)
    return bool(a and b and set(a)&set(b) and compact(actual)[:2]==compact(expected)[:2])


def kml_rows(body):
    root=ET.fromstring(body);rows=[]
    for p in root.iter():
        if p.tag.split('}')[-1]!='Placemark':continue
        children={n.tag.split('}')[-1]:n for n in p.iter()}
        coords=children.get('coordinates')
        if coords is None or not coords.text:continue
        lon,lat,*_=map(float,coords.text.split(','))
        attrs={d.attrib['name']:next((v.text for v in d if v.tag.split('}')[-1]=='value'),None)
               for d in p.iter() if d.tag.split('}')[-1]=='Data' and 'name' in d.attrib}
        rows.append(dict(name=children['name'].text,latitude=lat,longitude=lon,**attrs))
    return rows


def bus_match(place,rows):
    name=lambda s:re.sub(r'\(버스정류장\)|\(\d+\)|\s+','',s)
    candidates=[(distance_metres(place['latitude'],place['longitude'],r['latitude'],r['longitude']),r)
                for r in rows if name(r['name'])==name(place['name'])]
    candidates.sort(key=lambda p:p[0])
    if not candidates or candidates[0][0]>50:return None
    if len(candidates)>1 and candidates[0][0]>10 and candidates[1][0]-candidates[0][0]<15:return None
    return candidates[0][1]


def parse_school(body,place):
    soup=BeautifulSoup(body.decode('cp949','replace'),'html.parser')
    text=soup.get_text(' ',strip=True)
    address=re.search(r'주소\s*:\s*(.*?)\s*학생수\s*:',text)
    heading=soup.select_one('title')
    if not heading or compact(place['name']) not in compact(heading.get_text()) or not address or not same_address(address[1],place.get('address','')):return None
    student=re.search(r'학생수\s*:\s*([\d,]+)명',text);teachers=re.search(r'교원수\s*:\s*([\d,]+)명',text)
    year=soup.select_one('#gsYear option[selected]')
    return dict(fields=[f for f in [field('전교생',student[1]+'명' if student else None),field('교원',teachers[1]+'명' if teachers else None)] if f],
                as_of=year.get('value')+'학년도 공시' if year else '공시연도 미확인',address=address[1])


def parse_childcare(body,place):
    soup=BeautifulSoup(body,'html.parser');rows=[]
    for tr in soup.select('tbody tr'):
        cells=tr.select('td')
        if len(cells)<8:continue
        name=cells[1].get_text(' ',strip=True).replace('거점','').strip()
        if compact(name)!=compact(place['name']) or not same_address(cells[6].get_text(' ',strip=True),place.get('address','')):continue
        code=re.search(r'stCode=(\d+)',str(cells[7]));rows.append(dict(fields=[field('유형',cells[2].get_text(' ',strip=True)),field('정원',cells[3].get_text(' ',strip=True)),field('현원',cells[4].get_text(' ',strip=True)),field('전화',cells[5].get_text(' ',strip=True))],source_key=code[1] if code else None))
    return rows[0] if len(rows)==1 else None


def timetable_headways(rows):
    """Published scheduled departures, not live arrival gaps. Keep direction/time scope."""
    result=[]
    for key,label in [('upArrow','상행/내선'),('dnArrow','하행/외선')]:
        values=[]
        for row in rows:
            hour=int(row['hh'])
            for match in re.finditer(r'(?:^|,\s*)(\d{2})(?:\s*\([^)]*\))?',row.get(key) or ''):
                minute=int(match[1])
                if minute<60:values.append((hour if hour>=4 else hour+24)*60+minute)
        values=sorted(set(values))
        for start,end,title in [(7*60,9*60,'07~09시'),(10*60,16*60,'10~16시')]:
            selected=[v for v in values if start<=v<end];gaps=[b-a for a,b in zip(selected,selected[1:]) if b>a]
            if gaps:result.append(field('평일 '+title+' '+label,f'{min(gaps)}~{max(gaps)}분 · 시간표 기준'))
    return result


class FacilityDetails:
    def __init__(self):
        self._cache={};self._catalog={};self._lock=threading.RLock()

    def catalog(self,key,builder):
        with self._lock:
            cached=self._catalog.get(key)
            if cached and time.monotonic()-cached[0]<86400:return cached[1]
        value=builder()
        with self._lock:self._catalog[key]=(time.monotonic(),value)
        return value

    def get(self,place,service):
        key=(place['kind'],place['id'],place['name'],place.get('address'),place['latitude'],place['longitude'])
        ttl=600 if place['kind'] in ('bus','subway') else 86400
        with self._lock:
            cached=self._cache.get(key)
            if cached and time.monotonic()-cached[0]<(60 if cached[1]['status']=='UNAVAILABLE' else ttl):return cached[1]
        fetcher=Fetcher('facility_details',service.data_dir/'raw');fetcher.client.timeout=httpx.Timeout(6)
        result=dict(status='NOT_LINKED',fields=[],source_name=None,source_url=None,source_key=None,as_of=None,collected_at=today().isoformat(),notes=[])
        try:
            provider=getattr(self,'_'+place['kind'],None)
            if provider:result.update(provider(place,fetcher))
            if result['fields']:result['status']='READY'
            result['fields']=[f for f in result['fields'] if f]
        except (ValueError,RuntimeError,ET.ParseError,KeyError,TypeError,httpx.HTTPError):
            result.update(status='UNAVAILABLE',fields=[],notes=['상세 원천을 지금 조회할 수 없습니다.'])
        finally:
            result['evidence']=[{k:v for k,v in entry.items() if k in ('url','sha256','file','bytes','request_parameters')} for entry in fetcher.manifest]
            fetcher.close()
        with self._lock:
            if len(self._cache)>=300:self._cache.pop(next(iter(self._cache)))
            self._cache[key]=(time.monotonic(),result)
        return result

    def _school(self,p,f):
        name=compact(p['name']);address=p.get('address','');code='1100000000' if address.startswith('서울') else '4100000000' if address.startswith('경기') else '2800000000' if address.startswith('인천') else None
        if not code:return {'notes':['학교의 시도·주소 연결이 필요합니다.']}
        def load():
            soup=BeautifulSoup(f.get(SCHOOL_LIST,params={'SIDO_CODE':code}).decode('cp949','replace'),'html.parser')
            return [(compact(a.get_text()),re.search(r"searchSchul\('([a-f0-9-]+)'\)",a.get('href',''))[1]) for a in soup.select('a[href]') if re.search(r"searchSchul\('([a-f0-9-]+)'\)",a.get('href',''))]
        ids=[identifier for n,identifier in self.catalog('school:'+code,load) if n==name]
        for identifier in ids[:3]:
            url=SCHOOL_PROFILE+'?SHL_IDF_CD='+identifier;parsed=parse_school(f.get(url),p)
            if parsed:return dict(parsed,source_name='학교알리미',source_url=url,source_key=identifier,notes=['전교생은 재학생 수이며 입학 정원·배정 가능 인원이 아닙니다.'])
        return dict(source_name='학교알리미',source_url=SCHOOL_LIST,notes=['학교명·주소에 일치하는 공시정보 연결이 필요합니다.'])

    def _childcare(self,p,f):
        if not p.get('address','').startswith('서울'):return {'source_name':'어린이집정보공개포털','source_url':'https://info.childcare.go.kr/info_html5/oais/openapi/OpenApiSlL.jsp','notes':['지역별 어린이집 상세 원천 연결이 필요합니다.']}
        district=next((v for n,v in [('강남구','11680'),('강서구','11500'),('노원구','11350'),('서초구','11650'),('송파구','11710'),('영등포구','11560'),('은평구','11380')] if n in p['address']),None)
        params={'crname':p['name']}
        if district:params['cbgu']=district
        body=f.get(CHILD_LIST,params=params);parsed=parse_childcare(body,p)
        result=dict(source_name='서울시 보육포털',source_url=CHILD_LIST,as_of=today().isoformat()+' 0시 목록',notes=['정원−현원은 입소 가능 인원으로 확정할 수 없습니다.'])
        if parsed:
            result.update(parsed)
            if parsed['source_key']:result['source_url']='https://iseoul.seoul.go.kr/homepage/main.do?stCode='+parsed['source_key']
        return result

    def _mart(self,p,f):
        name=mart_name(p['name']).replace('가든파이브','가든5')
        if not name.startswith(('이마트','트레이더스')):return dict(source_name='점포 공식 안내',notes=['해당 점포의 휴무일·영업시간 원천 연결이 필요합니다.'])
        def load():
            soup=BeautifulSoup(f.get(EMART_LIST),'html.parser')
            return [(mart_name(a.get_text()).replace('가든파이브','가든5'),urljoin(EMART_LIST,a['href'])) for a in soup.select('a[href]') if re.fullmatch(r'/branch/view\.do\?id=\d+(?:&mallGbn=[a-zA-Z0-9]*)?',a['href'])]
        names=[u for n,u in self.catalog('emart',load) if n==name or n.replace('트레이더스홀세일클럽','트레이더스')==name.replace('이마트트레이더스','트레이더스').replace('트레이더스홀세일클럽','트레이더스')]
        if not names:return {'notes':['공식 점포와 장소정보의 연결이 필요합니다.']}
        url=names[0];soup=BeautifulSoup(f.get(url),'html.parser')
        addresses=[dl.find('dd').get_text(' ',strip=True) for dl in soup.select('dl') if dl.find('dt') and dl.find('dd') and dl.find('dt').get_text(strip=True) in ('도로명','지번')]
        if not any(same_address(a,p.get('address','')) for a in addresses):return {'notes':['공식 점포 주소와 장소 주소를 확인해야 합니다.']}
        values=[]
        for dl in soup.select('dl'):
            dt,dd=dl.find('dt'),dl.find('dd')
            if dt and dd and dt.get_text(strip=True) in ('영업시간','휴점일','고객센터'):values.append(field(dt.get_text(strip=True),dd.get_text(' ',strip=True)))
        return dict(fields=values,source_name='이마트 공식 점포 안내',source_url=url,source_key=re.search(r'id=(\d+)',url)[1],as_of=today().isoformat()+' 조회',notes=['월/일은 공식 안내 표기입니다. 임의의 정기 휴무 규칙을 생성하지 않습니다.'])

    def _bus(self,p,f):
        rows=self.catalog('bus-kml',lambda:kml_rows(f.get(KML['bus'],'xml')));station=bus_match(p,rows)
        if not station:return dict(source_name='서울시 TOPIS',source_url=TOPIS,notes=['정류소 ID·방향·좌표 연결이 필요합니다.'])
        payload={'url':'/getStationByUidDetourAt','arsId':station['code']}
        # The public map's read-only endpoint accepts form POST. No reservation or mutation.
        response=f.client.post(TOPIS+'/map/getBusStn.do',data=payload,headers={'Referer':TOPIS+'/openMain.do'});response.raise_for_status()
        raw=response.content;digest=hashlib.sha256(raw).hexdigest();path=f.raw_dir/f.source_id/(digest+'.json');path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
        f.manifest.append(dict(url=str(response.url),sha256=digest,bytes=len(raw),file=f.source_id+'/'+path.name,request_parameters=payload))
        routes=response.json().get('rows',[])
        routes=[r for r in routes if str(r.get('stId'))==station['flag']]
        values=[]
        for r in routes[:20]:
            code=r.get('busRouteId');row={}
            if len(values)<8:
                try:
                    detail=json.loads(f.get(BUS+'/sbus/bus/selectRouteInfo.do','json',params={'rtId':code})).get('ResponseVO',{}).get('data',{}).get('resultList',[])
                    row=next((d for d in detail if str(d.get('rtid'))==str(code)),{})
                except (ValueError,RuntimeError):pass
            values.append(field(r['rtNm'],(row.get('termAll') or ('배차 '+str(r['term'])+'분 · 원천 등록값' if r.get('term') else '배차 미확보'))+' · '+str(r.get('adirection') or '방향 미확보')))
        return dict(fields=values,source_name='서울시 TOPIS·서울버스정보',source_url=BUS+'/app/',source_key=station['code'],as_of=today().isoformat()+' 조회',notes=['정류소 방향별 경유 노선입니다. 최대 20개 노선이며 요일별 배차는 앞 8개 노선까지 조회합니다. 등록 배차간격은 실시간 도착 예정과 다릅니다.'])

    def _subway(self,p,f):
        rows=self.catalog('subway-kml',lambda:kml_rows(f.get(KML['subway'],'xml')))
        clean=lambda n:re.sub(r'역$|\([^)]*\)|\s+','',n)
        stations=[r for r in rows if clean(r['name'])==clean(p['name']) and distance_metres(p['latitude'],p['longitude'],r['latitude'],r['longitude'])<=500]
        values=[]
        for r in stations[:5]:
            station,line=r['code'].split('|');label={'1001':'1호선','1002':'2호선','1003':'3호선','1004':'4호선','1005':'5호선','1006':'6호선','1007':'7호선','1008':'8호선','1009':'9호선','1075':'수인분당선','1077':'신분당선','1063':'경의중앙선','1032':'GTX-A'}.get(line,line)
            body=json.loads(f.get(BUS+'/sbus/bus/selectPlanByStatn.do','json',params={'subwayId':line,'statnId':station,'dfkSe':'1'}))
            rows=body.get('ResponseVO',{}).get('data',{}).get('resultList',[])
            periods=timetable_headways(rows)
            values.append(field('노선',label))
            values.extend(field(label+' · '+v['label'],v['value']) for v in periods)
            if not periods:values.append(field(label+' 배차','시간표 미확보'))
        if p.get('line') and not any(v['value']==p['line'] for v in values):values.insert(0,field('노선',p['line']))
        return dict(fields=values,source_name='서울시 TOPIS·서울버스정보 열차시간표',source_url=BUS+'/app/',source_key=','.join(s['code'] for s in stations),as_of=today().isoformat()+' 조회',notes=['배차는 평일·표시 시간대·방향의 시간표 간격입니다. 급행/일반·운행 변경과 실시간 지연은 별도 확인합니다.'])

    def _hospital(self,p,f):
        # Verified official department directory pilot. HIRA expansion needs separate service approval.
        if compact(p['name'])=='삼성서울병원' and same_address('서울특별시 강남구 일원로 81',p.get('address','')):
            url='https://www.samsunghospital.com/home/reservation/deptSearch.do?DP_TYPE=O';soup=BeautifulSoup(f.get(url),'html.parser')
            names=list(dict.fromkeys(a.get_text(' ',strip=True) for a in soup.select('a[href]') if 'deptDetailInfo.do' in a['href'] and a.get_text(strip=True) not in ('진료과소개','의료진소개','진료예약')))
            if names:return dict(fields=[field('진료과목',' · '.join(names))],source_name='삼성서울병원 공식 진료과 안내',source_url=url,as_of=today().isoformat()+' 조회',notes=['실제 진료 가능 일시·예약·응급 운영은 병원 확인이 필요합니다.'])
        return dict(source_name='건강보험심사평가원 의료기관 상세',source_url='https://www.data.go.kr/data/15001699/openapi.do',notes=['병원 기본정보·진료과목 API 활용승인과 요양기관키 연결이 필요합니다.'])
