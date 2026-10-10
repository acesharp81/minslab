# HOME 통합 데이터셋 구축 PoC — 구현 계획

최신 구현(2026-10-07): 정책 → 프로그램 → 사업 관계를 두 단계로 분리해 관리합니다. 정책 미연계 프로그램·사업은 별도 검토 목록과 정책 화면에 표시하며 근거 없이 상위 정책을 자동 확정하지 않습니다. [운영 자료 이관·누락 검증](PROGRAM_HIERARCHY.md).

**HOME · Housing Operations Monitoring & Execution — 주택정책의 실행·모니터링**

> 목적: 기준일 현재 유효한 **정부 주택공급 정책**과 서울특별시·경기도에서 진행 중인 공급사업을 연결하고, 계획–인허가–착공–공급–준공–입주 진행상황을 근거와 이력에 따라 관리하는 통합 Master Dataset과 업무 화면을 PoC로 검증한다.

- 기준일 기본값: `2026-10-02`
- 기준일은 코드에 하드코딩하지 말고 `AS_OF_DATE` 설정값으로 관리한다.
- 지역 범위: **서울특별시와 경기도**
- 정책 범위: 중앙정부가 공식 발표하고 기준일 현재 유효한 주택공급 정책
- 사업 범위: 해당 정책에 연결되며 서울·경기 안에서 `PLANNING`부터 `SUPPLY` 단계까지 진행 중인 사업
- 원칙: 정책 귀속과 사업 매핑은 시스템이 임의 확정하지 않는다.
- 자동수집은 행정실적/공개정보를 보완·검증하는 수단이며, 정책관리 Master는 업무담당자가 확정한다.
- 모든 범위 판정은 근거 문서와 기준일을 남긴다. 승인 대기 `REVIEW`도 화면의 **검토 통계**에 반영하며 담당자 확정과 구분한다. `RELEASED`는 정책 통계에서 제외한다. 공식 정책 실적은 별도 근거 검증 전까지 미확보로 유지한다.

## 현재 구현 상태 — 2026-10-03

공급현황 지도 UI 후속 설계: 좌측 320~360px 패널과 지도 중심 화면, 시도·시군구 통합 현황에서 지구·블록·건물 3D 상세로 이어지는 개편안을 [MAPS_UI_PLAN.md](MAPS_UI_PLAN.md)에 정리했습니다. 기존 집계·API를 재사용하고 용지 입체 표현과 실제 건물 형상·높이를 구분합니다. 이 개편안은 구현 전 설계이며 운영 적용을 뜻하지 않습니다.

최신 추가: 공급 현황 아래 **정책별 진행현황** 메뉴. 3개 공급대책과 2개 프로그램 정책의 연결 목표·올해 목표·올해/누적 공고 확인 비율·완료 일정 확보 범위를 비교합니다. 정책–사업 연결 화면에서 자동 매칭·승인 전 통계 반영·담당자 정책 조정·개별/일괄 승인·해제·변경 이력을 제공합니다. 추가 API 서비스와 키 불필요 SH/GH 파일 연결을 구분하고 신청 방법을 안내합니다. [정책 진행·연결 구현](POLICY_PROGRESS_AND_MATCHING.md), [API 신청 안내](API_KEYS.md).

추가 구현: 우측 상단 정책 탭과 시도별 입체 그래프, 지도 직접 표출 시군구 원그래프/블록별 독립 공급 그래프, 현재 누적 목표와 확인량 위에 쌓는 향후 1/2/3년 전망, 근거 기반 공고월 지연/이행 확인과 위치 바로가기. 공식 시군구 경계 56개를 추가하고 사용자 승인에 따라 현재·과거 물량 CSV를 제공합니다. [POLICY_MAP_MONITOR.md](POLICY_MAP_MONITOR.md).

이 문서는 전체 목표 설계이며 모든 기능의 구현 완료를 뜻하지 않습니다. 사용자 요청에 따라 먼저 **공식 원천 수집과 홈페이지 조회로 범위·품질을 검증하는 첫 구현**을 배포했습니다.

- 독립 FastAPI·PostgreSQL/PostGIS, Alembic migration, Docker 런타임과 `/poc/home`·`/home` 연결.
- 정책자료·LH 공급계획·LH 공사 현황 7개 원천의 키 없는 수집, 원본 SHA-256 snapshot, 실패 시 마지막 정상 데이터 유지.
- 첫 정상 수집: 정책 3건, 사업 후보 150개 원천 레코드(서울 12 / 경기 138). 원천별 동일 사업 중복 가능.
- 공개 검색·필터·사업 상세·정책 Tree·검증 항목·CSV·수집 상태·API 키 안내.
- 관리자 정책 연결 검토, 동시 수정 방지·감사이력, 날짜별 수집 revision·매핑 재현.
- API 누적 수집: 정책 기원 2018년부터 서울·경기 × 연도별 공고 전체 페이지, 기존 6개 법정동 인허가 전체 조회 페이지. 청약 1,110·인허가 3,870·누적 주소 52개, 총 5,032개를 `TEST_SAMPLE`로 분리 적재. 좌표 누적 43개 성공·9개 미발견. 기본 자동수집에서 제외하고 관리자 요청으로 재수집.
- 과거 자료: 최초 계획·제도 도입·후속조치 정책자료 5건, LH 과거 공사 보고서 10개·641행을 별도 kind로 누적. 홈페이지 정책 흐름·과거 자료에서 2018년부터 자료연도 선택·당시 공정률·근거 조회. 원천 자료연도와 실제 저장일을 구분하고 현재 사업 상태를 유지. [HISTORICAL_COLLECTION.md](HISTORICAL_COLLECTION.md).
- 사업 후보 150건의 당해연도 + 향후 1~10년 연도별 추진목표 대시보드. 원천의 공급·계약 준공·입주 예정을 구분하고 관리자 연도별 단계·호수·근거를 별도 `goal` revision·감사이력으로 관리. 기간·연도·목표 확보 필터, 원천 월별 면적 물량 집계, 미등록/실적 미확인 표시와 CSV.
- 지도 중심 화면: VWorld 공식 공동주택용지 30개 지구·사업 후보 106건의 검토 연결, 대표점 표식·용지 도형, 우측 선택 사업 상세·목표 관리, 하단 연도 전환·재생, 위치 미연결 44건 목록. API 주소 관측점 43개는 별도 레이어이며 정책 실적에 합산하지 않음. 기존 VWorld 키를 서버 타일 프록시에서 재사용. [MAP_INTERFACE.md](MAP_INTERFACE.md).
- 과거·물량 지도: 자료 연도 2018~현재와 수집 조회일을 분리, 당시 보고서별 마지막 상태와 정책 흐름을 지도에 연결. 정책/프로그램/지역별 선언목표·검토 계획량·본 모집공고 확인량·실입주와 정책 실적 미확보·향후 1~10년 누적 예정량, 모집/입주/준공 선택, 관리자 목표 별도 표시. LH·지구·블록·유형을 확인한 본 공고 33건·18,656호의 조회용 검토 연결과 공고상 입주예정 보완, 사전·잔여·복수 공고 제외. 동일 지구·블록 중복과 복수현장을 보수적으로 제외한 뒤 분류별 합계 일치 검증. 과거 사업 참고용 공식 지구 5곳 추가, 총 35곳 보관. [SUPPLY_MAP.md](SUPPLY_MAP.md).

현재 물리 DB는 source revision·collection batch·검토 mapping·audit 중심의 검증용 모델이며 아래 전체 Master/cohort 모델과 동일하지 않습니다. API 표본은 `notice`·`permit`·`location` kind로 보관하고 정책 사업·공급 실적에는 합산하지 않습니다. 공식 지도 도형은 별도 `district` kind로 보관하며 대표 위치 연결은 검토 상태입니다. 일반 민간 청약공고와 과거 인허가도 API 응답 검증용 표본에 포함될 수 있으며, 아래 정책관리 사업 포함 규칙을 충족했다고 판단하지 않습니다. 확보된 일정의 향후 1~10년 물량은 검토 합계로 조회하지만, 확정된 공급묶음, 다중 정책 N:M 관계, 승인된 범위 기준선과 공식 총량, 개별 블록 경계 연결, 청약·건축행정 실적의 정책 사업 연결·전수 수집은 후속 구현입니다. 현 단계는 근거와 수집 후보를 검토하는 화면이며 서울·경기 전체 모집단과 정책 달성률을 주장하지 않습니다.

화면 기준일 기본값은 오늘(KST), 조회 필터는 `as_of_date`입니다. 최초 수집일 이전 지식 상태를 임의 생성하지 않습니다. LH 공정률의 확보 기준일은 2026-07-01이며 수집일과 구분합니다. 정책 유효상태·종료·취소·기준선과 공급묶음 실적을 확정한 뒤 공식 집계를 연결합니다.

원천: [SOURCE_REGISTRY.md](SOURCE_REGISTRY.md). 키·API 표본 범위: [API_KEYS.md](API_KEYS.md). 실행·복구: [OPERATIONS.md](OPERATIONS.md). 검증: [VERIFICATION.md](VERIFICATION.md), [TEST_COLLECTION.md](TEST_COLLECTION.md).

확대 수집과 향후 10년 목표의 현재 범위·수량·검증은 [EXPANDED_ROADMAP.md](EXPANDED_ROADMAP.md)에 기록합니다. 관리자 목표는 계획이며 실제 달성·공식 정책실적이 아닙니다. 전체 목표 설계의 N:M 관계·범위 기준선·공급묶음 총량 모델은 여전히 후속 범위입니다.

---

## 1. 문제 정의

현재 주택공급 관련 데이터는 정책자료, 공공기관 사업자료, 건축 인허가, 청약정보, 공간정보 등으로 분산되어 있다.

문제는 단순히 데이터가 흩어져 있다는 점만이 아니다.

1. 정책자료에는 정책 목표와 관리대상 사업이 존재한다.
2. 시행기관 자료에는 지구·블록·공급물량이 존재한다.
3. 건축행정 데이터에는 승인·착공·사용검사 정보가 존재한다.
4. 청약 데이터에는 모집공고·공급세대·입주예정 정보가 존재한다.
5. 그러나 기관 간 공통 사업 식별자가 충분히 공유되지 않아 동일 사업의 자동 JOIN이 어렵다.
6. 따라서 정책–사업–실적을 연결하는 **기준정보(Master Data)** 가 필요하다.

PoC의 핵심은 공개 API를 억지로 자동 매칭하는 것이 아니라, **업무담당자가 확정한 정책–사업 연결관계를 기준 Master로 두고 외부 데이터를 그 위에 연결하는 구조**를 검증하는 것이다.

---

# 2. 목표 시스템 정의

## 2.1 시스템 한 문장 정의

> 현재 유효한 정부 주택공급 정책과 서울·경기 진행사업을 기준정보로 관리하고, 사업별 계획–인허가–착공–공급–준공–입주 정보를 연결하여 정책별·지역별 실행상황과 향후 공급을 지도와 Tree로 관리하는 시스템.

## 2.2 관리 범위

### 지역 포함 기준

- 대표주소 또는 공식 사업구역이 서울특별시·경기도에 있는 사업
- 복수 시도에 걸친 사업은 `PROJECT_REGION_MAP`으로 지역별 구역·물량을 나눌 근거가 있을 때 포함
- 위치는 서울·경기이나 정책 목표가 전국 단위인 경우 정책 전체 목표와 서울·경기 배정·매핑 물량을 분리
- 주소만 있고 경계가 없는 사업은 `REVIEW`, 공식 경계 또는 담당자 확인이 있으면 `CONFIRMED`

### 정책·사업 포함

- 서울·경기에 사업이 존재하는 3기 신도시
- 공공택지 및 신규 공공택지
- LH 등 공공주택 직접시행 사업
- 공공분양
- 건설형 공공임대
- 도심 공공주택 복합사업
- 공공재개발
- 공공부지·공공청사 활용 주택공급
- 중앙정부 정책에 공식적으로 포함되고 위치·공급물량·시행주체 중 핵심 식별정보를 확인할 수 있는 사업
- 공공이 직접 시행하지 않더라도 정부 정책의 관리대상으로 공식 지정되고 개별 사업을 식별할 수 있는 사업

### 조건부 포함

- 신축매입임대
- 매입임대
- 전세임대

위 사업은 일반적인 `계획 → 인허가 → 착공 → 분양 → 준공 → 입주` Pipeline과 다르므로 `지도 직접관리`와 `총량관리`를 구분한다.

### 초기 제외

- 일반 민간분양
- 일반 민간 재개발·재건축
- PF 금융지원
- 세제·규제완화 등 공급지원 정책
- 사업 단위로 공간·물량을 특정할 수 없는 정책수단
- 서울·경기 밖에서만 진행되는 사업
- `COMPLETED`, `ENDED`, `CANCELED` 사업의 신규 관리. 단, 과거 이력과 정책 실적에는 보존

## 2.3 범위 기준선 승인

PoC는 “현재 진행 중”을 검색 결과로 매번 재정의하지 않는다. 먼저 기준일별 범위 기준선을 만든다.

1. 국토교통부 공식 정책·업무계획·후속대책에서 후보 정책을 수집한다.
2. 정책의 유효상태와 서울·경기 적용 여부를 담당자가 확인한다.
3. 공식 문서에서 진행사업 후보를 추출하고 정책–사업 관계를 `REVIEW`로 생성한다.
4. 담당자가 정책, 사업, 지역범위와 매핑을 `CONFIRMED`한다.
5. 승인된 기준선의 정책과 사업 전체를 해당 기준일의 PoC 모집단으로 고정한다.

완료율의 분모는 인터넷에서 발견 가능한 모든 사업이 아니라, 근거와 승인 이력이 있는 **범위 기준선의 전체 사업·물량**이다. 이후 신규 정책·사업과 종료·취소는 새 기준선 버전으로 반영한다.

---

# 3. 핵심 운영원리

## 원칙 1. Master First

외부 API 데이터에서 정책을 추론하지 않는다.

```text
정책 Master
   ↓
프로그램 Master
   ↓
사업 Master
   ↓
정책–사업 Mapping
   ↓
외부 원천 Source Mapping
   ↓
행정실적/청약/준공 데이터 연결
```

정책·사업 정의가 먼저이고, 공개 데이터는 이후에 붙인다.

---

## 원칙 2. 정책 귀속은 업무담당자가 확정

정책–사업 관계는 자동 유사도만으로 공식 확정하지 않는다.

허용 상태:

- `CONFIRMED`: 업무담당자가 확정
- `REVIEW`: 확인 필요
- `RELEASED`: 기존 연결 해제
- `PENDING`: 신규 검토

정책별 실적 집계에는 원칙적으로 `CONFIRMED`만 사용한다.

---

## 원칙 3. 한 사업은 여러 정책과 연결될 수 있다

동일 사업이 업무계획, 공급대책, 후속대책 등에 반복 포함될 수 있다.

따라서 정책–사업 관계는 N:M 구조로 설계한다.

단, 공급물량 중복집계를 막기 위해 다음 필드를 둔다.

- `mapping_type`
- `count_flag`
- `policy_target_units`
- `supply_cohort_id`
- `allocation_scope`

예:

```text
하남교산 A2
 ├ 3기 신도시                PRIMARY / count=Y
 ├ 수도권 공공택지 공급      PARENT  / count=N
 └ 2026 공급대책             RELATED / count=N
```

`count_flag`만으로는 같은 사업의 분양·임대 물량이나 상위 지구·하위 블록 중복을 구분할 수 없다. 실제 집계 단위는 `supply_cohort_id`로 고정하고, 한 정책·공급묶음·유효기간에 활성 `count_flag=TRUE` 매핑이 하나만 존재하도록 DB 제약을 둔다.

---

## 원칙 4. 정책과 프로그램을 분리

정책 발표자료는 시간이 지나면서 변경·통합될 수 있지만 실제 공급 프로그램은 계속 유지될 수 있다.

```text
정책 패키지
2026 업무계획 / 공급대책 / 후속대책
        ↓
공급 프로그램
3기 신도시 / 공공택지 / 도심복합 / 공공재개발
        ↓
사업·지구
남양주왕숙 / 하남교산 / ...
        ↓
블록·단지
A2 / B1 / S5 ...
```

---

## 원칙 5. 변경이력 보존

Master와 실적 데이터는 모두 과거 상태를 재현할 수 있어야 한다. 원천에서 효력이 발생한 시점과 시스템이 그 사실을 기록한 시점을 구분한다.

- 원천 유효시간: `source_effective_from`, `source_effective_to`
- 시스템 기록시간: `recorded_at`, `superseded_at`
- 조회 기준: `base_date`, `as_of_date`
- 레코드 버전: `revision_no`, `previous_revision_id`

원천값 변경 시 과거 레코드를 삭제하지 않는다.

단순 `updated_at` 덮어쓰기로는 과거 기준일을 재현할 수 없으므로 Master 변경도 새 revision을 추가한다.

---

## 원칙 6. 원천과 가공값을 분리

다음 계층을 분리한다.

```text
RAW
  ↓
STAGING / STANDARDIZED
  ↓
MASTER
  ↓
FACT / HISTORY
  ↓
DERIVED / ANALYTICS
  ↓
API / MAP / DASHBOARD
```

원천값과 계산값을 같은 컬럼에 덮어쓰지 않는다.

---

## 원칙 7. 데이터 출처 추적 가능성

모든 값은 가능하면 다음 정보를 가져야 한다.

- 원천기관
- 원천시스템
- 원천 object ID
- 원천 URL
- 원천 기준일
- 수집일시
- 수집 배치 ID
- 공식/비공식 여부
- 수기/자동 여부

---

## 원칙 8. 자동수집 우선순위

1. 공식 API
2. 공식 다운로드 파일(CSV/XLSX)
3. 공식 웹페이지 구조화 수집
4. 공식 보도자료/문서 추출
5. 업무담당자 직접 입력

크롤링은 API·공식 파일이 없는 경우에만 사용한다.

---

## 원칙 9. 상태 축을 분리

다음 상태를 한 필드에 혼합하지 않는다.

- 정책 생명주기: `PLAN`, `ACTIVE`, `HOLD`, `COMPLETE`, `MERGED`, `ENDED`
- 사업 생명주기: `PLANNING`, `DESIGNATED`, `APPROVED`, `COMPENSATION`, `CONSTRUCTION`, `SUPPLY`, `COMPLETED`, `HOLD`, `CANCELED`
- 매핑 검토상태: `PENDING`, `REVIEW`, `CONFIRMED`, `RELEASED`
- 값의 공개등급: `PUBLIC`, `INTERNAL`, `RESTRICTED`
- 데이터 품질상태: `NORMAL`, `CHECK`, `ERROR`

---

## 원칙 10. 공개 조회와 내부 관리를 분리

`/poc/home`의 공개 조회는 `PUBLIC`으로 승인된 데이터만 제공한다. 정책·사업·매핑 수정, 공개 전 예상일정, 협조과제와 담당자 정보는 인증된 내부 관리 화면에서만 조회·수정한다. 공개 조회 화면과 내부 관리 데이터의 공개등급을 구분한다. 현재 검증 구현의 정책 연결 근거는 공식 공개 원문을 전제로 공개 상세에 표시하므로 비공개 업무정보를 입력하지 않는다.

---

# 4. 시스템 아키텍처

```text
┌─────────────────────────────────────────────────┐
│                이용자 / 관리자                  │
│ 정책담당자 │ 사업담당자 │ 데이터관리자 │ 조회자 │
└────────────────────┬────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────┐
│              업무 / 서비스 계층                 │
│ 정책관리                                         │
│ 프로그램관리                                     │
│ 사업 Master 관리                                │
│ 정책–사업 Mapping 관리                          │
│ 원천 Source Mapping 관리                        │
│ 일정·공정·지연 관리                             │
│ 데이터 검증/승인                                │
└────────────────────┬────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────┐
│                분석 계층                        │
│ 정책별 계획/실적 집계                           │
│ Pipeline 상태 계산                              │
│ 지연/병목 Rule Engine                           │
│ 미래 공급 Forecast                              │
│ 지도 Aggregation                                │
└────────────────────┬────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────┐
│                통합 데이터 계층                 │
│ POLICY_MASTER                                    │
│ PROGRAM_MASTER                                   │
│ PROJECT_MASTER                                   │
│ POLICY_PROJECT_MAP                               │
│ PROJECT_SOURCE_MAP                               │
│ PROJECT_SCHEDULE / STAGE_HISTORY                 │
│ PROJECT_SUPPLY_ACTUAL / RISK / SNAPSHOT          │
└────────────────────┬────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────┐
│            수집 / 표준화 / 적재 계층            │
│ API Collector                                    │
│ File Collector                                   │
│ Web Collector                                    │
│ Parser / Normalizer                              │
│ Validator                                        │
│ Snapshot / Load                                  │
└────────────────────┬────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────┐
│                   원천                          │
│ 국토부 정책자료                                 │
│ LH / SH / GH / 서울·경기 지자체                 │
│ 건축HUB 주택인허가                              │
│ 청약홈                                           │
│ 행정구역 GIS/WFS                                │
│ 기타 공식 공공데이터                            │
└─────────────────────────────────────────────────┘
```

---

# 5. PoC 확정 기술 스택

공간범위, N:M 매핑, 이력, 제약조건과 동시 관리자 수정을 검증해야 하므로 1차 PoC의 주 저장소는 PostgreSQL + PostGIS로 고정한다. DuckDB + Parquet는 내보내기·분석용 산출물에만 사용할 수 있으며 운영 원본을 대체하지 않는다.

## Backend / ETL

- Python 3.12+
- `httpx`
- `pandas`
- `pydantic`
- `sqlalchemy`
- `alembic`
- `beautifulsoup4` (필요 시)
- `openpyxl` (XLSX 수집 시)

## Database

- PostgreSQL 16 + 호환 PostGIS
- Alembic migration을 유일한 스키마 변경 경로로 사용
- DB는 HOME 전용 사용자·DB·볼륨으로 격리
- 개발 호스트 publish가 필요하면 loopback 전용 포트를 사용

## API

- FastAPI 단일 서비스
- HOME 서비스 기본 loopback 포트 `18100`
- 부모 서비스는 `/poc/home/*`만 reverse proxy하고 `/home`은 해당 경로로 이동
- OpenAPI는 내부 관리 API와 공개 읽기 API를 구분

## 관리 UI

FastAPI와 같은 인증·권한·트랜잭션 경계를 쓰는 서버 렌더링 UI를 기본으로 한다. Streamlit은 격리된 데이터 검증 실험에는 사용할 수 있지만 운영 관리 원본을 수정하지 않는다.

필수 화면:

1. 정책 Master
2. 사업 Master
3. 정책–사업 Mapping
4. Source Mapping
5. 데이터 수집 현황
6. 오류/미매칭 데이터 목록

---

# 6. Master Dataset 구조

모든 Master와 Mapping 테이블은 별도 표에 반복 기재하지 않더라도 다음 공통 이력 컬럼을 가진다.

| 컬럼 | 설명 |
|---|---|
| source_effective_from/to | 원천에서 값이 유효한 기간 |
| recorded_at/superseded_at | HOME에 기록되어 유효한 기간 |
| revision_no | 엔터티별 증가 버전 |
| previous_revision_id | 직전 revision 참조 |
| visibility | PUBLIC/INTERNAL/RESTRICTED |
| created_by | 자동수집 배치 또는 관리자 식별자 |

논리 식별자와 revision 식별자를 분리하고, 같은 논리 식별자의 활성 revision은 한 건만 허용한다. 수정은 기존 행 갱신이 아니라 새 revision 추가와 이전 revision의 `superseded_at` 기록으로 처리한다.

## 6.1 POLICY_MASTER

| 컬럼 | 타입 | 필수 | 설명 |
|---|---|---:|---|
| policy_id | VARCHAR | Y | 내부 정책 ID |
| policy_name | VARCHAR | Y | 정책·대책명 |
| policy_type | VARCHAR | Y | 공급대책/업무계획/후속대책 등 |
| announce_date | DATE | Y | 발표일 |
| effective_from | DATE | Y | 유효 시작일 |
| effective_to | DATE | N | 종료일 |
| policy_status | VARCHAR | Y | PLAN/ACTIVE/COMPLETE/MERGED/ENDED/HOLD |
| target_units | INTEGER | N | 정책 목표호수 |
| target_end_year | INTEGER | N | 목표연도 |
| responsible_org_id | VARCHAR | N | 주관기관 |
| public_supply_flag | BOOLEAN | Y | 공공공급 정책 여부 |
| seoul_gyeonggi_scope | VARCHAR | Y | IN_SCOPE/PARTIAL/OUT_OF_SCOPE |
| scope_basis | TEXT | Y | 서울·경기 범위 판정 근거 |
| scope_baseline_id | VARCHAR | Y | 기준일별 승인 범위 버전 |
| management_scope | VARCHAR | Y | MAP/SUMMARY/EXCLUDE |
| parent_policy_id | VARCHAR | N | 상위·후속 정책 |
| official_basis_url | TEXT | N | 공식 근거자료 |
| official_basis_title | TEXT | N | 근거문서명 |
| description | TEXT | N | 설명 |
| verification_status | VARCHAR | Y | VERIFIED/PENDING |
| base_date | DATE | Y | 조회 기준일 |
| source_effective_from/to | TIMESTAMP | Y/N | 원천 유효기간 |
| recorded_at/superseded_at | TIMESTAMP | Y/N | 시스템 기록기간 |
| revision_no | INTEGER | Y | 레코드 버전 |

---

## 6.2 PROGRAM_MASTER

| 컬럼 | 설명 |
|---|---|
| program_id | 공급 프로그램 ID |
| program_name | 프로그램명 |
| program_type | 공공택지/도심복합/공공재개발 등 |
| supply_type | SALE/RENT/MIXED |
| developer_type | PUBLIC/MIXED |
| map_manage_flag | 지도 직접관리 여부 |
| pipeline_type | 적용 Pipeline |
| default_org_id | 대표 시행기관 |
| status | 상태 |
| description | 설명 |

---

## 6.3 PROJECT_MASTER

| 컬럼 | 설명 |
|---|---|
| project_id | HOME 통합 사업ID |
| parent_project_id | 상위 사업/지구 |
| project_level | DISTRICT/BLOCK/COMPLEX/PROJECT |
| project_name | 표준 사업명 |
| district_name | 지구명 |
| block_name | 블록명 |
| program_id | 공급 프로그램 |
| project_type | 사업유형 |
| developer_org_id | 시행기관 |
| primary_region_code | 대표 법정구역 코드 |
| region_scope | SEOUL/GYEONGGI/CROSS_BOUNDARY/OUT_OF_SCOPE |
| region_assignment_status | REVIEW/CONFIRMED |
| address | 대표주소 |
| latitude | 대표 위도 |
| longitude | 대표 경도 |
| geometry_id | 공간정보 ID |
| planned_units | 기준 계획호수 |
| supply_type | 분양/임대/혼합 |
| project_status | PLANNING/DESIGNATED/APPROVED/COMPENSATION/CONSTRUCTION/SUPPLY/COMPLETED/HOLD/CANCELED |
| management_scope | MAP/SUMMARY |
| management_flag | 상황판 관리 여부 |
| base_date | 기준일 |
| source_effective_from/to | 원천 유효기간 |
| recorded_at/superseded_at | 시스템 기록기간 |
| revision_no | 레코드 버전 |
| note | 비고 |

---

## 6.4 POLICY_PROJECT_MAP

정책–사업 매핑은 **업무담당자 관리영역**이다.

| 컬럼 | 설명 |
|---|---|
| mapping_id | 매핑 ID |
| policy_id | 정책 ID |
| program_id | 프로그램 ID |
| project_id | 사업 ID |
| supply_cohort_id | 정책상 인정하는 공급물량 묶음 |
| mapping_type | PRIMARY/PARENT/RELATED/FOLLOWUP |
| count_flag | 해당 정책의 물량합산 여부 |
| allocation_scope | SEOUL/GYEONGGI/CROSS_BOUNDARY |
| policy_target_units | 해당 정책상 인정 물량 |
| mapping_status | CONFIRMED/REVIEW/RELEASED/PENDING |
| mapping_basis | 매핑 근거 |
| basis_document_url | 공식 근거 URL |
| confirmed_org_id | 확인기관/부서 |
| confirmed_by | 확인 담당자 |
| confirmed_date | 확인일 |
| source_effective_from/to | 매핑 유효기간 |
| recorded_at/superseded_at | 시스템 기록기간 |
| revision_no | 매핑 버전 |
| change_reason | 변경사유 |

---

## 6.5 PROJECT_SOURCE_MAP

외부 원천시스템의 사업/공고/인허가 ID를 HOME `project_id`와 연결한다.

| 컬럼 | 설명 |
|---|---|
| source_map_id | Source Mapping ID |
| project_id | HOME 사업ID |
| supply_cohort_id | 연결 대상 공급물량 묶음, 해당 시 |
| source_system_id | 원천 시스템 |
| source_object_id | 원천 고유 ID |
| source_object_type | PROJECT/APPROVAL/NOTICE/COMPLETION 등 |
| source_project_name | 원천상 사업명 |
| source_address | 원천 주소 |
| mapping_status | CONFIRMED/REVIEW/RELEASED |
| mapping_basis | 연결 근거 |
| confirmed_by | 확인자 |
| confirmed_date | 확인일 |
| source_effective_from/to | 연결 유효기간 |
| recorded_at/superseded_at | 시스템 기록기간 |
| revision_no | 연결 버전 |

자동수집 결과가 신규 source object를 발견하면 기존 사업에 자동 확정 연결하지 않는다.

`REVIEW` 후보로 생성하고 관리자 화면에서 확인하도록 한다.

---

## 6.6 SOURCE_SYSTEM_MASTER

| 컬럼 | 설명 |
|---|---|
| source_system_id | 원천시스템 ID |
| source_org_id | 원천기관 |
| source_system_name | 시스템명 |
| data_name | 데이터명 |
| collection_type | API/FILE/WEB/MANUAL |
| endpoint_url | API/페이지 URL |
| catalog_id | 공공데이터포털 등 공식 카탈로그 ID |
| update_cycle | 갱신주기 |
| temporal_coverage | 원천의 기준시점·기간 |
| license_name | 이용조건·출처표시 조건 |
| schema_version | 원천 명세 버전 |
| official_flag | 공식정보 여부 |
| active_flag | 수집여부 |
| parser_version | Parser 버전 |

---

## 6.7 ORG_MASTER

| 컬럼 | 설명 |
|---|---|
| org_id | 기관 ID |
| org_name | 기관명 |
| org_type | 중앙부처/공기업/지방공기업/지자체 |
| parent_org_id | 상위기관 |
| active_flag | 사용여부 |

초기 seed:

- MOLIT
- LH
- SH
- GH
- 서울특별시와 경기도 및 범위 기준선에 포함된 기초지자체

---

## 6.8 REGION_MASTER

| 컬럼 | 설명 |
|---|---|
| region_code | 코드체계 안에서의 지역 코드 |
| code_system | BJDONG/ADMIN_DONG/SIDO_SIGUNGU |
| region_name | 행정구역명 |
| region_level | SIDO/SIGUNGU/EMD |
| parent_region_code | 상위지역 |
| sido_code | 시도 |
| sigungu_code | 시군구 |
| geometry_id | GIS ID |
| geometry_version | 경계 기준시점 |
| valid_from | 유효 시작 |
| valid_to | 종료 |

행정동과 법정동 코드는 같은 코드로 취급하지 않는다. 사업 주소·건축HUB 연결은 법정동을 우선 사용하고, 화면 집계용 행정구역 경계는 `code_system`과 `geometry_version`을 함께 기록한다.

---

## 6.9 PROJECT_REGION_MAP

서울·경기 범위 판정과 복수지역 사업의 물량 배분을 관리한다.

| 컬럼 | 설명 |
|---|---|
| project_region_map_id | 지역 매핑 ID |
| project_id | HOME 사업ID |
| region_code | REGION_MASTER 코드 |
| geometry_id | 공식 사업구역 또는 행정경계 |
| allocation_units | 공식 근거가 있을 때 지역 배분 물량 |
| allocation_ratio | 물량 대신 비율만 확인되는 경우 |
| mapping_method | OFFICIAL_GEOMETRY/OFFICIAL_ADDRESS/MANUAL |
| mapping_status | REVIEW/CONFIRMED/RELEASED |
| basis_document_url | 범위 판정 근거 |
| confirmed_by/confirmed_at | 확인자와 확인시각 |

지역별 집계에는 `CONFIRMED`만 사용하고, 공식 배분 근거가 없는 복수지역 사업의 물량을 면적비나 임의 비율로 나누지 않는다.

---

## 6.10 SCOPE_BASELINE / SCOPE_BASELINE_ITEM

| 컬럼 | 설명 |
|---|---|
| scope_baseline_id | 기준선 버전 ID |
| as_of_date | 범위 기준일 |
| region_scope | SEOUL_GYEONGGI |
| policy_count/project_count | 승인 당시 모집단 수 |
| status | DRAFT/APPROVED/SUPERSEDED |
| approved_by/approved_at | 승인자와 승인시각 |
| evidence_manifest_ref | 정책·사업 근거 목록 manifest |
| previous_baseline_id | 이전 기준선 |

기준선의 모집단은 count만 저장하지 않고 `SCOPE_BASELINE_ITEM`으로 고정한다.

| 컬럼 | 설명 |
|---|---|
| scope_baseline_item_id | 기준선 항목 ID |
| scope_baseline_id | 소속 기준선 |
| item_type/item_id | POLICY/PROJECT와 해당 논리 ID |
| inclusion_status | INCLUDED/EXCLUDED/REVIEW |
| lifecycle_status | 기준일 현재 정책·사업 상태 |
| region_scope | SEOUL/GYEONGGI/CROSS_BOUNDARY/OUT_OF_SCOPE |
| decision_basis | 포함·제외 판단 근거 |
| evidence_url | 공식 근거 URL |
| decided_by/decided_at | 판정자와 판정시각 |

승인된 기준선의 항목은 수정하지 않는다. 정정·신규·종료 사항은 이전 기준선을 참조하는 새 기준선에서 반영한다.

---

# 7. 변동/실적 Dataset

Master와 별도로 관리한다.

## PROJECT_SCHEDULE

| 컬럼 | 설명 |
|---|---|
| schedule_id | 일정 revision ID |
| project_id | 사업 |
| supply_cohort_id | 일정이 적용되는 공급물량 묶음 |
| milestone_type | 승인/착공/분양/준공/입주 |
| original_plan_date | 최초 계획일 |
| current_plan_date | 현재 예정일 |
| actual_date | 실제일 |
| date_precision | DAY/MONTH/YEAR |
| source_system_id | 출처 |
| source_object_id | 원천 레코드 |
| base_date | 기준일 |
| confirmed_flag | 담당자 확인 여부 |
| source_effective_from/to | 원천 유효기간 |
| recorded_at/superseded_at | 시스템 기록기간 |
| revision_no | 일정 버전 |

## PROJECT_STAGE_HISTORY

- `stage_history_id`
- `project_id`
- `supply_cohort_id`
- `stage_code`
- `status`
- `start_date`, `end_date`, `date_precision`
- `base_date`
- `source_system_id`, `source_object_id`
- `source_effective_from/to`
- `recorded_at/superseded_at`
- `revision_no`, `previous_revision_id`

## PROJECT_SUPPLY_ACTUAL

실적은 프로젝트 전체 숫자가 아니라 공급물량 묶음과 사건 단위로 저장한다.

- `supply_event_id`
- `supply_cohort_id`
- `project_id`
- `metric_type`
- `metric_semantics` (`STOCK`, `INCREMENT`)
- `units`
- `metric_date`
- `date_precision`
- `source_system_id`
- `source_object_id`
- `source_effective_from/to`
- `recorded_at/superseded_at`
- `revision_no`

예:

- APPROVED_UNITS
- STARTED_UNITS
- SALE_NOTICE_UNITS
- COMPLETED_UNITS
- MOVE_IN_UNITS

## SUPPLY_COHORT

동일 물량이 승인·착공·분양·준공·입주 단계에서 반복 관측되더라도 한 번만 집계할 수 있도록 안정적인 공급물량 묶음을 둔다.

- `supply_cohort_id`
- `project_id`
- `cohort_name`
- `housing_type`
- `tenure_type`
- `planned_units`
- `parent_cohort_id`
- `cohort_status`
- `official_basis_url`
- `source_effective_from/to`
- `recorded_at/superseded_at`
- `revision_no`, `previous_revision_id`

`CURRENT + FORECAST` 계산은 `supply_cohort_id`별로 선택한 기준 단계의 최신 유효 event 하나만 사용한다.

## PROJECT_RISK

- project_id
- risk_type
- risk_level
- risk_reason
- detected_date
- resolved_date
- input_type (`RULE`, `MANUAL`)

## PROJECT_SNAPSHOT

월/주 기준으로 상태를 Snapshot한다.

- snapshot_date
- project_id
- supply_cohort_id
- metric_basis
- stage
- planned_units
- current_plan_date
- actual_units
- risk_level

Snapshot은 파생 캐시이며 원천 사실을 대체하지 않는다. 동일 `snapshot_date + project_id + supply_cohort_id + metric_basis` 조합은 재실행해도 같은 결과가 나와야 한다.

## AUDIT_EVENT

관리자 변경은 업무 테이블과 별도로 append-only 감사 이벤트에 기록한다.

- `audit_event_id`
- `actor_id`, `actor_org_id`, `actor_role`
- `entity_type`, `entity_id`
- `action_type`
- `before_json`, `after_json`
- `reason`
- `request_id`
- `created_at`

감사 이벤트는 일반 수정 API로 변경·삭제할 수 없다.

## FIELD_RESOLUTION_RULE / VALUE_OBSERVATION

자동수집값과 담당자 입력값의 충돌을 재현 가능하게 해결하기 위해 원천별 관측값과 선택 규칙을 분리한다.

`VALUE_OBSERVATION`은 `entity_type`, `entity_id`, `field_name`, `value_json`, `source_system_id`, `source_object_id`, `input_type`, 유효·기록기간, `confirmation_status`, `visibility`를 가진다. `FIELD_RESOLUTION_RULE`은 필드별 허용 원천, 우선순위, 수기 승인 필요 여부와 유효기간을 버전으로 관리한다.

- 법적·행정적 실제일은 해당 사실을 관할하는 공식 원천을 우선한다.
- 공개 전 내부 예상일정은 승인된 담당자 입력을 사용할 수 있지만 `INTERNAL`로 유지한다.
- 수기 입력이라는 이유만으로 공식 실적을 덮어쓰지 않는다.
- 최종 선택값은 View에서 계산하고 선택된 observation과 rule revision을 함께 반환한다.
- 동일 우선순위 원천이 충돌하면 임의 선택하지 않고 `CHECK` 상태로 보낸다.

---

# 8. 직접입력 영역

다음 항목은 공개 API에서 안정적으로 확보되지 않으므로 관리자 입력영역으로 둔다.

1. 정책–사업 Mapping
2. 사업–외부 원천 Source Mapping 확정
3. 실제 공정률
4. 지연 원인
5. 공개 전 최신 예상일정
6. 일정 변경사유
7. 관계기관 협조과제
8. 기반시설 진행상태
9. 원천자료로 자동 판정할 수 없는 관리상태

수기 입력값에는 반드시 다음 Metadata를 남긴다.

- 입력자
- 입력기관/부서
- 입력일시
- 기준일
- 변경사유
- 이전값

---

## 8.1 인증·권한·공개등급

| 역할 | 권한 |
|---|---|
| 공개 조회자 | `PUBLIC` 승인 데이터와 공개 근거 조회 |
| 정책담당자 | 정책–사업 매핑 검토·확정·해제 |
| 사업담당자 | 사업 일정·공정·지연사유 입력 |
| 데이터관리자 | Source Mapping, 수집 오류와 원천 버전 관리 |
| 시스템관리자 | 계정·역할·운영 설정. 업무상 매핑을 대신 확정하지 않음 |

- 내부 관리 API와 화면은 인증을 필수로 하고 역할별 최소 권한을 적용한다.
- 변경 요청은 CSRF/Origin 검증, 세션 만료, 재인증 정책을 적용한다.
- 수정 대상의 `revision_no`를 요청에 포함해 동시 수정 충돌을 `409 Conflict`로 반환한다.
- `INTERNAL`, `RESTRICTED` 값은 공개 API·내보내기·로그에 포함하지 않는다.
- `confirmed_by` 등 담당자 식별정보는 업무상 필요한 최소 범위로 보관하고 공개 응답에서는 제외한다.
- API key와 DB 비밀번호는 HOME 전용 `.env` 또는 비밀 저장소에 두고 브라우저에 전달하지 않는다.

## 8.2 운영·복구 기준

- Raw와 DB는 서로 독립적으로 백업하고 SHA-256 manifest를 생성한다.
- 백업 보존기간, RPO, RTO는 제한 운영 전 승인해 `docs/operations.md`에 기록한다.
- 복구는 운영 DB가 아닌 격리 DB에서 migration, row count, provenance, Tree 합계를 검증한다.
- collector 실패가 기존 정상 Master·Fact를 삭제하거나 빈 값으로 덮어쓰지 않게 한다.
- 배치별 시작·종료·상태·수집/신규/변경/오류 건수와 parser/schema 버전을 남긴다.

---

# 9. 초기 수집원

Codex는 실제 구현 시 공식 원천의 최신 기술문서를 다시 확인해야 한다.

## P0

### 9.1 국토교통부 정책자료

목적:

- POLICY_MASTER 생성
- 정책 발표일
- 목표물량
- 목표연도
- 관리대상 프로그램/지구 후보
- 공식 근거 URL

수집 방식:

- 공식 보도자료/업무계획 웹
- 첨부 PDF/HWP/문서
- API가 없으면 웹/파일 수집

중요:

**보도자료 텍스트만 보고 사업을 자동으로 정책 귀속 확정하지 않는다.**

정책 후보는 기준일 당시의 국토교통부 업무계획·주택공급 대책·후속조치와 공식 첨부문서를 원문 snapshot으로 보존한다. 정책의 `ACTIVE` 여부와 서울·경기 적용 범위는 문서의 발표일만으로 확정하지 않고 후속 변경·종료 문서까지 검토한다.

---

### 9.2 LH 공급계획

목적:

- 공공사업 지구·블록
- 공급호수
- 공급예정시기
- 일부 입주예정 정보

수집 우선순위:

1. 공식 XLSX/CSV
2. 공식 페이지 구조화 데이터
3. 웹 파싱

초기 공식 원천은 LH청약플러스 연도별 공급계획과 엑셀 다운로드다. 화면이 명시하는 일정 변동 가능성을 보존하기 위해 수집일별 파일 hash와 원문 문구를 함께 저장한다. LH 자료만으로 정책 귀속을 확정하지 않는다.

---

### 9.3 건축HUB 주택인허가

- 공식 카탈로그: 공공데이터포털 `15136560`
- 원천명: `국토교통부_건축HUB_주택인허가정보 서비스`

목적:

- 승인일
- 총세대수
- 착공예정일
- 착공일
- 사용검사 관련 정보
- 위치/법정동 코드

주의:

건축HUB 내부 ID는 HOME의 `project_id`와 동일하지 않다.

기존 건축데이터 민간개방시스템에서 건축HUB로 전환되며 PK 체계가 변경됐으므로 source registry에 API 명세·PK 변환 규칙·schema version을 고정한다.

`PROJECT_SOURCE_MAP`을 통해 업무담당자가 연결을 확정한다.

---

### 9.4 청약홈 분양정보

- 공식 카탈로그: 공공데이터포털 `15098547`
- 원천명: `한국부동산원_청약홈 분양정보 조회 서비스`

목적:

- 모집공고일
- 공급주소
- 공급세대수
- 사업주체
- 입주예정월
- 주택관리번호

주의:

`HOUSE_MANAGE_NO`는 청약홈 내부 ID이다.

HOME 사업ID와 직접 JOIN하지 않는다.

실시간 OpenAPI와 연간 파일 자동변환 API를 같은 원천으로 혼용하지 않는다. 1차 collector는 `15098547`의 승인된 endpoint와 schema version을 사용하고, 운영 승인·호출량·재시도·rate limit을 source registry에 기록한다.

---

### 9.5 행정구역 GIS/WFS

- 공식 카탈로그: 공공데이터포털 `15059008`
- 원천명: `국토교통부_행정구역도(WMS/WFS)`

목적:

- 시도/시군구/읍면동
- 행정구역 코드
- Polygon
- 지도 집계

공식 데이터의 `temporalCoverage`와 geometry version을 snapshot마다 기록한다. 행정동 경계와 법정동 주소 코드를 구분하며, 최신 경계가 아직 제공되지 않았으면 이전 경계를 최신인 것처럼 표시하지 않는다.

### 9.6 Source Registry 선행 검증

collector 구현 전 `docs/source_registry.md`에 다음을 승인한다.

- 공식 카탈로그 ID·endpoint·활용승인 상태
- 필수 요청변수, pagination, 호출량, timeout, retry 조건
- 응답 schema와 natural key
- 갱신주기·기준시점·라이선스·출처표시
- 서울·경기 필터 방법과 누락 가능성
- fixture 수집일·원문 hash·민감정보 포함 여부
- 장애 시 마지막 정상 snapshot 유지 정책

---

# 10. 데이터 수집·처리 Pipeline

```text
[Extract]
API / XLSX / Web / Manual
       ↓
[Raw Snapshot]
원본 그대로 저장
       ↓
[Parse]
필드 파싱 / 타입 변환
       ↓
[Standardize]
기관명 / 행정구역 / 날짜 / 블록명 / 사업명 정규화
       ↓
[Validate]
필수값 / 타입 / 중복 / 범위 검증
       ↓
[Source Object]
원천 객체 단위 등록
       ↓
[Mapping]
PROJECT_SOURCE_MAP
       ↓
[Master Join]
project_id 기준
       ↓
[History]
Schedule / Stage / Supply / Risk
       ↓
[Derived]
정책별 진행률 / 미래공급 / 지역집계
```

---

# 11. RAW 저장 원칙

원천 데이터는 반드시 별도 저장한다.

예:

```text
data/
  raw/
    architecture_hub/
      2026-10-02/
    cheongyak/
      2026-10-02/
    lh_supply/
      2026-10-02/
    policy_docs/
      2026-10-02/
```

Raw는 수정하지 않는다.

파일마다 Metadata JSON 생성:

```json
{
  "source_system_id": "SRC_HUB",
  "collected_at": "2026-10-02T10:30:00+09:00",
  "base_date": "2026-10-02",
  "request_url": "...",
  "http_status": 200,
  "sha256": "...",
  "collector_version": "0.1.0"
}
```

---

# 12. 표준화 규칙

## 사업명

원본 사업명은 보존하고 별도 정규화 필드를 생성한다.

예:

```text
source_name          = "남양주왕숙지구 B-1블록 공공분양주택"
normalized_name      = "남양주왕숙 B1"
```

정규화값은 자동 Source Matching 후보 검색에만 사용한다.

자동으로 공식 Master 사업명을 덮어쓰지 않는다.

## 블록

예:

```text
B-1
B 1
B1블록
B1 BLOCK
```

→ `B1`

## 날짜

ISO 8601:

`YYYY-MM-DD`

월 단위만 존재할 경우 원본 precision을 별도 보존한다.

```text
date_value = 2028-06-01
date_precision = MONTH
```

## 세대수

정수형.

원본 단위 필드를 별도로 보존한다.

---

# 13. 데이터 품질 규칙

다음 Validation을 구현한다.

## 필수 검증

- `project_id` unique
- `policy_id` unique
- `mapping_id` unique
- `source_map_id` unique
- 계획호수 ≥ 0
- 위도/경도 범위 검증
- `valid_from <= valid_to`와 `source_effective_from <= source_effective_to`
- `actual_date`는 허용되지 않는 미래값인지 점검
- `count_flag=Y` 중복 물량 경고
- 동일 source system + source_object_id 중복 금지

## Warning

- 같은 지구/블록에 복수 project 생성
- 세대수 차이가 큰 source object
- 주소가 다른 source object
- 30일 이상 미갱신
- 정책은 ACTIVE인데 연결사업이 0개
- 사업은 ACTIVE인데 source mapping이 0개

---

# 14. 정책별 공급량 집계 원칙

중복 정책 귀속 때문에 다음 규칙을 따른다.

정책의 공식 목표는 `POLICY_MASTER.target_units`에서 읽고, 사업으로 확인된 물량은 별도 `mapped_units`로 계산한다. 두 수치는 정의와 범위가 다를 수 있으므로 하나로 합치지 않는다.

`mapped_units`는 기준일 현재 최신 유효한 `CONFIRMED`, `count_flag=TRUE` 매핑 중 `policy_id + supply_cohort_id`별 한 건만 선택하고, 매핑에 승인된 `policy_target_units` 또는 해당 cohort 물량을 합산한다. 서울·경기 지역집계에는 `PROJECT_REGION_MAP`이 `CONFIRMED`된 배분만 적용한다. 상위 지구와 하위 cohort의 물량을 동시에 합산하지 않는다.

프로젝트 전체 물량도 `project_id`의 단순 합이 아니라 Leaf cohort 우선 규칙을 사용한다. cohort가 없는 경우에만 Leaf Project의 `planned_units`를 사용한다.

---

# 15. PoC 단계별 작업계획

## Phase 0. Repository / 실행환경

### 작업

- 프로젝트 폴더 생성
- Python 환경
- Docker Compose
- DB Migration
- `.env.example`
- Logging
- Test Framework
- README
- HOME 전용 PostgreSQL/PostGIS와 FastAPI 실행계약
- 공개 조회와 내부 관리 인증 경계
- Source Registry 초안

### 완료조건

```bash
docker compose up
```

또는 이에 준하는 명령으로 개발환경이 실행되어야 한다.

`/poc/home/` 공개 화면, 인증된 내부 관리 경로, DB health와 migration 상태를 각각 확인할 수 있어야 한다.

---

## Phase 0.5. 서울·경기 범위 기준선

### 작업

- 기준일 현재 유효한 정부 주택공급 정책 후보 목록 작성
- 각 정책의 서울·경기 적용 여부와 공식 근거 저장
- 서울·경기 진행사업 후보 추출
- 정책·사업·지역 범위의 `REVIEW`/`CONFIRMED` 결정
- `SCOPE_BASELINE` 승인

### 완료조건

- 승인된 정책 목록과 제외 목록에 각각 근거·판정자·판정일이 있다.
- 승인된 진행사업 모집단과 상태 기준이 재현된다.
- 전국 목표, 서울·경기 매핑물량과 지역 배분 불가 물량이 구분된다.
- 새 정책·사업을 발견해도 승인된 과거 기준선이 바뀌지 않는다.

---

## Phase 1. Master Schema 구축

### 구현

- POLICY_MASTER
- PROGRAM_MASTER
- PROJECT_MASTER
- POLICY_PROJECT_MAP
- PROJECT_SOURCE_MAP
- SOURCE_SYSTEM_MASTER
- ORG_MASTER
- REGION_MASTER
- PROJECT_REGION_MAP
- SCOPE_BASELINE
- SCOPE_BASELINE_ITEM
- SUPPLY_COHORT
- COMMON_CODE
- STAGE_MASTER
- FIELD_RESOLUTION_RULE

### Deliverable

- SQLAlchemy Model
- Alembic Migration
- ERD (`docs/erd.md` 또는 Mermaid)
- Seed Script

---

## Phase 2. 서울·경기 정책–사업 Seed Dataset

Master 구조 검증을 위해 승인된 `SCOPE_BASELINE`에서 서로 다른 사업유형을 대표하는 서울·경기 진행사업을 Seed로 사용한다.

### 최소 구성

- 서울 사업과 경기 사업을 모두 포함
- 공공택지·3기 신도시 중 경기 진행사업
- 도심 공공주택 복합사업 또는 공공재개발 등 서울 도심형 진행사업
- 지구–블록 계층이 있는 사업과 단일 사업을 모두 포함
- 최소 2개 정책, 3개 프로그램, 10개 사업, 10개 이상의 블록·단지 또는 공급묶음

인천계양처럼 서울·경기 밖 사업은 기본 Seed에서 제외한다. 정책 전체 목표를 설명하는 근거로 필요하면 `OUT_OF_SCOPE` 비교 레코드로만 보존하고 서울·경기 집계에는 포함하지 않는다.

### 목표

정책 → 프로그램 → 지역 → 지구/사업 → 블록/단지/공급묶음 계층과 서울·경기 범위 판정이 실제로 표현되는지 검증한다.

### 중요한 조건

Seed 값은 반드시 공식자료 근거 URL을 남긴다.

불확실한 값은 추정하지 말고 `PENDING` 처리한다.

---

## Phase 3. Collector Framework

공통 Collector Interface 생성.

예:

```python
class Collector:
    source_system_id: str

    def extract(self, as_of_date):
        ...

    def save_raw(self, payload):
        ...

    def parse(self, payload):
        ...

    def validate(self, records):
        ...

    def load_staging(self, records):
        ...
```

구현 순서:

1. 공식 정책문서와 승인된 범위 기준선
2. LH 공급계획 파일
3. 건축HUB
4. 청약홈
5. 행정구역 GIS/WFS

API Key가 없는 경우 Mock Fixture와 Interface까지 완성한다.

실제 Key는 Repository에 저장하지 않는다.

---

## Phase 4. Source Object 저장

원천 객체를 바로 Master에 넣지 않는다.

예:

```text
SOURCE_OBJECT
source_system_id
source_object_id
source_object_type
source_name
source_address
source_region
source_units
raw_payload_ref
base_date
collected_at
schema_version
payload_hash
```

신규 객체는 Source Mapping 화면에서 검색할 수 있어야 한다.

---

## Phase 5. Mapping Admin

### 정책–사업 Mapping

기능:

- 정책 선택
- 사업 검색
- 연결
- 매핑 유형 선택
- count_flag 설정
- 근거 URL
- 확인자
- 유효기간
- 매핑해제

### Project–Source Mapping

기능:

- 미매핑 Source Object 목록
- 기존 사업 검색
- 사업에 연결
- 신규 사업 생성
- 연결 해제
- 근거/확인자 기록

시스템이 후보를 제시하는 기능은 허용하되, 확정은 사용자 행동으로만 수행한다.

---

## Phase 6. 실적/일정 통합

Source Mapping이 끝난 사업에 한해 다음을 생성한다.

- 승인일
- 착공 예정일
- 실제 착공일
- 모집공고일
- 공급세대
- 준공/사용검사
- 입주예정월

먼저 `FIELD_RESOLUTION_RULE`에 필드별 source priority와 공개등급을 정의한다.

예:

```text
정책 목표       → 정책 Master
사업 계획호수   → 업무 Master / LH 공식계획
승인/착공       → 건축HUB
분양공고        → 청약홈
입주예정        → 청약홈/LH
최신 내부일정   → 업무담당자 입력
```

위 표는 기본 후보 규칙이다. 실제 선택은 승인된 rule revision으로 수행하며, 공식 실제일과 내부 예상일정을 같은 필드로 덮어쓰지 않는다. 각 결과에는 선택된 `observation_id`, 대체 후보, 충돌상태를 남긴다.

---

## Phase 7. Derived Dataset 생성

다음 View 또는 Mart를 만든다.

### `vw_project_current_status`

- project_id
- scope_baseline_id
- policy_id
- program_id
- region
- planned_units
- current_stage
- approval_date
- start_plan_date
- start_actual_date
- sale_notice_date
- completion_plan_date
- move_in_plan_date
- delay_months
- risk_level
- data_freshness

### `vw_policy_progress`

- policy_id
- scope_baseline_id
- target_units
- mapped_units
- approved_units
- started_units
- sale_units
- completed_units
- mapping_coverage_rate
- latest_update

### `vw_region_supply_forecast`

- region_code
- scope_baseline_id
- year
- quarter
- stage
- units
- project_count

---

# 16. Mapping Coverage 지표

정책별로 얼마나 데이터가 연결되었는지 측정한다.

```text
Mapping Coverage
= 확인된 정책사업 물량 / 정책 목표물량
```

주의:

정책 목표호수와 개별 사업호수의 정의가 다른 경우 단순 계산하지 않는다.

`coverage_calculation_flag` 또는 Notes를 두어 계산가능한 정책만 표시한다.

---

# 17. 관리 UI 최소 요구사항

## 화면 1. 정책 목록

- 정책명
- 상태
- 목표호수
- 프로그램 수
- 연결사업 수
- Mapping Coverage
- 마지막 업데이트

## 화면 2. 정책–사업 Mapping

- 정책
- 프로그램
- 지구
- 사업
- 물량
- mapping_type
- count_flag
- 상태
- 근거문서

## 화면 3. Source Mapping

좌:

- 신규/미매핑 Source Object

우:

- 기존 PROJECT_MASTER 검색

Action:

- 연결
- 신규사업 생성
- 검토보류
- 해제

## 화면 4. 데이터 수집 현황

- Source
- 마지막 성공
- 마지막 실패
- 수집건수
- 신규건수
- 변경건수
- 오류건수

---

# 18. Repository 권장 구조

```text
PoC/10-home/
├─ README.md
├─ docker-compose.yml
├─ .env.example
├─ pyproject.toml
│
├─ app/
│  ├─ api/
│  ├─ models/
│  ├─ schemas/
│  ├─ services/
│  ├─ admin/
│  └─ main.py
│
├─ collectors/
│  ├─ base.py
│  ├─ architecture_hub.py
│  ├─ cheongyak.py
│  ├─ lh_supply.py
│  ├─ gis.py
│  └─ policy_docs.py
│
├─ pipelines/
│  ├─ extract.py
│  ├─ normalize.py
│  ├─ validate.py
│  ├─ load.py
│  └─ derive.py
│
├─ db/
│  ├─ migrations/
│  └─ seeds/
│
├─ data/
│  ├─ raw/
│  ├─ staging/
│  ├─ fixtures/
│  └─ exports/
│
├─ tests/
│  ├─ unit/
│  ├─ integration/
│  └─ fixtures/
│
└─ docs/
   ├─ architecture.md
   ├─ erd.md
   ├─ data_dictionary.md
   ├─ source_registry.md
   └─ operations.md
```

---

# 19. 테스트 요구사항

## Unit Test

- 날짜 Parser
- 블록명 Normalizer
- 행정구역 변환
- 세대수 Parser
- Policy 중복집계 방지
- SCD valid_from/to 처리

## Integration Test

1. Raw Fixture 입력
2. Staging 생성
3. Source Object 생성
4. 수기 Source Mapping Fixture 적용
5. Project Schedule 생성
6. Derived View 생성

## 핵심 시나리오

### Scenario A

동일 사업이 2개 정책에 연결되더라도 `count_flag=Y`인 정책에서만 공급총량 집계.

### Scenario B

청약홈에 신규 공고가 들어와도 자동으로 기존 사업에 확정 연결하지 않고 `REVIEW` 상태 생성.

### Scenario C

착공예정일이 변경되면 기존 값을 삭제하지 않고 History 유지.

### Scenario D

원천 API 호출 실패 시 이전 정상 데이터가 삭제되지 않음.

### Scenario E

수기 입력값이 자동수집 값보다 우선하는 필드에서는 `source_priority`에 따라 최신 내부일정이 유지됨.

### Scenario Scope-1 — 서울·경기 범위

전국 정책에 서울·경기와 타 시도 사업이 함께 연결되어도 서울·경기 집계에는 `PROJECT_REGION_MAP.mapping_status=CONFIRMED`인 대상 물량만 포함.

### Scenario Scope-2 — 복수지역 사업

서울·경기에 걸친 사업의 공식 지역 배분근거가 없으면 전체 물량을 임의 비율로 나누지 않고 `REVIEW`로 표시.

### Scenario Cohort-1 — 공급묶음 단계 전환

동일 `supply_cohort_id`의 승인·착공·분양·준공 event가 존재해도 선택한 현재 기준과 Forecast 기준에서 한 번만 집계.

### Scenario Concurrency-1 — 동시 수정

두 담당자가 같은 매핑 revision을 수정하면 먼저 저장된 변경만 성공하고 뒤 요청은 `409 Conflict`와 최신 revision을 반환.

### Scenario Access-1 — 공개등급

공개 API와 내보내기에서 `INTERNAL`, `RESTRICTED`, 담당자 식별정보와 공개 전 일정이 노출되지 않음.

---

# 20. Codex 구현 시 금지사항

1. 공식 근거가 없는 정책·사업 관계를 자동 확정하지 않는다.
2. 정책 목표호수와 사업 공급호수를 임의로 동일 개념으로 취급하지 않는다.
3. 동일 사업이 여러 정책에 포함됐다고 물량을 중복합산하지 않는다.
4. Source ID를 내부 `project_id`로 사용하지 않는다.
5. 원천 데이터를 overwrite하지 않는다.
6. 변경이력을 삭제하지 않는다.
7. API Key를 소스코드에 저장하지 않는다.
8. 웹 크롤링 결과를 공식 API보다 우선하지 않는다.
9. 미확인 데이터를 임의 보정하지 않는다.
10. 지도 좌표가 없다고 임의 좌표를 생성하지 않는다.
11. 서울·경기 밖 물량을 지역 집계에 포함하지 않는다.
12. 행정동·법정동 코드와 서로 다른 기준시점의 geometry를 혼용하지 않는다.
13. 공급단계별 반복 event를 서로 다른 물량처럼 합산하지 않는다.
14. 공개 전 일정과 담당자 정보를 공개 API·로그·내보내기에 노출하지 않는다.

---

# 21. PoC 완료 기준

다음이 모두 충족되면 1차 PoC 완료로 본다.

## Master

- [ ] 정책 Master 존재
- [ ] 프로그램 Master 존재
- [ ] 사업 Master 존재
- [ ] 정책–사업 Mapping 존재
- [ ] Source Mapping 존재
- [ ] 기관/지역/원천 Master 존재
- [ ] 사업–지역 Mapping과 공급물량 묶음 존재
- [ ] 기준선과 필드별 값 선택 규칙이 revision으로 존재

## Data

- [ ] 기준일 현재 정부 주택공급 정책 후보와 서울·경기 적용 여부 검토 완료
- [ ] 승인된 `SCOPE_BASELINE` 존재
- [ ] 서울 사업과 경기 사업을 모두 포함하는 최소 2개 정책·3개 프로그램·10개 사업 Seed 완료
- [ ] 최소 10개 블록·단지 또는 공급묶음 테스트
- [ ] 각 Seed의 공식 근거 URL 저장
- [ ] 최소 2개 외부 Source 연결 테스트
- [ ] 서울·경기 범위 집계와 타 시도 제외 검증

## Pipeline

- [ ] Raw Snapshot
- [ ] Normalize
- [ ] Validate
- [ ] Load
- [ ] History
- [ ] Derived Mart

## Admin

- [ ] 정책–사업 Mapping 조정 가능
- [ ] Project–Source Mapping 가능
- [ ] 매핑 해제 가능
- [ ] 변경이력 확인 가능
- [ ] 역할별 권한과 동시 수정 충돌 확인 가능
- [ ] 공개등급 승인과 공개 응답 분리 가능

## Quality

- [ ] 중복집계 방지
- [ ] Provenance 확인 가능
- [ ] 재수집해도 Idempotent
- [ ] 테스트 통과
- [ ] README만 보고 실행 가능
- [ ] 백업 manifest 생성과 격리 복구 검증

---

# 22. 1차 PoC 이후 확장과제

서울·경기 범위의 1차 PoC 성공 후 다음 순서로 확장한다.

1. 서울·경기 승인 기준선의 전체 사업 매핑률 확대
2. 지도 상황판과 지역별 병목 분석
3. 매입임대/전세임대 총량관리 모델 분리
4. SH/GH와 서울·경기 기초지자체 원천 확대
5. 비공개 내부일정의 승인·공개 workflow 고도화
6. Risk / Forecast / AI Briefing
7. 인천 등 수도권과 전국으로 지역 범위 확장

---

# 23. Codex가 최종 제출해야 하는 산출물

## 코드

- 실행 가능한 Repository
- Docker 또는 로컬 실행 스크립트
- DB Migration
- ETL Collector
- Admin UI
- API

## 데이터

- `policy_master.csv`
- `program_master.csv`
- `project_master.csv`
- `policy_project_map.csv`
- `project_source_map.csv`
- `source_system_master.csv`
- `scope_baseline.csv`
- `scope_baseline_item.csv`
- `project_region_map.csv`
- `supply_cohort.csv`
- `project_supply_actual.csv`
- `field_resolution_rule.csv`
- Seed Dataset
- Derived sample dataset

## 문서

- `README.md`
- `docs/architecture.md`
- `docs/erd.md`
- `docs/data_dictionary.md`
- `docs/source_registry.md`
- `docs/operations.md`
- `docs/test_report.md`

---

# 24. Codex 작업 순서 요약

Codex는 아래 순서를 변경하지 않는다.

```text
1. 프로젝트 구조 생성
2. 서울·경기 정책·사업 범위 기준선 승인
3. Master와 공급묶음 Schema 작성
4. DB Migration
5. 서울·경기 대표 Seed Data
6. Tree Derived Model과 Fixture UI
7. Source Registry 승인
8. Collector Framework
9. Raw Snapshot
10. Source Object 생성
11. Mapping Admin
12. Source Mapping
13. 실적/일정 Dataset
14. Tree Current/Forecast 연결
15. 품질·권한·공개등급 검증
16. 테스트와 복구훈련
17. 문서화
```

API 수집부터 먼저 시작하지 않는다.

**가장 먼저 Master와 Mapping 구조를 검증한 뒤 Collector를 붙인다.**

---

# 25. 핵심 판단 기준

이 PoC의 성공 여부는 “데이터를 많이 긁어왔는가”가 아니다.

다음 질문에 답할 수 있어야 한다.

> ① 이 사업은 어떤 공공 주택공급 정책의 관리대상인가?  
> ② 누가 그 관계를 확정했는가?  
> ③ 사업의 계획물량은 얼마인가?  
> ④ 어느 외부 원천데이터가 이 사업과 연결되어 있는가?  
> ⑤ 현재 승인·착공·분양·준공·입주 중 어느 단계인가?  
> ⑥ 원천값과 관리자가 입력한 값 중 어떤 값을 사용했는가?  
> ⑦ 과거 계획과 현재 계획이 어떻게 달라졌는가?  
> ⑧ 모든 숫자의 출처와 기준일을 추적할 수 있는가?

이 8개 질문에 데이터로 답할 수 있으면 1차 통합 데이터셋 설계는 성공으로 본다.

---

# 26. 장기 제도개선 방향

PoC에서는 `PROJECT_SOURCE_MAP`을 업무담당자가 관리하지만, 장기적으로는 데이터 생산기관에 공통 식별체계를 도입하는 것이 목표다.

권장 공통 식별필드:

- `policy_id`
- `program_id`
- `project_id`
- `district_id`
- `block_id`
- `source_org`
- `base_date`
- `update_date`

장기 목표는 **매칭 알고리즘을 고도화하는 것이 아니라 매칭이 불필요한 데이터 생산체계를 만드는 것**이다.


---

# 27. 계층형(Tree) 데이터 검증 디스플레이 기능

이하 화면·JSON에 등장하는 물량 숫자는 공식 근거가 연결되지 않은 한 **UI·API 구조 설명용 예시**다. Seed와 운영 화면에서는 모든 숫자에 `source_object_id`, 기준일과 공개등급을 연결한다.

## 27.1 목적

수집·매핑·가공된 데이터가 실제 정책관리 관점에서 논리적으로 맞는지 빠르게 확인할 수 있도록, **정책 → 프로그램 → 지구/사업 → 블록/단지** 계층을 Tree 구조로 탐색하면서 각 단위의 공급 목표, 현재까지의 실적, 향후 1·2·3년 이상 공급예정 물량을 한 화면에서 비교하는 검증 기능을 구축한다.

이 화면은 일반 대시보드보다 먼저 구축한다.

목적은 다음과 같다.

1. 정책 Master와 사업 Master의 계층관계가 올바른지 확인
2. 정책–사업 Mapping 누락·중복을 발견
3. 상위단위 집계값과 하위 사업 합계가 일치하는지 검증
4. 현재 실적과 미래 공급일정 데이터가 정상적으로 연결되는지 확인
5. 향후 지도 상황판에서 사용할 집계값을 사전에 검증
6. 데이터가 없는 경우 `0`으로 오인하지 않고 `미확보/미연계` 상태를 구분
7. 어떤 숫자든 하위 사업·원천 데이터까지 Drill-down 가능하게 함

---

## 27.2 기본 Tree 구조

PoC 기본 계층은 다음과 같이 한다.

```text
정책 POLICY
  └─ 프로그램 PROGRAM
      └─ 지역 REGION (서울/경기 → 시군구)
          └─ 지구 / 상위사업 DISTRICT
              └─ 블록 / 단지 / 사업 PROJECT
                  └─ 공급물량 묶음 SUPPLY COHORT
                      └─ 원천데이터 SOURCE OBJECT
```

예:

```text
3기 신도시 공급정책
  └─ 3기 신도시
      ├─ 남양주왕숙
      │   ├─ B1
      │   ├─ B2
      │   └─ A1
      ├─ 하남교산
      │   └─ A2
      └─ 고양창릉
          ├─ A4
          ├─ S5
          └─ S6
```

초기 PoC에서는 `PROJECT_MASTER.parent_project_id`를 활용해 지구와 블록을 계층화한다.

정책 중심 Tree와 지역 중심 Tree는 같은 `SUPPLY_COHORT` fact를 다른 차원으로 탐색한다. 지역을 정책–프로그램 계층 안에 중복 저장하지 않는다.

향후 필요 시 다음 계층까지 확장 가능해야 한다.

```text
정책
  → 프로그램
    → 지역
      → 지구
        → 블록
          → 단지
```

단, PoC에서는 계층을 과도하게 늘리지 않는다.

---

# 28. Tree 화면의 핵심 지표 정의

Tree의 모든 Node는 가능한 범위에서 다음 값을 표시한다.

| 지표 | 의미 |
|---|---|
| 목표 | 해당 정책/프로그램/사업이 관리하는 목표 공급호수 |
| 현재 | 기준일 현재까지 실제 공급단계에 도달한 물량 |
| 향후 1년 | 기준일 이후 1년 이내 예정 공급물량 |
| 향후 2년 | 기준일 +1년 초과 ~ +2년 이내 예정 공급물량 |
| 향후 3년 | 기준일 +2년 초과 ~ +3년 이내 예정 공급물량 |
| 3년 이후 | 기준일 +3년 이후 예정 공급물량 |
| 일정 미정 | 목표에는 포함되나 공급예정 시점이 없는 물량 |
| 연결 미완료 | 사업은 있으나 외부 Source Mapping이 완료되지 않은 물량 |
| 데이터 기준일 | 해당 집계에 사용된 최신 기준일 |
| 데이터 완전성 | 목표물량 중 일정/실적까지 연결된 비율 |

화면 기본 컬럼:

```text
[Tree Name]
[목표]
[현재]
[향후 1년]
[향후 2년]
[향후 3년]
[3년 이후]
[일정 미정]
[데이터 완전성]
[검증상태]
```

---

# 29. "현재"의 정의

`현재`라는 표현은 모호하므로 시스템 내부에서는 반드시 어떤 공급단계를 기준으로 하는지 선택 가능해야 한다.

## 기본 Current Metric

PoC 기본값:

`CURRENT = 실제 준공/사용검사 완료 물량`

단, 화면 상단에서 Current 기준을 변경할 수 있게 한다.

선택 가능한 기준:

- 승인 완료
- 실제 착공
- 모집공고/분양
- 준공/사용검사
- 입주

예:

```text
현재 기준: [준공 ▼]
```

따라서 같은 Tree를 다음 방식으로 재계산할 수 있다.

```text
목표 171,000
현재(착공 기준)  xx,xxx
현재(분양 기준)  xx,xxx
현재(준공 기준)  xx,xxx
```

Codex는 `현재`를 하나의 고정 컬럼으로 물리 저장하지 말고, FACT 데이터를 기준으로 계산하는 View/Query로 구현한다.

부분 준공·분할 공급은 프로젝트 전체 물량을 한 번에 완료 처리하지 않고 `supply_cohort_id`별 실제 event 물량만 계산한다.

---

# 30. "향후 공급"의 정의

향후 공급 역시 단계별 의미가 다르므로 화면에서 Forecast 기준을 선택할 수 있게 한다.

기본 Forecast Metric:

`입주예정일 기준 공급물량`

선택 가능 기준:

- 착공예정
- 모집/분양예정
- 준공예정
- 입주예정

예:

```text
향후 공급 기준: [입주예정 ▼]
기준일: 2026-10-02
```

기간 Bucketing 규칙:

```text
향후 1년
AS_OF_DATE < forecast_date <= AS_OF_DATE + 1 year

향후 2년
AS_OF_DATE + 1 year < forecast_date <= AS_OF_DATE + 2 years

향후 3년
AS_OF_DATE + 2 years < forecast_date <= AS_OF_DATE + 3 years

3년 이후
forecast_date > AS_OF_DATE + 3 years
```

정확한 일자가 없고 연월만 존재할 경우 `date_precision=MONTH`를 유지한다.

연도만 존재하는 경우:

- `date_precision=YEAR`
- 화면에는 `2028년 예정`으로 표시
- 임의로 1월 1일을 실제 예정일처럼 표현하지 않는다.

연도 단위 일정이 두 bucket의 경계에 걸리면 임의 배분하지 않고 `forecast_unknown_units` 또는 별도 `COARSE_DATE` 상태로 표시한다.

---

# 31. Tree 집계 원칙

## 31.1 Bottom-up 집계

하위 공급물량 묶음에서 계산된 값을 상위 Node로 합산하는 것을 원칙으로 한다.

```text
블록 합계
  ↓
지구 합계
  ↓
프로그램 합계
  ↓
정책 합계
```

단, 정책 목표치(`POLICY_MASTER.target_units`)는 별도 공식 목표값이므로 하위합계와 동일한 값이라고 가정하지 않는다.

따라서 정책 Node에는 두 값을 구분한다.

```text
공식 목표       171,000
매핑사업 목표   165,000
차이               6,000
```

---

## 31.2 중복집계 방지

정책 Tree 집계에는 다음 조건을 사용한다.

```text
mapping_status = CONFIRMED
AND count_flag = TRUE
```

동일 사업이 여러 정책·대책과 연결되어도 `count_flag=FALSE` 관계는 해당 정책 총량에 중복 합산하지 않는다.

집계 전에 `policy_id + supply_cohort_id + as_of_date` 기준으로 최신 유효 매핑 하나만 선택한다.

---

## 31.3 지구와 블록 중복 방지

`PROJECT_MASTER`에서 상위 지구에도 `planned_units`가 있고 하위 블록에도 `planned_units`가 존재할 수 있다.

상위/하위 값을 동시에 합산하면 중복되므로 집계 규칙을 둔다.

### 권장 규칙

- Leaf `SUPPLY_COHORT`가 존재하면 cohort 기준 합계 사용
- cohort가 없고 Leaf Project만 있으면 Leaf Project 기준 합계 사용
- Leaf가 없을 때만 상위 Project의 계획물량 사용
- 공식 지구 총량은 `reference_target_units`로 별도 보존 가능
- `planned_units`와 `reference_target_units`를 혼용하지 않는다

---

# 32. 데이터 상태를 숫자와 분리해서 표시

`NULL`, `0`, `미연계`를 같은 의미로 처리하지 않는다.

상태 코드를 둔다.

```text
VALUE_AVAILABLE       값 확인
SOURCE_NOT_MAPPED     원천 미연계
DATE_UNKNOWN          일정 미정
SOURCE_NOT_AVAILABLE  원천에서 미제공
PENDING_CONFIRMATION  담당자 확인 필요
NOT_APPLICABLE        해당 단계 비적용
```

화면 예:

| 사업 | 목표 | 현재 | 향후1년 | 향후2년 | 상태 |
|---|---:|---:|---:|---:|---|
| B1 | 1,200 | 0 | - | 1,200 | 일정 확인 |
| B2 | 1,000 | 0 | 미정 | 미정 | Source 미연계 |

`미정`을 `0호`로 표시하지 않는다.

---

# 33. Tree 검증용 Derived Mart

다음 View 또는 Materialized View를 생성한다.

## `vw_supply_tree_node`

필수 컬럼:

```text
node_id
parent_node_id
node_type
node_name
tree_depth

policy_id
program_id
region_code
project_id
supply_cohort_id
scope_baseline_id

official_target_units
mapped_target_units

current_stage_basis
current_units

forecast_basis
forecast_1y_units
forecast_2y_units
forecast_3y_units
forecast_after_3y_units
forecast_unknown_units

source_mapped_units
unmapped_units
data_completeness_rate

validation_status
warning_count

base_date
latest_source_update
```

`node_type` 값:

```text
POLICY
PROGRAM
REGION
DISTRICT
PROJECT
BLOCK
SUPPLY_COHORT
```

PoC 실제 계층에 맞지 않는 Node type은 생략 가능하다.

---

# 34. Tree 검증 상태 규칙

각 Node에 검증상태를 계산한다.

## NORMAL

다음 조건을 모두 만족:

- 목표물량 ≥ 하위 확정사업 물량
- 중복 매핑 경고 없음
- Source Mapping 기본요건 충족
- 미래 일정 또는 완료실적이 충분히 연결됨

## CHECK

다음 중 하나:

- 정책 목표와 매핑사업 합계 차이 존재
- 일정 미정 물량 존재
- Source Mapping 일부 미완료
- 하위 사업 합계와 상위 기준값 불일치
- 데이터 갱신일 30일 이상 경과

## ERROR

다음 중 하나:

- 동일 Source Object가 복수 사업에 동시에 CONFIRMED
- 동일 사업 물량 중복집계
- 현재 + 미래 공급물량이 합리적 범위를 벗어남
- 음수 물량
- 필수 Key 누락
- 순환 parent-child 관계 존재

---

# 35. 검증용 핵심 계산

## 35.1 목표 대비 매핑 Coverage

```text
mapping_coverage
= mapped_target_units / official_target_units
```

공식 목표가 없는 경우 계산하지 않는다.

---

## 35.2 일정 Coverage

```text
schedule_coverage
= 일정이 존재하는 관리대상 물량 / mapped_target_units
```

---

## 35.3 Source Coverage

```text
source_coverage
= 외부 Source가 1개 이상 연결된 사업물량 / mapped_target_units
```

---

## 35.4 공급 Balance

선택한 공급단계 기준으로:

```text
현재 완료
+ 향후 1년
+ 향후 2년
+ 향후 3년
+ 3년 이후
+ 일정 미정
```

과 `mapped_target_units`를 비교한다.

차이는 `unaccounted_units`로 계산한다.

```text
unaccounted_units
= mapped_target_units
- accounted_units
```

공급 Balance는 동일 `supply_cohort_id` 안에서 선택한 기준 단계의 최신 유효 `supply_event_id` 하나를 사용한다. 현재와 미래가 겹치거나 event 물량이 cohort 목표를 초과하면 합계를 확정하지 않고 `ERROR`로 표시한다.

---

# 36. Tree UI 요구사항

## 36.1 기본 화면

```text
정책/프로그램/사업 검색 [                 ]

기준일        [2026-10-02]
현재 기준     [준공 ▼]
향후 기준     [입주예정 ▼]

▶ 3기 신도시 정책            목표 171,000 | 현재 xx,xxx | +1Y xx,xxx | +2Y xx,xxx | +3Y xx,xxx | CHECK
   ▼ 3기 신도시 프로그램      목표 171,000 | ...
      ▶ 남양주왕숙             목표 66,000  | ...
      ▼ 하남교산               목표 33,000  | ...
         └ A2                  목표 1,115   | 현재 0 | +1Y 0 | +2Y 0 | +3Y 1,115
```

Tree Row를 선택하면 우측 Detail Panel을 연다.

---

## 36.2 Detail Panel

선택 Node의 다음 정보를 표시한다.

### 기본정보

- 정책
- 프로그램
- 사업/지구/블록
- 시행기관
- 계획물량
- 지역
- 관리상태

### Current

- 현재단계
- 현재 기준
- 실적물량
- 실제일자
- 출처

### Forecast

- +1년
- +2년
- +3년
- 3년 이후
- 일정 미정

### Mapping

- Policy Mapping
- Source Mapping
- 확인자
- 확인일
- 근거문서

### Validation

- 목표–하위합계 차이
- Mapping Coverage
- Schedule Coverage
- Source Coverage
- Warning List

---

# 37. Drill-down 원칙

화면의 모든 숫자는 최종 Leaf와 원천으로 추적 가능해야 한다.

예:

```text
정책 향후 2년: 24,500호
      ↓ Click
12개 지구
      ↓
31개 블록
      ↓
각 블록 입주예정
      ↓
LH / 청약홈 원천 레코드
```

원천 Record Detail에는 다음을 표시한다.

- source_system
- source_object_id
- source_name
- source_value
- source_url
- source_base_date
- collected_at
- raw_payload_ref

---

# 38. Tree API 설계

FastAPI 기준 예시.

## Tree 조회

```http
GET /poc/home/api/v1/supply-tree
```

Query Parameters:

```text
as_of_date
current_basis
forecast_basis
policy_id
program_id
region_code
management_scope
```

응답 예:

```json
{
  "as_of_date": "2026-10-02",
  "current_basis": "COMPLETION",
  "forecast_basis": "MOVE_IN",
  "nodes": [
    {
      "node_id": "POL001",
      "parent_node_id": null,
      "node_type": "POLICY",
      "node_name": "3기 신도시",
      "official_target_units": 171000,
      "mapped_target_units": 165000,
      "current_units": 1200,
      "forecast_1y_units": 3000,
      "forecast_2y_units": 23000,
      "forecast_3y_units": 41000,
      "forecast_after_3y_units": 75000,
      "forecast_unknown_units": 21800,
      "data_completeness_rate": 0.87,
      "validation_status": "CHECK",
      "warning_count": 3
    }
  ]
}
```

위 숫자는 API 구조 예시일 뿐 실제 데이터가 아니다.

---

## Node Detail

```http
GET /poc/home/api/v1/supply-tree/{node_id}
```

## Node Children

```http
GET /poc/home/api/v1/supply-tree/{node_id}/children
```

## Validation Issues

```http
GET /poc/home/api/v1/supply-tree/{node_id}/validation-issues
```

## Provenance

```http
GET /poc/home/api/v1/projects/{project_id}/provenance
```

---

# 39. Tree 계산 서비스 구조

다음 Service를 분리한다.

```text
TreeBuilder
AggregationService
CurrentStatusCalculator
ForecastBucketCalculator
CoverageCalculator
ValidationService
ProvenanceService
```

권장 처리 순서:

```text
1. 정책/사업 Master Load
2. CONFIRMED Mapping 적용
3. Leaf Supply Cohort 결정, 없으면 Leaf Project fallback
4. Current 상태 계산
5. Forecast Event 선택
6. 기간 Bucket 계산
7. Bottom-up Aggregation
8. Coverage 계산
9. Validation Rule 실행
10. Tree JSON 반환
```

---

# 40. 데이터 검증 시나리오

## Scenario F — 정상 Tree

정책 목표와 하위 사업들이 정상 연결.

기대결과:

- Tree 정상 출력
- 하위 합계 확인
- Provenance Drill-down 가능
- `NORMAL`

---

## Scenario G — 정책목표와 사업합계 불일치

```text
정책 목표      100,000
매핑 사업합계   92,000
```

기대결과:

- 차이 `8,000`
- `CHECK`
- `mapping_coverage=92%`
- 화면에서 차이 강조

---

## Scenario H — 미래일정 미확보

사업 10,000호 중:

```text
입주예정 확인  7,000
일정 미정      3,000
```

기대결과:

- `forecast_unknown_units=3,000`
- +1Y/+2Y 등에 임의 배분하지 않음
- `CHECK`

---

## Scenario I — 중복 정책 Mapping

동일 project가 같은 정책 아래 두 경로에서 `count_flag=Y`.

기대결과:

- 중복 물량 집계 금지
- `ERROR`
- 담당자 수정 전 정책 총량 확정 표시 금지

---

## Scenario J — 상위/하위 사업 이중합산

지구 33,000호 + 하위 블록 합계 20,000호가 함께 존재.

기대결과:

- 53,000으로 합산하지 않음
- Leaf 집계원칙 적용
- 지구의 33,000은 reference target으로 비교

---

## Scenario K — Source Mapping 미완료

Project는 Master에 있지만 외부 데이터가 없음.

기대결과:

- 목표는 표시
- Current/Forecast는 `미연계`
- 숫자 0으로 표시하지 않음
- `CHECK`

---

# 41. Tree 기능 완료기준

- [ ] 정책·지역 관점에서 프로그램 → 지구 → 블록/단지 → 공급묶음 계층이 표시된다.
- [ ] 각 Node에서 목표·현재·향후 1/2/3년·3년 이후를 볼 수 있다.
- [ ] 현재 기준을 착공/분양/준공/입주 등으로 변경할 수 있다.
- [ ] 향후 공급 기준을 착공예정/분양예정/준공예정/입주예정으로 변경할 수 있다.
- [ ] 목표와 하위 사업 합계의 차이를 확인할 수 있다.
- [ ] 일정 미정 물량을 0과 구분한다.
- [ ] Source Mapping 미완료 데이터를 별도 표시한다.
- [ ] 중복집계를 탐지한다.
- [ ] Tree의 숫자에서 Leaf 사업으로 Drill-down할 수 있다.
- [ ] Leaf 사업에서 원천 데이터 Provenance까지 확인할 수 있다.
- [ ] 기준일을 변경하여 과거 Snapshot을 조회할 수 있다.
- [ ] Tree 결과를 CSV/XLSX로 Export할 수 있다.
- [ ] 테스트 Fixture로 집계값을 재현할 수 있다.

---

# 42. 구현 우선순위 수정

기존 작업순서에 Tree 검증기능을 추가한다.

```text
1. 프로젝트 구조 생성
2. 서울·경기 정책·사업 범위 기준선 승인
3. Master·지역·공급묶음 Schema 작성
4. DB Migration
5. 서울·경기 대표 Seed 입력
6. Tree Derived Model 설계
7. Fixture 기반 Tree 기본 UI 구현
8. Source Registry 승인
9. Collector Framework
10. Raw Snapshot
11. Source Object 생성
12. Mapping Admin
13. Source Mapping
14. 실적/일정 Dataset
15. Tree Current/Forecast 집계 연결
16. Validation·권한·공개등급 Rule 연결
17. Derived Mart
18. 품질검증과 복구훈련
19. 테스트
20. 문서화
```

중요:

**Tree의 기본 골격은 Collector보다 먼저 만든다.**

이유는 수집된 데이터가 최종적으로 어떤 계층과 지표로 보여야 하는지를 먼저 고정해야 Collector와 Mapping의 품질을 즉시 검증할 수 있기 때문이다.

---

# 43. Codex 추가 산출물

기존 산출물에 다음을 추가한다.

## 코드

- Tree Aggregation Service
- Forecast Bucket Calculator
- Validation Service
- Tree API
- Tree Admin/Validation UI

## 데이터

- `supply_tree_sample.csv`
- `tree_validation_issues.csv`
- `policy_progress_sample.csv`
- `region_supply_forecast_sample.csv`

## 문서

- `docs/tree_view_spec.md`
- `docs/aggregation_rules.md`
- `docs/validation_rules.md`
- `docs/tree_test_cases.md`

---

# 44. Tree 화면의 최종 검증 질문

Tree 화면에서 담당자는 최소한 다음 질문에 답할 수 있어야 한다.

> ① 이 정책의 공식 목표는 몇 호인가?  
> ② 현재 Master에 연결된 사업은 몇 호인가?  
> ③ 현재 실제로 어느 단계까지 몇 호가 진행됐는가?  
> ④ 향후 1년 안에 몇 호가 공급될 예정인가?  
> ⑤ 2년 후와 3년 후에는 각각 몇 호인가?  
> ⑥ 공급시점을 아직 알 수 없는 물량은 얼마인가?  
> ⑦ 어떤 프로그램·지구·블록에서 그 물량이 구성되는가?  
> ⑧ 목표와 하위 사업합계가 맞지 않는 곳은 어디인가?  
> ⑨ 외부 데이터 연결이 안 된 사업은 어디인가?  
> ⑩ 각 숫자의 원천자료는 무엇인가?

이 10개 질문을 Tree에서 답할 수 있으면, 통합 데이터셋이 지도 상황판과 정책 모니터링 기능으로 확장될 수 있는 최소 품질을 확보한 것으로 본다.

2026-10-03 블록 표시 보완: 지구별 목록 대신 블록명·총 공급계획·누적 목표·현재량·공사율·1/2/3년 전망을 담은 독립 그래프를 지도에 펼칩니다. 동일 최초 일정·공고로 조기/정상/지연을 비교하며 근거 미확보와 지연 검토를 구분합니다. 지구 대표점 연결선과 화면 배치를 사용하고 실제 블록 좌표로 추정하지 않습니다. [표시·근거·검증](POLICY_MAP_MONITOR.md).

블록 표시 압축: 블록당 82×142px 영역에 폭 10px 세로 막대 1개로 총계획·현재 확인량·누적 목표·1/2/3년 전망 눈금을 모아 표시합니다. 단계별 일정·공사율·상세 전망 물량은 마우스/클릭 상세로 이동하고 지도 휠 확대·축소를 유지합니다.


2026-10-03 시각화 보완: 확대 시 공식 공동주택 용지 윤곽을 입체화하고 지붕·외벽·창문·그림자를 추가했습니다. 실제 동별 건물 윤곽·높이는 미확보이며 시각 높이를 층수로 해석하지 않습니다. 지도·우측 그래프에서 미확인 수치·일정 상태·전망 눈금·단계를 생략하되 API·CSV 결측은 유지합니다. 원본 도형과 블록 좌표를 변경하지 않습니다. [표시 범위와 검증](POLICY_MAP_MONITOR.md).


2026-10-03 정책 진행현황 재구성: 정책 선택 → 목적/위치/기간/세부 공급 내역 → 연도별 공급계획 → 시도/시군구/블록 트리 시계열 → 원본 링크 순서입니다. 블록명·공급수량과 같은 행의 상단에 원천 계획 기간·예정량, 하단에 연도별 마지막 확보 실제 공정률을 표시합니다. 물량과 공정률·계획과 실적·현재 정책 연결과 과거 이력을 구분하고 미확보를 보간하지 않습니다. [정책 시계열 표시·집계 기준](POLICY_PROGRESS_AND_MATCHING.md).

## 2026-10-03 수집 전체성 점검 및 보완

수집 성공과 전체 사업 확보를 분리한다. 건축물대장 첫 페이지 제한을 제거하고, 1·29 공식 PDF 별첨의 행·합계 검증 후 서울·경기 사업을 추가한다. SH 최신 공개본을 사업 후보에 연결하며 GH 공식 계획·2018년 이후 주택 공고 목록을 새로운 원천으로 수집한다. 검증 화면에서 제공·조회·적재 건수, 지역·실제 자료 기간·미확보 범위를 표시한다. 기존 승인 기록과 과거 공개본은 보존하며 공급 실적을 추정 생성하지 않는다. 전수 인허가·정책 변경 이력·2018~2024년 사업별 공정은 남은 범위로 명시한다. [검증 결과와 남은 범위](COLLECTION_COVERAGE.md).

### 2026-10-03 미확보 자료 추가 확보 및 연속 수집

- 9·30 공식 첨부의 후보지 11개, 지정지구 5개, 이미지 추진 명단 47개를 대조한다. 서울·경기 추진 40개를 사용하고 지정지구 5개 중복을 통합한다. 개별 물량 미제공은 전국 합계를 배분하지 않는다. 이미지 대조 명단은 원본 PDF SHA-256과 함께 보존한다.
- SH 주택관리현황 2024~2026 파일 2,364개 판본 행과 GH 재건축 매입임대 21개 단지를 별도 재고 자료로 보존한다. SH 과거 세대수와 최신 임대세대수의 지표 차이를 공급 증감으로 오해하지 않도록 안내한다. 두 파일 연결에는 추가 키가 필요하지 않다.
- 행정표준코드의 서울·경기 현존 법정동 2,629개를 수집 대상으로 삼는다. 인허가·대장을 법정동별 전체 페이지 검증 후 누적 저장하고 완료 동을 건너뛰어 다음 동부터 계속한다. 최초 확대 18개 동을 확보했으며 전체 범위의 연속 수집을 실행한다. 호출량 제한·응답 오류·건수 변경이 발생하면 마지막 성공 배치를 보존하고 실패 원천을 표시한다.
- 홈페이지 검증 패널에서 실제 조회 완료·잔여 동 수를 표출한다. 재고·법정동 코드도 별도 유형과 연도 필터로 조회·CSV 다운로드를 제공한다. 목록은 DB 페이지 조회, 지도·상세는 필요한 식별자 조회, 과거 집계·CSV는 순차 처리로 대량 적재를 지원한다.
- 2018~2024년 사업별 공정률 원본은 아직 확보하지 못했다. 현재 공개 LH 첨부가 실제로 2025~2026년 자료인지 검증하며, 과거 기준일의 공정률을 추정 생성하지 않는다. 원천 요청 컬럼과 확보 경로는 COLLECTION_COVERAGE.md를 참고한다.
- 검증: 백엔드 149개 테스트, 운영 PostgreSQL 실제 조회, 홈페이지 파일 조회·CSV·모바일, 정책 시계열 트리, 지도 표시 검증 통과.

### 2026-10-03 과거 원천 실제 수집 보완

- LH 공공분양 2020~2025 XLSX, 연도별 입주계획 2022~2026 HWPX·DOCX, 단지정보 CSV를 추가 키 없이 자동 수집한다.
- 공급현황의 공고 공급호수와 총세대수, 입주계획 예정량, 단지정보 현재 재고·과거 일정을 별도 유형으로 저장한다. 확인되지 않은 실제 공정률이나 입주실적을 만들지 않는다.
- 홈페이지 유형·자료연도 조회와 CSV, 수집 원천·검증·연결 안내에 연결한다. 원본 링크·SHA-256·실제 소재지·연도별 상세 합계·누락 기간을 검증한다.
- 2018~2021 입주계획 공개본, 2018~2019 분양 공급현황 및 2018~2024 월별 사업 실제 공정률은 확보된 자료와 분리해 미확보 상태를 유지한다. 2026 입주계획의 원천 총계 불일치도 표시한다.
- `.env`/`.env.example`의 기존 키 목록에 신청·이용 안내 링크를 명시한다. 공개 파일을 얻는 데 불필요한 새 키를 신청 항목으로 추가하지 않는다.
- 범위·건수·검증은 `docs/COLLECTION_COVERAGE.md`, 키 및 원본 링크는 `docs/API_KEYS.md`에 기록한다.
