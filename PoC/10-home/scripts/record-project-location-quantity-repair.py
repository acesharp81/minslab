"""Record representative-location linkage and compact quantity management changes."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.db import engine_for
from backend.service import HomeService
from backend.project_collection import collection_matrix
from backend.collection_repairs import save
from backend.api_samples import today
s=HomeService(engine_for());m=collection_matrix(s,policy_id='POL_2025_0907')
print(save(s,'project-representative-location-quantity-20261014',dict(
 title='대표 위치 시설 조회·입력창 연결, 교통 분류 및 기본 물량 관리 정비',repair_type='OTHER',status='RESOLVED',base_date=today().isoformat(),
 stages=['BUSINESS','APPROVAL','CONSTRUCTION','SUPPLY','MOVE_IN'],project_ids=[r['id'] for r in m['items']],
 cause='시설 조회가 LH 검증 블록점만 허용해 저장된 대표 좌표가 있는 사업도 시설 정보가 비어 있었다. 주소 필드와 별도 위치 원천의 주소·좌표가 입력창에 연결되지 않았다. GTX를 별도 종류로 분리하고 버스 정류장은 수집하지 않았다. 단계별 목표·진행 물량이 반복 노출되어 기본 수량과 일정 관리의 구분이 불명확했다.',
 action='지도·입력창·시설 조회에 공통 대표 위치 선택 기준 적용. 블록점 외 조회는 대표점 기준 참고 거리로 표시하고 근거 좌표를 보존. 위치 원문 주소를 입력 기본값에 연결하되 사용자 입력 우선. VWorld 버스 정류장 추가, 미정차·폐쇄·폐지 제외 및 반대 방향 동명 정류장 유지. GTX는 지하철로 통합하고 노선·운영 근거 유지. 시설 종류·이름·거리 한 줄 표시. 총 목표 공급량·공급량·입주량을 기본 입력으로 모으고 단계별 물량은 분할 추진 펼침에 보존. 일부 입주 물량을 전체 입주로 확대하지 않도록 집계 보정.',
 impact='정책 197개 사업의 공통 입력·위치 표시 경로 적용. 고덕강일3단지 대표 주소와 동일 좌표를 지도·시설 API·입력창에서 대조. 지하철·버스·학교·병원 4종 요약 및 레이더 유지. 실제 운영 목표량·진행량·주소를 일괄 수정하지 않고 조회 기본값·입력 구조를 정비.',
 remaining='대표점 거리는 실제 필지 경계나 출입구의 이동거리가 아님. 시군구 대표점은 지역 참고용. 버스 노선·배차·실시간 도착은 미연계. 수량과 실적일 근거가 모두 있어야 집계에 반영하며, 모집공고량과 계약량의 의미는 원문에서 구분. 기존 수집 사실과 사용자 이력은 유지.',
 quality_checks=[dict(id='representative-location-primary-quantities',title='좌표·거리 기준 일치 및 물량 보존',kind='CONSISTENCY',layer='DISPLAY',result='PASS',rule='같은 대표 좌표 사용, 근사 위치 명시, 단계 수량 접기 시 값 보존, 부분 입주 전체 확대 금지',evidence='고덕강일3단지 원문 주소·대표 좌표·시설 조회, 고양장항 S2 버스 정류장 및 GTX 통합, 분할 추진 토글·요청 인터셉트 검증',repair='resolve_anchor, InfrastructureContext, ProjectLocation, project_profile, policy_delivery, ProjectWorkspace',completion_criteria='확보된 대표 위치 및 근거 표시; 기본 수량 3개와 단계 일정 표시; 원천 물량 보존',checked_at=today().isoformat(),checked_scope='자동 회귀·운영 API·관리자 및 모바일 화면, 운영 입력 저장 차단')]
)))
