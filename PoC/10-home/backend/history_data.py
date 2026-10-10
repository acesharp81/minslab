"""Historical evidence is stored separately; backfill never overwrites current projects."""
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .api_samples import today
from .collection_period import collection_start
from .collectors import article_text, parse_construction
from .db import entity_id

POLICY_EVENTS = [
    {'event_id':'THIRD_2018','name':'3기 신도시 최초 계획 발표','event_date':'2018-12-19','origin_id':'THIRD_NEW_TOWN',
     'url':'https://www.korea.kr/news/policyNewsView.do?newsId=148856563','assertion':'제3기 신도시','basis':'남양주·하남 등 최초 입지 발표'},
    {'event_id':'THIRD_2019','name':'3기 신도시 창릉·대장 추가 발표','event_date':'2019-05-07','origin_id':'THIRD_NEW_TOWN',
     'url':'https://www.korea.kr/news/policyNewsView.do?newsId=148860598','assertion':'대장','basis':'고양 창릉·부천 대장 추가 입지 발표'},
    {'event_id':'URBAN_2021','name':'3080+ 도심 공공주택 복합사업 도입','event_date':'2021-02-04','origin_id':'URBAN_COMPLEX',
     'url':'https://www.korea.kr/news/policyNewsView.do?newsId=148883564','assertion':'3080','basis':'도심 복합사업 도입 방안 발표'},
    {'event_id':'URBAN_FIRST_2021','name':'도심 공공주택 복합사업 첫 후보지 발표','event_date':'2021-03-31','origin_id':'URBAN_COMPLEX',
     'url':'https://www.korea.kr/news/policyNewsView.do?newsId=148885699','assertion':'21곳','basis':'서울 4개구 첫 후보지 발표'},
    {'event_id':'URBAN_SEASON2_2025','name':'공공 도심복합사업 시즌2 후속조치','event_date':'2025-10-21','origin_id':'URBAN_COMPLEX',
     'url':'https://www.korea.kr/news/policyNewsView.do?newsId=148952578','assertion':'2021','basis':'9·7 대책 후속조치 · 기존 제도 연속성 확인'},
]


def collect_policy_events(source,fetcher):
    records=[]
    for event in POLICY_EVENTS:
        if event['event_date']<collection_start().isoformat() or event['event_date']>today().isoformat():continue
        html=fetcher.get(event['url'])
        text=article_text(html)
        page=BeautifulSoup(html,'html.parser').get_text(' ',strip=True)
        date_pattern=r'\s*[.년/-]\s*'.join(event['event_date'].split('-'))
        if event['assertion'] not in text or not re.search(date_pattern,page):
            raise ValueError('과거 정책자료 제목·발표일 근거 불일치: 기존 이력 유지')
        payload={'name':event['name'],'event_date':event['event_date'],'base_date':event['event_date'],
            'date_precision':'DAY','origin_id':event['origin_id'],'evidence_url':event['url'],'basis':event['basis'],
            'date_basis':'공식 발표일 · 법적 시행일과 구분','relation_status':'REVIEW','availability':'PUBLIC'}
        records.append(('policy_event',event['event_id'],payload))
    return records,{'period_start':collection_start().isoformat(),'period_end':today().isoformat(),'policy_events':len(records)}


def construction_files(html,source_url):
    files={}
    for anchor in BeautifulSoup(html,'html.parser').select('a[href*="boardDownload.es"]'):
        title=anchor.get('title','')
        match=re.search(r'(20\d{6})',title)
        if '.docx' not in title.lower() or not match:continue
        stamp=match[1];when=f'{stamp[:4]}-{stamp[4:6]}-{stamp[6:]}'
        if collection_start().isoformat()<=when<=today().isoformat():
            if when in files:raise ValueError('동일 기준일의 공사 보고서 중복: 판본 확인 필요')
            files[when]=urljoin(source_url,anchor['href'])
    if not files:raise ValueError('기간 내 공식 과거 공사 DOCX 없음: 기존 이력 유지')
    return sorted(files.items())


def collect_project_reports(source,fetcher,service):
    current={row['id'] for row in service.projects()}
    files=construction_files(fetcher.get(source['url']),source['url'])
    records=[]
    for report_date,url in files:
        rows,_=parse_construction(fetcher.get(url,'docx'),report_date)
        for _,identifier,row in rows:
            project_id=entity_id('project','lh_construction',identifier)
            payload=dict(row,report_date=report_date,current_project_id=project_id if project_id in current else None,
                source_object_id=identifier,evidence_url=url,history_mode='SOURCE_REPORT',relation_status='REVIEW')
            records.append(('project_report',report_date+'|'+identifier,payload))
    return records,{'period_start':collection_start().isoformat(),'period_end':today().isoformat(),
        'report_dates':[stamp for stamp,_ in files],'report_count':len(files),'project_reports':len(records),
        'scope_note':'공개 DOCX 첨부 기준일별 누적. 과거 보고서는 현재 사업 레코드를 덮어쓰지 않음'}
