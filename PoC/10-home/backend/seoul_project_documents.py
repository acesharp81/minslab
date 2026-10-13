"""Scoped parsing of Seoul construction overviews and SH advance notices.

Construction dates, undated progress and advance reservations have different
meanings. No parsing operation writes project totals or policy attribution.
"""
import re
from datetime import date
from bs4 import BeautifulSoup


def compact(value):
    return re.sub(r'\s+', '', value)


def parse_construction_overview(body, project_code, expected_name):
    soup=BeautifulSoup(body,'html.parser');text=soup.get_text(' ',strip=True)
    if compact(expected_name) not in compact(text):raise ValueError('건설알림이 공사명 불일치')
    html=str(soup)
    if not re.search(r'pjt_cd\s*(?:=|:)\s*["\']?'+re.escape(project_code)+r'(?!\d)',html):
        raise ValueError('건설알림이 사업 코드 불일치')
    table={}
    for tr in soup.find_all('tr'):
        cells=tr.find_all(['th','td'],recursive=False)
        if len(cells)==2:table[compact(cells[0].get_text(' ',strip=True))]=cells[1].get_text(' ',strip=True)
    period=table.get('공사기간','')
    dates=re.fullmatch(r'(20\d{2}-\d{2}-\d{2})\s*~\s*(20\d{2}-\d{2}-\d{2})',period)
    if not dates:raise ValueError('건설알림이 공사기간 미확인')
    start,end=dates.groups();date.fromisoformat(start);date.fromisoformat(end)
    if start>=end:raise ValueError('건설알림이 공사기간 역전')
    # Only accept a start event when the overview explicitly calls it 착공.
    if not re.search(r'착공\s*'+re.escape(start),text):raise ValueError('건설알림이 착공 표기 미확인')
    facts=[dict(stage='CONSTRUCTION',kind='ACTUAL',date=start,milestone='CONSTRUCTION',
                basis='서울 건설알림이의 착공일 표기 · 공사 계약/착공식 날짜와 구분 검토'),
           dict(stage='CONSTRUCTION',kind='PLAN',date=end,milestone='COMPLETION',
                basis='서울 건설알림이 공사기간 종료일 · 준공 예정, 사용승인·실제 준공·입주 아님')]
    raw={}
    for label,key in [('계획','planned_pct'),('실적','actual_pct'),('달성','achievement_pct')]:
        match=re.search(label+r'\s*(\d+(?:\.\d+)?)\s*%',text)
        if match:
            value=float(match[1])
            if value<0 or (key!='achievement_pct' and value>100):raise ValueError('건설알림이 공정률 범위 오류')
            raw[key]=value
    if raw:
        facts.append(dict(stage='CONSTRUCTION',kind='DOCUMENT',date=None,
            date_label='공정률 기준일 미표기',
            basis='건설알림이 화면 공정 수치 확보: '+', '.join({'planned_pct':'계획','actual_pct':'실적','achievement_pct':'달성'}[k]+' '+str(v)+'%' for k,v in raw.items())+
                  ' · 기준일 미확인으로 현재 실적·지연 계산에는 미적용'))
    return dict(name=expected_name+' · 서울 건설알림이',source_object_id=project_code,
        source_start_date=start,source_completion_plan_date=end,raw_progress=raw,
        progress_observation_date=None,construction_overview=table,facts=facts,
        planned_units=None,unit_basis='공사개요의 일정 근거 · 주택 총호수는 SH 원문에서 별도 대조')


def parse_godeok_pre_notice_text(text, notice_date, round_no):
    """Require exact complex and conserved quantities; dates apply to notice scope."""
    t=compact(text)
    if '고덕강일' not in t or '3단지' not in t or '사전예약' not in t:raise ValueError('SH 사전예약 공고 범위 미확인')
    if not re.search(r'총건설호수는1,305호.*?59㎡715호.*?49㎡590호',t):
        raise ValueError('고덕강일 전체·주택형 물량 대조 실패')
    year,mon,day=map(int,notice_date.split('-'));date(year,mon,day)
    if not re.search(rf'{year}[.년/-]0?{mon}[.월/-]0?{day}',t):raise ValueError('SH 모집공고일 미확인')
    section=t[t.find('4.본청약및입주예정시기'):]
    dates=re.search(r'고덕강일공공주택지구3단지(20\d{2})년(\d{1,2})월(20\d{2})년(\d{1,2})월',section)
    if not dates:raise ValueError('SH 본청약·입주 예정월 미확인')
    sy,sm,my,mm=map(int,dates.groups());date(sy,sm,1);date(my,mm,1)
    supply=f'{sy:04d}-{sm:02d}';move=f'{my:04d}-{mm:02d}'
    if round_no==1:area,scope,offered=59,715,500
    elif round_no==2:area,scope,offered=49,590,590
    else:raise ValueError('사전예약 회차 미확인')
    if not re.search(rf'사전예약공급호수{offered}(?:세대|호)',t):raise ValueError('SH 금회 사전예약 물량 미확인')
    partial=dict(scope_partial=True,scope_units=scope,scope_label=f'{area}㎡ {scope:,}호 / 전체 1,305호')
    facts=[dict(stage='SUPPLY',kind='STATE',date=notice_date,event_type='ADVANCE_RESERVATION',
                units=offered,scope_partial=True,scope_units=offered,scope_label=f'{round_no}차 사전예약 {offered:,}호 / 전체 1,305호',
                basis=f'SH {round_no}차 사전예약 모집공고 게시 · {offered}호, 본청약·계약 실적 및 별도 신규 물량으로 합산하지 않음'),
           dict(stage='SUPPLY',kind='PLAN',date=supply,milestone='SUPPLY',**partial,
                basis='SH 사전예약 원문 당시 본청약 예정월 · 현재 모집공고 실적 아님, 후속 변경 확인 필요'),
           dict(stage='MOVE_IN',kind='PLAN',date=move,milestone='MOVE_IN',**partial,
                basis='SH 사전예약 공고문의 입주 예정월 · '+str(area)+'㎡ 주택형 범위, 후속 일정 변경 및 실제 입주 별도 확인')]
    return dict(name=f'고덕강일 3단지 · SH {round_no}차 사전예약 공고문',planned_units=1305,
        scope_breakdown={'59㎡':715,'49㎡':590},offered_units=offered,notice_round='ADVANCE_RESERVATION',
        announcement_date=notice_date,move_in_month=move,main_subscription_plan_month=supply,
        region='서울특별시',municipality='강동구',address='서울특별시 강동구 강일동 174 일원',
        facts=facts,unit_basis='SH 총 건설호수 1,305호 · 사전예약·본청약 중복 합산 금지')
