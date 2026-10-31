"""Run with Playwright Python installed: browser_shell_smoke.py --html rendered.html.

Executes the real inline browser code with isolated API responses; no provider calls
or production data writes. --url checks a deployed shell with the same API fixtures.
"""
import argparse,json
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect

def check(page,html=None,url='https://www.minslab.kr/'):
    errors=[];seen=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    def serve(route):
        path=urlparse(route.request.url).path
        if route.request.url.split('#')[0]==url and html is not None:
            route.fulfill(content_type='text/html',body=html)
        elif path=='/api/models':
            route.fulfill(json={'models':[{'name':'smoke-model','label':'Smoke Model','provider':'upstage'}],'default':'smoke-model'})
        elif path=='/api/health':
            route.fulfill(json={'ok':True,'services':{},'stats':{}})
        elif path=='/api/history':
            route.fulfill(json={'saved':True,'items':[],'storage':'local'})
        elif path=='/api/chat':
            seen.append(route.request.post_data_json)
            route.fulfill(content_type='application/x-ndjson',body=json.dumps({'type':'token','content':'검증 응답입니다.'},ensure_ascii=False)+'\n'+json.dumps({'type':'done','metrics':{}})+'\n')
        elif path.startswith('/api/'):
            route.fulfill(json={})
        elif route.request.is_navigation_request() and route.request.frame!=page.main_frame:
            route.fulfill(content_type='text/html',body='<!doctype html><title>Isolated service frame</title>')
        elif urlparse(route.request.url).hostname not in {'www.minslab.kr','127.0.0.1','localhost'}:
            route.fulfill(body='',content_type='text/javascript' if route.request.resource_type=='script' else 'text/css')
        else:route.continue_()
    page.route('**/*',serve)
    page.goto(url,wait_until='domcontentloaded')
    expect(page.locator('#modelSelect')).to_have_value('smoke-model')
    expect(page.locator('#healthLabel')).to_have_text('서버 정상')
    assert page.evaluate('typeof document.querySelector("#chatForm").onsubmit')=='function'
    page.locator('#chatInput').fill('초기화 회귀 검증')
    page.locator('#chatInput').press('Enter')
    expect(page.locator('.message.assistant .message-body')).to_have_text('검증 응답입니다.')
    assert seen and seen[0]['messages'][-1]['content']=='초기화 회귀 검증'
    expect(page.locator('#sendButton')).to_be_enabled()
    for menu in ['portfolio','poc','presentations','home']:
        page.locator(f'.site-nav [data-page="{menu}"]').click()
        expect(page.locator(f'.site-nav [data-page="{menu}"]')).to_have_class('active')
    assert errors==[],errors
    return {'chat_submit_and_stream':True,'navigation':['portfolio','poc','presentations','home'],'page_errors':errors}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--html',type=Path);parser.add_argument('--url',default='https://www.minslab.kr/');args=parser.parse_args()
    with sync_playwright() as p:
        options={'headless':True,'args':['--no-sandbox']}
        installed=list(Path('/home/ubuntu/.cache/ms-playwright/chromium-1248').glob('chrome-linux*/chrome'))
        if installed:options['executable_path']=str(installed[0])
        with p.chromium.launch(**options) as browser:
            for viewport in [{'width':1440,'height':1000},{'width':390,'height':844}]:
                page=browser.new_page(viewport=viewport)
                print(json.dumps({'viewport':viewport,**check(page,args.html.read_text() if args.html else None,args.url)},ensure_ascii=False));page.close()

if __name__=='__main__':main()
