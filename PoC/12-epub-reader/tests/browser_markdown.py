"""Generated Markdown books in isolated Chromium storage; desktop and mobile."""
import argparse
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
from browser_reader import assert_bookmark_visible, fixture as epub_fixture


def fixture():
    intro = '''---
title: "작은 문장의 숲"
author: 책자리 편집실
---
# 작은 문장의 숲

**천천히 읽는 시간**과 *생각의 여백*, ~~지워진 문장~~을 담았습니다.

[다음 장으로](#두-번째-산책)

> 문장은 오래 머무를수록 깊어집니다.

- 첫 번째 생각
- 두 번째 생각

1. 책을 펼치기
2. 마음에 드는 문장 찾기

- [x] 읽은 문장
- [ ] 남겨둔 문장

| 항목 | 기록 |
| :--- | ---: |
| 오늘의 문장 | 한 페이지의 여유 |
| 읽은 시간 | 30분 |

`inline_code`와 코드 예제입니다.

```python
# 코드 안 제목은 목차가 아닙니다
print("<script>실행되지 않는 텍스트</script>")
```

![숲의 이미지](https://example.invalid/image.png)
![로컬 이미지](./forest.png)
<script>parent.__mdAttack = true</script>
<img src="https://example.invalid/attack" onerror="parent.__mdAttack=true">
<iframe src="https://example.invalid/frame"></iframe>
<style>body {background:url(https://example.invalid/css)}</style>
<a href="javascript:parent.__mdAttack=true">위험한 링크</a>
<details><summary>접힌 메모</summary>숨겨지지 않는 본문</details>
<div id="reader-flow" data-book-path="attack" style="position:fixed" onclick="parent.__mdAttack=true">안전한 본문</div>

'''
    paragraphs = '\n\n'.join(f'문단 {i}. '+ '바람이 부는 오후에 책장을 넘깁니다. 마음에 남은 문장을 천천히 따라가며 오늘의 생각을 기록합니다. '*5 for i in range(45))
    return (intro + paragraphs + '\n\n## 두 번째 산책\n\n다음 장의 첫 문장입니다.\n\n### 깊은 생각\n\n목차로 이동하는 작은 제목입니다.\n\n### 깊은 생각\n\n같은 이름도 서로 다른 위치입니다.\n').encode()


def check(page, url, mobile):
    errors, external = [], []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.on('request', lambda r: external.append(r.url) if 'example.invalid' in r.url else None)
    page.goto(url)
    assert '.md' in page.locator('#file-input').get_attribute('accept')
    book = {'name':'산책.MD','mimeType':'text/markdown','buffer':fixture()}
    page.locator('#file-input').set_input_files(book)
    frame = page.frame_locator('#book-frame')
    expect(page.locator('#reader-title')).to_have_text('작은 문장의 숲')
    expect(page.locator('#reader-author')).to_have_text('책자리 편집실')
    expect(page.locator('#save-status')).to_have_text('이 브라우저에 읽던 위치 저장됨')
    expect(page.locator('#book-frame')).to_have_attribute('data-columns','2')
    expect(frame.locator('strong').first).to_have_text('천천히 읽는 시간')
    assert frame.locator('details,summary').count() == 0
    expect(frame.locator('body')).to_contain_text('숨겨지지 않는 본문')
    expect(frame.locator('table')).to_have_count(1)
    expect(frame.locator('pre code')).to_contain_text('# 코드 안 제목')
    expect(frame.locator('.md-check')).to_have_count(2)
    expect(frame.locator('.md-image')).to_have_count(3)
    assert frame.locator('script,iframe,img,input,[onclick],#reader-flow [style],style:not(#reader-style)').count() == 0
    assert frame.locator('#reader-flow').count() == 1
    assert page.evaluate('window.__mdAttack') is None
    assert not external, external
    assert page.locator('#toc-panel .toc-item').count() == 4
    assert int(page.locator('#book-frame').get_attribute('data-pages')) > 4
    assert page.locator('.reader-toolbar').bounding_box()['height'] <= 49
    Path('/tmp/bookjari-md').mkdir(exist_ok=True)
    page.screenshot(path=f'/tmp/bookjari-md/{"mobile" if mobile else "desktop"}.png')
    # Follow an anchor into a different chapter, then the duplicate heading's unique ID.
    frame.locator('a[data-book-path]').evaluate('(a) => a.click()')
    expect(frame.locator('h2')).to_have_text('두 번째 산책')
    expect(page.locator('#add-bookmark')).to_be_enabled()
    expect(frame.locator('#깊은-생각-1')).to_have_text('깊은 생각')
    page.locator('#toggle-sidebar').click(); page.locator('.toc-item').first.click()
    expect(frame.locator('h1')).to_have_text('작은 문장의 숲')
    expect(page.locator('#next-page')).to_be_enabled()
    page.locator('#next-page').click()
    expect(page.locator('#book-frame')).to_have_attribute('data-page','3')
    page.locator('#next-page').click()
    expect(page.locator('#book-frame')).to_have_attribute('data-page','5')
    page.locator('#add-bookmark').click()
    expect(page.locator('#status')).to_have_text('책갈피를 저장했습니다.')
    page.reload()
    expect(page.locator('#save-status')).to_have_text('이 브라우저에 읽던 위치 저장됨')
    expect(page.locator('#book-frame')).to_have_attribute('data-page','5')
    assert_bookmark_visible(page)
    page.locator('#font-plus').click(); expect(page.locator('#font-size')).to_have_text('20')
    assert_bookmark_visible(page)
    page.locator('#page-layout').select_option('1')
    expect(page.locator('#book-frame')).to_have_attribute('data-columns','1')
    assert_bookmark_visible(page)
    page.locator('#theme').select_option('dark')
    assert frame.locator('body').evaluate('(e)=>getComputedStyle(e).backgroundColor') == 'rgb(36, 44, 38)'
    page.locator('#back-library').click()
    expect(page.locator('#import-top')).to_be_enabled()
    expect(page.locator('.book-actions small')).to_contain_text('Markdown')
    # Duplicates retain the original bookmark and automatically reopen.
    page.locator('#file-input').set_input_files({**book,'name':'복사.markdown'})
    expect(page.locator('#reader')).to_be_visible()
    expect(page.locator('#mark-count')).to_have_text('1')
    expect(page.locator('#back-library')).to_be_enabled()
    page.locator('#back-library').click()
    expect(page.locator('#import-top')).to_be_enabled()
    expect(page.locator('#book-count')).to_have_text('1')
    for name, data, message in [('빈.md',b'', '본문이 있는'),('바이너리.md',b'\xff\x00', 'UTF-8'),('내용없음.md',b'---\ntitle: Empty\n---\n', '본문'),('큰.md',b'x'*(5*1024*1024+1),'5 MB')]:
        page.locator('#file-input').set_input_files({'name':name,'mimeType':'text/markdown','buffer':data})
        expect(page.locator('#status')).to_contain_text(message)
        expect(page.locator('#book-count')).to_have_text('1')
    # Setext heading and no-heading documents, plus an EPUB in the same library.
    page.locator('#file-input').set_input_files([
        {'name':'제목.markdown','mimeType':'text/markdown','buffer':'밑줄 제목\n==========\n\n본문입니다.'.encode()},
        {'name':'메모.md','mimeType':'text/markdown','buffer':'제목 없이도 책으로 읽습니다.'.encode()},
        {'name':'산책.epub','mimeType':'application/epub+zip','buffer':epub_fixture()},
    ])
    expect(page.locator('#book-count')).to_have_text('4')
    page.reload(); expect(page.locator('#book-count')).to_have_text('4')
    assert not errors, errors
    assert not external, external
    print('PASS Markdown', 'mobile' if mobile else 'desktop', flush=True)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--url',default='http://127.0.0.1:18122/'); args=parser.parse_args()
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path='/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome',args=['--no-sandbox'])
        for mobile in (False,True):
            context=browser.new_context(viewport={'width':390 if mobile else 1440,'height':844 if mobile else 1000},is_mobile=mobile,has_touch=mobile)
            check(context.new_page(),args.url,mobile);context.close()
        browser.close()
