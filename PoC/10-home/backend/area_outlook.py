"""Source-labelled comparison of observed housing stock and planned completions.

This is an arithmetic scenario, never an estimate of available dwellings. Gross
completions ignore demolitions and the curated project schedules are incomplete.
"""
from datetime import date

from .area_stats import area_context
from .annual_supply import annual_supply


def build_outlook(region, area, annual, projection, current_year):
    stock_rows = [row for row in area['housing_balance'] if row['housing_units'] is not None and row['households'] is not None]
    if not stock_rows:
        return {'region': region, 'baseline': None, 'years': [], 'note': '같은 연도 주택 재고·가구 자료 미확보'}
    baseline = stock_rows[-1]
    annual_by_year = {row['year']: row for row in annual['rows'] if row['region'] == region}
    current = annual_by_year.get(current_year)
    completion = current['metrics']['준공'] if current else None
    observed_cells = [annual_by_year.get(year, {}).get('metrics', {}).get('준공')
                      for year in range(baseline['year'] + 1, current_year + 1)]
    observed_gross = (sum(cell['units'] for cell in observed_cells)
                      if observed_cells and all(cell and cell['units'] is not None for cell in observed_cells) else None)
    plans = {row['end_year']: row for row in projection.get('future', [])}
    records = []
    for forecast in area['household_forecast']:
        year = forecast['year']
        if year <= baseline['year']:
            continue
        planned = plans.get(year)
        scheduled = planned.get('increment_units') if planned else None
        # The official current-year gross completions are a separate observed
        # flow. Future project plans exclude past events, so these cohorts do
        # not overlap by completion year.
        known_additions = (observed_gross or 0) + (scheduled or 0)
        can_compare = observed_gross is not None and (year == current_year or scheduled is not None)
        scenario_stock = baseline['housing_units'] + known_additions if can_compare else None
        records.append({'year': year, 'forecast_households': forecast['households'],
                        'observed_completion_since_baseline': observed_gross if year == current_year else None,
                        'planned_completion_cumulative': scheduled,
                        'planned_event_count': planned.get('eligible_events', 0) if planned else 0,
                        'excluded_event_count': planned.get('excluded_events', 0) if planned else 0,
                        'scenario_housing_units': scenario_stock,
                        'scenario_gap_units': scenario_stock - forecast['households'] if scenario_stock is not None else None,
                        'coverage': 'PARTIAL_YEAR' if year == current_year and completion and not completion['complete'] else
                                    'KNOWN_SCHEDULE_ONLY' if scheduled is not None else 'SCHEDULE_UNAVAILABLE'})
    return {'region': region, 'baseline': {'year': baseline['year'], 'housing_units': baseline['housing_units'],
            'households': baseline['households'], 'gap_units': baseline['gap_units']},
            'completion_current_year': completion, 'forecast_published_at': area['household_forecast'][0]['published_at'] if area['household_forecast'] else None,
            'years': records,
            'note': '주택 재고 기준연도 + 당해연도 확인 준공 총계 + 중복·용량 충돌을 제외한 사업 준공 예정량의 단순 합. 기준 재고 이후 멸실·공실·민간 미래계획 미확보와 예정 변경을 반영하지 않은 검토 시나리오. 수급 부족 또는 여유의 확정치가 아님.'}


def area_outlook(service, region):
    from .read_scope import projection_reads
    with projection_reads():
        return _area_outlook(service, region)


def _area_outlook(service, region):
    if region not in ('서울특별시', '경기도', '인천광역시'):
        raise ValueError('수도권 지역만 조회할 수 있습니다')
    year = date.today().year
    area = area_context(service, region, None, year)
    annual = annual_supply(service, region, year)
    dashboard = service.supply_dashboard(region=region, analysis_year=year, horizon=10, measure='COMPLETION')
    group = next((row for row in dashboard['groups']['region'] if row['name'] == region), {})
    return build_outlook(region, area, annual, group.get('projection', {}), year)
