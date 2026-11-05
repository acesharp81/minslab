"""Bounded capture of public publisher attachments; never approves their claims."""
import json,re,subprocess,sys
from pathlib import Path
from urllib.parse import urljoin,urlsplit,urlencode
from bs4 import BeautifulSoup
from .ai_collection_fetch import text_content
from .source_authority import public_url

OFFICIAL_HOSTS={'www.molit.go.kr','www.lh.or.kr','www.i-sh.co.kr'}

def attachment_links(raw,url):
    soup=BeautifulSoup(raw,'html.parser');links={};host=urlsplit(url).hostname
    for a in soup.select('a[href]'):
        target=public_url(urljoin(url,a['href']));name=a.get('title') or a.get_text(' ',strip=True)
        if urlsplit(target).hostname!=host:continue
        if re.search(r'preview|viewer',target,re.I):continue
        if re.search(r'download|DWN\.jsp|\.(pdf|hwpx|hwp)(?:$|[?&])',target,re.I):
            links[target]=dict(name=name or '첨부파일',url=target,status='UNVERIFIED',file_state='MISSING',verification_status='UNVERIFIED')
    # SH exposes the exact download arguments as JSON, not a navigable href.
    if host=='www.i-sh.co.kr':
        m=re.search(r'initParam\.downList\s*=\s*(\[.*?\]);',raw.decode('utf-8',errors='replace'),re.S)
        if m:
            try:rows=json.loads(m[1])
            except ValueError:rows=[]
            for a in rows[:30]:
                if not all(re.fullmatch(r'[A-Za-z0-9]+',str(a.get(k,''))) for k in ('brdId','seq','fileTp','fileSeq')):continue
                target='https://www.i-sh.co.kr/main/com/file/innoFD.do?'+urlencode({k:a[k] for k in ('brdId','seq','fileTp','fileSeq')})
                links[target]=dict(name=a.get('oriFileNm','첨부파일'),url=target,status='UNVERIFIED',file_state='MISSING',verification_status='UNVERIFIED')
    return list(links.values())[:30]

def pdf_text(path):
    result=subprocess.run([sys.executable,'-m','backend.publication_capture','--pdf-text',str(path)],capture_output=True,text=True,timeout=20)
    if result.returncode:raise ValueError('PDF 추출 실패 · 스캔/암호/처리 상한 확인 필요')
    return json.loads(result.stdout)

def capture(raw,url,fetcher,*,force_attachment=False):
    """One same-host official PDF at most; personal selection lists are not read."""
    meta=dict(fetcher.last);links=attachment_links(raw,url)
    try:title,body,truncated=text_content(raw)
    except ValueError:
        soup=BeautifulSoup(raw,'html.parser');title=soup.title.get_text(' ',strip=True) if soup.title else '';body='';truncated=False
    attachment=None
    if urlsplit(url).hostname in OFFICIAL_HOSTS and (force_attachment or len(body)<40):
        attachment=next((a for a in links if '.pdf' in (a['name']+a['url']).lower() and not re.search(r'당첨자|계약대상자|명단|선정결과',a['name'])),None)
    if attachment:
        try:
            data=fetcher.get(attachment['url'],allow_pdf=True)
            if not data.startswith(b'%PDF'):raise ValueError('첨부 PDF 응답 아님')
            detail=pdf_text(fetcher.folder/(fetcher.last['sha256']+'.raw'))
            if len(detail['text'].strip())<40:raise ValueError('첨부 텍스트 부족 · 이미지 판독 필요')
            attachment.update(sha256=fetcher.last['sha256'],bytes=len(data),file_state='PRESENT',status='PRESENT',text_extracted=True,pages=detail['pages'],verification_status='UNVERIFIED')
            body=detail['text'];truncated=detail['truncated'];meta=dict(fetcher.last,landing_page=meta,body_source='ATTACHMENT_TEXT',attachments=links)
        except Exception as error:attachment.update(error=str(error),verification_status='UNVERIFIED')
    meta['attachments']=links;fetcher.last=meta
    if len(body.strip())<40:raise ValueError('ATTACHMENT_REQUIRED: 상세 본문은 첨부에만 존재하며 추출 미완료')
    return (title,body,truncated),meta

if __name__=='__main__':
    if len(sys.argv)!=3 or sys.argv[1]!='--pdf-text':raise SystemExit(2)
    import resource
    resource.setrlimit(resource.RLIMIT_CPU,(15,15));resource.setrlimit(resource.RLIMIT_AS,(512*1024*1024,512*1024*1024))
    from pypdf import PdfReader
    reader=PdfReader(sys.argv[2]);count=len(reader.pages)
    text='\n'.join(p.extract_text() or '' for p in reader.pages[:30])
    print(json.dumps(dict(text=text[:24000],pages=count,truncated=count>30 or len(text)>24000),ensure_ascii=False))
