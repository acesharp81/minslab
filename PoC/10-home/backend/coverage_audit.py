"""Query completeness is distinct from population coverage and policy attribution."""
SCOPES = {
 'molit_demolition':('공개된 연도별 멸실 엑셀의 서울·경기 시도 행','미공표 연도·시군구별 멸실량 미확보; 개별 정책 공급량에 배분하지 않음'),
 'seoul_plan_notice_pilot':('서울 공덕1 정비구역 변경 고시 1건 원문','2011년 최초 지정 등 전체 사건 체인·사업 연결은 별도 확인'),
 'gyeonggi_plan_notice_pilot':('경기 고양창릉 지구지정 변경 고시 1건 원문','최초 지정부터 후속 변경까지 전체 사건 체인·사업 연결은 별도 확인'),
 'lh_progress':('LH 공개 공사진행현황 전체 페이지 및 서울·경기 블록별 날짜 이력','등록일과 사진 기준월 구분 · 공개 이력 없는 연도·블록 및 SH·GH 공정률 별도 확인'),
 'lh_reit_progress':('LH 제6호 공공임대리츠 2018 투자보고서','하남미사 A24 기준말 실제 공정률 · 다른 리츠·연도는 미확보'),
 'lh_supply_history':('LH 2020~2025 공공분양 공급현황 XLSX의 서울·경기 전체 행','공고 공급호수 · 준공·실입주량과 구분 · 2018~2019 공급현황 미확보'),
 'lh_movein_history':('LH 현재 공개된 연도별 입주계획 첨부 전체','입주 예정량 · 실제 입주실적과 구분 · 2018~2021 판본 미확보 · 2026 원천 총계 불일치'),
 'lh_stock':('LH 단지정보 CSV 중 주소·지구명으로 서울·경기 확인된 단지','현재 재고와 과거 일정 · 위치 불명·집계 자료 제외 · 당시 월별 공정률 미확보'),
 'molit_renewal_inventory':('국토부 전국 정비사업 통합 CSV 중 서울·경기 현황 행','단일 시점 정비구역 후보 · 지정/변경 원고시와 실제 준공·입주 및 다른 공급 유형 별도'),
 'building_hub_details':('지정 파일럿 법정동의 주택인허가 동별·대지위치 전체 페이지','다른 서울·경기 법정동 미수집 · 동별 구성/필지는 실제 정책 공급실적 아님'),
 'lh_completion_plan':('LH 공공주택 준공예정 CSV 중 서울·경기 블록','준공 예정일·예정 호수 · 실제 준공/입주 증거 아님 · 0/공란은 미확정 가능'),
 'policy_907':('9·7 발표 정책 원문','개별 대상사업 전체 명단·후속 변경 미확보'),
 'policy_129':('1·29 정책 브리핑에 명시된 사업','별첨 34행 검증 · 지구별 물량 일부 미배분 · 후속 변경·이행 근거 미확보'),
 'policy_813':('8·13 발표 정책 원문','개별 대상사업 전체 명단·후속 변경 미확보'),
 'urban_930':('9·30 공식 PDF 후보지 11곳·지정지구 5곳','추진사업 47곳 중 서울·경기 40곳 명단 확보 · 일부 개별 호수·과거 이행 자료 미확보'),
 'sh_files':('SH 관리현황 2024·2025·2026 XLSX 전체','기존 관리 재고 · 연도별 지표 차이 · 신규 정책 공급실적과 구분'),
 'gh_files':('GH 재건축 매입임대 CSV 전체','기존 확보 재고 · GH 전체 신축·진행 사업 목록은 별도 확인'),
 'legal_dongs':('서울·경기 현존 법정동 전체 코드','행정코드 확보 · 해당 지역의 주택 API 수집은 별도 진행'),
 'lh_sale':('LH 올해 서울·경기 분양 공급계획 전체 페이지','과거 연간 계획 판본·타 기관·민간 사업 제외'),
 'lh_rent':('LH 올해 서울·경기 임대 공급계획 전체 페이지','과거 연간 계획 판본·타 기관·민간 사업 제외'),
 'lh_construction':('LH 최신 공사 보고서 중 위치 확인된 서울·경기 사업','위치 불명 계약 제외 · 모든 정부 주택사업 목록 아님'),
 'cheongyak':('서울·경기 APT 분양공고 · 2018년부터 연도별 조회','2018~2019년 응답 0건은 미확보 · 다른 주택 유형 제외'),
 'building_hub':('개포·고덕·진관·이의·다산·덕풍 6개 법정동','서울·경기 전체 법정동 미수집 · 사업 연결 미확정'),
 'building_register':('동일 6개 법정동 주거용 표제부 · 기존 재고 포함','서울·경기 전체 법정동 미수집 · 신규 공급실적과 구분'),
 'lh_notice':('서울·경기·인천 LH 분양·임대·신혼희망타운 공고 · 2018년부터','다기관 공고·원문 첨부별 물량·실적 연결 미확정'),
 'molit_statistics':('서울·경기 월별 분양승인·착공·준공 및 연간 인허가','지역 전체 통계 · 개별 정책·블록 실적으로 배분 불가'),
 'sh_supply_plan':('SH API의 공개된 분양계획 판본 전체','공개 판본 사이 연도 누락 · SH 전체 공급유형 제외'),
 'sh_redevelopment':('SH API 2023년 재개발·재건축 공개본 전체','2023년 기준 · 현재 추진 상태 미확인'),
 'sh_inventory':('수집된 SH 두 데이터셋 최신본 사업 연결','정책 귀속 검토 · SH 전체 사업 목록 아님'),
 'gh_supply_plan':('GH 홈페이지 최신 분양·임대 계획 표 전체','과거 판본·표에 없는 GH 사업 제외 · 물량은 계획'),
 'gh_notice':('GH 홈페이지 주택 공고 전체 페이지 · 2018년부터','추가모집·당첨결과 포함 · 첨부별 물량·정책 연결 미확인'),
 'gh_completion_evidence':('GH 입주안내 목록의 사용검사·승인·임시허가 PDF','사업·건물/공구 연결 미검토 · 실제 입주 호수 아님'),
 'complex_approval_reference':('공시대상 공동주택 단지·필지의 2018년 이후 사용승인 참조','정책사업 연결 미확정 · 파일 모집단과 모든 승인/입주 전수는 다름'),
 'vworld':('청약공고·인허가 일부 주소의 좌표 검증','배치 주소 표본 · 모든 수집 자료 지오코딩 미완료'),
 'vworld_district':('수집 사업명과 매칭되는 공식 공동주택용지','미응답 지구·블록 개별 좌표 미확보'),
 'vworld_municipality':('서울 25구·경기 31시군 공식 행정경계','행정경계 확보와 전체 사업 확보는 별개'),
 'policy_history':('선정한 프로그램 기원·주요 발표 원문','전체 정책 변경·고시 이력 미수집'),
 'lh_history':('LH 공개 게시물의 날짜별 공사 보고서','공개 첨부 밖 과거 공정률·2018~2024 보고서 미확보'),
}


def coverage_audit(sources):
    items=[]
    for source in sources:
        sid=source['id'];stats=source.get('stats',{}); provided=fetched=None
        groups=stats.get('district_counts') or stats.get('region_counts',{})
        if groups and all(isinstance(x, dict) and ('fetched' in x or 'sampled' in x) for x in groups.values()):
            provided=sum(x.get('matching_records',x.get('matching_notices',0)) for x in groups.values())
            fetched=sum(x.get('fetched',x.get('sampled',0)) for x in groups.values())
        elif 'provided' in stats:
            provided,fetched=stats['provided'],stats.get('fetched')
        elif 'file_rows' in stats:
            provided=fetched=stats['file_rows']
        if sid == 'molit_demolition' and stats.get('years'):
            provided = fetched = 2 * len(stats['years'])
        complete=stats.get('complete_query')
        if complete is None and groups and all(isinstance(x, dict) for x in groups.values()):
            complete=all(x.get('complete_query') is True for x in groups.values())
        versions=stats.get('dataset_versions',[])
        if versions:
            provided=fetched=sum(v['records'] for v in versions)
            complete=all(v.get('complete_query') is True for v in versions)
        if sid in ('lh_sale','lh_rent') and provided is None:
            # Legacy metadata recorded the validated page total as raw_rows.
            provided=fetched=stats.get('raw_rows')
            complete=True if provided is not None else None
        series=stats.get('series',[])
        if series:
            provided=fetched=sum(v['records'] for v in series)
            complete=all(v.get('complete_query') is True for v in series)
        scope,gap=SCOPES.get(sid,('등록 원천 범위','전체성 미검증'))
        if 'scope_total_dongs' in stats:
            scope=f"공식 법정동 {stats['scope_total_dongs']:,}개 중 {stats['scope_completed_dongs']:,}개 전체 페이지 누적"
            gap=f"남은 {stats['scope_remaining_dongs']:,}개 동 이어받기 필요 · 정책·사업 연결 미확정"
        dates=stats.get('report_dates',[])
        source_period=(f'{min(stats["years"])} ~ {max(stats["years"])}' if sid == 'molit_demolition' and stats.get('years') else
            f'{min(dates)} ~ {max(dates)}' if dates else
            ' ~ '.join(str(x) for x in (stats.get('period_start'),stats.get('period_end')) if x) or
            stats.get('latest_dataset_version') or stats.get('dataset_version') or stats.get('source_base_date') or '기준일은 원천 상세 참고')
        query_status='PARTIAL' if stats.get('complete_scope') is False else 'VERIFIED' if complete is True else 'PARTIAL' if complete is False else 'UNVERIFIED'
        if not source.get('last_success'): query_status='NOT_COLLECTED'
        items.append(dict(source_id=sid,name=source['name'],evidence_url=source['url'],
            provided_records=provided,fetched_records=fetched,collected_records=source.get('record_count',0),
            query_status=query_status,complete_population=False,scope=scope,gap=gap,source_period=source_period,
            collection_status=source.get('status'),last_success=source.get('last_success')))
    return dict(complete_population=False,items=items,
        notice='조회 조건 내 전체 페이지와 서울·경기 전체 정책·사업 확보는 다릅니다. 수집 성공만으로 전체 확보를 뜻하지 않습니다.',
        remaining_gaps=['LH 공개 이력 밖 연도·블록의 실제 공정 이력 및 SH·GH 공정률', 'SH·GH 및 지자체의 공개본 밖 사업·계획',
            '서울·경기 전체 법정동 인허가·대장과 정책 사업의 개별 연결', '그 밖의 정책 대상사업 전체 명단·후속 변경 이력'])
