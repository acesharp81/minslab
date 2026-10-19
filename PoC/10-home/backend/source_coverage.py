"""Normalize verified query scopes without claiming policy/population completeness."""


def coverage_rows(source_id, stats):
    note = stats.get('scope_note')
    if source_id in ('lh_department_plans','eum_housing_notices'):
        return [dict(endpoint='official_plan_attachments' if source_id=='lh_department_plans' else 'housing_notice_details',
            region=None,area_code=None,source_period='2025~' if source_id=='lh_department_plans' else stats.get('period_start')+'~'+stats.get('period_end'),
            expected_count=stats.get('provided',stats.get('housing_candidates',0)),
            fetched_count=stats.get('fetched',len(stats.get('detail_checked',{}))),
            query_status='COMPLETE_QUERY' if stats.get('complete_query') else 'PARTIAL',
            population_status='PARTIAL_SCOPE',scope_note=note)]
    if source_id=='ih_notice':
        return [dict(endpoint='ih_'+board+'_board_pages',region='인천광역시',area_code=None,
                     source_period=stats.get('period_start')+'~'+stats.get('period_end'),
                     expected_count=meta['pages'],fetched_count=len(meta['queried_pages']),
                     query_status='COMPLETE_QUERY' if meta['complete_window'] and not stats.get('failures') else 'PARTIAL',
                     population_status='PARTIAL_SCOPE',scope_note='배치 조회 페이지 수와 기간 커버리지 · '+(note or ''))
                for board,meta in stats.get('board_checkpoints',{}).items()]
    if source_id == 'lh_notice_detail':
        return [dict(endpoint='project_matched_notice_details',region=None,area_code=None,source_period=None,
            expected_count=stats.get('candidate_notices',0),fetched_count=stats.get('detail_acquired',0),
            query_status='COMPLETE_QUERY' if stats.get('candidate_notices',0)>0 and not stats.get('failed_details') else 'PARTIAL',
            population_status='PARTIAL_SCOPE',scope_note=note)]
    if source_id == 'molit_demolition':
        years = stats.get('years', [])
        return [dict(endpoint='annual_demolition_xlsx', region=region, area_code=None,
            source_period=f'{min(years)}~{max(years)}' if years else None,
            expected_count=len(years), fetched_count=count,
            query_status='COMPLETE_QUERY' if count == len(years) and stats.get('complete_query') else 'PARTIAL',
            population_status='PARTIAL_SCOPE', scope_note='공개 첨부 연도 수 · 시도 단위; 시군구 미제공')
            for region, count in sorted(stats.get('region_counts', {}).items())]
    if source_id in ('building_hub', 'building_hub_incheon', 'building_general_permit', 'building_register', 'building_register_recap') and stats.get('scope_total_dongs'):
        # These counters measure legal dongs, not housing units or projects.
        total = stats['scope_total_dongs']
        done = stats.get('scope_completed_dongs', 0)
        return [dict(endpoint='legal_dong_page_coverage', region=None, area_code=None,
            source_period=None, expected_count=total, fetched_count=done,
            query_status='COMPLETE_QUERY' if done >= total else 'PARTIAL',
            population_status='PARTIAL_SCOPE', scope_note='법정동 조회 수 · ' + (note or '정책사업 연결 미확정'))]
    if source_id == 'complex_approval_reference':
        return [dict(endpoint='official_complex_csv', region=region, area_code=None,
            source_period=stats.get('dataset_version'), expected_count=count, fetched_count=count,
            query_status='COMPLETE_QUERY' if stats.get('complete_query') else 'PARTIAL',
            population_status='PARTIAL_SCOPE', scope_note=stats.get('scope_note'))
            for region, count in sorted(stats.get('region_counts', {}).items())]
    if source_id == 'gh_completion_evidence':
        return [dict(endpoint='gh_movein_notice_list_and_pdf', region='경기도', area_code=None,
            source_period=None, expected_count=stats['provided'], fetched_count=stats['fetched'],
            query_status='COMPLETE_QUERY' if stats.get('complete_query') else 'PARTIAL',
            population_status='PARTIAL_SCOPE', scope_note=stats.get('scope_note'))]
    if source_id in ('seoul_plan_notice_pilot', 'gyeonggi_plan_notice_pilot'):
        return [dict(endpoint='official_notice_pdf', region=item['region'], area_code=None,
            source_period=item['notice_date'], expected_count=1, fetched_count=1,
            query_status='COMPLETE_QUERY', population_status='PARTIAL_SCOPE', scope_note=note)
            for item in stats.get('notices', [])]
    if source_id == 'building_hub_details':
        return [dict(endpoint=item['endpoint'], region=item['region'],
            area_code=item['legal_dong_code'], source_period=None,
            expected_count=item['expected'], fetched_count=item['fetched'],
            query_status='COMPLETE_QUERY' if item['complete_query'] and item['expected'] == item['fetched'] else 'PARTIAL',
            population_status='PARTIAL_SCOPE', scope_note=note)
            for item in stats.get('endpoint_coverage', [])]
    if source_id in ('molit_renewal_inventory', 'lh_completion_plan'):
        return [dict(endpoint='official_csv', region=region, area_code=None,
            source_period=stats.get('dataset_version'), expected_count=count, fetched_count=count,
            query_status='COMPLETE_QUERY' if stats.get('complete_query') else 'PARTIAL',
            population_status='PARTIAL_SCOPE', scope_note=note)
            for region, count in sorted(stats.get('region_counts', {}).items())]
    return []
