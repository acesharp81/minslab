"""Recurring publisher lists/RSS, retained as review candidates, never stage facts."""
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from html import unescape
import re
from urllib.parse import urljoin, urlsplit, parse_qs, urlencode
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup
from .api_samples import today
from .collectors import clean
from .source_authority import authority

KST = ZoneInfo('Asia/Seoul')
KEYWORDS = ('주택','분양','임대','착공','준공','입주','재개발','재건축','모아타운','모아주택','신도시','택지','주거','도심복합','공공복합')

def housing_title(title):
    # Agency name alone must not make an unrelated LH news item a housing item.
    value=re.sub(r'한국토지주택공사\s*\(LH\)|한국토지주택공사|경기주택도시공사|인천도시공사','',title)
    return any(word in value for word in KEYWORDS)

def stamp(raw):
    value=clean(raw)
    try:
        dt=datetime.fromisoformat(value)
    except ValueError:
        dt=parsedate_to_datetime(value)
    if dt.tzinfo is None:dt=dt.replace(tzinfo=KST)
    return dt.astimezone(KST).isoformat()

def rss_rows(body, source):
    if len(body)>5_000_000 or b'<!DOCTYPE' in body.upper() or b'<!ENTITY' in body.upper():
        raise ValueError('RSS 크기·외부 정의 검증 실패')
    root=ET.fromstring(body);items=root.findall('./channel/item')
    if root.tag!='rss' or root.find('channel') is None:raise ValueError('RSS 응답 구조 변경')
    rows=[]
    for item in items:
        title=clean(unescape(item.findtext('title') or ''));url=clean(item.findtext('link') or '')
        host=urlsplit(url).hostname or ''
        if urlsplit(url).scheme not in ('https','http') or not any(host==h or host.endswith('.'+h) for h in source['publisher_hosts']):
            raise ValueError('RSS 기사 출처 호스트 변경')
        try:published=stamp(item.findtext('pubDate') or '')
        except (ValueError,TypeError,OverflowError):raise ValueError('RSS 게시시각 미확보') from None
        if not title:raise ValueError('RSS 기사 제목 미확보')
        rows.append(dict(source_object_id=url,name=title,evidence_url=url,source_date=published[:10],published_at=published))
    return rows

def board_rows(body, source):
    soup=BeautifulSoup(body,'html.parser');rows={}
    for a in soup.select('a[href]'):
        url=urljoin(source['url'],a['href']);parts=urlsplit(url);q=parse_qs(parts.query)
        if source['id']=='lh_press_watch':
            if parts.path!='/gallery.es' or q.get('bid')!=['0003'] or q.get('act')!=['view']:continue
            node=a;heading=a.select_one('.title');key=(q.get('list_no') or [''])[0]
            title=clean(heading.get_text(' ',strip=True)) if heading else ''
            url='https://www.lh.or.kr/gallery.es?'+urlencode(dict(mid='a10502000000',bid='0003',act='view',list_no=key))
        else:
            if parts.path!='/main/bbs/bbsMsgDetail.do' or q.get('bcd')!=['idtc_press']:continue
            node=a.find_parent('li');key=(q.get('msg_seq') or [''])[0];title=clean(a.get_text(' ',strip=True))
            url='https://www.ih.co.kr/main/bbs/bbsMsgDetail.do?'+urlencode(dict(bcd='idtc_press',msg_seq=key))
        if not node or not key.isdigit() or not title:raise ValueError('보도자료 목록 식별자·제목 변경')
        match=re.search(r'20\d{2}[-.]\d{2}[-.]\d{2}',node.get_text(' ',strip=True))
        if not match:raise ValueError('보도자료 게시일 미확보')
        date=match[0].replace('.','-');datetime.fromisoformat(date)
        title=re.sub(r'^새글\s*','',title)
        rows[key]=dict(source_object_id=key,name=title,evidence_url=url,source_date=date)
    if not rows:raise ValueError('보도자료 목록 미발견 · 구조/접근 확인 필요')
    return list(rows.values())

def sh_board_rows(body):
    """Read the publication date column, never an older date inside its title."""
    soup=BeautifulSoup(body,'html.parser');rows={}
    for tr in soup.select('tr'):
        anchor=tr.select_one('a[onclick*="getDetailView"]')
        if not anchor:continue
        match=re.search(r"getDetailView\(\s*['\"](\d+)['\"]\s*\)",anchor.get('onclick',''))
        dates=[clean(td.get_text(' ',strip=True)) for td in tr.select('td.num')]
        dates=[d for d in dates if re.fullmatch(r'20\d{2}-\d{2}-\d{2}',d)]
        title=clean(anchor.get_text(' ',strip=True))
        if not match or len(dates)!=1 or not title:raise ValueError('SH 공고 식별자·게시일·제목 미확보')
        datetime.fromisoformat(dates[0]);key=match[1]
        row=dict(source_object_id=key,name=title,source_date=dates[0],
                 evidence_url='https://www.i-sh.co.kr/main/lay2/program/S1T294C295/www/brd/m_241/view.do?seq='+key)
        if key in rows and rows[key]!=row:raise ValueError('동일 SH 공고 식별자의 목록 내용 상충')
        rows[key]=row
    if not rows:raise ValueError('SH 공고 목록 미발견 · 구조/접근 확인 필요')
    return list(rows.values())


def government_board_rows(body, source):
    soup=BeautifulSoup(body,'html.parser');rows={}
    molit=source['id']=='molit_press_watch'
    expected=urlsplit(source['url'])
    for tr in soup.select('tr'):
        a=tr.select_one('td.bd_title a[href]' if molit else 'a.c-board-title[href]')
        if not a:continue
        parts=urlsplit(urljoin(source['url'],a['href']));q=parse_qs(parts.query)
        key=(q.get('id' if molit else 'articleNo') or [''])[0]
        if parts.hostname!=expected.hostname or parts.path!=('/USR/NEWS/m_71/dtl.jsp' if molit else expected.path) or not key.isdigit():
            raise ValueError('정부 보도자료 출처·식별자 변경')
        date_node=tr.select_one('.bd_date' if molit else '.c-board-info-m')
        dates=re.findall(r'20\d{2}[-.]\d{2}[-.]\d{2}',date_node.get_text(' ',strip=True) if date_node else '')
        title=clean(a.get_text(' ',strip=True))
        if len(dates)!=1 or not title:raise ValueError('정부 보도자료 제목·게시일 미확보')
        day=dates[0].replace('.','-');datetime.fromisoformat(day)
        url=('https://www.molit.go.kr/USR/NEWS/m_71/dtl.jsp?id='+key if molit else
             'https://www.opm.go.kr/opm/news/press-release.do?mode=view&articleNo='+key)
        row=dict(source_object_id=key,name=title,evidence_url=url,source_date=day)
        if key in rows and rows[key]!=row:raise ValueError('정부 보도자료 동일 식별자 내용 상충')
        rows[key]=row
    if not rows:raise ValueError('정부 보도자료 목록 미발견 · 구조/접근 확인 필요')
    return list(rows.values())


def collect(source, fetcher):
    found={};counts=[]
    for url in source.get('feed_urls') or [source['url']]:
        body=fetcher.get(url,'xml' if source.get('watch_format')=='RSS' else 'html')
        rows=(rss_rows(body,source) if source.get('watch_format')=='RSS' else
              government_board_rows(body,source) if source.get('watch_format')=='GOV_BOARD' else
              sh_board_rows(body) if source.get('watch_format')=='SH_BOARD' else board_rows(body,source))
        counts.append(dict(url=url,listed=len(rows)))
        for row in rows:
            if row['source_object_id'] in found and found[row['source_object_id']]!=row:
                raise ValueError('동일 기사 식별자의 피드 내용 상충')
            found[row['source_object_id']]=row
    start=(today()-timedelta(days=30)).isoformat();end=today().isoformat();records=[]
    for key,row in sorted(found.items()):
        if not start<=row['source_date']<=end or not housing_title(row['name']):continue
        records.append(('document_evidence',key,dict(row,sample_kind='document_evidence',
            base_date=row['source_date'],date_precision='DAY',document_role='PUBLICATION_DISCOVERY',
            listing_urls=source.get('feed_urls') or [source['url']],publisher=source['org'],
            authority=authority(row['evidence_url'],source['id']),verification_status='DISCOVERED_REVIEW_REQUIRED',
            content_scope='게시 목록/RSS의 제목·게시시각·원문 링크. 기사 전문·첨부 분석 및 사실 검증 전.',
            facts=[],matched_project_ids=[],planned_units=None,units=None,
            policy_candidate_only=True,proposed_policy='UNASSIGNED',status='REVIEW',
            unit_basis='주택 관련 신규 게시물 탐색 후보 · 원문·사업·시점 대조와 승인 전 실적 가산 없음')))
    return records,dict(incremental=True,complete_query=True,complete_population=False,
        discovery_only=True,provided=len(found),fetched=len(records),feed_counts=counts,
        latest_published=max((r[2]['source_date'] for r in records),default=None),
        actual_events_created=0,period_start=start,period_end=end,
        scope_note='등록 공식 게시판 최신 페이지 또는 언론사 RSS 현재 항목 중 최근30일 주택 키워드. 과거 전수·모든 언론사 탐색 아님. 원문 링크 검토 후보로 보존; 호수/실적 자동 추출 없음.')
