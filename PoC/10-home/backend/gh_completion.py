"""Archive GH use-inspection/approval evidence without inferring occupied units."""

import hashlib
import io
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from pypdf import PdfReader

from .collectors import clean


COMPLETE_WORDS = ('사용검사 확인증', '사용승인필증')
PROVISIONAL_WORDS = ('임시사용승인', '준공인가전 사용허가')
DATE = re.compile(r'(20\d{2})년\s*(\d{1,2})월\s*(\d{1,2})일')


def evidence_type(title):
    compact = re.sub(r'\s+', '', title)
    if any(re.sub(r'\s+', '', word) in compact for word in PROVISIONAL_WORDS):
        return 'PROVISIONAL_EXTENSION' if '연장' in compact else 'PROVISIONAL'
    if any(re.sub(r'\s+', '', word) in compact for word in COMPLETE_WORDS):
        return 'USE_APPROVAL_CANDIDATE'
    return None


def parse_list(content, source):
    soup = BeautifulSoup(content, 'html.parser')
    summary = clean(soup.get_text(' ', strip=True))
    count = re.search(r'총게시물\s*:\s*(\d+)\s*페이지\s*:\s*(\d+)\s*/\s*(\d+)', summary)
    if not count or int(count[2]) != 1 or int(count[3]) != 1:
        raise ValueError('GH 입주안내 페이지 구조·페이지 수 변경: 기존 정상 자료 유지')
    rows = []
    for anchor in soup.select('a[data-sn]'):
        tr = anchor.find_parent('tr')
        columns = tr.find_all('td', recursive=False) if tr else []
        sn = anchor.get('data-sn', '')
        if len(columns) != 8 or not sn.isdigit():
            raise ValueError('GH 입주안내 목록 열·식별자 변경')
        title = clean(anchor.get_text(' ', strip=True))
        published_at = clean(columns[6].get_text(' ', strip=True))
        if not re.fullmatch(r'20\d{2}-\d{2}-\d{2}', published_at):
            raise ValueError('GH 입주안내 게시일 형식 변경')
        rows.append(dict(source_object_id=sn, name=title, municipality=clean(columns[1].get_text()),
                         housing_type=clean(columns[2].get_text()), source_date=published_at,
                         evidence_type=evidence_type(title),
                         evidence_url=urljoin(source['url'], f'selectNoticeDetailView.do?bbsSn={sn}')))
    if len(rows) != int(count[1]) or len({r['source_object_id'] for r in rows}) != len(rows):
        raise ValueError('GH 입주안내 목록 건수·중복 불일치')
    return rows


def pdf_facts(content, evidence_type_value):
    if not content.startswith(b'%PDF'):
        raise ValueError('GH 사용검사 첨부가 PDF가 아님')
    try:
        reader = PdfReader(io.BytesIO(content))
        text = clean(' '.join(page.extract_text() or '' for page in reader.pages))
    except Exception as error:
        raise ValueError('GH 사용검사 PDF 열기 실패') from error
    result = dict(pdf_sha256=hashlib.sha256(content).hexdigest(), pdf_pages=len(reader.pages),
                  pdf_text_extracted=bool(text), approval_date=None, permit_no=None, site_location=None)
    if evidence_type_value != 'USE_APPROVAL_CANDIDATE' or not text:
        return result
    # A date is recognized only on a certificate itself, never from its website posting date.
    marker = re.search(r'(?:사용검사\s*확인증|사용승인서)\s*(20\d{2}년\s*\d{1,2}월\s*\d{1,2}일)', text)
    stamp = DATE.fullmatch(marker[1]) if marker else None
    if stamp is None:
        dates = list(DATE.finditer(text))
        stamp = dates[0] if len(dates) == 1 else None
    if stamp:
        result['approval_date'] = f'{int(stamp[1]):04d}-{int(stamp[2]):02d}-{int(stamp[3]):02d}'
    permit = re.search(r'(?:허가\(신고\)번호|사업계획승인번호)\s*((?:20\d{2})-[^\s]{5,90})', text)
    if permit:
        result['permit_no'] = permit[1]
    location = re.search(r'대\s*지\s*위\s*치\s*((?:경기도|서울특별시)\s*[^\s]+(?:\s+[^\s]+){0,2})', text)
    if location:
        result['site_location'] = location[1]
    return result


def collect_gh_completion(source, fetcher):
    rows = parse_list(fetcher.get(source['url']), source)
    records = []
    for row in rows:
        if not row['evidence_type']:
            continue
        detail = BeautifulSoup(fetcher.get(row['evidence_url']), 'html.parser')
        attachments = detail.select('a[href*="selectFileDown.do"]')
        if len(attachments) != 1:
            raise ValueError('GH 사용검사 상세 첨부 수 변경')
        pdf_url = urljoin(source['url'], attachments[0]['href'])
        facts = pdf_facts(fetcher.get(pdf_url, 'pdf'), row['evidence_type'])
        payload = dict(row, sample_kind='gh_completion_evidence', region='경기도',
            source_id=source['id'], source_date_label='GH 입주안내 게시일 · 승인일 아님',
            base_date=row['source_date'], base_date_basis='원문 게시일', original_url=pdf_url,
            original_sha256=facts['pdf_sha256'], **facts,
            approval_scope='원문상 건물·공구 범위 검토 필요', project_link_status='REVIEW',
            actual_occupied_units=None, units=None,
            record_role='COMPLETION_EVIDENCE_REVIEW',
            warnings=['NO_AUTOMATIC_PROJECT_LINK', 'NOT_OCCUPANCY_ACTUAL'] +
                (['PROVISIONAL_NOT_FINAL_COMPLETION'] if row['evidence_type'].startswith('PROVISIONAL') else []) +
                (['SCANNED_PDF_TEXT_UNAVAILABLE'] if not facts['pdf_text_extracted'] else []))
        records.append(('gh_completion_evidence', row['source_object_id'], payload))
    if not records:
        raise ValueError('GH 입주안내에서 사용검사·승인 자료 미확인')
    return records, dict(complete_query=True, complete_population=False, provided=len(rows),
        fetched=len(rows), collected=len(records), document_count=len(records),
        full_use_approval_candidates=sum(r[2]['evidence_type']=='USE_APPROVAL_CANDIDATE' for r in records),
        provisional_count=sum(r[2]['evidence_type'].startswith('PROVISIONAL') for r in records),
        text_extractable_count=sum(r[2]['pdf_text_extracted'] for r in records),
        scope_note='GH 입주안내 게시물 전체 목록 중 사용검사·사용승인·임시허가 문서. 건물/공구 범위·사업 연결 검토 필요; 실제 입주 호수 아님')
