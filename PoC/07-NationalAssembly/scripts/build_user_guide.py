#!/usr/bin/env python3
"""Build the static user guide from reviewed copy and captured real UI images."""
from html import escape
import json
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
TARGET = PROJECT / 'web/user-guide'


def main() -> None:
    content = json.loads((PROJECT / 'docs/user_guide_content.json').read_text())
    pages = content['pages']
    count = len(pages)
    head = '''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>국정ON 사용자 매뉴얼</title><link rel="stylesheet" href="guide.css?v=20261020-quick-sheet-1"><script src="guide.js?v=20261020-4" defer></script></head><body><header class="guide-toolbar"><a class="guide-brand" href="../../">국정ON <span>사용자 매뉴얼</span></a><nav aria-label="매뉴얼 도구"><a href="gukjeongon-user-guide.pdf" download>PDF 다운로드</a><button id="guidePrint" type="button">인쇄</button><a href="../../">서비스로 돌아가기</a></nav></header><div class="guide-layout"><aside class="guide-toc"><h2>차례</h2><button type="button" id="guideTocToggle" aria-expanded="false" aria-controls="guideTocList">목차 보기 ▾</button><p>1쪽부터 따라 하거나 필요한 기능을 선택하세요.</p><ol id="guideTocList">'''
    head = head.replace('href="gukjeongon-user-guide.pdf"', 'href="gukjeongon-user-guide.pdf?v=' + content.get('asset_version', content['updated_at']) + '"')
    head += ''.join(f'<li><a href="#page-{i}" data-page-link="{i}">{escape(p["title"])}</a></li>' for i, p in enumerate(pages, 1))
    head += f'</ol><small>화면 촬영·갱신: {escape(content["updated_at"])}<br>실제 운영 화면 기준</small></aside><main id="guideMain">'
    body = []
    for i, page in enumerate(pages, 1):
        image = 'screens/' + page['image'] + '?v=' + content.get('asset_version', content['updated_at'])
        classes = 'guide-page' + (' is-start' if i == 1 else ' is-detailed') + (' has-reference' if page.get('reference') else '')
        text = f'<section class="{classes}" id="page-{i}" data-page="{i}" aria-labelledby="title-{i}"' + (' hidden' if i != 1 else '') + '>'
        text += f'<header><span class="page-label">국정ON 사용 안내 · {i:02d} / {count:02d}</span><h1 id="title-{i}">{escape(page["title"])}</h1><p class="subtitle">{escape(page["subtitle"])}</p></header>'
        text += f'<figure><a href="{escape(image)}" target="_blank" rel="noopener" aria-label="{escape(page["alt"])} 크게 보기"><img src="{escape(image)}" alt="{escape(page["alt"])}" width="1440" height="1000"></a><figcaption>{escape(page["alt"])} · 화면을 누르면 크게 볼 수 있습니다.</figcaption></figure>'
        if page.get('menu_cards'):
            text += '<div class="quick-menu-grid">'
            for number, card in enumerate(page['menu_cards'], 1):
                text += f'<section class="quick-menu-card" aria-labelledby="quick-menu-{number}"><header><span>{number}</span><h2 id="quick-menu-{number}">{escape(card["menu"])}</h2></header><p class="quick-menu-purpose">{escape(card["purpose"])}</p><ol>'
                text += ''.join(f'<li><strong>{escape(action["label"])}</strong><p>{escape(action["text"])}</p></li>' for action in card['actions'])
                text += f'</ol><p class="quick-menu-result"><strong>확인할 결과</strong> {escape(card["result"])}</p><a class="quick-menu-detail" href="#page-{card["detail_page"]}">{escape(card["detail_label"])} →</a></section>'
            text += '</div>'
        else:
            text += '<ol class="guide-steps">' + ''.join(f'<li><strong>{escape(step["title"])}</strong><p>{escape(step["text"])}</p></li>' for step in page['steps']) + '</ol>'
        if page.get('reference'):
            text += '<table class="guide-reference"><thead><tr><th>항목·상태</th><th>뜻과 사용 방법</th></tr></thead><tbody>'
            text += ''.join(f'<tr><th>{escape(row["label"])}</th><td>{escape(row["meaning"])}</td></tr>' for row in page['reference']) + '</tbody></table>'
        text += f'<aside class="guide-tip">{escape(page["tip"])}</aside><footer>국정ON · 처음 사용자를 위한 실제 화면 매뉴얼 <span>{i} / {count}</span></footer></section>'
        body.append(text)
    foot = f'<nav class="guide-pager" aria-label="페이지 이동"><button id="guidePrev" type="button">← 이전 페이지</button><span id="guidePageStatus" aria-live="polite">1 / {count}</span><button id="guideNext" type="button">다음 페이지 →</button></nav></main></div></body></html>'
    TARGET.mkdir(exist_ok=True, parents=True)
    image_dialog = '<dialog id="guideImageDialog" aria-label="화면 크게 보기"><header><strong>실제 화면 크게 보기</strong><button id="guideImageClose" type="button" autofocus>닫기 ×</button></header><div><img id="guideFullImage" alt=""></div></dialog>'
    foot = foot.replace('</body>', image_dialog + '</body>')
    (TARGET / 'index.html').write_text(head + ''.join(body) + foot)
    print(f'Built {count} guide pages')


if __name__ == '__main__':
    main()
