"""Publish already verified example files and assemble the complete download kit."""
import json,shutil,zipfile
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1];src=ROOT/'test-results/comprehensive/verified';out=ROOT/'release/public'
for ext in ['html','md','docx']:shutil.copyfile(src/f'comprehensive-report.{ext}',out/f'comprehensive-report.{ext}')
shutil.copyfile(src/'validation.json',out/'comprehensive-validation.json')
with sync_playwright() as pw:
 b=pw.chromium.launch(headless=True,args=['--no-sandbox']);p=b.new_page(viewport={'width':1500,'height':1000});p.goto((out/'comprehensive-report.html').as_uri());p.evaluate('document.fonts.ready');p.pdf(path=str(out/'comprehensive-report.pdf'),format='A4',print_background=True);p.screenshot(path=str(src/'report-desktop.png'));p.set_viewport_size({'width':390,'height':844});p.screenshot(path=str(src/'report-mobile.png'));b.close()
names=['comprehensive-base.zip','comprehensive-current.zip','comprehensive-old.zip','comprehensive-draft.zip','comprehensive-expected.json','comprehensive-validation.json']+[f'comprehensive-report.{ext}' for ext in ['html','pdf','docx','md']]
with zipfile.ZipFile(out/'comprehensive-kit.zip','w',zipfile.ZIP_DEFLATED) as z:
 for name in names:z.write(out/name,name)
 z.writestr('시작하기.md',(out/'comprehensive-guide.md').read_bytes())
print('Published integrated sample, verified report, guide and validation; no model calls.')
