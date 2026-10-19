# HOME 요구사항 재검증 · 2026-10-15

평가 버전: `HOME-REQ-20261015`. 대상: PoC10 HOME. 원문 F-01~F-12의 61개 세부 요구사항은 수정하지 않았다. 코드는 현재 `main` 작업 트리 기준이며 미커밋 변경을 포함한다. 점수는 기능에 대한 자체 평가로 공식 인수검사 점수·정책 달성률·전국 자료 확보율이 아니다.

## 재평가 결과

| 구분 | 이전 정밀값 | 최신 |
| --- | ---: | ---: |
| 총점 | 56 / 61 | 58.5 / 61 |
| 기능 충족률 | 91.8% (기존 화면 92%) | 95.9% |
| 세부 충족 / 부분 / 미구현 | 51 / 10 / 0 | 56 / 5 / 0 |

산식은 세부항목별 1점·0.5점·0점을 합산해 61로 나누고 100을 곱한 뒤 소수 첫째 자리로 반올림한다. 12개 항목 백분율을 다시 평균하지 않는다. 기능 평가일과 데이터 기준일은 화면·CSV에서 별도로 제공한다.

| ID | 요구사항 | 점수 | 충족률 |
| --- | --- | ---: | ---: |
| F-01 | 주택공급 현황 통합 조회 | 4.5 / 5 | 90% |
| F-02 | 주택공급 목표 대비 이행실적 관리 | 5 / 5 | 100% |
| F-03 | 공급 단계별 진행상황 관리 | 4.5 / 5 | 90% |
| F-04 | 사업별 상세정보 조회 | 5 / 5 | 100% |
| F-05 | 연도별 공급계획 및 시계열 분석 | 6 / 6 | 100% |
| F-06 | 공급사업 일정 및 지연 관리 | 5 / 5 | 100% |
| F-07 | 사업 지연 원인 및 병목 관리 | 5 / 5 | 100% |
| F-08 | 기관별·정책별 추진현황 관리 | 4 / 4 | 100% |
| F-09 | 국민의 공급 예측가능성 지원 | 5 / 5 | 100% |
| F-10 | 공급정보의 신뢰성 및 갱신 관리 | 5.5 / 6 | 91.7% |
| F-11 | 정책 이행상황 종합 판단 | 4 / 5 | 80% |
| F-12 | 향후 공급실적 예측 및 시나리오 분석 | 5 / 5 | 100% |

## 점수가 변경된 세부항목

기존 평가는 일부 항목에서 기능 구현과 데이터 확보를 섞거나, 원문이 요구하지 않은 학습형 예측을 필수 조건으로 사용했다. 현재 구현·회귀 근거와 원문을 대조해 아래 다섯 판정을 갱신했다.

| 항목 | 이전 → 현재 | 재검증 근거 |
| --- | ---: | --- |
| F-02.3 | 0.5 → 1 | 지역·연도 비교와 기관·단계·연도별 승인 배정 목표/확인 실적 집계 구현. 운영 배정자료 미등록은 데이터 확보 지표에서 별도 표시 |
| F-05.3 | 0.5 → 1 | 착공·공급·준공·입주 단계별 예정량과 연도별 누적 계획 조회. 실제 입주량 미확보는 별도 상태로 유지 |
| F-05.4 | 0.5 → 1 | 원천 일정과 평균기간 보완 목표를 기준으로 향후 단계별 예정 시점·물량을 표시하며 추정 가정과 근거를 보존 |
| F-09.2 | 0.5 → 1 | 선택 원장의 연도별 착공·준공·입주 예정량과 공급 단계 계획을 규모·일정으로 제공. 지역 전체 시장 전망과 모집단을 분리 |
| F-12.1 | 0.5 → 1 | 현재 단계·원천 일정과 보유 표본의 평균기간을 이용해 향후 일정·물량을 산정. 학습형 예측은 원 요구사항의 필수 조건이 아님 |

## 부분 충족으로 유지한 항목

| 항목 | 원문 | 남은 제한 |
| --- | --- | --- |
| F-01.1 | 전국 및 지역별 주택공급 현황을 통합적으로 조회할 수 있어야 한다. | 수도권 개별 사업 지도와 전국·시도 참고 통계를 제공하나 전국 개별 사업의 동일 키·정책 귀속 통합은 미완료 |
| F-03.5 | 단계별 대상물량의 차이와 중복 집계 여부를 검증할 수 있어야 한다. | 합계 보존 검증은 구현, 전체 원천의 복합·부분 사업 정체성 확정은 미완성 |
| F-10.3 | 정책·사업·공급단계 간 집계 기준의 일관성을 검증할 수 있어야 한다. | 동일 범위 합계 검증 지원, 전체 자료의 의미적 정합성은 계속 검토 |
| F-11.1 | 전국 및 지역별 공급정책의 전체 이행상황을 확인할 수 있어야 한다. | 9·7 수도권 종합 화면 지원, 전국 정책 통합 판단 미완성 |
| F-11.4 | 향후 일정에 영향을 미칠 수 있는 주요 위험 요인을 확인할 수 있어야 한다. | 지역여건의 가격·주택보급률·미분양·향후 일정과 추진현황의 갭·병목을 조회. 지역 참고 통계의 개별 사업 귀속·실미입주 위험·외부 원인의 자동 판정은 미완료 |

## 최신 데이터 확보 스냅샷

운영 HTTPS의 `GET /poc/home/api/requirements-status`에서 확인했다. 기준일 2026-10-15, 등록 사업 기록 197건, 사업화~입주 단계 셀 985개. 중복 가능 원천 기록이며 고유 실사업·전국 모집단의 분모가 아니다. 추정 제외/포함은 같은 분모를 사용한다. 건설 셀은 착공·준공을 통합한 확보 지표다.

| ID · 지표 | 추정 제외 | 추정 포함 |
| --- | ---: | ---: |
| F-01 · 지도 위치 근거가 있는 사업 기록 | 96/197 · 48.7% | 185/197 · 93.9% |
| F-02 · 일정 목표와 실적 근거를 함께 확보한 셀 | 241/985 · 24.5% | 655/985 · 66.5% |
| F-03 · 실적·진척 근거를 확보한 셀 | 312/985 · 31.7% | 655/985 · 66.5% |
| F-04 · 사업명·지역·계획량을 확보한 기록 | 190/197 · 96.4% | 197/197 · 100.0% |
| F-05 · 날짜가 있는 단계 계획을 확보한 사업 | 189/197 · 95.9% | 197/197 · 100.0% |
| F-06 · 담당자 승인 최초 기준선 등록 셀 | 276/985 · 28.0% | 985/985 · 100.0% |
| F-07 · 원인·기관·조치·기한이 채워진 병목 기록 | 0/0 · 산정 불가 | 0/0 · 산정 불가 |
| F-08 · 승인 기관 배정 목표를 등록한 사업 | 0/197 · 0.0% | 0/197 · 0.0% |
| F-09 · 공급 또는 입주 예정일이 있는 사업 | 135/197 · 68.5% | 197/197 · 100.0% |
| F-10 · 원천 링크와 기준일이 있는 사업 | 197/197 · 100.0% | 197/197 · 100.0% |
| F-11 · 목표·실적 동시 확보 셀 | 241/985 · 24.5% | 655/985 · 66.5% |
| F-12 · 가정·기준 원장을 저장한 시나리오 | 0/0 · 산정 불가 | 0/0 · 산정 불가 |

기관 배정 목표 0/197건, 병목·시나리오 분모 0건은 입력·실제 자료 확보 과제다. 0분모를 100%나 0%로 바꾸지 않는다. F-02/F-11 데이터 지표는 같은 목표·실적 동시 확보 셀이므로 합산하지 않는다. 향후 공급 예정과 입주 시작은 실제 거주 호수와 구분한다.

## 확인한 최근 변경 기능

- 지도·사업 단계 카드: 해당 단계 측정값과 확인된 기간, 후속단계 누적 도달량·목표의 분리, 동일한 2% 부족률 기준.
- 사업 상세: 일정·분양/임대 조건·시설 상세, 근거·미확보 표시.
- 지역여건: 네 주제로 구성한 가구/주택·가격/미분양·실적/구성·향후 목표, 지역 전체와 선택 정책 원장의 분리.
- 추진현황: 정책·프로그램 관리 통계, 기관별 비교·지연 최대값과 미래 가구/공급 비교.
- 평균기간·병행 공구 목표 보완: 수집 일정 우선, 표본과 가정 보존, 미래 산정을 실제 사건으로 생성하지 않음.
- 보고서 MD: 네 화면의 원 정밀도·0/미확보·선택 조건·근거·61개 요구사항, 조회 도중 범위 변경·비동기 재렌더 경계.

## 검증 결과와 재현

- 관련 Python unittest 57건 통과: 격리 SQLite의 요구사항 확보 지표·기관/일정/시나리오·단계 비교·평균기간.
- 추가 기능 pytest 37건, 별도 subtest 24건 통과: 주택시장 지표·지도 요약·시설 상세·기반시설.
- Node 18건 통과: 요구사항 산식·MD·지도 실제값·공급 전망.
- 실제 HTTPS 브라우저: 12항목/61원문, 95.9%·평가일·버전, 부분항목 필터 4개, 검색·우선순위, CSV 12행·점수/근거/기준일, 원천 화면 연결, 1440px/390px, 가로 넘침·JavaScript 오류 없음.
- 사업 자료 변경·수집 실행·운영 기관 배정/병목/시나리오 저장은 수행하지 않았다. 자료 입력 기능은 격리 회귀 결과와 기존 구현 근거로 평가했다.

```bash
cd PoC/10-home
node --test tests/js/requirements-audit.test.cjs tests/js/report-md.test.cjs tests/js/map-progress-summary.test.cjs tests/js/policy-report-projection.test.cjs
HOME_CHECK_BASE=https://www.minslab.kr node scripts/check-requirements-manual.cjs
```

브라우저 실행기는 현재 호스트의 Playwright·Chromium 경로를 사용한다. 다른 환경에서는 해당 경로를 맞춘다. `HOME_CHECK_LOCAL_REQUIREMENTS=1`은 소스의 요구사항 HTML/JS만 읽기 전용 운영 API 위에 덮어 검수하며, 최종 기록은 이 옵션 없이 실제 배포 파일로 확인했다. 기존 프로그램·사업의 선택 범위/6단계/이력/입지 검사는 `HOME_CHECK_DETAILS=1`로 유지하며, 이번 운영 읽기 전용 점검에는 그 추가 분기를 실행하지 않았다.

## 구현·검증 근거

| ID | 코드·회귀 근거 |
| --- | --- |
| F-01 | backend/supply_dashboard.py · map_progress.py · housing_indicators.py · map-progress-tracking.js · tests/test_map_progress.py |
| F-02 | backend/policy_delivery.py · policy_delivery_comparison.py · execution_insights.py · policy-stage-flow.js · tests/test_execution_insights.py · tests/test_policy_delivery_comparison.py |
| F-03 | backend/map_stage_state.py · evidence_bridge.py · map_progress.py · tests/js/map-progress-summary.test.cjs |
| F-04 | project-information.js · project-location.js · scope-evidence.js · backend/facility_details.py · tests/test_facility_details.py |
| F-05 | backend/policy_delivery_comparison.py · housing_indicators.py:future_schedules · officer_duration.py · policy-stage-flow.js · tests/test_policy_delivery_comparison.py · tests/test_officer_duration.py |
| F-06 | backend/delivery_operations.py · delivery-operations.js · execution_insights.py |
| F-07 | delivery-operations.js: filterCases / summarizeCases / caseAnalysis |
| F-08 | home_program_mapping · backend/delivery_operations.py · execution_agency(kind) · execution_insights.py |
| F-09 | backend/plan_schedule.py · housing_indicators.py:future_schedules · lh_notice_detail.py · housing-indicators.js · project-information.js · tests/test_housing_indicators.py |
| F-10 | backend/collection_lineage.py · collection_repairs.py · api_requests.py · report-md.js · tests/js/report-md.test.cjs |
| F-11 | policy-decision.js · policy-report.js · backend/housing_indicators.py · occupancy_monitor.py · tests/test_housing_indicators.py |
| F-12 | backend/officer_duration.py · delivery_operations.py:scenario_comparison · policy-report.js · tests/test_officer_duration.py · tests/test_delivery_operations.py · tests/js/policy-report-projection.test.cjs |

원시 점수·항목별 판정·데이터 스냅샷·소스 해시는 [JSON](HOME_REQUIREMENTS_REVIEW_20261015.json)에 보존한다. 과거 `HOME_REQUIREMENTS_AUDIT_20261012.*`는 당시 평가로 남긴다.
