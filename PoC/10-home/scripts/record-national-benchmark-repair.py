"""Record the national benchmark definition and cross-source comparability checks."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.db import engine_for
from backend.service import HomeService
from backend.collection_repairs import save
from backend.api_samples import today
s=HomeService(engine_for())
projects=s.projects(policy_id='POL_2025_0907')
print(save(s,'national-location-benchmarks-20261014',dict(
 title='입지 연령·가구·산업 지표에 동일 시점 전국 구성비 비교 추가',repair_type='OTHER',status='RESOLVED',base_date=today().isoformat(),
 stages=['POLICY','BUSINESS','APPROVAL','CONSTRUCTION','SUPPLY','MOVE_IN'],project_ids=[r['id'] for r in projects],
 cause='지역 수치만 표시하여 전국 평균과 비교할 수 없었다. 인구 원수를 직접 겹치거나 서로 다른 연도·산업 묶음의 비율을 비교하면 해석 오류가 생긴다.',
 action='KOSIS 전국 00 코드의 남녀 연령·일반가구 및 SGIS 전국 종사자를 별도 수집. 연령 점선은 전국 구성비를 지역 총인구로 환산. 항목별 가구·산업 비율에 전국 평균을 병기. 지역·전국 기준시점과 산업 분류를 맞추고 기타는 양쪽 모두 지역 상위 5개 산업을 제외한 동일 범위로 계산.',
 impact='사업 입지 분석 공통 적용. 2026-09 인구, 2025 가구, 2024 산업. 전국 연령·남녀 및 가구 합계 검증, SGIS 17개 시도 합계와 전국 총계 교차 검증. 505개 백엔드 테스트와 운영 브라우저 점선·11개 범례 비교 검증 통과.',
 remaining='전국 평균은 전국 전체 중 항목 비율이며 시군구 비율의 단순 평균이 아님. 지역과 같은 시점 자료 또는 분류가 없으면 비교 미확보로 표시. 산업별 종사자는 직업별 분포와 구분. 지역 분류 미확인 인원은 기타에 포함하고 표시한다.'
)))
