"""Generated PDF integration tests; no upload or real user book is used."""
import argparse
import json
from playwright.sync_api import sync_playwright, expect
from browser_reader import fixture as epub_fixture


def fixture(pages=5):
    objects = {}
    def obj(number, data): objects[number] = data.encode() if isinstance(data,str) else data
    first_outline = 6 + pages * 2
    image = first_outline + 2
    annotation = image + 1
    korean = annotation + 1
    obj(1, '<< /Type /Catalog /Pages 2 0 R /Outlines 5 0 R >>')
    obj(2, f'<< /Type /Pages /Count {pages} /Kids [' + ' '.join(f'{6+i*2} 0 R' for i in range(pages)) + '] >>')
    obj(3, '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>')
    obj(4, f'<< /Title (PDF Reading Test {pages}) /Author (Bookjari) >>')
    obj(5, f'<< /Type /Outlines /First {first_outline} 0 R /Last {first_outline+1} 0 R /Count 2 >>')
    obj(first_outline, f'<< /Title (Beginning) /Parent 5 0 R /Dest [6 0 R /Fit] /Next {first_outline+1} 0 R >>')
    obj(first_outline+1, f'<< /Title (Ending) /Parent 5 0 R /Dest [{6+(pages-1)*2} 0 R /Fit] /Prev {first_outline} 0 R >>')
    obj(image, b'<< /Type /XObject /Subtype /Image /Width 2 /Height 2 /ColorSpace /DeviceRGB /BitsPerComponent 8 /Length 12 >>\nstream\n' + bytes([30,90,60,200,180,80,90,120,180,220,220,210]) + b'\nendstream')
    obj(annotation, '<< /Type /Annot /Subtype /Link /Rect [10 10 200 100] /A << /S /URI /URI (https://example.invalid/pdf-tracking) >> >>')
    obj(korean, f'<< /Type /Font /Subtype /Type0 /BaseFont /HYSMyeongJo-Medium /Encoding /UniKS-UCS2-H /DescendantFonts [{korean+1} 0 R] >>')
    obj(korean+1, f'<< /Type /Font /Subtype /CIDFontType0 /BaseFont /HYSMyeongJo-Medium /CIDSystemInfo << /Registry (Adobe) /Ordering (Korea1) /Supplement 2 >> /FontDescriptor {korean+2} 0 R /DW 1000 >>')
    obj(korean+2, '<< /Type /FontDescriptor /FontName /HYSMyeongJo-Medium /Flags 6 /FontBBox [-100 -200 1000 900] /Ascent 880 /Descent -120 /CapHeight 700 /StemV 80 >>')
    for i in range(pages):
        landscape = i == 2
        width,height = (792,612) if landscape else (612,792)
        rotation = ' /Rotate 90' if i == 3 else ''
        obj(6+i*2, f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width} {height}] /Resources << /Font << /F1 3 0 R /F2 {korean} 0 R >> /XObject << /Im1 {image} 0 R >> >> /Contents {7+i*2} 0 R{rotation} /Annots [{annotation} 0 R] >>')
        if i == pages - 1 and pages > 1:
            content = b'q 440 0 0 560 80 100 cm /Im1 Do Q'
        else:
            content = (f'0.16 0.36 0.28 rg 36 36 {width-72} {height-72} re f\n1 1 1 rg BT /F1 28 Tf 60 {height-90} Td (PAGE {i+1}) Tj ET\nBT /F1 14 Tf 60 {height-125} Td (Two-page local PDF reading) Tj ET\n').encode()
        if i == 0:
            korean_text = '한글 PDF 읽기'.encode('utf-16-be').hex()
            content += f'BT /F2 22 Tf 60 {height-165} Td <{korean_text}> Tj ET'.encode()
        obj(7+i*2, f'<< /Length {len(content)} >>\nstream\n'.encode()+content+b'\nendstream')
    result=bytearray(b'%PDF-1.7\n%\xe2\xe3\xcf\xd3\n');offsets=[0]
    for i in range(1,max(objects)+1):
        offsets.append(len(result));result.extend(f'{i} 0 obj\n'.encode()+objects[i]+b'\nendobj\n')
    xref=len(result);result.extend(f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode())
    for offset in offsets[1:]:result.extend(f'{offset:010d} 00000 n \n'.encode())
    result.extend(f'trailer\n<< /Size {len(offsets)} /Root 1 0 R /Info 4 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode())
    return bytes(result)


def canvas_pages(page, values):
    expect(page.locator('#pdf-pages canvas')).to_have_count(len(values))
    assert page.locator('#pdf-pages canvas').evaluate_all('(els)=>els.map(e=>Number(e.dataset.pageNumber))') == values
    for canvas in page.locator('#pdf-pages canvas').all():
        # A nonblank render, including a scanned page and rotated pages.
        assert canvas.evaluate('c => {const d=c.getContext("2d").getImageData(Math.floor(c.width/2),Math.floor(c.height/2),1,1).data;return d[3]>0 && (d[0]<245||d[1]<245||d[2]<245)}')


def check(browser, url, mobile):
    context=browser.new_context(viewport={'width':390 if mobile else 1440,'height':844 if mobile else 1000})
    page=context.new_page();errors=[];outside=[]
    page.on('pageerror',lambda e: errors.append(str(e)))
    page.on('request',lambda r: outside.append(r.url) if 'example.invalid' in r.url else None)
    page.goto(url);expect(page.locator('#empty')).to_be_visible()
    file={'name':'reading.pdf','mimeType':'application/pdf','buffer':fixture()}
    page.locator('#file-input').set_input_files(file)
    expect(page.locator('#reader')).to_be_visible(timeout=20000)
    expect(page.locator('#add-bookmark')).to_be_enabled(timeout=20000)
    expect(page.locator('#reader-title')).to_have_text('PDF Reading Test 5')
    expect(page.locator('#font-plus')).to_be_hidden();expect(page.locator('#pdf-zoom')).to_be_visible()
    canvas_pages(page,[1,2])
    expect(page.locator('#pdf-pages .sr-only').first).to_contain_text('한글 PDF 읽기')
    expect(page.locator('#prev-page')).to_be_disabled()
    page.locator('#next-page').click();expect(page.locator('#add-bookmark')).to_be_enabled();canvas_pages(page,[3,4])
    page.locator('#add-bookmark').click();expect(page.locator('#status')).to_have_text('책갈피를 저장했습니다.')
    page.locator('#add-bookmark').click();expect(page.locator('#mark-count')).to_have_text('1')
    page.reload();expect(page.locator('#add-bookmark')).to_be_enabled(timeout=20000);canvas_pages(page,[3,4])
    page.locator('#next-page').click();expect(page.locator('#add-bookmark')).to_be_enabled();canvas_pages(page,[5])
    expect(page.locator('#pdf-pages .pdf-blank')).to_have_count(1);expect(page.locator('#next-page')).to_be_disabled()
    page.locator('#toggle-sidebar').click();page.locator('#marks-tab').click();page.locator('.bookmark-go').click()
    expect(page.locator('#add-bookmark')).to_be_enabled();canvas_pages(page,[3,4])
    page.locator('#page-layout').select_option('1');expect(page.locator('#add-bookmark')).to_be_enabled();canvas_pages(page,[3])
    page.locator('#pdf-page-input').fill('4');page.locator('#pdf-page-input').press('Enter')
    expect(page.locator('#add-bookmark')).to_be_enabled();canvas_pages(page,[4])
    page.locator('#page-layout').select_option('2');expect(page.locator('#add-bookmark')).to_be_enabled();canvas_pages(page,[3,4])
    expect(page.locator('#pdf-page-input')).to_have_value('4')
    page.locator('#pdf-zoom').select_option('1.5');expect(page.locator('#add-bookmark')).to_be_enabled()
    assert page.locator('#pdf-pages').evaluate('e=>e.scrollWidth>e.clientWidth')
    page.locator('#theme').select_option('dark');expect(page.locator('#add-bookmark')).to_be_enabled();canvas_pages(page,[3,4])
    page.locator('#pdf-zoom').select_option('1');expect(page.locator('#add-bookmark')).to_be_enabled()
    page.locator('#toggle-sidebar').click();page.locator('#toc-tab').click();expect(page.locator('.toc-item')).to_have_count(2)
    page.locator('.toc-item').last.click();expect(page.locator('#add-bookmark')).to_be_enabled();canvas_pages(page,[5])
    original_viewport=page.viewport_size
    page.set_viewport_size({'width':820,'height':700});page.wait_for_timeout(400);canvas_pages(page,[5])
    page.set_viewport_size(original_viewport);page.wait_for_timeout(400);canvas_pages(page,[5])
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
    assert page.locator('#pdf-pages').bounding_box()['height'] >= page.viewport_size['height']-82
    page.screenshot(path=f'/tmp/poc12-pdf-{"mobile" if mobile else "desktop"}.png')
    page.locator('#back-library').click();expect(page.locator('#library')).to_be_visible();expect(page.locator('#import-top')).to_be_enabled()
    expect(page.locator('.book-card')).to_have_count(1);expect(page.locator('.book-cover img')).to_have_count(1)
    page.locator('#file-input').set_input_files({**file,'name':'renamed.pdf'})
    expect(page.locator('#reader')).to_be_visible();expect(page.locator('#add-bookmark')).to_be_enabled();canvas_pages(page,[5])
    page.locator('#back-library').click();expect(page.locator('#import-top')).to_be_enabled()
    page.locator('#file-input').set_input_files({'name':'broken.pdf','mimeType':'application/pdf','buffer':b'bad-pdf'})
    expect(page.locator('#status')).to_contain_text('유효한 PDF')
    expect(page.locator('.book-card')).to_have_count(1)
    # Mix formats in the same library and verify switching back doesn't leak PDF state.
    page.locator('#file-input').set_input_files({'name':'epub.epub','mimeType':'application/epub+zip','buffer':epub_fixture()})
    expect(page.locator('#add-bookmark')).to_be_enabled();expect(page.locator('#book-frame')).to_be_visible();expect(page.locator('#pdf-pages')).to_be_hidden()
    expect(page.frame_locator('#book-frame').locator('h1')).to_have_text('1장 산책')
    page.locator('#back-library').click();expect(page.locator('#import-top')).to_be_enabled();expect(page.locator('.book-card')).to_have_count(2)
    page.get_by_role('button',name='PDF Reading Test 5 이어 읽기',exact=True).click()
    expect(page.locator('#add-bookmark')).to_be_enabled();canvas_pages(page,[5]);expect(page.locator('#mark-count')).to_have_text('1')
    page.locator('#toggle-sidebar').click();page.locator('#marks-tab').click();page.locator('.bookmark-delete').click()
    expect(page.locator('#mark-count')).to_have_text('0')
    page.locator('#back-library').click();expect(page.locator('#import-top')).to_be_enabled()
    page.get_by_role('button',name='PDF Reading Test 5 삭제',exact=True).click();page.locator('#delete-confirm').click();expect(page.locator('.book-card')).to_have_count(1)
    page.locator('#file-input').set_input_files({'name':'one.pdf','mimeType':'application/pdf','buffer':fixture(1)})
    expect(page.locator('#reader')).to_be_visible();expect(page.locator('#add-bookmark')).to_be_enabled();canvas_pages(page,[1])
    expect(page.locator('#prev-page')).to_be_disabled();expect(page.locator('#next-page')).to_be_disabled()
    assert not errors,errors
    assert not outside,outside
    context.close()
    return {'mobile':mobile,'pdf_render_and_scan':True,'two_page_and_single_page':True,'bookmark_reload':True,'zoom_resize_theme':True,'outline_and_page_jump':True,'odd_last_and_one_page':True,'mixed_library':True,'duplicate_and_delete':True,'invalid_file':True,'page_errors':errors,'external_requests':outside}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--url',default='http://127.0.0.1:18122/');args=parser.parse_args()
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path='/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome',args=['--no-sandbox'])
        results=[check(browser,args.url,mobile) for mobile in [False,True]]
        browser.close();print(json.dumps(results,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
