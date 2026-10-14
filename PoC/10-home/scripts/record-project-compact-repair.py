"""Record managed-field display and demographic collection changes without editing source project facts."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.db import engine_for
from backend.service import HomeService
from backend.project_collection import collection_matrix
from backend.collection_repairs import save
from backend.api_samples import today
s=HomeService(engine_for());matrix=collection_matrix(s,policy_id='POL_2025_0907')
ages=[r for r in s.rows('area_stat') if r.get('metric_group')=='kosis_age' and r.get('sex_age_classes')]
print(save(s,'project-managed-fields-age-charts-20261014',dict(
 title='사업 목표·진행값 입력 구조 개편 및 남녀 연령·입지 차트 보완',repair_type='OTHER',status='RESOLVED',base_date=today().isoformat(),
 stages=['POLICY','BUSINESS','APPROVAL','CONSTRUCTION','SUPPLY','MOVE_IN'],project_ids=[r['id'] for r in matrix['items']],
 cause='수집값 긴 표와 목표 입력칸이 분리되어 관리 항목과 근거의 대응이 불명확했고 화면 스크롤이 길었다. 남녀 연령별 자료는 총인구만 수집하고 있었으며 입지 지표가 세로로 나열됐다.',
 action='목표일·목표량·진행일·진행량의 6단계 입력표에 수집값을 기본 적용. 출처·수집 방법·부분 범위·검토 상태는 서류철 팝업으로 이동. 사용자 진행값을 원천과 별도 보존하고 정책 진행 및 수집 현황에 연결. 확인 체크박스 제거, 과거 이력은 보존. 남녀 T3/T4를 기존 KOSIS 연령표에서 추가 수집하고 3열 입지 차트로 개편.',
 impact=f"9.7 사업 {len(matrix['items'])}개 공통 적용. 남녀 연령 원천 {len(ages)}개 지역 확보. 1366×768 및 1440×900 입력 화면 내부 세로 스크롤 없음. 운영 사용자 목표·실적·매핑값의 일괄 변경은 없음.",
 remaining='사업 원천 연결 검토와 실제 진행일 미확보는 계속 구분. 산업별 종사자는 직업별 분류와 다름. 지역·기준시점이 다른 입지 통계는 범위를 명시하고 미확보는 보간하지 않음. 모바일 표에는 내부 가로 스크롤 적용.',
 quality_checks=[dict(id='managed-values-and-sex-age',title='원천 보존·성별 연령 합계·한 화면 입력 검증',kind='CONSISTENCY',layer='DISPLAY',result='PASS',rule='계획과 실적 구분, 남녀·연령·지역 합계 보존, 수치 쉼표 왕복 변환',evidence='KOSIS DT_1B04005N T2/T3/T4, 2026-09 70개 지역. 마곡17 공급 실적 381호, 준공 확인 2026-07-31, 입주 예정 2026-08-28을 각각 대응 칸에 표시.',repair='project_profile.progress, 관리 입력표, ProjectAreaCharts, age_distribution.parse_sexes',completion_criteria='원천값 수정 없이 출처 조회·입력·원천 복원 및 합계 일치',checked_at=today().isoformat(),checked_scope='백엔드 전체 회귀 및 운영 브라우저, 실제 저장 요청은 차단')]
)))
