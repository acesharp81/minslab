"""Explain configured collection behavior, without claiming complete discovery."""
import os


def duration(seconds):
    seconds=int(seconds)
    if seconds % 86400 == 0:
        days = seconds // 86400
        return '매일' if days == 1 else f'{days}일마다'
    return f'{seconds // 3600}시간마다' if seconds % 3600 == 0 else f'{seconds // 60}분마다'


def operations(source, stats=None, scheduler_running=None):
    from .collection_jobs import FAST
    stats = stats or {}
    sid, mode = source['id'], source.get('collection_mode')
    regular = FAST.get(sid, source.get('refresh_days', 1) * 86400)
    backfill = bool(source.get('backfill_seconds') and
                    (stats.get('scope_remaining_dongs', 0) > 0 or stats.get('backfill_pending')))
    interval = source['backfill_seconds'] if backfill else regular
    keys = [source.get('key_env'), source.get('fallback_key_env')]
    key_ready = any(os.environ.get(k, '').strip() for k in keys if k)
    enabled = os.environ.get('POC10_AUTO_COLLECT', 'true').lower() == 'true'
    if scheduler_running is not None:enabled = scheduler_running
    manual = source.get('manual_only', False)
    if mode == 'AI_DISCOVERY':
        state, frequency = 'AI 수집 설정에서 실행', '신규 자료 검토에서 예약 관리'
    elif source.get('implemented', True) is False:
        state, frequency = '연결 준비', '정기 수집 없음'
    elif manual:
        state, frequency = '수동 실행', '필요 시 실행'
    elif source.get('requires_key_for_schedule') and not key_ready:
        state, frequency = '자동 수집 대기 · API 키 필요', '예정 ' + duration(interval)
    elif not enabled:
        state, frequency = '자동 수집 일시 중지', '설정 ' + duration(interval)
    else:
        state, frequency = '자동 수집', duration(interval)
    tags = [dict(label=state, kind='manual' if manual else 'auto'),
            dict(label=frequency, kind='period')]
    discovery = '등록된 원천·조회 조건을 재조회합니다. 전체 공개자료의 신규 게시물을 모두 탐색한다는 뜻은 아닙니다.'
    discovery_tag = '등록 범위 재조회'
    parser = '출처별 API·HTML·파일 파서로 항목을 추출하고 수량·날짜 형식을 정리합니다.'
    pdf = ''
    manual_note = '작업자가 수집 범위와 실행 시점을 정합니다.' if manual else ''
    if mode == 'AI_DISCOVERY':
        discovery_tag = '공개 자료 자동 탐색'
        discovery = '신규 자료 검토의 AI 자료 수집 자동화에서 등록 출처·뉴스 검색·추가 URL을 탐색합니다. 전수 수집을 보장하지 않습니다.'
        parser = 'Solar 단독 또는 mini 1차·5.4 재검토로 원문 근거와 검토 질문을 정리합니다. 자료 연결·물량 승인과 별도입니다.'
        manual_note = '예약·중지·비용 한도는 AI 수집 설정에서 관리합니다.'
    elif mode == 'PUBLICATION_WATCH':
        discovery_tag = '신규 게시물 탐색'
        discovery = '등록된 공식 보도자료 최신 목록 또는 언론사 RSS에서 최근 30일 주택 관련 제목·게시일·원문 링크를 매시간 탐색합니다. 모든 기관·언론사 또는 과거 게시물 전수를 포함하지 않습니다.'
        parser = 'HTML/RSS의 식별키·게시일·출처 도메인을 검증합니다. 후보만 보관하며 기사 전문·호수·단계 실적을 자동 확정하지 않습니다.'
    elif sid == 'lh_policy_followup':
        discovery_tag = '지정 문서 재확인'
        discovery = '검토·등록된 LH 보도자료 4건과 공모 1건을 재다운로드합니다. 게시판 전체의 신규 공모를 자동 발견하는 수집기는 아닙니다.'
        parser = 'PDF는 pypdf PdfReader의 layout 텍스트 추출 후 지구·블록·호수·목표월 규칙으로 구조화합니다. HTML은 BeautifulSoup으로 읽습니다.'
        pdf = '표 구조나 수량 검증에 실패한 자료는 오류로 남겨 파서를 점검합니다. 스캔 PDF는 원문을 보관하고 별도 판독·추출 보완이 필요합니다.'
    elif sid == 'eum_housing_notices':
        discovery_tag = '신규 고시 탐색'
        limit=max(1,min(100,int(stats.get('details_per_batch') or 15)))
        discovery = f'수도권 3개 시도, 2025-09-07 이후 고시의 최신 목록과 과거 이어받기 페이지를 조회합니다. 고시 ID로 상세·첨부를 추적하고, 최근 자료와 과거 대기를 나누어 배치당 최대 {limit}건을 처리합니다. 실패 첨부는 미완료로 유지하고 다음날 재시도합니다.'
        parser = 'PDF는 pypdf로 텍스트 추출, HWPX는 XML 본문·표 파싱을 수행합니다.'
        pdf = '보관 HWP·스캔 PDF·이미지를 배치당 최대 4개 복구합니다. HWP는 hwp5txt, OCR_REQUIRED는 한국어 OCR로 최대 4쪽을 추출하며 OCR_REVIEW_REQUIRED로 별도 검토합니다. 지형도면·변환 실패·미처리 자료는 대기로 유지하고 실패는 7일 후 재시도합니다.'
        manual_note = '이미지 표의 문자·수치 판독과 자동 추출되지 않은 항목의 입력은 별도 수동 보완 대상으로 관리합니다.'
    elif sid == 'lh_department_plans':
        discovery_tag = '등록 게시글 첨부 탐색'
        discovery = '등록된 LH 업무계획 게시글의 첨부 링크·제목·연도를 다시 읽습니다. 2025년부터 현재 연도까지의 업무계획 첨부가 대상이며 모든 부서 게시판을 검색하지 않습니다.'
        parser = 'HWPX ZIP 내부 XML에서 문단과 표를 추출합니다.'
        pdf = ''
    elif sid == 'molit_monthly_release':
        discovery_tag = '최신 월 PDF 탐색'
        discovery = 'e-나라지표의 첨부 목록에서 주택통계 제목·연월·PDF 링크를 찾아 가장 최신 월을 선택합니다.'
        parser = 'pypdf layout 텍스트 추출 후 인허가 표의 연월·지역·열을 규칙으로 읽고 수도권 합계를 검산합니다.'
        pdf = '이미지 표나 형식이 변경된 표는 별도 판독·파서 점검 대상으로 남깁니다.'
    elif mode == 'AGENCY_PLAN_FILE':
        discovery_tag = '파일 링크·판본 감지'
        discovery = '등록된 공공데이터포털 상세 페이지의 contentUrl 다운로드 링크와 파일명 기준일을 매번 읽습니다. 같은 데이터셋의 교체 파일은 감지하지만 새 데이터셋 ID는 자동 등록하지 않습니다.'
        parser = 'CSV 인코딩·필수 열·행 식별키·호수·일정 규칙으로 파싱합니다.'
        pdf = ''
    elif sid in {'policy_907', 'policy_907_plan', 'policy_129', 'urban_930'}:
        discovery_tag = '정책 원문 재확인'
        discovery = '등록된 정책 본문·첨부 URL을 재조회합니다. 새로운 정책 게시물 전체를 자동 검색하는 경로가 아닙니다.'
        parser = 'HTML·PDF 텍스트를 파싱하고 문서에 적힌 항목명과 수량을 자료별 추출 규칙으로 구조화합니다.'
        pdf = 'PDF 텍스트는 pypdf로 읽습니다. 이미지 표 및 새로운 문서 구조는 별도 판독·파서 보완이 필요합니다.'
    elif mode == 'RAW_REPLAY':
        discovery_tag = '보관 원문 재처리'
        discovery = '이미 보관된 원문을 수동 실행으로 다시 추출합니다. 외부 신규 자료를 발견하는 수집은 아닙니다.'
        manual_note = '작업자가 재처리 범위와 실행 시점을 결정합니다.'
    elif sid in {'lh_construction', 'lh_incheon_construction', 'lh_history'}:
        discovery_tag = '공사현황 첨부 탐색'
        discovery = ('등록 게시글에서 날짜가 있는 DOCX 첨부 링크를 찾아 기간 내 판본을 누적 수집합니다.'
                     if sid == 'lh_history' else
                     '등록 게시글의 DOCX 첨부 제목에서 기준일을 읽고 가장 최신 파일을 선택합니다. 같은 게시글의 새 첨부는 감지하지만 다른 게시글까지 전수 검색하지 않습니다.')
        parser = 'DOCX ZIP 내부 word/document.xml의 표를 읽고 공종·블록·호수·착공일·공정률 열을 검증합니다.'
        pdf = ''
    elif source.get('key_env'):
        discovery_tag = 'API 페이지 조회'
        discovery = '설정된 API·지역·기간 조건의 페이지를 조회하고 원천 식별키를 비교합니다. 성공한 조회 범위만 완료로 기록하며, 조건 밖 자료나 원천 미입력 값은 자동 생성하지 않습니다.'
        parser = 'API 응답에서 항목별 값을 읽고 식별키·수량·날짜 형식을 정리합니다.'
        pdf = ''
    elif sid in {'lh_sale', 'lh_rent', 'lh_incheon_sale', 'lh_incheon_rent'}:
        discovery_tag = '공급계획 표 재조회'
        discovery = '현재 공개된 공급계획 표의 전체 페이지를 읽고 게시 총건수와 조회 행 수를 대조합니다. 블록·유형·면적·월로 중복을 검사하며 공개 전 계획은 가져올 수 없습니다.'
        parser = 'BeautifulSoup HTML 표 파싱과 수량·월 검산을 사용합니다.'
        pdf = ''
    tags.append(dict(label=discovery_tag, kind='scope'))
    if 'pypdf' in parser or 'pypdf' in pdf:
        tags.append(dict(label='PDF 텍스트 추출', kind='parser'))
    return dict(tags=tags, mode=state, frequency=frequency, interval_seconds=interval,
                regular_interval_seconds=regular, backfill=backfill,
                schedule_note=('미조회 보충 중 ' + duration(interval) + ', 통상 ' + duration(regular) + '. ' if backfill else '') +
                '정상 수집 이후 재실행 기준 간격입니다. 예약 점검·대기열·호출 제한·실패 재시도로 실제 시각은 달라질 수 있습니다.',
                discovery=discovery, parser=parser, pdf=pdf, manual=manual_note,
                changes='원문 SHA-256과 레코드 식별키·내용 해시를 보존합니다. 동일 자료는 유지하고 변경 자료는 개정 이력을 남깁니다. 원문 다운로드와 항목 추출은 구분하며, 파일 확보만으로 전처리 완료로 판단하지 않습니다.')
