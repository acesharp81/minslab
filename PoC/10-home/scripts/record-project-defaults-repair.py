"""Record source/editor consistency repair and compact three-column overview."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.db import engine_for
from backend.service import HomeService
from backend.project_collection import collection_matrix
from backend.collection_repairs import save
from backend.api_samples import today
s=HomeService(engine_for());m=collection_matrix(s,policy_id='POL_2025_0907')
print(save(s,'project-linked-defaults-three-columns-20261014',dict(
 title='단계 수집표–입력창 수집값 누락 정비 및 사업 개요·지도·입지 3열 요약',repair_type='OTHER',status='RESOLVED',base_date=today().isoformat(),
 stages=['BUSINESS','CONSTRUCTION','SUPPLY','MOVE_IN'],project_ids=[r['id'] for r in m['items']],
 cause='착공 사건일과 공정률 관측일을 동일한 날짜 집합으로 비교하여 상충으로 판정. 대표 사업 레코드에 공정률이 없으면 연결 원천 공정률을 입력창에서 누락. source_events의 예정 물량을 단계 셀과 연결 facts 생성 중 누락. 상태·예정 근거만 확보된 단계에도 단순 미확보 문구를 표시해 실제 데이터 누락과 혼동.',
 action='공정률 관측을 착공 사건일 비교에서 제외. 전체 범위의 같은 최신 관측일에 공정률이 일치하는 경우에만 연결 원천값을 기본 표시하고 0% 보존, 사용자 입력 우선. 원천·연결 판본·검토 상태·수집 방법을 서류철에 표시. source_events 예정 물량 전달. 기존 동일 범위 연결은 저장된 원천 판본의 같은 단계·날짜·종류와 대조하여 누락 물량만 복원하고 Audit 기록. 상태 근거·예정 정보·원천 항목 미제공을 별도 설명. 사업 개요–지도–입지 요약을 1행 3열로 배치, 기존 시설 상대 위치도 유지, 상세 목록·근거는 펼침 처리.',
 impact='9.7 정책 197개 사업 점검. 착공·관측일 혼동 137개, 원천 필드가 비어 있는 연결 공정률 기본 표시 32개. 동일 범위 46개 사업의 연결 46건에서 예정 물량 47건 복원. 부천대장 A2 착공 2026-02-01, 공정률 0% / 2026-07-01, 공급 예정 2026-09 / 548호, 준공 예정 2028-05-31 / 548호 표시.',
 remaining='상태·문서 확보는 실제 실적일·물량 확보와 다름. 예정 공급을 실제 공급으로 간주하지 않음. 연결 검토 상태와 부분 범위는 유지하며 부분 범위·실제 물량을 전체 사업 물량으로 추정하지 않음. 정확한 개별 위치가 없으면 시설 거리 대신 보완 항목 표시. 좁은 화면은 3열을 세로로 배치.',
 quality_checks=[dict(id='linked-defaults-consistency',title='수집표와 입력 기본값 정합성',kind='CONSISTENCY',layer='DISPLAY',result='PASS',rule='실적 사건일/관측일 분리, 0% 보존, 원천 판본 고정, 부분 범위 제외, 사용자 입력 우선',evidence='부천대장 A2 운영 API 및 관리자 입력창, 고덕강일3단지 3열 요약, 고양장항 S2 시설 레이더, 데스크톱·모바일 실브라우저 검증',repair='project_profile, project_collection, evidence_bridge, restore-bridge-plan-units.py, ProjectWorkspace, ProjectLocation',completion_criteria='알려진 수집값이 대응 입력란에 표시되고 출처 조회 가능; 실제값 미확보는 빈칸 및 사유 보존',checked_at=today().isoformat(),checked_scope='자동 회귀 테스트 및 운영 화면, 브라우저 저장 요청 차단')]
)))
