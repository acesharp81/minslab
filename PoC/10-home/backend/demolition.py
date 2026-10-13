"""Annual official housing-demolition files; only verified provincial totals."""
import re

from bs4 import BeautifulSoup

from .collectors import integer
from .public_files import xlsx_rows

PAGE = 'https://www.index.go.kr/unity/potal/main/EachDtlPageDetail.do?idx_cd=2839'
DOWNLOAD = 'https://www.index.go.kr/unity/potal/FileDown.do?seq={seq}&id=2839&div=1'
CATEGORIES = ('단독주택', '다가구', '연립주택', '다세대주택', '아파트')


def file_index(content):
    soup = BeautifulSoup(content, 'html.parser')
    result = {}
    for anchor in soup.select('a[href*="fn_downLoadApndFile"]'):
        title = anchor.get_text(' ', strip=True)
        year_match = re.search(r'(?<!\d)(\d{2})년[_\s]*멸실주택수', title)
        seq_match = re.search(r"fn_downLoadApndFile\(['\"](\d+)['\"],\s*['\"]2839['\"],\s*['\"]1['\"]\)", anchor.get('href', ''))
        if not year_match or not seq_match:
            continue
        year = 2000 + int(year_match[1])
        if year in result and result[year] != seq_match[1]:
            raise ValueError('멸실 첨부 연도 중복')
        result[year] = seq_match[1]
    if not set(range(2018, 2025)).issubset(result):
        raise ValueError('2018~2024 멸실 첨부 파일 목록 미확인')
    return result


def parse_demolition(content, source, year, evidence_url):
    rows = xlsx_rows(content)
    if len(rows) < 15 or rows[0].get('A') != f'{year}년 멸실 주택수':
        raise ValueError('멸실 엑셀 자료연도·제목 변경')
    if [rows[1].get(c) for c in 'ABCDEFG'] != ['시도', '계', *CATEGORIES]:
        raise ValueError('멸실 엑셀 열 구조 변경')
    selected = {row.get('A'): row for row in rows[2:] if row.get('A') in {'서울', '경기'}}
    if set(selected) != {'서울', '경기'}:
        raise ValueError('멸실 서울·경기 시도 행 미확인')
    national = next((row for row in rows[2:] if row.get('A') == '전국'), None)
    if not national or integer(national.get('B')) is None:
        raise ValueError('멸실 전국 총계 미확인')
    national_total = integer(national['B'])
    records = []
    for short, region in (('서울', '서울특별시'), ('경기', '경기도')):
        row = selected[short]
        total = integer(row.get('B'))
        categories = {name: integer(row.get(col)) for name, col in zip(CATEGORIES, 'CDEFG')}
        if total is None or any(value is None for value in categories.values()) or total != sum(categories.values()) or total > national_total:
            raise ValueError(f'{year}년 {region} 멸실 총계·유형 합계 불일치')
        payload = {'name': f'{region} {year}년 주택 멸실', 'region': region,
                   'source_object_id': f'{year}:{region}', 'sample_kind': 'statistic',
                   'statistic_metric': '멸실', 'statistic_frequency': 'YEAR',
                   'statistic_period': str(year), 'units': total,
                   'demolition_breakdown': categories, 'national_units': national_total,
                   'base_date': f'{year}-12-31', 'source_date': f'{year}-12-31',
                   'source_date_label': '자료연도 말일 · 공표일 아님',
                   'unit_basis': '연간 멸실 주택 호수 · 기존 재고 감소',
                   'source_note': '국토부/e-나라지표 시도별 공식 통계. 시군구·블록으로 배분하지 않음; 준공에서 차감한 값은 공식 재고가 아닌 산술 대조.',
                   'evidence_url': evidence_url, 'warnings': ['REGIONAL_TOTAL_NOT_POLICY_ACTUAL']}
        records.append(('statistic', f'{year}:{region}', payload))
    return records


def collect_demolition(source, fetcher):
    indexed = file_index(fetcher.get(PAGE))
    records = []
    years = []
    for year, seq in sorted(indexed.items()):
        if year < 2018:
            continue
        url = DOWNLOAD.format(seq=seq)
        records.extend(parse_demolition(fetcher.get(url, 'xlsx'), source, year, url))
        years.append(year)
    if len(records) != 2 * len(years):
        raise ValueError('멸실 연도별 서울·경기 2행 확인 실패')
    return records, {'first_year': min(years), 'latest_year': max(years),
                     'years': years, 'region_counts': {'서울특별시': len(years), '경기도': len(years)},
                     'complete_query': True, 'complete_population': False,
                     'scope_note': '공개된 연도별 엑셀의 시도 행 전체. 시군구 멸실량·미공표 연도는 미확보.'}
