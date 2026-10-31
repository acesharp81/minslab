"""Bounded public HTTP fetch with DNS pinning; never exposes model credentials."""
import hashlib
import http.client
import ipaddress
import re
from http.cookies import SimpleCookie
from pathlib import Path
import socket
import ssl
import time
from urllib.parse import urlsplit, urljoin, urlunsplit, parse_qsl, urlencode, quote
from bs4 import BeautifulSoup

MAX_BYTES=3_000_000


def canonical(url):
    parts=urlsplit(url)
    if parts.scheme not in ('https','http') or not parts.hostname or parts.username or parts.password:
        raise ValueError('공개 http(s) 원문 URL만 입력하세요')
    if parts.port not in (None,80,443): raise ValueError('표준 웹 포트만 지원합니다')
    if len(url)>2000: raise ValueError('원문 URL이 너무 깁니다')
    pairs=parse_qsl(parts.query,keep_blank_values=True)
    if any(k.lower() in ('key','servicekey','service_key','api_key','apikey','authkey','authorization','token','password','secret','access_token','consumer_key','consumer_secret') for k,v in pairs):
        raise ValueError('인증정보가 포함된 URL은 수집할 수 없습니다')
    host=parts.hostname.encode('idna').decode().lower()
    try:
        if not ipaddress.ip_address(host).is_global: raise ValueError('내부 주소는 수집할 수 없습니다')
    except ValueError as error:
        if '내부 주소' in str(error): raise
    if host=='localhost' or host.endswith(('.localhost','.local','.internal')): raise ValueError('내부 주소는 수집할 수 없습니다')
    # Seoul's hash identifies a real article, not an ignorable UI anchor.
    if host in ('www.seoul.go.kr','seoul.go.kr') and parts.path=='/news/news_report.do' and re.fullmatch(r'view/\d+',parts.fragment):
        pairs=[(k,v) for k,v in pairs if k!='nttNo']+[('nttNo',parts.fragment.split('/')[1])]
    query=urlencode(sorted((k,v) for k,v in pairs if not k.lower().startswith('utm_') and k.lower() not in ('fbclid','gclid')))
    return urlunsplit((parts.scheme,host+(':'+str(parts.port) if parts.port else ''),parts.path or '/',query,''))


def public_addresses(host, port):
    addresses=list(dict.fromkeys(r[4][0] for r in socket.getaddrinfo(host,port,type=socket.SOCK_STREAM)))
    if not addresses or any(not ipaddress.ip_address(a).is_global for a in addresses):
        raise ValueError('공개 인터넷 주소가 아닙니다')
    return addresses


class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, port, address):
        super().__init__(host,port,timeout=20,context=ssl.create_default_context())
        self.address=address
    def connect(self):
        self.sock=self._context.wrap_socket(socket.create_connection((self.address,self.port),self.timeout),server_hostname=self.host)


class Fetcher:
    def __init__(self,data_dir):
        self.folder=Path(data_dir)/'raw'/'ai_publication'
        self.folder.mkdir(parents=True,exist_ok=True)
        self.last={}

    def get(self,url,suffix='html'):
        self.last={}
        current=canonical(url)
        cookies={}  # Ephemeral, exact-origin and path scoped; never persisted or logged.
        for _ in range(4):
            parts=urlsplit(current);port=parts.port or (443 if parts.scheme=='https' else 80)
            address=public_addresses(parts.hostname,port)[0]
            conn=(PinnedHTTPS(parts.hostname,port,address) if parts.scheme=='https' else http.client.HTTPConnection(address,port,timeout=20))
            try:
                # Encode only the HTTP request target; preserve stored URL identity.
                path=urlunsplit(('','',quote(parts.path,safe="/%:@!$&'()*+,;=-._~"),parts.query,''))
                origin=(parts.scheme,parts.hostname,port)
                headers={'Host':parts.netloc,'User-Agent':'HOME-publication-review/1.0','Accept-Encoding':'identity'}
                sent=[name+'='+value for (site,cpath,name),(value,secure) in cookies.items()
                      if site==origin and (parts.path==cpath or parts.path.startswith(cpath.rstrip('/')+'/'))
                      and (not secure or parts.scheme=='https')]
                if sent: headers['Cookie']='; '.join(sent)
                conn.request('GET',path,headers=headers)
                response=conn.getresponse()
                for key,value in response.getheaders():
                    if key.lower()!='set-cookie':continue
                    parsed=SimpleCookie()
                    try:parsed.load(value)
                    except Exception:continue
                    for name,morsel in parsed.items():
                        if morsel['domain'] and morsel['domain'].lstrip('.').lower()!=parts.hostname:continue
                        cpath=morsel['path'] or parts.path.rsplit('/',1)[0] or '/'
                        if not cpath.startswith('/'):cpath='/'
                        ck=(origin,cpath,name)
                        if morsel['max-age']=='0':cookies.pop(ck,None)
                        else:cookies[ck]=(morsel.value,bool(morsel['secure']))
                if response.status in (301,302,303,307,308):
                    current=canonical(urljoin(current,response.getheader('Location','')))
                    continue
                if response.status!=200: raise ValueError('원문 응답 HTTP '+str(response.status))
                chunks=[];size=0;deadline=time.monotonic()+25
                while size<=MAX_BYTES:
                    remaining=deadline-time.monotonic()
                    if remaining<=0: raise ValueError('원문 읽기 시간 상한 초과')
                    if conn.sock: conn.sock.settimeout(min(20,remaining))
                    chunk=response.read1(min(65536,MAX_BYTES+1-size))
                    if not chunk: break
                    chunks.append(chunk);size+=len(chunk)
                data=b''.join(chunks)
                if not data or len(data)>MAX_BYTES: raise ValueError('원문이 비었거나 3MB 상한 초과')
                mime=response.getheader('Content-Type','').lower()
                if data.startswith(b'%PDF') or 'pdf' in mime:
                    raise ValueError('PDF 첨부는 원문 링크를 보존하고 담당자 수집 필요')
                if not any(x in mime for x in ('text/','xml','html','json')) and mime:
                    raise ValueError('텍스트/HTML/RSS 원문만 자동 수집합니다')
                digest=hashlib.sha256(data).hexdigest()
                (self.folder/(digest+'.raw')).write_bytes(data)
                self.last=dict(url=current,sha256=digest,bytes=len(data))
                return data
            finally: conn.close()
        raise ValueError('원문 리다이렉트 상한 초과')


def text_content(raw):
    soup=BeautifulSoup(raw,'html.parser')
    title=soup.title.get_text(' ',strip=True) if soup.title else ''
    for node in soup.select('script,style,noscript,nav,footer,header,form'): node.decompose()
    # Prefer article bodies over navigation, popular-news lists and social widgets.
    main=None
    for selector in ('.board-view-txt', '.viewer', '.detailTable td.cont', '#scrabArea', '.bd_view_cont', 'article.board_view .contents', '.board_view_con'):
        candidate=soup.select_one(selector)
        if candidate is not None:
            main=candidate
            break
    if main is None:main=soup.select_one('article') or soup.select_one('main') or soup.body or soup
    body=main.get_text(' ',strip=True)
    if len(body)<40: raise ValueError('원문 본문 부족 · 접근 제한 또는 스캔 첨부 확인 필요')
    return title[:500],body[:24000],len(body)>24000
