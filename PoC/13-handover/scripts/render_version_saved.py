"""Render already-confirmed evidence with current renderer, without model calls."""
import json,sys
from pathlib import Path
import httpx
from dotenv import dotenv_values
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app.reports import build_report,render_html,render_markdown,render_docx
OUT=ROOT/'test-results/versions/live';cid=json.loads((OUT/'checkpoint.json').read_text())['case_id']
c=httpx.Client(base_url='http://127.0.0.1:18130',headers={'Authorization':'Bearer '+dotenv_values(ROOT/'.env')['HANDOVER_ACCESS_TOKEN']},timeout=30)
def get(path,**kw):r=c.get('/api/cases/'+cid+path,**kw);r.raise_for_status();return r.json()
info=get('');rev=get('/revisions/confirmed');assert rev==get('/revisions/confirmed',headers={'X-Role':'successor'})
lookup={}
for doc in info['documents']:
 for block in get('/documents/'+doc['id']+'/blocks'):lookup[block['id']]={**block,'path':doc['path']}
r=build_report(info,rev,lookup.__getitem__)
(OUT/'version-report.html').write_text(render_html(r));(OUT/'version-report.md').write_text(render_markdown(r));(OUT/'version-report.docx').write_bytes(render_docx(r))
(OUT/'report-data.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));(OUT/'source-blocks.json').write_text(json.dumps(lookup,ensure_ascii=False,indent=2))
with sync_playwright() as p:
 b=p.chromium.launch(headless=True,args=['--no-sandbox']);page=b.new_page(viewport={'width':1440,'height':1000});page.goto((OUT/'version-report.html').as_uri());page.evaluate('document.fonts.ready')
 assert page.locator('summary').filter(has_text='최신본 채택·구판 및 초안 제외 근거').count()==4
 assert page.locator('.gantt-svg').count()==1
 page.pdf(path=str(OUT/'version-report.pdf'),format='A4',print_background=True,prefer_css_page_size=True)
 page.screenshot(path=str(OUT/'report-desktop.png'),full_page=True)
 page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1');b.close()
result=json.loads((OUT/'result.json').read_text());result.update(same_report_both_roles=True,mobile_no_page_overflow=True,report_formats=['html','pdf','md','docx'],render_method='current renderer from identical confirmed payload and source blocks; no model calls')
(OUT/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print('Four format reports rendered; version selection visible; no model calls')
