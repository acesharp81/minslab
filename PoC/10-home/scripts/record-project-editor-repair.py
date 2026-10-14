"""Record the reviewed display repair; does not mutate project/source facts."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.db import engine_for
from backend.service import HomeService
from backend.project_collection import collection_matrix
from backend.collection_repairs import save
from backend.api_samples import today

service=HomeService(engine_for())
matrix=collection_matrix(service,policy_id='POL_2025_0907')
month_rows=[(p['id'],t) for p in matrix['items'] for cell in p['cells'].values() for t in cell.get('targets',[]) if len(t.get('date') or '') in (4,7)]
result=save(service,'project-editor-collected-display-20261014',dict(
 title='사업정보 편집 화면의 수집 근거 누락 표시·월 단위 목표 공란 개선',repair_type='OTHER',status='RESOLVED',base_date=today().isoformat(),
 stages=['POLICY','BUSINESS','APPROVAL','CONSTRUCTION','SUPPLY','MOVE_IN'],project_ids=[p['id'] for p in matrix['items']],
 cause='편집 화면이 원천 project 필드와 일 단위 목표만 표시하고, 이미 연결된 단계별 실적·문서는 근거 팝업 안에만 표시했다. YYYY-MM/YYYY 일정이 날짜 입력칸에서 공란 처리됐고, 검토 기록 체크박스를 확인 승인으로 표현하여 수집값 반영의 선행조건처럼 보였다.',
 action='수집 계획과 실적·상태·문서를 별도 열로 편집 화면 상단에 표출. 월/연도 일정은 원문 정밀도와 월말/연말 변환 기준을 함께 표시. 상충 일정·일부 범위·실적을 사업 전체 목표로 자동 채택하지 않음. 체크박스는 담당자 검토 기록(선택)으로 명명하고 기본 접음. 미확보 필드와 수집값 자동 반영을 구분.',
 impact=f"9.7 소속 {len(matrix['items'])}개 사업 공통 적용. 월·연도 일정 근거 {len(month_rows)}건, 해당 자료를 가진 사업 {len(set(pid for pid,_ in month_rows))}개. 자료 표시 개선이며 원천·목표·매핑·실적값을 일괄 변경하지 않음.",
 remaining='원문–사업 연결 REVIEW 상태는 별도 원천 연결 검증 필요. 공정률 미제공을 준공 자료만으로 100% 원천값으로 생성하지 않으며, 입주 지정기간은 실제 입주 실적으로 전환하지 않음.',
 quality_checks=[dict(id='editor-source-visibility',title='수집값 표출과 목표 날짜 정밀도',kind='CONSISTENCY',layer='DISPLAY',result='PASS',rule='저장된 단계 근거를 검토 체크 여부와 무관하게 표출하며 날짜 정밀도를 보존',evidence='마곡17: 분양공고 2026-02-27 381호, 사용검사 2026-07-31, 입주 시작 예정 2026-08-28. 실제 준공일은 목표 입력칸에 복사하지 않음.',repair='project_profile.target_default 및 사업정보 수집근거 표 추가',completion_criteria='월 일정 정상 표시, 원문 근거 직접 조회, 검토 체크박스가 집계 조건이 아님을 설명',checked_at=today().isoformat(),checked_scope='9.7 사업 전체 공통 코드·마곡17 운영 브라우저 검증')]))
print(result)
