"""Official REIT annual report: construction percentages, not financial ratios."""
import io
import re
from pypdf import PdfReader
from .collectors import GYEONGGI_CITIES


def collect_reit_progress(source,fetcher):
    reader=PdfReader(io.BytesIO(fetcher.get(source['url'],'pdf')))
    cover=reader.pages[0].extract_text(extraction_mode='layout')
    if not re.search(r'2018\.01\.01\s+부터\s+2018\.12\.31\s+까지',cover) or '제6호' not in cover:
        raise ValueError('LH 제6호 리츠 2018 투자보고서 기간·회사 불일치')
    records=[]
    for page_index,page in enumerate(reader.pages):
        text=page.extract_text(extraction_mode='layout')
        if '부동산개발사업의 현황' not in text or '공정률' not in text:continue
        for line in text.splitlines():
            # Each development row repeats its site in the location column.
            match=re.match(r'^\s*(.+?)\s{2,}(.+?)\s{2,}([\d,]+)\s+(20\d{2}-\d{2}-\d{2})\s+(\d+(?:\.\d+)?)%',line)
            if not match:continue
            name,location,area,end,pct=match.groups()
            city=next((c for c in GYEONGGI_CITIES if name.startswith(c)),None)
            region='경기도' if city else '서울특별시' if name.startswith('서울') else None
            if not region:continue
            block_match=re.fullmatch(r'(.+?)\s+([A-Z]+-?\d+)',name)
            if not block_match:raise ValueError('리츠 사업 지구·블록 구분 변경')
            progress=float(pct)
            if not 0<=progress<=100:raise ValueError('리츠 공정률 범위 오류')
            payload=dict(name=name,district=block_match[1],block=block_match[2],region=region,municipality=city or '서울 (구 확인 필요)',
                source_object_id=name,report_date='2018-12-31',report_period='2018-12-31',base_date='2018-12-31',
                source_date='2018-12-31',date_precision='DAY',source_registration_date='2019-04-01',
                progress_pct=progress,planned_units=None,current_project_id=None,developer='LH',program='공공임대 리츠',
                stage='COMPLETED' if progress==100 else 'CONSTRUCTION',stage_label='투자보고서상 공사 완료' if progress==100 else '투자보고서상 공사 진행',
                evidence_url=source['url'],source_page=page_index+1,progress_date_basis='공식 투자보고서 보고기간 말 기준 · 준공 예정일과 구분',
                history_mode='SOURCE_REPORT',relation_status='REVIEW',availability='PUBLIC',warnings=[])
            records.append(('project_report','2018-12-31|'+name,payload))
    if len(records)!=1 or records[0][2]['name']!='하남미사 A-24':
        raise ValueError('LH 리츠 2018 보고서 서울·경기 공정률 표 행 검증 불일치')
    return records,dict(report_count=1,project_reports=1,observations_by_year={'2018':1},
        period_start='2018-12-31',period_end='2018-12-31',
        scope_note='LH 제6호 공공임대리츠 연간 투자보고서 1개 공개본 · 전체 리츠 또는 전체 정책 공정률 아님')
