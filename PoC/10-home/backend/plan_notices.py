"""Two fixed official notice pilots, preserving source PDFs without inferring units."""
import hashlib
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

SEOUL_PDF = ('https://event.seoul.go.kr/seoulsibo/fileDownload.do'
             '?fileName=2020-%EC%A0%9C3617%ED%98%B8-pdf.pdf')
CONFIG = {
    'seoul_plan_notice_pilot': dict(region='서울특별시', plan_name='공덕1 주택재건축정비구역',
        plan_type='RENEWAL_ZONE', notice_no='서울특별시고시 제2020-418호',
        notice_date='2020-10-22', page_date='2020.10.22',
        page_terms=('공덕1', '제2020-418호'), event_type='CHANGE'),
    'gyeonggi_plan_notice_pilot': dict(region='경기도', plan_name='고양창릉 공공주택지구',
        plan_type='PUBLIC_HOUSING_DISTRICT', notice_no='국토교통부고시 제2024-372호',
        notice_date='2024-07-15', page_date='2024-07-15',
        page_terms=('고양창릉', '제2024-372호'), event_type='CHANGE'),
}


def collect_plan_notice(source, fetcher):
    config = CONFIG[source['id']]
    page = fetcher.get(source['url']).decode('utf-8', 'replace')
    soup = BeautifulSoup(page, 'html.parser')
    visible = soup.get_text(' ', strip=True)
    if not all(term in visible for term in (*config['page_terms'], config['page_date'])):
        raise ValueError('공식 고시 게시 페이지의 제목·번호·날짜 변경')
    if source['id'] == 'seoul_plan_notice_pilot':
        pdf_url = SEOUL_PDF
    else:
        links = [a.get('href') for a in soup.find_all('a')
                 if '고양창릉_공공주택지구_지정_변경(4차)_고시문' in a.get_text(' ', strip=True)]
        if len(links) != 1:
            raise ValueError('국토부 고시 PDF 첨부 링크 미확보')
        pdf_url = urljoin(source['url'], links[0])
        if urlparse(pdf_url).hostname != 'www.molit.go.kr' or '/LCMS/DWN.jsp' not in pdf_url:
            raise ValueError('국토부 고시 PDF 공식 호스트/경로 불일치')
    pdf = fetcher.get(pdf_url, 'pdf')
    if not pdf.startswith(b'%PDF') or len(pdf) < 50000:
        raise ValueError('공식 고시 PDF 원문 확인 실패')
    digest = hashlib.sha256(pdf).hexdigest()
    payload = dict(sample_kind='plan_notice', name=config['plan_name'], region=config['region'],
        address=None, units=None, source_object_id=config['notice_no'],
        plan_name=config['plan_name'], plan_type=config['plan_type'],
        notice_no=config['notice_no'], notice_date=config['notice_date'],
        source_date=config['notice_date'], base_date=config['notice_date'],
        source_date_label='공식 고시 게시일', date_precision='DAY',
        event_type=config['event_type'], original_sha256=digest,
        original_url=pdf_url, evidence_url=source['url'],
        verification_status='SOURCE_FILE_CAPTURED', legal_status='EVIDENCE_REVIEW',
        record_role='LEGAL_NOTICE_EVIDENCE', availability='PUBLIC',
        value_status='NOT_APPLICABLE', stage_label='공식 계획 변경 고시 · 사업 연결 검토 전',
        unit_basis='고시 사건 기록; 주택 공급 호수 아님',
        warnings=['PLAN_PROJECT_LINK_REVIEW'])
    return [('plan_notice', config['notice_no'], payload)], dict(
        provided=1, fetched=1, complete_query=True, complete_population=False,
        notices=[dict(region=config['region'], notice_no=config['notice_no'],
                      notice_date=config['notice_date'], sha256=digest)],
        scope_note='검증된 공식 고시 원문 1건의 게시 페이지·PDF 캡처. 최초 지정부터 현재까지 전수 이력 아님')



def upsert_plan_notice(session, revision, payload):
    """Link a captured official document to a plan event; no project attribution."""
    from .db import Plan, PlanEvent
    raw = '|'.join((payload['region'], payload['plan_type'], payload['plan_name']))
    plan_id = 'PLN_' + hashlib.sha256(raw.encode()).hexdigest()[:24]
    if session.get(Plan, plan_id) is None:
        session.add(Plan(id=plan_id, name=payload['plan_name'], region=payload['region'],
                         plan_type=payload['plan_type'], legal_status='EVIDENCE_REVIEW'))
        session.flush()
    event_key = payload['notice_no'] + ':' + payload['original_sha256']
    event_id = 'PLE_' + hashlib.sha256(event_key.encode()).hexdigest()[:24]
    if session.get(PlanEvent, event_id) is None:
        session.add(PlanEvent(id=event_id, plan_id=plan_id, event_type=payload['event_type'],
            notice_no=payload['notice_no'], notice_date=payload['notice_date'],
            evidence_url=payload['original_url'], evidence_sha256=payload['original_sha256'],
            source_revision_id=revision.id, verification_status='SOURCE_FILE_CAPTURED'))
    return plan_id, event_id
