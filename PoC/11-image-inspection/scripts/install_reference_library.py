"""Register the reviewed baseline through the running service's authenticated API.
No model calls. Never replaces an existing reference; same version/content is reused.
"""
from pathlib import Path
import argparse,hashlib,json,sys,io
import httpx
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.config import Settings


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url',default='http://127.0.0.1:18110')
    args=parser.parse_args()
    library=ROOT/'rules/reference-library'
    catalog=json.loads((library/'catalog.json').read_text())
    # Validate every asset and evidence record before any writes.
    for item in catalog['records']:
        assert len(item['verifications'])>=2,item['key']
        if item.get('image'):
            raw=(library/item['image']).read_bytes()
            assert hashlib.sha256(raw).hexdigest()==item['image_sha256'],item['key']
        assert len(item['reference']['content'])<=12000
    settings=Settings()
    with httpx.Client(base_url=args.base_url,timeout=30,follow_redirects=True) as client:
        client.post('/api/login',json={'role':'admin','password':settings.get('ADMIN_PASSWORD')}).raise_for_status()
        response=client.get('/api/references');response.raise_for_status();existing=response.json()
        output=[]
        for item in catalog['records']:
            body=item['reference']
            ref=next((r for r in existing if r['name']==body['name'] and r['version']==body['version'] and r['content']==body['content']),None)
            if ref is None:
                response=client.post('/api/references',json=body);response.raise_for_status();ref=response.json()
            if ref['status']=='DRAFT':
                if item.get('image') and not ref.get('image_file'):
                    with Image.open(library/item['image']) as im:
                        data=io.BytesIO();im.convert('RGB').save(data,format='PNG')
                    response=client.post('/api/references/'+ref['id']+'/image',files={'file':(item['key']+'.png',data.getvalue(),'image/png')});response.raise_for_status()
                response=client.post('/api/references/'+ref['id']+'/approve');response.raise_for_status();ref=response.json()
            assert ref['status']=='APPROVED'
            if item.get('image'):
                response=client.get('/api/references/'+ref['id']+'/image');response.raise_for_status()
                assert hashlib.sha256(response.content).hexdigest()==ref['image_hash']
            output.append({'key':item['key'],'id':ref['id'],'status':ref['status'],'verification_count':len(item['verifications'])})
        print(json.dumps(output,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
