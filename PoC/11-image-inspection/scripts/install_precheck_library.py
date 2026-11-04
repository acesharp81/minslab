"""Install the reviewed 21-item PDF mapping via the existing admin API.

No model calls. Existing references and rule Markdown are never replaced.
The original PDF/page images stay in authenticated runtime storage.
"""
import argparse,hashlib,json,subprocess,sys,tempfile
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app.config import Settings
from app.precheck import parse,KIND


def validate(catalog,pdf):
    if len(catalog['items'])!=21 or [x['number'] for x in catalog['items']]!=list(range(1,22)):raise ValueError('21개 항목 누락/중복')
    if hashlib.sha256(pdf.read_bytes()).hexdigest()!=catalog['source']['sha256']:raise ValueError('검토된 PDF와 원문 해시가 다릅니다. 새 버전으로 매핑을 검토하세요.')
    raw=subprocess.check_output(['pdftotext','-raw',str(pdf),'-']).decode().split('\f')
    layout=subprocess.check_output(['pdftotext','-layout',str(pdf),'-']).decode().split('\f')
    for item in catalog['items']:
        parse(json.dumps(item,ensure_ascii=False,separators=(',',':')))
        page=raw[item['source_page']-1].rsplit('검수 요령',1)[1]
        # Independent extraction modes: all ten markers and raw blocks must be
        # present on the cited page. Case article dates are not validated facts.
        import re
        if re.findall('[①②③④⑤⑥⑦⑧⑨⑩]',page)!=list('①②③④⑤⑥⑦⑧⑨⑩'):raise ValueError('요령 순서 확인 필요')
        block=layout[item['source_page']-1].rsplit('검수 요령',1)[1]
        if set(re.findall('[①②③④⑤⑥⑦⑧⑨⑩]',block))!=set('①②③④⑤⑥⑦⑧⑨⑩'):raise ValueError('2차 추출 검증 실패')
        for tip in item['tips']:
            if tip['source_text'] not in page:raise ValueError('원문 추적 실패: '+tip['id'])


def install(base,pdf,report,rendered=None):
    catalog=json.loads((ROOT/'rules/precheck-library/catalog.json').read_text());validate(catalog,pdf)
    s=Settings();output=[]
    with tempfile.TemporaryDirectory(prefix='poc11-reference-') as temp,httpx.Client(base_url=base,timeout=30) as client:
        client.post('/api/login',json={'role':'admin','password':s.get('ADMIN_PASSWORD')}).raise_for_status()
        response=client.get('/api/references');response.raise_for_status();existing=response.json()
        for item in catalog['items']:
            body=dict(name=f"사전점검 {item['number']:02} · {item['title']} — 내부 검수 참고",kind=KIND,
                      issuer='사용자 제공 · 대국민 홍보물 사전점검 참고자료',official_url='',
                      content=json.dumps(item,ensure_ascii=False,separators=(',',':')),parent_ids=item['parent_ids'],version=item['version'])
            ref=next((r for r in existing if all(r.get(k)==body[k] for k in ('name','version','content','kind'))),None)
            created=ref is None
            if ref is None:
                response=client.post('/api/references',json=body);response.raise_for_status();ref=response.json()
            if ref['status']=='DRAFT':
                if not ref.get('document_file'):
                    response=client.post(f"/api/references/{ref['id']}/document",files={'file':('precheck.pdf',pdf.read_bytes(),'application/pdf')});response.raise_for_status();ref=response.json()
                if not ref.get('image_file'):
                    page=item['source_page'];image=rendered/f'page-{page:02}.jpg' if rendered else Path(temp)/f'p{page}.png'
                    if not image.is_file():
                        prefix=Path(temp)/f'p{page}'
                        subprocess.run(['pdftoppm','-f',str(page),'-l',str(page),'-singlefile','-r','110','-png',str(pdf),str(prefix)],check=True,capture_output=True)
                        image=prefix.with_suffix('.png')
                    response=client.post(f"/api/references/{ref['id']}/image",files={'file':('case-page'+image.suffix,image.read_bytes(),'image/jpeg' if image.suffix=='.jpg' else 'image/png')});response.raise_for_status();ref=response.json()
                response=client.post(f"/api/references/{ref['id']}/approve");response.raise_for_status();ref=response.json()
            if ref['status']!='APPROVED' or not ref.get('document_file') or not ref.get('image_file'):raise ValueError('승인/원문/사례 이미지 확인 실패')
            document=client.get(f"/api/references/{ref['id']}/document");document.raise_for_status()
            if hashlib.sha256(document.content).hexdigest()!=item['source_sha256']:raise ValueError('원문 저장 해시 불일치')
            image=client.get(f"/api/references/{ref['id']}/image");image.raise_for_status()
            if hashlib.sha256(image.content).hexdigest()!=ref['image_hash']:raise ValueError('페이지 이미지 저장 해시 불일치')
            output.append(dict(item_id=item['id'],reference_id=ref['id'],created=created,status=ref['status'],tips=10,source_page=item['source_page'],source_sha256=item['source_sha256'],image_sha256=ref['image_hash']))
        client.post('/api/logout').raise_for_status()
    report.parent.mkdir(parents=True,exist_ok=True);report.write_text(json.dumps(dict(version=catalog['version'],items=output,source_validations=['PDF SHA-256','pdftotext raw: 210 source blocks','pdftotext layout: 210 circled markers','authenticated PDF/page readback SHA-256'],api_model_calls=0),ensure_ascii=False,indent=2))
    print(json.dumps(dict(items=len(output),tips=sum(x['tips'] for x in output),created=sum(x['created'] for x in output),model_calls=0)))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--base-url',default='http://127.0.0.1:18110');p.add_argument('--pdf',type=Path,default=ROOT/'docs/대국민 홍보물 사전점검 참고자료.pdf');p.add_argument('--rendered',type=Path);p.add_argument('--report',type=Path,default=ROOT/'docs/precheck-2026-11-04/registration.json');a=p.parse_args();install(a.base_url,a.pdf,a.report,a.rendered)
