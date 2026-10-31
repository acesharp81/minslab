"""Bound automatic historic work; manual collection remains available."""
from zoneinfo import ZoneInfo

STRUCTURAL_PREFIXES = (
    '공식 파일 링크·기준일 확인 실패', 'GH 공개 CSV 다운로드 링크 미확보',
    'LH 단지정보 공개본 날짜·다운로드 링크 미확보',
    'GH 입주안내 페이지 구조·페이지 수 변경',
)
REPAIR_MARKER = 'SOURCE_REPAIR_REQUIRED:'


def structural_failure(message):
    return str(message or '').startswith(STRUCTURAL_PREFIXES)


def backfill_window_open(instant):
    return 1 <= instant.astimezone(ZoneInfo('Asia/Seoul')).hour < 5


def unchanged_collection(result):
    """Only skip with explicit, internally consistent accounting of all rows."""
    try:
        records = result['records']
        if isinstance(records, bool) or not isinstance(records, int) or records < 0:
            return False
        return (result.get('new', 0) == 0 and result.get('changed', 0) == 0
                and result.get('unchanged', 0) == records)
    except (KeyError, TypeError):
        return False
