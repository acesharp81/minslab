import csv
import io
import pytest
from backend.agency_plan_files import parse_plan_file
from backend.lh_public_history import address_area, name_area, parse_supply
from backend.sources import SOURCES
from tests.test_missing_sources import stock_xlsx

S={s['id']:s for s in SOURCES}

def body(rows):
    stream=io.StringIO();w=csv.DictWriter(stream,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    return stream.getvalue().encode('utf-8-sig')

def test_capital_filter_keeps_incheon_by_location_not_headquarters():
    assert address_area('인천광역시 서구 검단로 1')==('인천광역시','서구')
    assert name_area('인천검단')==('인천광역시',None)
    assert name_area('부천원종')==('경기도','부천시')
    assert name_area('위례')==(None,None)
    h=['공급년도','사업지구','블록','시도','주소','공급유형','세대수','모집공고일','최초입주시기','공급유형별 호수']
    r=['2025','인천검단','AA19','인천광역시','인천광역시 서구','공공분양','1323','20250102','202712','991']
    records,stats=parse_supply(stock_xlsx([['기준일: 25.11.13'],h,r]),S['lh_supply_history'],'https://www.lh.or.kr/')
    assert records[0][2]['units']==991 and stats['region_counts']=={'인천광역시':1}

def test_movein_unknown_month_and_other_regions_not_made_into_events():
    row={'입주예정월':'2027-00','지역':'인천','사업유형':'임대','주소':'인천광역시 서구 검단','아파트명':'인천검단 AA1','세대수':'100'}
    outside=dict(row,지역='부산',주소='부산광역시 강서구')
    rs,stats=parse_plan_file(body([row,row,outside]),S['reb_movein_plan_file'],'2026-06-30')
    assert len(rs)==1 and stats['duplicate_rows']==1 and stats['excluded_rows']==1
    assert rs[0][2]['facts']==[] and 'MOVE_IN_DATE_UNPARSED' in rs[0][2]['warnings']
    with pytest.raises(ValueError,match='주소'):parse_plan_file(body([dict(row,주소='부산광역시 강서구')]),S['reb_movein_plan_file'],'2026-06-30')

def test_year_only_plan_and_inconsistent_source_totals_preserved():
    row={'단지명':'테스트 1단지','소재지':'서울특별시 강동구','공급(예정) 년도':'2026','공급예정물량 총계':'20'}
    rs,_=parse_plan_file(body([row]),S['sh_happy_plan_file'],'2026-08-03')
    fact=rs[0][2]['facts'][0]
    assert fact['date']=='2026-12-31' and fact['precision']=='YEAR' and fact['kind']=='PLAN'
    row={'단지명':'고덕강일4단지','공급 계':'396','소재지':'강동구','공급(예정) 년도':'2020','공급(예정)월':'05','공급예정물량(29제곱미터)':'166','공급예정물량(39제곱미터)':'230','공급예정물량(49제곱미터) 이상':'163'}
    rs,_=parse_plan_file(body([row]),S['sh_national_plan_file'],'2026-08-31')
    assert rs[0][2]['units']==396 and rs[0][2]['warnings']==['SOURCE_TOTAL_MISMATCH']

def test_contract_end_is_never_a_completion_or_start_fact():
    row={'계약명':'아파트 시설공사','계약금액(원)':'100000','계약시작일':'2025-01-01','계약종료일':'2027-01-01','입찰방법':'경쟁','계약대상':'시공사'}
    rs,_=parse_plan_file(body([row]),S['sh_contract_file'],'2026-08-03')
    assert rs[0][0]=='agency_contract' and rs[0][2]['facts']==[] and rs[0][2]['units'] is None

def test_same_area_conflicting_quantities_remain_unaggregated():
    row={'지역':'경기도','유형':'행복주택','지구명':'부천괴안 B1','면적':'55.65','공급호수':'58','공급시기':'2023-06','입주예정':'2024-11','비고':''}
    rs,stats=parse_plan_file(body([row,dict(row,공급호수='8')]),S['lh_happy_plan_file'],'2025-09-22')
    assert len(rs)==2 and stats['warning_counts']['AMBIGUOUS_PLAN_DIMENSION']==2
    assert all(not r[2]['facts'] for r in rs)

def test_undecided_movein_does_not_discard_incheon_supply_record():
    h=['공급년도','사업지구','블록','시도','주소','공급유형','세대수','모집공고일','최초입주시기','공급유형별 호수']
    r=['2025','인천검단','AA19','인천광역시','인천광역시 서구','공공분양','1323','20250102','미정','991']
    records,_=parse_supply(stock_xlsx([['기준일: 25.11.13'],h,r]),S['lh_supply_history'],'https://www.lh.or.kr/')
    p=records[0][2]
    assert p['move_in_plan_month'] is None and p['move_in_raw']=='미정' and p['units']==991
