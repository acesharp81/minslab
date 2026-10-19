"""Attach per-source collector implementation and extraction checks to a HOME export."""
import json
from pathlib import Path

from scripts.verify_export import sha256_file
from scripts.write_data_sharing_guide import method

METRIC_DEFINITIONS = {
    'statistic.molit_demolition': {
        'time_field': 'statistic_period', 'basis': '국토부/e-나라지표 연간 주택멸실 시도별 XLSX',
        'fields': {'units': '호 · 해당 연도 멸실 주택 수',
                   'demolition_breakdown': '호 · 단독/다가구/연립/다세대/아파트'},
        'do_not_combine_with': '실제 입주·사업별 공급으로 취급 금지; 준공 차감은 공식 재고 순증 아님'},
    'area_stat.sgis_census': {
        'time_field': 'year', 'basis': 'SGIS 총조사 기준연도',
        'fields': {'population': '명 · 총인구', 'households': '가구 · 일반가구',
                   'workplace_workers': '명 · 사업체 소재지 종사자',
                   'businesses': '개 · 사업체', 'industry_workers': '산업별 사업체 소재지 종사자'},
        'do_not_combine_with': '거주지 기준 취업자 또는 신규 공급실적'},
    'area_stat.kosis_employment': {
        'time_field': 'year + half', 'basis': 'KOSIS 지역별고용조사 반기',
        'fields': {'resident_employed': '명 · 거주지 취업자, 원천 천명 단위를 명으로 환산',
                   'labor_force': '명 · 경제활동인구, 원천 천명 단위를 명으로 환산',
                   'employment_rate': '% · 고용률'},
        'do_not_combine_with': '사업체 소재지 종사자'},
    'area_stat.kosis_household_forecast': {
        'time_field': 'year', 'basis': 'KOSIS 시도 장래가구추계; source_date는 추계판본 날짜',
        'fields': {'forecast_households': '가구 · 전망값'},
        'do_not_combine_with': '같은 연도 실제 관측 가구로 오인하지 않음'},
    'area_stat.kosis_housing': {
        'time_field': 'year', 'basis': '같은 행정구역·연도의 주택재고/일반가구 통계',
        'fields': {'housing_units': '호 · 다가구 구분거처 반영 주택 재고',
                   'households': '가구 · 일반가구 수',
                   'census_housing_units': '호 · 주택총조사 주택_계, 2018~2025; 보정 재고와 다른 기준'},
        'do_not_combine_with': '공실률·실점유·실입주량을 직접 의미하지 않음'},
    'area_stat.kosis_household_size': {
        'time_field': 'year', 'basis': 'KOSIS 일반가구 가구원수별 통계',
        'fields': {'household_total': '가구 · 일반가구 전체',
                   'sizes': '가구 · 1/2/3/4/5+인 가구별 수'},
        'do_not_combine_with': 'sizes의 5+는 5인 이상 합계; household_total과 중복 합산 금지'},
    'project': {
        'time_field': 'base_date / schedule_month', 'basis': '기관별 사업 후보·계획',
        'fields': {'planned_units': '호 · 해당 후보의 계획 세대수, unit_basis 확인',
                   'supply_units': '호 · 원천의 공급 예정/계획 수량, 없으면 null',
                   'progress_pct': '% · 원천상 공정 관측이 있을 때만 기록'},
        'do_not_combine_with': '공식 정책 전체 목표 또는 실제 준공/입주량으로 단순 합산 금지'},
    'project_report': {
        'time_field': 'report_date', 'basis': '기관 공사 보고서/공개 상세 이력',
        'fields': {'progress_pct': '% · 관측 당시 실제 공정률',
                   'planned_units': '호 · 보고서의 계획 규모, 확인 가능한 경우'},
        'do_not_combine_with': '공정률을 공급·준공·입주 호수로 변환 금지'},
    'notice': {
        'time_field': 'source_date', 'basis': '모집공고·계획 확인',
        'fields': {'units': '호 · 해당 공고의 모집/공급 호수, unit_basis 확인'},
        'do_not_combine_with': '실제 입주·준공 물량으로 해석 금지'},
    'lh_movein_plan': {
        'time_field': 'source_date / move_in_plan_month', 'basis': 'LH 공개 입주계획',
        'fields': {'units': '호 · 입주 예정 물량'},
        'do_not_combine_with': '입주 실적과 혼용 금지'},
    'renewal_inventory': {
        'time_field': 'dataset_version', 'basis': '국토부 전국 정비사업 단일 공개본의 서울·경기·인천 후보',
        'fields': {'planned_units': '세대 · 정비사업 후 공급 예정 규모; 0·해당없음은 별도 값 상태'},
        'do_not_combine_with': '법적 고시 사건·정책 확정 귀속·실제 준공/입주와 혼용 금지'},
    'lh_completion_plan': {
        'time_field': 'dataset_version / completion_plan_date', 'basis': 'LH 블록별 준공예정 파일',
        'fields': {'planned_units': '세대 · 준공 예정 규모'},
        'do_not_combine_with': '실제 준공/입주·공정률 또는 같은 블록의 다른 계획과 무검토 합산 금지'},
    'complex_approval_reference': {
        'time_field': 'approval_date / dataset_version', 'basis': '한국부동산원 공동주택 단지 식별정보 CSV',
        'fields': {'complex_id': '단지고유번호', 'parcel_id': '필지고유번호',
                   'units': '세대 · 단지/필지 원본 행 세대수, 무검토 합산 금지'},
        'do_not_combine_with': '정책 실적 또는 실제 입주 호수로 자동 집계 금지'},
    'gh_completion_evidence': {
        'time_field': 'source_date / approval_date', 'basis': 'GH 입주안내 첨부 원문',
        'fields': {'pdf_sha256': '첨부 PDF SHA-256', 'approval_date': 'PDF 본문에 명시된 발급일; 스캔 등으로 미추출 가능',
                   'permit_no': 'PDF 본문에서 추출 가능한 허가·사업계획승인번호'},
        'do_not_combine_with': '사용승인을 실제 입주 호수로 간주 금지; 임시사용허가를 최종 준공으로 간주 금지'},
    'plan_notice': {
        'time_field': 'notice_date', 'basis': '서울시보·국토교통부 공식 고시 원문',
        'fields': {'original_sha256': '고시 PDF 원본 SHA-256; 공급 세대수 아님'},
        'do_not_combine_with': '고시 사건을 준공·입주 실적으로 환산 금지'},
    'permit_dong': {
        'time_field': 'source_date / base_date', 'basis': '건축HUB 주택허가 동별개요',
        'fields': {'household_breakdown': '가구 · 동별 유형 구성; 실제 공급량 아님'},
        'do_not_combine_with': '주택공급 실적·정책 승인 연결로 자동 승격 금지'},
    'permit_parcel': {
        'time_field': 'source_date / base_date', 'basis': '건축HUB 주택허가 대지위치',
        'fields': {'parent_permit_native_id': '주택허가 관리번호; 필지 연결용'},
        'do_not_combine_with': '실제 공급량과 무관'},
    'agency_stock': {
        'time_field': 'source_date / dataset_version', 'basis': '기관 공개 관리·매입 재고',
        'fields': {'units': '호 · 해당 공개본의 재고 세대수, unit_basis 확인'},
        'do_not_combine_with': '공개본 간 합계 또는 신규 공급실적과 혼용 금지'},
}

MODULE = {
    'lh_policy_followup': 'backend/lh_policy_followup.py::collect',
    'lh_happy_plan_file': 'backend/agency_plan_files.py::collect_plan_file',
    'sh_national_plan_file': 'backend/agency_plan_files.py::collect_plan_file',
    'sh_jeonse_plan_file': 'backend/agency_plan_files.py::collect_plan_file',
    'sh_happy_plan_file': 'backend/agency_plan_files.py::collect_plan_file',
    'reb_movein_plan_file': 'backend/agency_plan_files.py::collect_plan_file',
    'sh_contract_file': 'backend/agency_plan_files.py::collect_plan_file',

    'lh_department_plans':'backend/route_documents.py::collect_lh_department_plans',
    'eum_housing_notices':'backend/route_documents.py::collect_eum',
    'molit_monthly_release': 'backend/monthly_release.py',
    'ih_notice': 'backend/ih_public.py',
    'building_general_permit': 'backend/general_building_permits.py',
    'ih_housing_inventory': 'backend/ih_public.py',
    'reb_apartment_price': 'backend/apartment_prices.py',
    'kosis_living': 'backend/area_living.py',
    'area_national_benchmarks':'backend/area_benchmarks.py',
    'project_locations': 'backend/project_locations.py',
    'seoul_cleanup': 'backend/seoul_cleanup.py',
    'unsold_statistics': 'backend/unsold.py',
    'kosis_age': 'backend/age_distribution.py',
    "national_statistics":"backend/national_statistics.py",
    "ih_supply":"backend/ih_stock.py",
    "incheon_legal_dongs":"backend/public_files.py",
    "building_hub_incheon":"backend/api_samples.py",
    "building_register_recap":"backend/additional_apis.py",
    **{sid:"backend/policy_907_sources.py" for sid in ("policy_907_plan","policy_907_incheon_geometry","incheon_statistics","lh_incheon_sale","lh_incheon_rent","lh_incheon_construction")},
    'molit_demolition': 'backend/demolition.py',
    **{key: 'backend/area_stats.py' for key in ('kosis_housing','kosis_household_size','sgis_area','kosis_employment','kosis_household_forecast')},
    'seoul_plan_notice_pilot': 'backend/plan_notices.py',
    'gyeonggi_plan_notice_pilot': 'backend/plan_notices.py',
    'building_hub_details': 'backend/building_details.py',
    'molit_renewal_inventory': 'backend/official_supply_files.py',
    'lh_completion_plan': 'backend/official_supply_files.py',
    'lh_notice_detail': 'backend/lh_notice_detail.py',
    'lh_block_location': 'backend/lh_block_location.py',
    'lh_reit_progress': 'backend/lh_reit_progress.py',
    'lh_progress': 'backend/lh_progress.py',
    **{key: 'backend/lh_public_history.py' for key in ('lh_supply_history','lh_movein_history','lh_stock')},
    **{key: 'backend/public_files.py' for key in ('legal_dongs','sh_files','gh_files')},
    **{key: 'backend/agency_data.py' for key in ('gh_supply_plan','gh_notice','sh_inventory')},
    'gh_completion_evidence': 'backend/gh_completion.py',
    'complex_approval_reference': 'backend/complex_approvals.py',
    **{key: 'backend/collectors.py' for key in ('policy_907','policy_129','policy_813','urban_930','lh_sale','lh_rent','lh_construction')},
    **{key: 'backend/api_samples.py' for key in ('cheongyak','building_hub','building_register','lh_notice','molit_statistics','sh_supply_plan','sh_redevelopment','vworld')},
    'vworld_district': 'backend/map_data.py',
    'vworld_municipality': 'backend/municipality_geo.py',
    **{key: 'backend/history_data.py' for key in ('policy_history','lh_history')},
}
VALIDATION = {
    'ih_notice': 'iH 공식 게시판 코드·공고 ID·페이지·게시일·본문 제목·첨부 고유번호·원문 해시 대조; 예비/추가/정정과 실제 공급·계약·실입주 분리',
    'building_general_permit': '일반 건축인허가 전용키·mgmPmsrgstPk·법정동·전체 페이지 검증. hhldCnt/hoCnt/fmlyCnt와 실제/예정 착공일을 분리하고 기존 주택인허가에 자동 병합하지 않음',
    'ih_housing_inventory': 'iH 공개 단지 고유번호·명부 7열·재고호수·상세 원문 해시 검증; 운영단지와 광역 프로그램을 분리하고 신규 실적으로 합산하지 않음',
    'reb_apartment_price': '한국부동산원 주간 지수의 기준주·지역·단위·계열 검증; 지수와 실제 거래가격·사업 실적을 구분',
    'kosis_living': 'KOSIS 표·연도·지역·분류 및 단위 검증; 소득·이동·거주기간·점유형태·주택유형·PIR의 통계 범위와 결측을 구분',
    'project_locations': '주소·지역·사업 식별자와 위치 근거 검증; 대표/근사 위치를 필지 PNU나 공식 경계로 해석하지 않음',
    'seoul_cleanup': '서울시 정비사업 공개 페이지의 주소·명칭·추진경과 확인; 신청과 인가, 예정과 실적 구분; 담당자 확정 연결 보존',
    'unsold_statistics': '월·지역 코드·전체/준공 후 지표·시군구 합계 검증; 미제공과 0 구분; 실제 미입주 호수로 전환하지 않음',
    'kosis_age': '공식 통계표·월·지역 코드·21개 연령구간·총계와 시군구 합계 검증; 주민등록 인구 분모와 가구 통계 분모 구분',
    'molit_demolition': '공식 첨부 목록 2018~2024 확인, XLSX 제목·열·서울경기 2행·유형별 합계 검증; 시군구 배분 금지',
    'seoul_plan_notice_pilot': '서울시보 게시일·고시번호·계획명과 PDF 원본 SHA-256 확인; 전체 변경 이력 아님',
    'gyeonggi_plan_notice_pilot': '국토부 게시일·고시번호·계획명과 PDF 원본 SHA-256 확인; 전체 변경 이력 아님',
    'building_hub_details': '법정동별 동별·대지위치 endpoint 전체 페이지와 관리번호·지역 검증; 동일 원천 중복행은 별도 계수 후 1회 저장',
    'molit_renewal_inventory': '전국 정비사업 CSV 원본·헤더·날짜·서울경기 행·자연키 중복 확인; 예정 세대수와 0/해당없음 구분',
    'lh_completion_plan': 'LH 준공예정 CSV 원본·헤더·날짜·서울경기 블록·자연키 중복 확인; 실제 준공/입주 아님',
    'building_hub': '서울·경기 법정동별 페이지 전체와 건수/원천 PK 중복 확인; 실패 시 해당 배치 미적재',
    'building_register': '서울·경기 법정동별 페이지 전체와 건수/원천 PK 중복 확인; 주거 용도 필터; 실패 시 마지막 정상판 유지',
    'cheongyak': '지역·기간별 페이지 총수와 공고 ID 중복 확인; 공고를 실제 입주로 간주하지 않음',
    'lh_notice': '2018년 이후 지역·기간별 페이지 및 공고 ID 중복 검증',
    'gh_notice': '목록 연속 순번과 전체 페이지 수·중복 확인; 모집 공고와 공급실적 분리',
    'gh_completion_evidence': '입주안내 목록 전체 건수·첨부 PDF 해시·발급일 추출 확인; 임시허가와 최종 사용승인 분리, 사업·입주실적 자동 연결 금지',
    'complex_approval_reference': '공식 CSV 전체 헤더·단지/필지 복합키 중복·서울경기 주소·2018년 이후 사용승인일 검증; 실제 입주/정책 공급과 분리',
    'sh_supply_plan': 'ODcloud 메타데이터로 판본 API 확인, 모든 페이지·건수 검증; 공개본 간 호수 미합산',
    'sh_redevelopment': 'ODcloud 메타데이터로 판본 API 확인, 사업 식별자·전체 페이지 검증; 과거 추진현황을 현재 실적으로 간주하지 않음',
    'sh_inventory': '최신 SH sh_plan/sh_project 표본의 사업명·공급유형을 묶어 사업 후보를 파생; 중복 주택형만 합산',
    'lh_progress': '목록 페이지 경계와 사업코드 중복 검증 후 상세 공정률 관측일별 보존',
    'lh_supply_history': '공식 XLSX의 헤더·기준일·서울경기 소재지 검증; 공급현황과 입주실적 분리',
    'lh_movein_history': '공식 첨부의 입주계획 원문 날짜와 사업·블록 유지; 실제 입주로 변환하지 않음',
    'lh_stock': 'LH 단지 공개 파일의 세대수·준공·입주 지정 일정 원문 보존; 신규 공급과 분리',
    'vworld_district': '공공주택지구 공동주택용지 도형을 지구·블록 이름으로 연결, 근거 없는 위치 보간 금지',
    'vworld_municipality': '시군구 경계 폴리곤을 행정구역 코드로 확인',
    'policy_129': '공식 본문·첨부 PDF에 명시된 후보지만 적재; 공동 물량은 임의 배분하지 않음',
    'urban_930': '정책 PDF 본문·별첨의 후보지 행과 합계를 확인; 이름 없는 사업을 생성하지 않음',
    'kosis_housing': '공식 통계표 코드·연도·지역코드와 중복/합계 행 검증',
    'kosis_household_size': '가구원수별 연도·지역·총합 일치 확인',
    'sgis_area': '행정구역 코드·기준연도·소지역 응답 범위 확인; 사업장 종사자와 거주지 인구 구분',
    'molit_statistics': '통계월·지역·지표코드와 월별 구성 검증; 인허가/착공/준공 지표 분리',
}


def build(root):
    root = Path(root).resolve()
    registry = json.loads((root/'source_registry.json').read_text())
    missing = {r['id'] for r in registry} - set(MODULE)
    if missing:
        raise ValueError(f'collector module이 누락된 원천: {sorted(missing)}')
    output = []
    for source in registry:
        sid = source['id']
        output.append({
            'source_id': sid, 'name': source['name'], 'organization': source['org'],
            'source_url': source['url'], 'method': method(sid),
            'collector_entry': 'backend/service.py::HomeService.collect_one',
            'collector_module': MODULE[sid],
            'authentication_env_name': source.get('key_env'),
            'manual_only': bool(source.get('manual_only')),
            'schedule': '수동 실행' if source.get('manual_only') else
                f"기동 후 자동 수집 · 최근 성공 뒤 {source['refresh_days']}일 간격" if source.get('refresh_days') else
                '기동 후 및 기본 24시간 간격 자동 수집',
            'validation_note': VALIDATION.get(sid, '원천별 파서·지역/날짜/중복 검증; 자세한 기준은 collector_module과 배치 stats 참조'),
            'current_records': source['current'],
            'first_source_date': source['first_source_date'],
            'last_source_date': source['last_source_date'],
            'last_attempt_status': source['last_attempt_status'],
            'last_success': source.get('last_success'),
        })
    path = root/'schema/collection_methods.json'
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2)+'\n')
    manifest_path = root/'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    manifest['files']['schema/collection_methods'] = {'path': 'schema/collection_methods.json',
        'records': len(output), 'bytes': path.stat().st_size, 'sha256': sha256_file(path)}
    metrics_path = root/'schema/metric-definitions.json'
    metrics_path.write_text(json.dumps(METRIC_DEFINITIONS, ensure_ascii=False, indent=2)+'\n')
    manifest['files']['schema/metric-definitions'] = {'path': 'schema/metric-definitions.json',
        'bytes': metrics_path.stat().st_size, 'sha256': sha256_file(metrics_path)}
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    return path


if __name__ == '__main__':
    import sys
    if len(sys.argv) != 2:
        raise SystemExit('usage: python -m scripts.export_collection_methods <snapshot-dir>')
    print(build(sys.argv[1]))
