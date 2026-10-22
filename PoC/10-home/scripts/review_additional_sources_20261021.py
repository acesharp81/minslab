"""Capture targeted public originals for previously unverified A01–A08 checks."""
import hashlib,json,re
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from concurrent.futures import ThreadPoolExecutor

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/analysis/official_followup_sources_20261021'
PRIOR=ROOT/'docs/analysis/official_additional_checks_20261021'

def main():
    import requests
    from bs4 import BeautifulSoup
    OUT.mkdir(parents=True,exist_ok=True)
    rows=json.loads((PRIOR/'home_current_rows.json').read_text())
    known={r['payload'].get('notice_entity_id') for r in rows if r['source_id']=='lh_notice_detail'}
    pending=[r for r in rows if r['kind']=='lh_notice' and r['entity_id'] not in known and
        '2026-01-01'<=str(r['payload'].get('source_date',''))<='2026-09-30' and not any(w in r['payload']['name']
        for w in ['예비','정정','추가','잔여','재공고','선착순','선순위','동호','동·호'])]
    tasks=[dict(key=r['entity_id'],url=r['payload']['evidence_url'],notice=r) for r in pending]
    tasks.extend([
        dict(key='seoul_housing_type',url='https://data.seoul.go.kr/bsp/wgs/dataView/data300View/10182.do'),
        dict(key='kosis_type_starts',url='https://kosis.kr/statHtml/statHtml.do?orgId=116&tblId=DT_MLTM_5387'),
        dict(key='molit_type_starts_period',url='https://stat.molit.go.kr/portal/api/period.do?form_id=5387&style_num=1'),
        dict(key='molit_type_permit_period',url='https://stat.molit.go.kr/portal/api/period.do?form_id=5376&style_num=1'),
        dict(key='yonhap_definition',url='https://www.yna.co.kr/amp/view/AKR20261016083900003'),
    ])
    def fetch(task):
        result=dict(task,checked_at=datetime.now(ZoneInfo('Asia/Seoul')).isoformat())
        try:
            r=requests.get(task['url'],timeout=30);r.raise_for_status();raw=r.content
            file=task['key']+('.json' if 'period' in task['key'] else '.html');(OUT/file).write_bytes(raw)
            r.encoding=r.apparent_encoding;soup=BeautifulSoup(r.text,'html.parser')
            (OUT/(task['key']+'.txt')).write_text(soup.get_text('\n',strip=True))
            result.update(status=r.status_code,file=file,sha256=hashlib.sha256(raw).hexdigest())
            if 'notice' in task:
                result['complex_headings']=[h.get_text(' ',strip=True) for h in soup.select('div[id^="wrtancSbdTab"] h4')]
                result['offer_tables']=[]
                for table in soup.select('table'):
                    heads=[h.get_text(' ',strip=True) for h in table.select('thead th')]
                    if any('공급' in h for h in heads):
                        result['offer_tables'].append(dict(heads=heads,rows=[[c.get_text(' ',strip=True) for c in tr.find_all(['th','td'],recursive=False)] for tr in table.select('tbody tr')]))
        except Exception as exc:result.update(error=type(exc).__name__)
        return result
    with ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(fetch,tasks))
    (OUT/'capture_manifest.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
    print(json.dumps([dict(key=r['key'],status=r.get('status'),error=r.get('error')) for r in results],ensure_ascii=False))

if __name__=='__main__':main()
