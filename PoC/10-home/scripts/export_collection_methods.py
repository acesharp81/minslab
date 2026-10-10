"""Attach per-source collector implementation and extraction checks to a HOME export."""
import json
from pathlib import Path

from scripts.verify_export import sha256_file
from scripts.write_data_sharing_guide import method

METRIC_DEFINITIONS = {
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
                   'households': '가구 · 일반가구 수'},
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
    'agency_stock': {
        'time_field': 'source_date / dataset_version', 'basis': '기관 공개 관리·매입 재고',
        'fields': {'units': '호 · 해당 공개본의 재고 세대수, unit_basis 확인'},
        'do_not_combine_with': '공개본 간 합계 또는 신규 공급실적과 혼용 금지'},
}

MODULE = {
    **{key: 'backend/area_stats.py' for key in ('kosis_housing','kosis_household_size','sgis_area','kosis_employment','kosis_household_forecast')},
    'lh_block_location': 'backend/lh_block_location.py',
    'lh_reit_progress': 'backend/lh_reit_progress.py',
    'lh_progress': 'backend/lh_progress.py',
    **{key: 'backend/lh_public_history.py' for key in ('lh_supply_history','lh_movein_history','lh_stock')},
    **{key: 'backend/public_files.py' for key in ('legal_dongs','sh_files','gh_files')},
    **{key: 'backend/agency_data.py' for key in ('gh_supply_plan','gh_notice','sh_inventory')},
    **{key: 'backend/collectors.py' for key in ('policy_907','policy_129','policy_813','urban_930','lh_sale','lh_rent','lh_construction')},
    **{key: 'backend/api_samples.py' for key in ('cheongyak','building_hub','building_register','lh_notice','molit_statistics','sh_supply_plan','sh_redevelopment','vworld')},
    'vworld_district': 'backend/map_data.py',
    'vworld_municipality': 'backend/municipality_geo.py',
    **{key: 'backend/history_data.py' for key in ('policy_history','lh_history')},
}
VALIDATION = {
    'building_hub': '서울·경기 법정동별 페이지 전체와 건수/원천 PK 중복 확인; 실패 시 해당 배치 미적재',
    'building_register': '서울·경기 법정동별 페이지 전체와 건수/원천 PK 중복 확인; 주거 용도 필터; 실패 시 마지막 정상판 유지',
    'cheongyak': '지역·기간별 페이지 총수와 공고 ID 중복 확인; 공고를 실제 입주로 간주하지 않음',
    'lh_notice': '2018년 이후 지역·기간별 페이지 및 공고 ID 중복 검증',
    'gh_notice': '목록 연속 순번과 전체 페이지 수·중복 확인; 모집 공고와 공급실적 분리',
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
            'schedule': '수동 실행' if source.get('manual_only') else '기동 후 및 기본 24시간 간격 자동 수집',
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
