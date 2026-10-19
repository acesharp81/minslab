"""Official monthly housing PDF fallback; YTD is never summed as monthly flow."""
import calendar
import hashlib
import io
import re
from bs4 import BeautifulSoup
from pypdf import PdfReader
from .api_samples import base

LIST_URL = 'https://www.index.go.kr/unity/potal/main/EachDtlPageDetail.do?idx_cd=1229'
REGIONS = {'서울': '서울특별시', '인천': '인천광역시', '경기': '경기도'}


def discover(body):
    found = {}
    for a in BeautifulSoup(body, 'html.parser').select('a[href]'):
        title = a.get_text(' ', strip=True)
        period = re.search(r'(\d{2,4})년\s*(\d{1,2})월\s*주택\s*통계', title)
        link = re.search(r"fn_downLoadApndFile\('([0-9]+)'\s*,\s*'1229'\s*,\s*'1'\)", a['href'])
        if not period or not link or not title.lower().endswith('.pdf'):
            continue
        year, month = map(int, period.groups()); year += 2000 if year < 100 else 0
        if not 1 <= month <= 12:raise ValueError('월별 보도자료 대상월 오류')
        found[f'{year:04d}{month:02d}'] = (title, 'https://www.index.go.kr/unity/potal/FileDown.do?seq='+link[1]+'&id=1229&div=1')
    if not found:raise ValueError('월별 주택통계 공식 PDF 목록 형식 확인 필요')
    return max(found), found[max(found)]


def parse_pdf(body, period, source, url):
    if not body.startswith(b'%PDF') or len(body)>20_000_000:raise ValueError('공식 통계 PDF 형식·크기 확인 필요')
    reader=PdfReader(io.BytesIO(body))
    if len(reader.pages)>100:raise ValueError('통계 PDF 페이지 상한 초과')
    pages=[(i+1,p.extract_text(extraction_mode='layout')) for i,p in enumerate(reader.pages)]
    candidates=[(i,t) for i,t in pages if re.search(r'주택\s*인허가\s*\(전체주택\)',t)]
    if len(candidates)!=1:raise ValueError('전체주택 인허가 상세표 단일 페이지 확인 필요')
    page,text=candidates[0]; year,month=int(period[:4]),int(period[4:])
    if not re.search(rf"(?:{year}|{year%100})\s*[.년]\s*{month}\s*월\s*주택",text):
        raise ValueError('공식 PDF 대상 연월 불일치')
    def values(label):
        pattern=r'^\s*'+r'\s*'.join(label)+r'\s+([\d,]+)\s+([\d,]+)\s+'
        hits=re.findall(pattern,text,re.M)
        if len(hits)!=1:raise ValueError('공식 PDF 지역 총계 단일 행 확인 필요: '+label)
        return tuple(int(v.replace(',','')) for v in hits[0])
    regional={k:values(k) for k in REGIONS}; metro=values('수도권')
    if tuple(sum(v[i] for v in regional.values()) for i in (0,1))!=metro:
        raise ValueError('공식 월별 인허가 수도권·시도 합계 불일치')
    records=[];stamp=f'{year}-{month:02d}-{calendar.monthrange(year,month)[1]}'
    for label,(monthly,ytd) in regional.items():
        if monthly>ytd:raise ValueError('당월 인허가가 누계를 초과')
        for frequency,units in [('MONTH',monthly),('YTD',ytd)]:
            p=base(source,'statistic_reference',REGIONS[label]+' '+period+' 인허가 '+frequency,REGIONS[label],'시도 공식 통계',stamp)
            p.update(units=units,statistic_metric='인허가',statistic_frequency=frequency,statistic_period=period,
                statistic_unit='호',period_start=f'{year}-01-01' if frequency=='YTD' else f'{year}-{month:02d}-01',
                period_end=stamp,evidence_url=url,source_document_sha256=hashlib.sha256(body).hexdigest(),pdf_page=page,
                unit_basis='공식 전체주택 인허가 '+('연초부터 대상월까지 누계 · 월별값과 합산 금지' if frequency=='YTD' else '당월'),
                source_date_label='통계 관측 종료일 · 공표일 아님',warnings=['REGIONAL_TOTAL_NOT_POLICY_ACTUAL'])
            records.append(('statistic_reference',f'{period}:{label}:{frequency}',p))
    return records


def collect(source,fetcher):
    period,(title,url)=discover(fetcher.get(LIST_URL))
    records=parse_pdf(fetcher.get(url,'pdf'),period,source,url)
    return records,dict(period=period,title=title,reference_records=len(records),complete_query=True,
        complete_population=False,scope_note='공식 PDF의 수도권 3개 시도 인허가 당월·누계. 월별 API 보완이며 개별 사업 실적에 합산하지 않음')
