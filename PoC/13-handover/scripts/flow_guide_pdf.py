"""Print the same downloadable Markdown guide to a readable standalone PDF."""
import html
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1];out=ROOT/'release/public'
parts=[];in_table=False
for line in (out/'handover-guide.md').read_text().splitlines():
 if line.startswith('|'):
  if '|---' in line:continue
  if not in_table:parts.append('<table>');in_table=True
  parts.append('<tr>'+''.join('<td>'+html.escape(c.strip())+'</td>' for c in line.strip('|').split('|'))+'</tr>');continue
 if in_table:parts.append('</table>');in_table=False
 if line.startswith('# '):parts.append('<h1>'+html.escape(line[2:])+'</h1>')
 elif line.startswith('## '):parts.append('<h2>'+html.escape(line[3:])+'</h2>')
 elif line:parts.append('<p>'+html.escape(line)+'</p>')
page='<!doctype html><html lang="ko"><meta charset="utf-8"><style>body{font:12px/1.85 sans-serif;color:#234334}h1{font-size:29px}h2{font-size:19px;margin-top:25px;break-after:avoid}p{break-inside:avoid}table{border-collapse:collapse;font-size:11px;width:100%}td{border:1px solid #d8e2d5;padding:7px}tr{break-inside:avoid}tr:first-child{background:#edf4e8;font-weight:bold}</style><body>'+''.join(parts)+'</body></html>'
(out/'handover-guide.html').write_text(page)
with sync_playwright() as p:
 b=p.chromium.launch(headless=True,args=['--no-sandbox']);tab=b.new_page();tab.set_content(page);tab.pdf(path=str(out/'handover-guide.pdf'),format='A4',print_background=True,margin={'top':'15mm','bottom':'15mm','left':'16mm','right':'16mm'});b.close()
print('Guide PDF created')
