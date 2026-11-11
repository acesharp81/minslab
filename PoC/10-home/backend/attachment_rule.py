"""Execute a reviewed PDF-link selector; URLs must come from the source HTML."""
import re
from urllib.parse import urljoin, urlsplit
from bs4 import BeautifulSoup
from .ai_collection_fetch import canonical
from .source_authority import authority
from .publication_capture import pdf_text


def extract_attachment(raw, url, selector, fetcher):
    from .algorithm_review import selector_ok
    selector_ok(selector)
    if authority(url) != 'OFFICIAL':
        raise ValueError('첨부 규칙은 공식 원문에만 적용할 수 있습니다')
    soup = BeautifulSoup(raw, 'html.parser')
    nodes = soup.select(selector)
    if len(nodes) != 1 or nodes[0].name != 'a' or not nodes[0].get('href'):
        raise ValueError('PDF 다운로드 링크를 정확히 1개 선택해야 합니다')
    node = nodes[0]
    label = ' '.join([node.get('title', ''), node.get_text(' ', strip=True), node['href']])
    if '.pdf' not in label.lower() or re.search(r'당첨자|계약대상자|명단|선정결과', label):
        raise ValueError('공개 PDF 본문 링크만 허용합니다. 개인별 명단은 수집하지 않습니다')
    target = canonical(urljoin(url, node['href']))
    if urlsplit(target).netloc != urlsplit(canonical(url)).netloc:
        raise ValueError('원문과 같은 호스트의 첨부만 허용합니다')
    landing = dict(fetcher.last)
    raw_pdf = fetcher.get(target, allow_pdf=True)
    if authority(fetcher.last.get('url', '')) != 'OFFICIAL':
        raise ValueError('첨부 최종 출처가 공식 출처가 아닙니다')
    if not raw_pdf.startswith(b'%PDF'):
        raise ValueError('선택한 첨부가 PDF가 아닙니다')
    detail = pdf_text(fetcher.folder / (fetcher.last['sha256'] + '.raw'))
    if detail['truncated'] or len(detail['text'].strip()) < 60:
        raise ValueError('완전한 PDF 본문 미확보')
    meta = dict(fetcher.last, landing_page=landing, body_source='APPROVED_PDF_ATTACHMENT',
                selector=selector, pages=detail['pages'])
    fetcher.last = meta
    title = soup.title.get_text(' ', strip=True)[:500] if soup.title else ''
    return (title, detail['text'], False), meta
