"""Re-render the same confirmed revision without any model call."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
from app.reports import build_report,render_html,render_docx,render_markdown
ROOT=Path(__file__).resolve().parents[1];out=ROOT/'test-results/practice/llm'
revision=json.loads((out/'confirmed.json').read_text());documents=json.loads((out/'sources.json').read_text())
blocks={b['id']:b|{'path':d['path']} for d in documents for b in d['blocks']}
report=build_report({'title':'한빛시 4개 업무 · 인수인계 상세실무편 (합성 시연)','predecessor':'김전임 (가상)','successor':'이후임 (가상)'},revision,lambda bid:blocks[bid])
(out/'report-data.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
(out/'practice-report.html').write_text(render_html(report));(out/'practice-report.md').write_text(render_markdown(report));(out/'practice-report.docx').write_bytes(render_docx(report))
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True,args=['--no-sandbox']);page=browser.new_page(viewport={'width':1440,'height':1100});page.goto((out/'practice-report.html').as_uri());page.pdf(path=str(out/'practice-report.pdf'),format='A4',print_background=True,prefer_css_page_size=True,display_header_footer=True,header_template='<span></span>',footer_template='<div style="font-size:8px;color:#6b7b70;width:100%;text-align:center">업무바통 · 상세실무편　<span class="pageNumber"></span> / <span class="totalPages"></span></div>');page.screenshot(path=str(out/'report-desktop.png'),full_page=True)
 page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1');page.screenshot(path=str(out/'report-mobile.png'));browser.close()
print('Same confirmed report rendered; no model calls')
