"""Policy origin years and evidence dates, independent of collection timestamps."""
import os
from datetime import date,datetime
from zoneinfo import ZoneInfo

ORIGINS = {
    'THIRD_NEW_TOWN': {'name':'3기 신도시', 'origin_date':'2018-12-19',
        'date_basis':'최초 계획 발표 연도', 'evidence_url':'https://www.korea.kr/news/policyNewsView.do?newsId=148856563'},
    'URBAN_COMPLEX': {'name':'도심 공공주택 복합사업', 'origin_date':'2021-02-04',
        'date_basis':'제도 도입 방안 발표 연도', 'evidence_url':'https://www.korea.kr/news/policyNewsView.do?newsId=148883564'},
}


def collection_start():
    earliest=min(int(origin['origin_date'][:4]) for origin in ORIGINS.values())
    automatic=date(earliest,1,1)
    configured=os.environ.get('POC10_NOTICE_START_DATE','').strip()
    if not configured:
        return automatic
    try:
        requested=date.fromisoformat(configured)
    except ValueError:
        raise ValueError('역사 수집 시작일은 YYYY-MM-DD로 설정하세요') from None
    if requested<date(2010,1,1) or requested>datetime.now(ZoneInfo('Asia/Seoul')).date():
        raise ValueError('역사 수집 시작일 범위를 확인하세요')
    # A legacy recent-year setting must not truncate the monitored policy history.
    return min(automatic,requested)


def annual_windows(end):
    start=collection_start()
    return [(max(start,date(year,1,1)),min(end,date(year,12,31))) for year in range(start.year,end.year+1)]
