# PoC 10 — 단계별 수집 항목과 실제 출처: 스타맵 제작용 원본

## 1. 문서 목적과 기준

이 문서는 PoC 10 「the주택」의 **수집 원천 → 단계별 수집 항목과 출처** 화면을 설명하고, 외부 시각화 도구에서 스타맵을 만들 수 있도록 실제 집계의 노드와 관계를 Markdown으로 옮긴 자료다. 화면 안내 문구는 “단계 → 수집 항목 → 실제 출처 순서로 확인하세요.”이다.

- 집계 기준일: **2026-10-22**.
- 집계 생성 시각: **2026-10-22T08:59:07+09:00 (한국 시간)**.
- 대상: **9·7 정책에 연결된 232개 사업**.
- 범위: 정책 및 사업 기본정보와, 연결된 단계별 수집 근거에 실제 값이 있는 항목.
- 자료 성격: 화면이 사용하는 저장된 완료 집계의 스냅샷. 외부 사이트를 새로 수집하거나 출처 분류를 재판정한 자료가 아니다.

## 2. 다이어그램을 읽는 방법

첫 번째 층은 주택공급을 살펴보는 관리 단계, 두 번째 층은 그 단계에서 확보한 데이터 항목, 세 번째 층은 해당 항목을 확보한 실제 출처다. 한 항목에 여러 출처가 연결되고, 한 출처가 여러 항목과 단계에 반복 연결될 수 있다. 따라서 스타맵에서는 같은 출처 노드를 공유하면 수집 근거의 연결 구조를 볼 수 있다.

화면의 단계 표시 순서는 다음과 같다.

**정책 → 사업화 → 인허가 → 건축·착공 → 건축·준공 → 공급 → 입주**

이 순서는 조회 화면의 관리 순서다. 모든 사업이 이 순서대로만 진행되거나 준공 이후에만 모집·공급이 이루어진다는 법정 절차를 뜻하지 않는다. 스타맵의 주 연결선은 단계 간 선후관계가 아니라 **단계 → 수집 항목 → 출처** 관계로 그린다.

각 단계의 의미는 다음과 같다.

| 단계 | 설명 | 이번 스냅샷의 항목 수 | 항목→출처 연결 수 |
|---|---|---:|---:|
| 정책 | 상위 주택공급 정책의 명칭·발표일·목표 호수에 대한 근거 | 3 | 3 |
| 사업화 | 정책에 연결된 사업의 식별·분류·시행자·규모·지역·주소·공급 형태 및 사업화 관련 근거 | 10 | 166 |
| 인허가 | 인허가 관련 일자·호수와 예정 일정·예정 호수의 근거 | 4 | 26 |
| 건축·착공 | 착공 관련 일자·호수, 예정 일정·예정 호수와 관측 공정률의 근거 | 5 | 53 |
| 건축·준공 | 준공 관련 일자·호수와 예정 일정·예정 호수의 근거 | 4 | 20 |
| 공급 | 공급 관련 일자·호수와 예정 일정·예정 호수의 근거 | 4 | 44 |
| 입주 | 입주 관련 예정 일정·예정 호수와 확보된 일자의 근거 | 3 | 36 |

## 3. 수치·출처·항목 해석 규칙

1. **건수의 단위**: 괄호는 해당 항목을 확보한 서로 다른 원천 기록 건수입니다. 호수·전체 API 수집량이 아닙니다. 같은 기록이 여러 항목에 포함되므로 항목별 건수를 합산하지 않습니다.
2. **수집 범위**: 담당자 추정·수기 입력, 단계 선행조건으로 추론한 기록, 연결 상태만을 나타내는 기록은 이 다이어그램의 수집 건수에서 제외된다. 외부 근거를 연결한 `external_officer`라는 출처 ID는 남아 있을 수 있다. 출처 ID의 이름만으로 수기 입력이나 공식 여부를 판단하지 않는다.
3. **출처 구분**: 공식·비공식은 화면이 URL 도메인과 출처 ID를 바탕으로 부여한 분류값이다. 아래 자료는 이 값을 그대로 보존한다. 출처명이 “공식 공고·고시 원문”이어도 화면의 분류값은 비공식일 수 있다. 담당자가 사실을 확인했다는 이유로 게시처의 분류를 바꾸지 않는다.
4. **실제 출처 URL의 범위**: 원본 집계는 각 항목 안에서 `출처ID + 출처구분 + URL 호스트명`으로 원천 기록을 묶고, 그룹에서 먼저 확보된 URL 하나를 대표로 보관한다. 따라서 아래 URL은 그 그룹의 대표 링크이며, 해당 건수에 포함된 개별 원문 전체 목록은 아니다.
5. **실제·예정 구분**: `date`, `units`와 `plan_date`, `plan_units`는 별도 항목이다. 예정 일자·예정 호수를 실제 실적으로 바꾸지 않는다. `pct`는 수집 근거에 있는 관측 공정률이며, 전체 사업의 평균 공정률을 뜻하지 않는다.
6. **미확보와 0 구분**: 표시되지 않은 항목이나 출처 연결이 없다는 사실은 실제 실적이 0이라는 뜻이 아니다. 예를 들어 이번 입주 단계에는 실제 호수 항목이 없지만 이를 입주 0호로 해석하지 않는다.
7. **스키마 경로와 노드 식별**: 실제 일자와 예정 일자는 모두 `stage_source.date` 경로를 쓴다. 호수도 마찬가지다. 경로만으로 항목을 합치지 말고, 아래의 단계 ID와 필드 키를 결합한 항목 노드 ID를 사용한다.
8. **문서 목록과 구분**: 화면 하단의 수집·검토 문서 게시처 목록은 별도 목록이다. 아래 스타맵은 7단계 다이어그램의 항목→출처 연결만 포함한다. 문서가 수집되었다는 사실만으로 정책 귀속이나 실적 채택이 확정되지는 않는다.

## 4. 외부 도구에 전달할 스타맵 제작 지시문

> 이 문서의 5절 계층 구조와 6절 출처 목록을 이용해 「주택공급 단계별 수집 항목과 출처」 스타맵을 제작한다. 중앙에 `ROOT_POC10_COLLECTION` 노드를 놓고, 그 주위에 7개 단계 노드를 표시한다. 각 단계에는 해당 단계의 수집 항목을 연결하고, 각 항목에는 나열된 출처 노드를 연결한다. 단계→항목은 “수집 항목”, 항목→출처는 “확보 근거” 관계다. 같은 SRC ID는 하나의 노드로 공유한다. 각 항목→출처 연결에 기록 건수를 표시하고, 출처 노드에는 출처명·도메인·공식/비공식 분류·대표 URL을 보존한다. 예정 항목은 실제 항목과 구별하여 표시한다. 주택 호수로 오해할 수 있는 전체 건수 합계나 사업 진행률을 새로 계산하지 않는다. 모든 노드와 연결은 본문에 있는 데이터만 사용한다.

권장 표시 방식:

- 단계 노드: 가장 큰 크기로 표시하고 7단계 순서를 유지한다.
- 수집 항목 노드: 단계와 가까이 배치한다. 예정 항목은 점선 테두리 등으로 구별한다.
- 출처 노드: 공식 출처와 비공식 출처의 색상을 다르게 하고 범례를 둔다.
- 출처가 여러 단계에 공통으로 연결되면 하나의 공유 노드로 표시한다. 같은 이름이라도 SRC ID가 다르면 임의로 합치지 않는다.
- 출처의 긴 URL은 상세 정보에 넣고, 기본 라벨은 출처명과 도메인으로 표시한다.
- 기본 연결선 굵기는 동일하게 한다. 기록 수를 반영한다면 “원천 기록 수”라고 명시하고 주택 규모나 신뢰도 점수로 해석하지 않는다.

### 노드와 연결의 식별 규칙

| 종류 | ID 규칙 | 표시 내용 |
|---|---|---|
| 중앙 | `ROOT_POC10_COLLECTION` | 단계별 수집 항목과 출처 |
| 단계 | `STAGE_<단계코드>` | 단계명 |
| 항목 | `FIELD_<단계코드>_<필드키>` | 수집 항목명·스키마 경로 |
| 출처 | `SRC_001` 등 | 출처명·구분·도메인·대표 URL |

출처 노드는 **출처ID + 출처구분 + 대표 URL**이 같은 경우 공유한다. 이 규칙은 MD를 스타맵으로 변환하기 위한 식별 규칙이다. 같은 기관의 서로 다른 원문이나 같은 URL을 사용하는 서로 다른 수집경로가 별도 노드일 수 있으므로 출처 노드 수를 기관 수·고유 문서 수·전체 등록 수집경로 수로 읽지 않는다.

이번 자료는 **7개 단계, 33개 항목, 83개 출처·대표URL 노드, 348개의 항목→출처 연결**을 포함한다. 중앙 노드까지 포함하면 노드는 124개이며, 중앙→단계 7개와 단계→항목 33개를 포함한 연결은 388개다. 이는 시각화 구조의 개수이고 수집 기록 총량이 아니다.

## 5. 단계 → 수집 항목 → 실제 출처 전체 계층

아래에는 화면에 있는 모든 항목→출처 연결을 빠짐없이 담았다. 출처의 SRC ID는 6절의 대표 URL과 연결된다. 괄호 안 건수는 해당 항목·출처 그룹에 속한 서로 다른 원천 기록 수다.

### 1. 정책

- 단계 노드 ID: `STAGE_POLICY`
- 의미: 상위 주택공급 정책의 명칭·발표일·목표 호수에 대한 근거.

#### 정책 → 정책명

- 항목 노드 ID: `FIELD_POLICY_name`
- 필드 키: `name`
- 스키마 경로: `policy.name`
- 실제 출처:

  - `SRC_001` — 9·7 주택공급 확대방안 · d.nts.go.kr · **공식 출처** · **1건**

#### 정책 → 정책 발표일

- 항목 노드 ID: `FIELD_POLICY_announced_at`
- 필드 키: `announced_at`
- 스키마 경로: `policy.announced_at`
- 실제 출처:

  - `SRC_001` — 9·7 주택공급 확대방안 · d.nts.go.kr · **공식 출처** · **1건**

#### 정책 → 정책 목표 호수

- 항목 노드 ID: `FIELD_POLICY_target_units`
- 필드 키: `target_units`
- 스키마 경로: `policy.target_units`
- 실제 출처:

  - `SRC_001` — 9·7 주택공급 확대방안 · d.nts.go.kr · **공식 출처** · **1건**


### 2. 사업화

- 단계 노드 ID: `STAGE_BUSINESS`
- 의미: 정책에 연결된 사업의 식별·분류·시행자·규모·지역·주소·공급 형태 및 사업화 관련 근거.

#### 사업화 → 사업명

- 항목 노드 ID: `FIELD_BUSINESS_name`
- 필드 키: `name`
- 스키마 경로: `project.name`
- 실제 출처:

  - `SRC_002` — 1·29 도심 주택공급 확대 및 신속화 · www.korea.kr · **공식 출처** · **3건**
  - `SRC_003` — 9·7 주택공급 확대방안 · eiec.kdi.re.kr · **공식 출처** · **3건**
  - `SRC_004` — 9·7 주택공급 확대방안 · molit.go.kr · **공식 출처** · **13건**
  - `SRC_005` — GH 주택 분양·임대 공급계획 · www.gh.or.kr · **공식 출처** · **2건**
  - `SRC_006` — LH 9·7 후속 민간참여 공모 · 블록별 착공계획 · www.lh.or.kr · **공식 출처** · **19건**
  - `SRC_007` — LH 건설공사 현황 · www.lh.or.kr · **공식 출처** · **87건**
  - `SRC_008` — LH 블록별 실제 공정률 · 공개 상세 이력 · apply.lh.or.kr · **공식 출처** · **10건**
  - `SRC_009` — LH 연간 분양주택 공급계획 · apply.lh.or.kr · **공식 출처** · **34건**
  - `SRC_010` — LH 연간 임대주택 공급계획 · apply.lh.or.kr · **공식 출처** · **18건**
  - `SRC_011` — LH 인천 분양 공급계획 · apply.lh.or.kr · **공식 출처** · **5건**
  - `SRC_012` — LH 인천 실제 착공·공정 현황 · www.lh.or.kr · **공식 출처** · **16건**
  - `SRC_013` — LH 인천 임대 공급계획 · apply.lh.or.kr · **공식 출처** · **5건**
  - `SRC_014` — SH 최신 공개본 사업 연결 · www.data.go.kr · **공식 출처** · **2건**
  - `SRC_015` — iH 공식 주택 사업·분양·임대 모집공고 · www.ih.co.kr · **공식 출처** · **7건**
  - `SRC_016` — official_document · www.g2b.go.kr · **공식 출처** · **1건**
  - `SRC_017` — official_document · www.fsc.go.kr · **공식 출처** · **1건**
  - `SRC_018` — official_document · cis.seoul.go.kr · **공식 출처** · **1건**
  - `SRC_019` — 건축HUB 주택인허가 · www.data.go.kr · **공식 출처** · **1건**
  - `SRC_020` — 국토부 전국 정비사업 통합 현황 · 수도권 후보 · www.data.go.kr · **공식 출처** · **3건**
  - `SRC_021` — official_document · ms.smc.seoul.kr · **비공식 출처** · **1건**

#### 사업화 → 사업 분류

- 항목 노드 ID: `FIELD_BUSINESS_program`
- 필드 키: `program`
- 스키마 경로: `project.program`
- 실제 출처:

  - `SRC_002` — 1·29 도심 주택공급 확대 및 신속화 · www.korea.kr · **공식 출처** · **3건**
  - `SRC_003` — 9·7 주택공급 확대방안 · eiec.kdi.re.kr · **공식 출처** · **3건**
  - `SRC_004` — 9·7 주택공급 확대방안 · molit.go.kr · **공식 출처** · **13건**
  - `SRC_005` — GH 주택 분양·임대 공급계획 · www.gh.or.kr · **공식 출처** · **2건**
  - `SRC_006` — LH 9·7 후속 민간참여 공모 · 블록별 착공계획 · www.lh.or.kr · **공식 출처** · **19건**
  - `SRC_007` — LH 건설공사 현황 · www.lh.or.kr · **공식 출처** · **87건**
  - `SRC_008` — LH 블록별 실제 공정률 · 공개 상세 이력 · apply.lh.or.kr · **공식 출처** · **10건**
  - `SRC_009` — LH 연간 분양주택 공급계획 · apply.lh.or.kr · **공식 출처** · **34건**
  - `SRC_010` — LH 연간 임대주택 공급계획 · apply.lh.or.kr · **공식 출처** · **18건**
  - `SRC_011` — LH 인천 분양 공급계획 · apply.lh.or.kr · **공식 출처** · **5건**
  - `SRC_012` — LH 인천 실제 착공·공정 현황 · www.lh.or.kr · **공식 출처** · **16건**
  - `SRC_013` — LH 인천 임대 공급계획 · apply.lh.or.kr · **공식 출처** · **5건**
  - `SRC_014` — SH 최신 공개본 사업 연결 · www.data.go.kr · **공식 출처** · **2건**
  - `SRC_015` — iH 공식 주택 사업·분양·임대 모집공고 · www.ih.co.kr · **공식 출처** · **7건**
  - `SRC_016` — official_document · www.g2b.go.kr · **공식 출처** · **1건**
  - `SRC_017` — official_document · www.fsc.go.kr · **공식 출처** · **1건**
  - `SRC_018` — official_document · cis.seoul.go.kr · **공식 출처** · **1건**
  - `SRC_019` — 건축HUB 주택인허가 · www.data.go.kr · **공식 출처** · **1건**
  - `SRC_020` — 국토부 전국 정비사업 통합 현황 · 수도권 후보 · www.data.go.kr · **공식 출처** · **3건**
  - `SRC_021` — official_document · ms.smc.seoul.kr · **비공식 출처** · **1건**

#### 사업화 → 시행자

- 항목 노드 ID: `FIELD_BUSINESS_developer`
- 필드 키: `developer`
- 스키마 경로: `project.developer`
- 실제 출처:

  - `SRC_002` — 1·29 도심 주택공급 확대 및 신속화 · www.korea.kr · **공식 출처** · **3건**
  - `SRC_003` — 9·7 주택공급 확대방안 · eiec.kdi.re.kr · **공식 출처** · **3건**
  - `SRC_004` — 9·7 주택공급 확대방안 · molit.go.kr · **공식 출처** · **13건**
  - `SRC_005` — GH 주택 분양·임대 공급계획 · www.gh.or.kr · **공식 출처** · **2건**
  - `SRC_006` — LH 9·7 후속 민간참여 공모 · 블록별 착공계획 · www.lh.or.kr · **공식 출처** · **19건**
  - `SRC_007` — LH 건설공사 현황 · www.lh.or.kr · **공식 출처** · **87건**
  - `SRC_008` — LH 블록별 실제 공정률 · 공개 상세 이력 · apply.lh.or.kr · **공식 출처** · **10건**
  - `SRC_009` — LH 연간 분양주택 공급계획 · apply.lh.or.kr · **공식 출처** · **34건**
  - `SRC_010` — LH 연간 임대주택 공급계획 · apply.lh.or.kr · **공식 출처** · **18건**
  - `SRC_011` — LH 인천 분양 공급계획 · apply.lh.or.kr · **공식 출처** · **5건**
  - `SRC_012` — LH 인천 실제 착공·공정 현황 · www.lh.or.kr · **공식 출처** · **16건**
  - `SRC_013` — LH 인천 임대 공급계획 · apply.lh.or.kr · **공식 출처** · **5건**
  - `SRC_014` — SH 최신 공개본 사업 연결 · www.data.go.kr · **공식 출처** · **2건**
  - `SRC_015` — iH 공식 주택 사업·분양·임대 모집공고 · www.ih.co.kr · **공식 출처** · **7건**
  - `SRC_016` — official_document · www.g2b.go.kr · **공식 출처** · **1건**
  - `SRC_017` — official_document · www.fsc.go.kr · **공식 출처** · **1건**
  - `SRC_018` — official_document · cis.seoul.go.kr · **공식 출처** · **1건**
  - `SRC_020` — 국토부 전국 정비사업 통합 현황 · 수도권 후보 · www.data.go.kr · **공식 출처** · **3건**
  - `SRC_021` — official_document · ms.smc.seoul.kr · **비공식 출처** · **1건**

#### 사업화 → 사업 계획 호수

- 항목 노드 ID: `FIELD_BUSINESS_planned_units`
- 필드 키: `planned_units`
- 스키마 경로: `project.planned_units`
- 실제 출처:

  - `SRC_002` — 1·29 도심 주택공급 확대 및 신속화 · www.korea.kr · **공식 출처** · **3건**
  - `SRC_003` — 9·7 주택공급 확대방안 · eiec.kdi.re.kr · **공식 출처** · **2건**
  - `SRC_004` — 9·7 주택공급 확대방안 · molit.go.kr · **공식 출처** · **10건**
  - `SRC_005` — GH 주택 분양·임대 공급계획 · www.gh.or.kr · **공식 출처** · **2건**
  - `SRC_006` — LH 9·7 후속 민간참여 공모 · 블록별 착공계획 · www.lh.or.kr · **공식 출처** · **19건**
  - `SRC_007` — LH 건설공사 현황 · www.lh.or.kr · **공식 출처** · **87건**
  - `SRC_008` — LH 블록별 실제 공정률 · 공개 상세 이력 · apply.lh.or.kr · **공식 출처** · **10건**
  - `SRC_009` — LH 연간 분양주택 공급계획 · apply.lh.or.kr · **공식 출처** · **31건**
  - `SRC_010` — LH 연간 임대주택 공급계획 · apply.lh.or.kr · **공식 출처** · **18건**
  - `SRC_011` — LH 인천 분양 공급계획 · apply.lh.or.kr · **공식 출처** · **5건**
  - `SRC_012` — LH 인천 실제 착공·공정 현황 · www.lh.or.kr · **공식 출처** · **16건**
  - `SRC_013` — LH 인천 임대 공급계획 · apply.lh.or.kr · **공식 출처** · **5건**
  - `SRC_014` — SH 최신 공개본 사업 연결 · www.data.go.kr · **공식 출처** · **2건**
  - `SRC_015` — iH 공식 주택 사업·분양·임대 모집공고 · www.ih.co.kr · **공식 출처** · **6건**
  - `SRC_016` — official_document · www.g2b.go.kr · **공식 출처** · **1건**
  - `SRC_017` — official_document · www.fsc.go.kr · **공식 출처** · **1건**
  - `SRC_018` — official_document · cis.seoul.go.kr · **공식 출처** · **1건**
  - `SRC_019` — 건축HUB 주택인허가 · www.data.go.kr · **공식 출처** · **1건**
  - `SRC_020` — 국토부 전국 정비사업 통합 현황 · 수도권 후보 · www.data.go.kr · **공식 출처** · **3건**
  - `SRC_021` — official_document · ms.smc.seoul.kr · **비공식 출처** · **1건**

#### 사업화 → 시도

- 항목 노드 ID: `FIELD_BUSINESS_region`
- 필드 키: `region`
- 스키마 경로: `project.region`
- 실제 출처:

  - `SRC_002` — 1·29 도심 주택공급 확대 및 신속화 · www.korea.kr · **공식 출처** · **3건**
  - `SRC_003` — 9·7 주택공급 확대방안 · eiec.kdi.re.kr · **공식 출처** · **3건**
  - `SRC_004` — 9·7 주택공급 확대방안 · molit.go.kr · **공식 출처** · **13건**
  - `SRC_005` — GH 주택 분양·임대 공급계획 · www.gh.or.kr · **공식 출처** · **2건**
  - `SRC_006` — LH 9·7 후속 민간참여 공모 · 블록별 착공계획 · www.lh.or.kr · **공식 출처** · **19건**
  - `SRC_007` — LH 건설공사 현황 · www.lh.or.kr · **공식 출처** · **87건**
  - `SRC_008` — LH 블록별 실제 공정률 · 공개 상세 이력 · apply.lh.or.kr · **공식 출처** · **10건**
  - `SRC_009` — LH 연간 분양주택 공급계획 · apply.lh.or.kr · **공식 출처** · **34건**
  - `SRC_010` — LH 연간 임대주택 공급계획 · apply.lh.or.kr · **공식 출처** · **18건**
  - `SRC_011` — LH 인천 분양 공급계획 · apply.lh.or.kr · **공식 출처** · **5건**
  - `SRC_012` — LH 인천 실제 착공·공정 현황 · www.lh.or.kr · **공식 출처** · **16건**
  - `SRC_013` — LH 인천 임대 공급계획 · apply.lh.or.kr · **공식 출처** · **5건**
  - `SRC_014` — SH 최신 공개본 사업 연결 · www.data.go.kr · **공식 출처** · **2건**
  - `SRC_015` — iH 공식 주택 사업·분양·임대 모집공고 · www.ih.co.kr · **공식 출처** · **7건**
  - `SRC_016` — official_document · www.g2b.go.kr · **공식 출처** · **1건**
  - `SRC_017` — official_document · www.fsc.go.kr · **공식 출처** · **1건**
  - `SRC_018` — official_document · cis.seoul.go.kr · **공식 출처** · **1건**
  - `SRC_019` — 건축HUB 주택인허가 · www.data.go.kr · **공식 출처** · **1건**
  - `SRC_020` — 국토부 전국 정비사업 통합 현황 · 수도권 후보 · www.data.go.kr · **공식 출처** · **3건**
  - `SRC_021` — official_document · ms.smc.seoul.kr · **비공식 출처** · **1건**

#### 사업화 → 시군구

- 항목 노드 ID: `FIELD_BUSINESS_municipality`
- 필드 키: `municipality`
- 스키마 경로: `project.municipality`
- 실제 출처:

  - `SRC_002` — 1·29 도심 주택공급 확대 및 신속화 · www.korea.kr · **공식 출처** · **3건**
  - `SRC_003` — 9·7 주택공급 확대방안 · eiec.kdi.re.kr · **공식 출처** · **3건**
  - `SRC_004` — 9·7 주택공급 확대방안 · molit.go.kr · **공식 출처** · **13건**
  - `SRC_005` — GH 주택 분양·임대 공급계획 · www.gh.or.kr · **공식 출처** · **2건**
  - `SRC_006` — LH 9·7 후속 민간참여 공모 · 블록별 착공계획 · www.lh.or.kr · **공식 출처** · **19건**
  - `SRC_007` — LH 건설공사 현황 · www.lh.or.kr · **공식 출처** · **87건**
  - `SRC_008` — LH 블록별 실제 공정률 · 공개 상세 이력 · apply.lh.or.kr · **공식 출처** · **10건**
  - `SRC_009` — LH 연간 분양주택 공급계획 · apply.lh.or.kr · **공식 출처** · **34건**
  - `SRC_010` — LH 연간 임대주택 공급계획 · apply.lh.or.kr · **공식 출처** · **18건**
  - `SRC_011` — LH 인천 분양 공급계획 · apply.lh.or.kr · **공식 출처** · **5건**
  - `SRC_012` — LH 인천 실제 착공·공정 현황 · www.lh.or.kr · **공식 출처** · **16건**
  - `SRC_013` — LH 인천 임대 공급계획 · apply.lh.or.kr · **공식 출처** · **5건**
  - `SRC_015` — iH 공식 주택 사업·분양·임대 모집공고 · www.ih.co.kr · **공식 출처** · **7건**
  - `SRC_016` — official_document · www.g2b.go.kr · **공식 출처** · **1건**
  - `SRC_017` — official_document · www.fsc.go.kr · **공식 출처** · **1건**
  - `SRC_018` — official_document · cis.seoul.go.kr · **공식 출처** · **1건**
  - `SRC_020` — 국토부 전국 정비사업 통합 현황 · 수도권 후보 · www.data.go.kr · **공식 출처** · **3건**
  - `SRC_021` — official_document · ms.smc.seoul.kr · **비공식 출처** · **1건**

#### 사업화 → 주소

- 항목 노드 ID: `FIELD_BUSINESS_address`
- 필드 키: `address`
- 스키마 경로: `project.address`
- 실제 출처:

  - `SRC_004` — 9·7 주택공급 확대방안 · molit.go.kr · **공식 출처** · **1건**
  - `SRC_015` — iH 공식 주택 사업·분양·임대 모집공고 · www.ih.co.kr · **공식 출처** · **7건**
  - `SRC_016` — official_document · www.g2b.go.kr · **공식 출처** · **1건**
  - `SRC_018` — official_document · cis.seoul.go.kr · **공식 출처** · **1건**
  - `SRC_019` — 건축HUB 주택인허가 · www.data.go.kr · **공식 출처** · **1건**
  - `SRC_021` — official_document · ms.smc.seoul.kr · **비공식 출처** · **1건**

#### 사업화 → 공급 형태

- 항목 노드 ID: `FIELD_BUSINESS_tenure`
- 필드 키: `tenure`
- 스키마 경로: `project.tenure`
- 실제 출처:

  - `SRC_002` — 1·29 도심 주택공급 확대 및 신속화 · www.korea.kr · **공식 출처** · **3건**
  - `SRC_003` — 9·7 주택공급 확대방안 · eiec.kdi.re.kr · **공식 출처** · **3건**
  - `SRC_004` — 9·7 주택공급 확대방안 · molit.go.kr · **공식 출처** · **13건**
  - `SRC_005` — GH 주택 분양·임대 공급계획 · www.gh.or.kr · **공식 출처** · **2건**
  - `SRC_006` — LH 9·7 후속 민간참여 공모 · 블록별 착공계획 · www.lh.or.kr · **공식 출처** · **19건**
  - `SRC_007` — LH 건설공사 현황 · www.lh.or.kr · **공식 출처** · **87건**
  - `SRC_008` — LH 블록별 실제 공정률 · 공개 상세 이력 · apply.lh.or.kr · **공식 출처** · **10건**
  - `SRC_009` — LH 연간 분양주택 공급계획 · apply.lh.or.kr · **공식 출처** · **34건**
  - `SRC_010` — LH 연간 임대주택 공급계획 · apply.lh.or.kr · **공식 출처** · **18건**
  - `SRC_011` — LH 인천 분양 공급계획 · apply.lh.or.kr · **공식 출처** · **5건**
  - `SRC_012` — LH 인천 실제 착공·공정 현황 · www.lh.or.kr · **공식 출처** · **16건**
  - `SRC_013` — LH 인천 임대 공급계획 · apply.lh.or.kr · **공식 출처** · **5건**
  - `SRC_014` — SH 최신 공개본 사업 연결 · www.data.go.kr · **공식 출처** · **2건**
  - `SRC_015` — iH 공식 주택 사업·분양·임대 모집공고 · www.ih.co.kr · **공식 출처** · **7건**
  - `SRC_016` — official_document · www.g2b.go.kr · **공식 출처** · **1건**
  - `SRC_017` — official_document · www.fsc.go.kr · **공식 출처** · **1건**
  - `SRC_018` — official_document · cis.seoul.go.kr · **공식 출처** · **1건**
  - `SRC_021` — official_document · ms.smc.seoul.kr · **비공식 출처** · **1건**

#### 사업화 → 일자

- 항목 노드 ID: `FIELD_BUSINESS_date`
- 필드 키: `date`
- 스키마 경로: `stage_source.date`
- 실제 출처:

  - `SRC_005` — GH 주택 분양·임대 공급계획 · www.gh.or.kr · **공식 출처** · **2건**
  - `SRC_007` — LH 건설공사 현황 · www.lh.or.kr · **공식 출처** · **87건**
  - `SRC_022` — LH 블록별 실제 공정률 · 공개 상세 이력 · apply.lh.or.kr · **공식 출처** · **9건**
  - `SRC_009` — LH 연간 분양주택 공급계획 · apply.lh.or.kr · **공식 출처** · **34건**
  - `SRC_010` — LH 연간 임대주택 공급계획 · apply.lh.or.kr · **공식 출처** · **18건**
  - `SRC_011` — LH 인천 분양 공급계획 · apply.lh.or.kr · **공식 출처** · **5건**
  - `SRC_012` — LH 인천 실제 착공·공정 현황 · www.lh.or.kr · **공식 출처** · **16건**
  - `SRC_013` — LH 인천 임대 공급계획 · apply.lh.or.kr · **공식 출처** · **5건**
  - `SRC_023` — 경기 고양창릉 지구지정 변경 고시 원문 · www.molit.go.kr · **공식 출처** · **1건**
  - `SRC_024` — 공식 공고·고시 원문 · www.lh.or.kr · **공식 출처** · **4건**
  - `SRC_025` — 공식 공고·고시 원문 · www.i-sh.co.kr · **공식 출처** · **1건**
  - `SRC_026` — 공식 공고·고시 원문 · www.molit.go.kr · **공식 출처** · **1건**
  - `SRC_027` — 공식 공고·고시 원문 · www.incheon.go.kr · **공식 출처** · **1건**
  - `SRC_020` — 국토부 전국 정비사업 통합 현황 · 수도권 후보 · www.data.go.kr · **공식 출처** · **3건**
  - `SRC_028` — 서울 정비사업 정보몽땅·추진경과 · cleanup.seoul.go.kr · **공식 출처** · **2건**

#### 사업화 → 호수

- 항목 노드 ID: `FIELD_BUSINESS_units`
- 필드 키: `units`
- 스키마 경로: `stage_source.units`
- 실제 출처:

  - `SRC_005` — GH 주택 분양·임대 공급계획 · www.gh.or.kr · **공식 출처** · **2건**
  - `SRC_007` — LH 건설공사 현황 · www.lh.or.kr · **공식 출처** · **87건**
  - `SRC_022` — LH 블록별 실제 공정률 · 공개 상세 이력 · apply.lh.or.kr · **공식 출처** · **9건**
  - `SRC_009` — LH 연간 분양주택 공급계획 · apply.lh.or.kr · **공식 출처** · **31건**
  - `SRC_010` — LH 연간 임대주택 공급계획 · apply.lh.or.kr · **공식 출처** · **18건**
  - `SRC_011` — LH 인천 분양 공급계획 · apply.lh.or.kr · **공식 출처** · **5건**
  - `SRC_012` — LH 인천 실제 착공·공정 현황 · www.lh.or.kr · **공식 출처** · **16건**
  - `SRC_013` — LH 인천 임대 공급계획 · apply.lh.or.kr · **공식 출처** · **5건**
  - `SRC_024` — 공식 공고·고시 원문 · www.lh.or.kr · **공식 출처** · **3건**
  - `SRC_020` — 국토부 전국 정비사업 통합 현황 · 수도권 후보 · www.data.go.kr · **공식 출처** · **3건**


### 3. 인허가

- 단계 노드 ID: `STAGE_APPROVAL`
- 의미: 인허가 관련 일자·호수와 예정 일정·예정 호수의 근거.

#### 인허가 → 일자

- 항목 노드 ID: `FIELD_APPROVAL_date`
- 필드 키: `date`
- 스키마 경로: `stage_source.date`
- 실제 출처:

  - `SRC_029` — 9·7 인천 주택인허가 원천 · www.data.go.kr · **공식 출처** · **3건**
  - `SRC_007` — LH 건설공사 현황 · www.lh.or.kr · **공식 출처** · **41건**
  - `SRC_022` — LH 블록별 실제 공정률 · 공개 상세 이력 · apply.lh.or.kr · **공식 출처** · **6건**
  - `SRC_009` — LH 연간 분양주택 공급계획 · apply.lh.or.kr · **공식 출처** · **2건**
  - `SRC_010` — LH 연간 임대주택 공급계획 · apply.lh.or.kr · **공식 출처** · **1건**
  - `SRC_012` — LH 인천 실제 착공·공정 현황 · www.lh.or.kr · **공식 출처** · **15건**
  - `SRC_019` — 건축HUB 주택인허가 · www.data.go.kr · **공식 출처** · **53건**
  - `SRC_030` — 공식 공고·고시 원문 · molit.go.kr · **공식 출처** · **1건**
  - `SRC_031` — 공식 공고·고시 원문 · www.eum.go.kr · **공식 출처** · **18건**
  - `SRC_032` — 공식 공고·고시 원문 · www.molit.go.kr · **공식 출처** · **4건**
  - `SRC_027` — 공식 공고·고시 원문 · www.incheon.go.kr · **공식 출처** · **1건**
  - `SRC_028` — 서울 정비사업 정보몽땅·추진경과 · cleanup.seoul.go.kr · **공식 출처** · **2건**

#### 인허가 → 호수

- 항목 노드 ID: `FIELD_APPROVAL_units`
- 필드 키: `units`
- 스키마 경로: `stage_source.units`
- 실제 출처:

  - `SRC_029` — 9·7 인천 주택인허가 원천 · www.data.go.kr · **공식 출처** · **3건**
  - `SRC_007` — LH 건설공사 현황 · www.lh.or.kr · **공식 출처** · **41건**
  - `SRC_022` — LH 블록별 실제 공정률 · 공개 상세 이력 · apply.lh.or.kr · **공식 출처** · **6건**
  - `SRC_009` — LH 연간 분양주택 공급계획 · apply.lh.or.kr · **공식 출처** · **2건**
  - `SRC_010` — LH 연간 임대주택 공급계획 · apply.lh.or.kr · **공식 출처** · **1건**
  - `SRC_012` — LH 인천 실제 착공·공정 현황 · www.lh.or.kr · **공식 출처** · **15건**
  - `SRC_019` — 건축HUB 주택인허가 · www.data.go.kr · **공식 출처** · **51건**
  - `SRC_033` — 공식 공고·고시 원문 · www.eum.go.kr · **공식 출처** · **1건**
  - `SRC_034` — 공식 공고·고시 원문 · www.molit.go.kr · **공식 출처** · **2건**
  - `SRC_027` — 공식 공고·고시 원문 · www.incheon.go.kr · **공식 출처** · **1건**

#### 인허가 → 예정 일자

- 항목 노드 ID: `FIELD_APPROVAL_plan_date`
- 필드 키: `plan_date`
- 스키마 경로: `stage_source.date`
- 실제 출처:

  - `SRC_035` — 공식 공고·고시 원문 · www.lh.or.kr · **공식 출처** · **1건**
  - `SRC_032` — 공식 공고·고시 원문 · www.molit.go.kr · **공식 출처** · **3건**

#### 인허가 → 예정 호수

- 항목 노드 ID: `FIELD_APPROVAL_plan_units`
- 필드 키: `plan_units`
- 스키마 경로: `stage_source.units`
- 실제 출처:

  - `SRC_035` — 공식 공고·고시 원문 · www.lh.or.kr · **공식 출처** · **1건**
  - `SRC_032` — 공식 공고·고시 원문 · www.molit.go.kr · **공식 출처** · **3건**


### 4. 건축·착공

- 단계 노드 ID: `STAGE_CONSTRUCTION`
- 의미: 착공 관련 일자·호수, 예정 일정·예정 호수와 관측 공정률의 근거.

#### 건축·착공 → 일자

- 항목 노드 ID: `FIELD_CONSTRUCTION_date`
- 필드 키: `date`
- 스키마 경로: `stage_source.date`
- 실제 출처:

  - `SRC_007` — LH 건설공사 현황 · www.lh.or.kr · **공식 출처** · **156건**
  - `SRC_036` — LH 블록별 실제 공정률 · 공개 상세 이력 · apply.lh.or.kr · **공식 출처** · **76건**
  - `SRC_012` — LH 인천 실제 착공·공정 현황 · www.lh.or.kr · **공식 출처** · **31건**
  - `SRC_037` — external_officer · www.gwanak.go.kr · **공식 출처** · **1건**
  - `SRC_038` — 공식 공고·고시 원문 · apply.lh.or.kr · **공식 출처** · **1건**
  - `SRC_039` — 공식 공고·고시 원문 · cis.seoul.go.kr · **공식 출처** · **4건**
  - `SRC_040` — 공식 공고·고시 원문 · www.gwanak.go.kr · **공식 출처** · **1건**
  - `SRC_041` — 공식 공고·고시 원문 · www.korea.kr · **공식 출처** · **2건**
  - `SRC_042` — 공식 공고·고시 원문 · www.seoul.go.kr · **공식 출처** · **2건**
  - `SRC_043` — 공식 공고·고시 원문 · housinginfo.seoul.go.kr · **공식 출처** · **1건**
  - `SRC_044` — 공식 공고·고시 원문 · www.lh.or.kr · **공식 출처** · **1건**
  - `SRC_045` — external_officer · dwce.co.kr · **비공식 출처** · **1건**
  - `SRC_046` — external_officer · m.go.seoul.co.kr · **비공식 출처** · **1건**
  - `SRC_047` — external_officer · go.seoul.co.kr · **비공식 출처** · **1건**
  - `SRC_048` — external_officer · m.richgo.ai · **비공식 출처** · **1건**
  - `SRC_049` — external_officer · nwww.newsis.com · **비공식 출처** · **1건**
  - `SRC_021` — 공식 공고·고시 원문 · ms.smc.seoul.kr · **비공식 출처** · **1건**

#### 건축·착공 → 관측 공정률

- 항목 노드 ID: `FIELD_CONSTRUCTION_pct`
- 필드 키: `pct`
- 스키마 경로: `stage_source.pct`
- 실제 출처:

  - `SRC_007` — LH 건설공사 현황 · www.lh.or.kr · **공식 출처** · **69건**
  - `SRC_036` — LH 블록별 실제 공정률 · 공개 상세 이력 · apply.lh.or.kr · **공식 출처** · **76건**
  - `SRC_012` — LH 인천 실제 착공·공정 현황 · www.lh.or.kr · **공식 출처** · **15건**

#### 건축·착공 → 예정 일자

- 항목 노드 ID: `FIELD_CONSTRUCTION_plan_date`
- 필드 키: `plan_date`
- 스키마 경로: `stage_source.date`
- 실제 출처:

  - `SRC_002` — 1·29 도심 주택공급 확대 및 신속화 · www.korea.kr · **공식 출처** · **3건**
  - `SRC_003` — 9·7 주택공급 확대방안 · eiec.kdi.re.kr · **공식 출처** · **2건**
  - `SRC_004` — 9·7 주택공급 확대방안 · molit.go.kr · **공식 출처** · **6건**
  - `SRC_006` — LH 9·7 후속 민간참여 공모 · 블록별 착공계획 · www.lh.or.kr · **공식 출처** · **28건**
  - `SRC_007` — LH 건설공사 현황 · www.lh.or.kr · **공식 출처** · **87건**
  - `SRC_022` — LH 블록별 실제 공정률 · 공개 상세 이력 · apply.lh.or.kr · **공식 출처** · **13건**
  - `SRC_012` — LH 인천 실제 착공·공정 현황 · www.lh.or.kr · **공식 출처** · **16건**
  - `SRC_035` — 공식 공고·고시 원문 · www.lh.or.kr · **공식 출처** · **1건**
  - `SRC_032` — 공식 공고·고시 원문 · www.molit.go.kr · **공식 출처** · **5건**
  - `SRC_050` — 공식 공고·고시 원문 · mas.smc.seoul.kr · **비공식 출처** · **3건**

#### 건축·착공 → 예정 호수

- 항목 노드 ID: `FIELD_CONSTRUCTION_plan_units`
- 필드 키: `plan_units`
- 스키마 경로: `stage_source.units`
- 실제 출처:

  - `SRC_002` — 1·29 도심 주택공급 확대 및 신속화 · www.korea.kr · **공식 출처** · **3건**
  - `SRC_003` — 9·7 주택공급 확대방안 · eiec.kdi.re.kr · **공식 출처** · **2건**
  - `SRC_004` — 9·7 주택공급 확대방안 · molit.go.kr · **공식 출처** · **6건**
  - `SRC_006` — LH 9·7 후속 민간참여 공모 · 블록별 착공계획 · www.lh.or.kr · **공식 출처** · **28건**
  - `SRC_022` — LH 블록별 실제 공정률 · 공개 상세 이력 · apply.lh.or.kr · **공식 출처** · **13건**
  - `SRC_035` — 공식 공고·고시 원문 · www.lh.or.kr · **공식 출처** · **1건**
  - `SRC_032` — 공식 공고·고시 원문 · www.molit.go.kr · **공식 출처** · **5건**
  - `SRC_051` — 공식 공고·고시 원문 · www.incheon.go.kr · **공식 출처** · **1건**
  - `SRC_052` — 공식 공고·고시 원문 · mas.smc.seoul.kr · **비공식 출처** · **1건**

#### 건축·착공 → 호수

- 항목 노드 ID: `FIELD_CONSTRUCTION_units`
- 필드 키: `units`
- 스키마 경로: `stage_source.units`
- 실제 출처:

  - `SRC_053` — LH 블록별 실제 공정률 · 공개 상세 이력 · apply.lh.or.kr · **공식 출처** · **7건**
  - `SRC_037` — external_officer · www.gwanak.go.kr · **공식 출처** · **1건**
  - `SRC_038` — 공식 공고·고시 원문 · apply.lh.or.kr · **공식 출처** · **1건**
  - `SRC_018` — 공식 공고·고시 원문 · cis.seoul.go.kr · **공식 출처** · **1건**
  - `SRC_040` — 공식 공고·고시 원문 · www.gwanak.go.kr · **공식 출처** · **1건**
  - `SRC_041` — 공식 공고·고시 원문 · www.korea.kr · **공식 출처** · **2건**
  - `SRC_042` — 공식 공고·고시 원문 · www.seoul.go.kr · **공식 출처** · **2건**
  - `SRC_043` — 공식 공고·고시 원문 · housinginfo.seoul.go.kr · **공식 출처** · **1건**
  - `SRC_044` — 공식 공고·고시 원문 · www.lh.or.kr · **공식 출처** · **1건**
  - `SRC_045` — external_officer · dwce.co.kr · **비공식 출처** · **1건**
  - `SRC_046` — external_officer · m.go.seoul.co.kr · **비공식 출처** · **1건**
  - `SRC_048` — external_officer · m.richgo.ai · **비공식 출처** · **1건**
  - `SRC_049` — external_officer · nwww.newsis.com · **비공식 출처** · **1건**
  - `SRC_021` — 공식 공고·고시 원문 · ms.smc.seoul.kr · **비공식 출처** · **1건**


### 5. 건축·준공

- 단계 노드 ID: `STAGE_COMPLETION`
- 의미: 준공 관련 일자·호수와 예정 일정·예정 호수의 근거.

#### 건축·준공 → 예정 일자

- 항목 노드 ID: `FIELD_COMPLETION_plan_date`
- 필드 키: `plan_date`
- 스키마 경로: `stage_source.date`
- 실제 출처:

  - `SRC_007` — LH 건설공사 현황 · www.lh.or.kr · **공식 출처** · **115건**
  - `SRC_054` — LH 공공주택 블록별 준공예정 · www.data.go.kr · **공식 출처** · **77건**
  - `SRC_022` — LH 블록별 실제 공정률 · 공개 상세 이력 · apply.lh.or.kr · **공식 출처** · **13건**
  - `SRC_012` — LH 인천 실제 착공·공정 현황 · www.lh.or.kr · **공식 출처** · **21건**
  - `SRC_038` — 공식 공고·고시 원문 · apply.lh.or.kr · **공식 출처** · **1건**
  - `SRC_039` — 공식 공고·고시 원문 · cis.seoul.go.kr · **공식 출처** · **2건**
  - `SRC_055` — 공식 공고·고시 원문 · www.icbp.go.kr · **공식 출처** · **1건**
  - `SRC_021` — 공식 공고·고시 원문 · ms.smc.seoul.kr · **비공식 출처** · **1건**
  - `SRC_052` — 공식 공고·고시 원문 · mas.smc.seoul.kr · **비공식 출처** · **1건**

#### 건축·준공 → 예정 호수

- 항목 노드 ID: `FIELD_COMPLETION_plan_units`
- 필드 키: `plan_units`
- 스키마 경로: `stage_source.units`
- 실제 출처:

  - `SRC_007` — LH 건설공사 현황 · www.lh.or.kr · **공식 출처** · **107건**
  - `SRC_054` — LH 공공주택 블록별 준공예정 · www.data.go.kr · **공식 출처** · **10건**
  - `SRC_022` — LH 블록별 실제 공정률 · 공개 상세 이력 · apply.lh.or.kr · **공식 출처** · **13건**
  - `SRC_012` — LH 인천 실제 착공·공정 현황 · www.lh.or.kr · **공식 출처** · **19건**
  - `SRC_038` — 공식 공고·고시 원문 · apply.lh.or.kr · **공식 출처** · **1건**
  - `SRC_018` — 공식 공고·고시 원문 · cis.seoul.go.kr · **공식 출처** · **1건**
  - `SRC_051` — 공식 공고·고시 원문 · www.incheon.go.kr · **공식 출처** · **1건**
  - `SRC_021` — 공식 공고·고시 원문 · ms.smc.seoul.kr · **비공식 출처** · **1건**
  - `SRC_052` — 공식 공고·고시 원문 · mas.smc.seoul.kr · **비공식 출처** · **1건**

#### 건축·준공 → 일자

- 항목 노드 ID: `FIELD_COMPLETION_date`
- 필드 키: `date`
- 스키마 경로: `stage_source.date`
- 실제 출처:

  - `SRC_056` — 공식 공고·고시 원문 · www.i-sh.co.kr · **공식 출처** · **1건**

#### 건축·준공 → 호수

- 항목 노드 ID: `FIELD_COMPLETION_units`
- 필드 키: `units`
- 스키마 경로: `stage_source.units`
- 실제 출처:

  - `SRC_056` — 공식 공고·고시 원문 · www.i-sh.co.kr · **공식 출처** · **1건**


### 6. 공급

- 단계 노드 ID: `STAGE_SUPPLY`
- 의미: 공급 관련 일자·호수와 예정 일정·예정 호수의 근거.

#### 공급 → 일자

- 항목 노드 ID: `FIELD_SUPPLY_date`
- 필드 키: `date`
- 스키마 경로: `stage_source.date`
- 실제 출처:

  - `SRC_057` — GH 주택 공고·과거 목록 · apply.gh.or.kr · **공식 출처** · **4건**
  - `SRC_058` — LH 모집공고 상세 · 입주 예정월 · apply.lh.or.kr · **공식 출처** · **123건**
  - `SRC_059` — external_officer · apply.lh.or.kr · **공식 출처** · **7건**
  - `SRC_060` — external_officer · anyang.go.kr · **공식 출처** · **1건**
  - `SRC_061` — 공식 공고·고시 원문 · apply.lh.or.kr · **공식 출처** · **6건**
  - `SRC_062` — 공식 공고·고시 원문 · www.i-sh.co.kr · **공식 출처** · **3건**
  - `SRC_063` — 청약홈 분양정보 · www.data.go.kr · **공식 출처** · **47건**
  - `SRC_064` — external_officer · www.xn--3-3u6ey6lv7rsa.kr · **비공식 출처** · **2건**
  - `SRC_065` — external_officer · partnexa.com · **비공식 출처** · **1건**
  - `SRC_066` — external_officer · www.newsis.com · **비공식 출처** · **1건**
  - `SRC_067` — external_officer · info-zip.kr · **비공식 출처** · **1건**

#### 공급 → 호수

- 항목 노드 ID: `FIELD_SUPPLY_units`
- 필드 키: `units`
- 스키마 경로: `stage_source.units`
- 실제 출처:

  - `SRC_057` — GH 주택 공고·과거 목록 · apply.gh.or.kr · **공식 출처** · **4건**
  - `SRC_058` — LH 모집공고 상세 · 입주 예정월 · apply.lh.or.kr · **공식 출처** · **120건**
  - `SRC_059` — external_officer · apply.lh.or.kr · **공식 출처** · **4건**
  - `SRC_061` — 공식 공고·고시 원문 · apply.lh.or.kr · **공식 출처** · **6건**
  - `SRC_062` — 공식 공고·고시 원문 · www.i-sh.co.kr · **공식 출처** · **3건**
  - `SRC_063` — 청약홈 분양정보 · www.data.go.kr · **공식 출처** · **6건**
  - `SRC_064` — external_officer · www.xn--3-3u6ey6lv7rsa.kr · **비공식 출처** · **2건**
  - `SRC_065` — external_officer · partnexa.com · **비공식 출처** · **1건**
  - `SRC_066` — external_officer · www.newsis.com · **비공식 출처** · **1건**
  - `SRC_067` — external_officer · info-zip.kr · **비공식 출처** · **1건**

#### 공급 → 예정 일자

- 항목 노드 ID: `FIELD_SUPPLY_plan_date`
- 필드 키: `plan_date`
- 스키마 경로: `stage_source.date`
- 실제 출처:

  - `SRC_005` — GH 주택 분양·임대 공급계획 · www.gh.or.kr · **공식 출처** · **2건**
  - `SRC_009` — LH 연간 분양주택 공급계획 · apply.lh.or.kr · **공식 출처** · **52건**
  - `SRC_010` — LH 연간 임대주택 공급계획 · apply.lh.or.kr · **공식 출처** · **22건**
  - `SRC_011` — LH 인천 분양 공급계획 · apply.lh.or.kr · **공식 출처** · **7건**
  - `SRC_013` — LH 인천 임대 공급계획 · apply.lh.or.kr · **공식 출처** · **6건**
  - `SRC_014` — SH 최신 공개본 사업 연결 · www.data.go.kr · **공식 출처** · **2건**
  - `SRC_060` — external_officer · anyang.go.kr · **공식 출처** · **1건**
  - `SRC_068` — 공식 공고·고시 원문 · www.goyang.go.kr · **공식 출처** · **1건**
  - `SRC_017` — 공식 공고·고시 원문 · www.fsc.go.kr · **공식 출처** · **4건**
  - `SRC_069` — 공식 공고·고시 원문 · www.korea.kr · **공식 출처** · **10건**
  - `SRC_038` — 공식 공고·고시 원문 · apply.lh.or.kr · **공식 출처** · **1건**
  - `SRC_070` — 공식 공고·고시 원문 · www.anyang.go.kr · **공식 출처** · **1건**
  - `SRC_062` — 공식 공고·고시 원문 · www.i-sh.co.kr · **공식 출처** · **2건**

#### 공급 → 예정 호수

- 항목 노드 ID: `FIELD_SUPPLY_plan_units`
- 필드 키: `plan_units`
- 스키마 경로: `stage_source.units`
- 실제 출처:

  - `SRC_005` — GH 주택 분양·임대 공급계획 · www.gh.or.kr · **공식 출처** · **2건**
  - `SRC_009` — LH 연간 분양주택 공급계획 · apply.lh.or.kr · **공식 출처** · **52건**
  - `SRC_010` — LH 연간 임대주택 공급계획 · apply.lh.or.kr · **공식 출처** · **22건**
  - `SRC_011` — LH 인천 분양 공급계획 · apply.lh.or.kr · **공식 출처** · **7건**
  - `SRC_013` — LH 인천 임대 공급계획 · apply.lh.or.kr · **공식 출처** · **6건**
  - `SRC_014` — SH 최신 공개본 사업 연결 · www.data.go.kr · **공식 출처** · **2건**
  - `SRC_068` — 공식 공고·고시 원문 · www.goyang.go.kr · **공식 출처** · **1건**
  - `SRC_017` — 공식 공고·고시 원문 · www.fsc.go.kr · **공식 출처** · **4건**
  - `SRC_069` — 공식 공고·고시 원문 · www.korea.kr · **공식 출처** · **10건**
  - `SRC_038` — 공식 공고·고시 원문 · apply.lh.or.kr · **공식 출처** · **1건**


### 7. 입주

- 단계 노드 ID: `STAGE_MOVE_IN`
- 의미: 입주 관련 예정 일정·예정 호수와 확보된 일자의 근거.

#### 입주 → 예정 일자

- 항목 노드 ID: `FIELD_MOVE_IN_plan_date`
- 필드 키: `plan_date`
- 스키마 경로: `stage_source.date`
- 실제 출처:

  - `SRC_071` — 9·7 주택공급 확대방안 · eiec.kdi.re.kr · **공식 출처** · **6건**
  - `SRC_072` — GH 주택 공고·과거 목록 · apply.gh.or.kr · **공식 출처** · **1건**
  - `SRC_005` — GH 주택 분양·임대 공급계획 · www.gh.or.kr · **공식 출처** · **2건**
  - `SRC_058` — LH 모집공고 상세 · 입주 예정월 · apply.lh.or.kr · **공식 출처** · **122건**
  - `SRC_010` — LH 연간 임대주택 공급계획 · apply.lh.or.kr · **공식 출처** · **16건**
  - `SRC_073` — LH 연도별 입주계획 공개본 · www.lh.or.kr · **공식 출처** · **2건**
  - `SRC_013` — LH 인천 임대 공급계획 · apply.lh.or.kr · **공식 출처** · **6건**
  - `SRC_074` — external_officer · apply.lh.or.kr · **공식 출처** · **9건**
  - `SRC_075` — external_officer · m.myhome.go.kr · **공식 출처** · **1건**
  - `SRC_076` — 공식 공고·고시 원문 · apply.lh.or.kr · **공식 출처** · **4건**
  - `SRC_068` — 공식 공고·고시 원문 · www.goyang.go.kr · **공식 출처** · **1건**
  - `SRC_077` — 공식 공고·고시 원문 · anyang.go.kr · **공식 출처** · **1건**
  - `SRC_070` — 공식 공고·고시 원문 · www.anyang.go.kr · **공식 출처** · **1건**
  - `SRC_032` — 공식 공고·고시 원문 · www.molit.go.kr · **공식 출처** · **5건**
  - `SRC_062` — 공식 공고·고시 원문 · www.i-sh.co.kr · **공식 출처** · **3건**
  - `SRC_078` — 공식 공고·고시 원문 · www.lh.or.kr · **공식 출처** · **1건**
  - `SRC_063` — 청약홈 분양정보 · www.data.go.kr · **공식 출처** · **41건**
  - `SRC_079` — 한국부동산원 입주예정물량 · www.data.go.kr · **공식 출처** · **19건**
  - `SRC_080` — external_officer · xn--3-3u6ey6lv7rsa.kr · **비공식 출처** · **3건**
  - `SRC_081` — external_officer · member.newspim.com · **비공식 출처** · **2건**
  - `SRC_082` — external_officer · www.newsis.com · **비공식 출처** · **2건**

#### 입주 → 예정 호수

- 항목 노드 ID: `FIELD_MOVE_IN_plan_units`
- 필드 키: `plan_units`
- 스키마 경로: `stage_source.units`
- 실제 출처:

  - `SRC_073` — LH 연도별 입주계획 공개본 · www.lh.or.kr · **공식 출처** · **2건**
  - `SRC_074` — external_officer · apply.lh.or.kr · **공식 출처** · **9건**
  - `SRC_075` — external_officer · m.myhome.go.kr · **공식 출처** · **1건**
  - `SRC_076` — 공식 공고·고시 원문 · apply.lh.or.kr · **공식 출처** · **4건**
  - `SRC_068` — 공식 공고·고시 원문 · www.goyang.go.kr · **공식 출처** · **1건**
  - `SRC_077` — 공식 공고·고시 원문 · anyang.go.kr · **공식 출처** · **1건**
  - `SRC_032` — 공식 공고·고시 원문 · www.molit.go.kr · **공식 출처** · **5건**
  - `SRC_083` — 공식 공고·고시 원문 · www.i-sh.co.kr · **공식 출처** · **1건**
  - `SRC_051` — 공식 공고·고시 원문 · www.incheon.go.kr · **공식 출처** · **1건**
  - `SRC_078` — 공식 공고·고시 원문 · www.lh.or.kr · **공식 출처** · **1건**
  - `SRC_079` — 한국부동산원 입주예정물량 · www.data.go.kr · **공식 출처** · **19건**
  - `SRC_080` — external_officer · xn--3-3u6ey6lv7rsa.kr · **비공식 출처** · **3건**
  - `SRC_081` — external_officer · member.newspim.com · **비공식 출처** · **2건**
  - `SRC_082` — external_officer · www.newsis.com · **비공식 출처** · **2건**

#### 입주 → 일자

- 항목 노드 ID: `FIELD_MOVE_IN_date`
- 필드 키: `date`
- 스키마 경로: `stage_source.date`
- 실제 출처:

  - `SRC_083` — 공식 공고·고시 원문 · www.i-sh.co.kr · **공식 출처** · **1건**

## 6. 실제 출처 목록과 대표 URL

이 표는 5절에서 사용하는 출처 노드 사전이다. 원본의 출처 ID·출처명·구분·URL을 보존했다. `official_document` 또는 `external_officer`처럼 출처명에 내부 식별자가 표시된 항목은 임의의 기관명이나 문서명으로 바꾸지 않았다.

| 출처 노드 ID | 원본 출처 ID | 출처명 | 화면 출처 구분 | 도메인 | 대표 URL |
|---|---|---|---|---|---|
| `SRC_001` | `policy_907` | 9·7 주택공급 확대방안 | 공식 출처 | d.nts.go.kr | [원문·수집경로](https://d.nts.go.kr/cheonan/na/ntt/selectNttInfo.do?mi=4611&nttSn=1353601) |
| `SRC_002` | `policy_129` | 1·29 도심 주택공급 확대 및 신속화 | 공식 출처 | www.korea.kr | [원문·수집경로](https://www.korea.kr/common/download.do?fileId=198344116) |
| `SRC_003` | `policy_907` | 9·7 주택공급 확대방안 | 공식 출처 | eiec.kdi.re.kr | [원문·수집경로](https://eiec.kdi.re.kr/policy/callDownload.do?filenum=2&num=270716) |
| `SRC_004` | `policy_907` | 9·7 주택공급 확대방안 | 공식 출처 | molit.go.kr | [원문·수집경로](https://molit.go.kr/atmo/USR/N0201/m_36515/dtl.jsp?id=95091185&lcmspage=2) |
| `SRC_005` | `gh_supply_plan` | GH 주택 분양·임대 공급계획 | 공식 출처 | www.gh.or.kr | [원문·수집경로](https://www.gh.or.kr/gh/housing-stability-in-gyeonggi-do001.do) |
| `SRC_006` | `lh_policy_followup` | LH 9·7 후속 민간참여 공모 · 블록별 착공계획 | 공식 출처 | www.lh.or.kr | [원문·수집경로](https://www.lh.or.kr/boardDownload.es?bid=0034&list_no=727339&seq=2#page=1) |
| `SRC_007` | `lh_construction` | LH 건설공사 현황 | 공식 출처 | www.lh.or.kr | [원문·수집경로](https://www.lh.or.kr/boardDownload.es?bid=0007&list_no=654682&seq=14) |
| `SRC_008` | `lh_progress` | LH 블록별 실제 공정률 · 공개 상세 이력 | 공식 출처 | apply.lh.or.kr | [원문·수집경로](https://apply.lh.or.kr/lhapply/land/cwsttInfo.do?mi=1352&bzdtCd=100576&hcBlkCd=39&seBzdtNm=%ED%99%94%EC%84%B1%EB%8F%99%ED%83%842&cnpNm=%EA%B2%BD%EA%B8%B0%EB%8F%84&bnm=C-14) |
| `SRC_009` | `lh_sale` | LH 연간 분양주택 공급계획 | 공식 출처 | apply.lh.or.kr | [원문·수집경로](https://apply.lh.or.kr/lhapply/apply/noti/sp/list.do?sUppAisTpCd=05) |
| `SRC_010` | `lh_rent` | LH 연간 임대주택 공급계획 | 공식 출처 | apply.lh.or.kr | [원문·수집경로](https://apply.lh.or.kr/lhapply/apply/noti/sp/list.do?sUppAisTpCd=06) |
| `SRC_011` | `lh_incheon_sale` | LH 인천 분양 공급계획 | 공식 출처 | apply.lh.or.kr | [원문·수집경로](https://apply.lh.or.kr/lhapply/apply/noti/sp/list.do?sUppAisTpCd=05) |
| `SRC_012` | `lh_incheon_construction` | LH 인천 실제 착공·공정 현황 | 공식 출처 | www.lh.or.kr | [원문·수집경로](https://www.lh.or.kr/boardDownload.es?bid=0007&list_no=654682&seq=14) |
| `SRC_013` | `lh_incheon_rent` | LH 인천 임대 공급계획 | 공식 출처 | apply.lh.or.kr | [원문·수집경로](https://apply.lh.or.kr/lhapply/apply/noti/sp/list.do?sUppAisTpCd=06) |
| `SRC_014` | `sh_inventory` | SH 최신 공개본 사업 연결 | 공식 출처 | www.data.go.kr | [원문·수집경로](https://www.data.go.kr/data/15008820/fileData.do) |
| `SRC_015` | `ih_notice` | iH 공식 주택 사업·분양·임대 모집공고 | 공식 출처 | www.ih.co.kr | [원문·수집경로](https://www.ih.co.kr/main/land/landDetail.do?land_seq=136&landDiv=1120) |
| `SRC_016` | `official_document` | official_document | 공식 출처 | www.g2b.go.kr | [원문·수집경로](https://www.g2b.go.kr/pn/pnp/pnpe/UntyAtchFile/downloadFile.do?bidPbancNo=R26BK01440851&bidPbancOrd=000&fileSeq=4&fileType=&prcmBsneSeCd=07) |
| `SRC_017` | `official_document` | official_document | 공식 출처 | www.fsc.go.kr | [원문·수집경로](https://www.fsc.go.kr/comm/getFile?srvcId=BBSTY1&upperNo=87948&fileTy=ATTACH&fileNo=3#page=6) |
| `SRC_018` | `official_document` | official_document | 공식 출처 | cis.seoul.go.kr | [원문·수집경로](https://cis.seoul.go.kr/TotalAlimi_new/PopInfo.action?cmd=info1&pjt_cd=7042024123093) |
| `SRC_019` | `building_hub` | 건축HUB 주택인허가 | 공식 출처 | www.data.go.kr | [원문·수집경로](https://www.data.go.kr/data/15136560/openapi.do) |
| `SRC_020` | `molit_renewal_inventory` | 국토부 전국 정비사업 통합 현황 · 수도권 후보 | 공식 출처 | www.data.go.kr | [원문·수집경로](https://www.data.go.kr/data/15160169/fileData.do) |
| `SRC_021` | `official_document` | official_document | 비공식 출처 | ms.smc.seoul.kr | [원문·수집경로](https://ms.smc.seoul.kr/attach/record/SEOUL/appendix/a11/A0068940.pdf) |
| `SRC_022` | `lh_progress` | LH 블록별 실제 공정률 · 공개 상세 이력 | 공식 출처 | apply.lh.or.kr | [원문·수집경로](https://apply.lh.or.kr/lhapply/land/cwsttInfo.do?mi=1352&bzdtCd=105175&hcBlkCd=22&seBzdtNm=%EB%82%A8%EC%96%91%EC%A3%BC%EC%99%95%EC%88%99&cnpNm=%EA%B2%BD%EA%B8%B0%EB%8F%84&bnm=S-18) |
| `SRC_023` | `gyeonggi_plan_notice_pilot` | 경기 고양창릉 지구지정 변경 고시 원문 | 공식 출처 | www.molit.go.kr | [원문·수집경로](https://www.molit.go.kr/USR/I0204/m_45/dtl.jsp?idx=18272) |
| `SRC_024` | `official_document` | 공식 공고·고시 원문 | 공식 출처 | www.lh.or.kr | [원문·수집경로](https://www.lh.or.kr/board.es?mid=a10604010000&bid=0034&act=view&list_no=733198&tag=&nPage=2) |
| `SRC_025` | `official_document` | 공식 공고·고시 원문 | 공식 출처 | www.i-sh.co.kr | [원문·수집경로](https://www.i-sh.co.kr/app/lay2/program/S48T561C562/www/brd/m_244/view.do?multi_itm_seq=1&seq=301479) |
| `SRC_026` | `official_document` | 공식 공고·고시 원문 | 공식 출처 | www.molit.go.kr | [원문·수집경로](https://www.molit.go.kr/USR/I0204/m_45/dtl.jsp?idx=17267&gubun=4) |
| `SRC_027` | `official_document` | 공식 공고·고시 원문 | 공식 출처 | www.incheon.go.kr | [원문·수집경로](https://www.incheon.go.kr/IC010205/view?repSeq=DOM_0000000011454303) |
| `SRC_028` | `seoul_cleanup` | 서울 정비사업 정보몽땅·추진경과 | 공식 출처 | cleanup.seoul.go.kr | [원문·수집경로](https://cleanup.seoul.go.kr/cafe/mainIndx.do?cafeUrl=silim2) |
| `SRC_029` | `building_hub_incheon` | 9·7 인천 주택인허가 원천 | 공식 출처 | www.data.go.kr | [원문·수집경로](https://www.data.go.kr/data/15136560/openapi.do) |
| `SRC_030` | `official_document` | 공식 공고·고시 원문 | 공식 출처 | molit.go.kr | [원문·수집경로](https://molit.go.kr/LCMS/DWN.jsp?fold=%2FN01_B%2F&fileName=%28%EB%B6%99%EC%9E%846%29_%EB%B3%80%EA%B2%BD_%EA%B3%A0%EC%8B%9C%EB%AC%B8%28%EC%84%B1%EB%82%A8%EA%B8%88%ED%86%A0_A-2BL%29.pdf) |
| `SRC_031` | `official_document` | 공식 공고·고시 원문 | 공식 출처 | www.eum.go.kr | [원문·수집경로](https://www.eum.go.kr/web/gs/gv/gvGosiDet.jsp?mobile_yn=&seq=399106) |
| `SRC_032` | `official_document` | 공식 공고·고시 원문 | 공식 출처 | www.molit.go.kr | [원문·수집경로](https://www.molit.go.kr/LCMS/DWN.jsp?fold=koreaNews%2Fmobile%2Ffile&fileName=251002%28%EC%A1%B0%EA%B0%84%29_9%C2%B77_%EA%B3%B5%EA%B8%89%EB%8C%80%EC%B1%85_%ED%99%95%EB%8C%80%EB%B0%A9%EC%95%88_%EC%A4%91_%ED%95%98%EB%82%98%EC%9D%B8_%EB%85%B8%ED%9B%84_%EA%B3%B5%EA%B3%B5%EC%9E%84%EB%8C%80_%EC%9E%AC%EA%B1%B4%EC%B6%95_%EB%B3%B8%EA%B2%A9_%EC%B6%94%EC%A7%84%28%EA%B3%B5%EA%B3%B5%EC%A3%BC%ED%83%9D%EC%A0%95%EC%B1%85%EA%B3%BC%29%3D.pdf) |
| `SRC_033` | `official_document` | 공식 공고·고시 원문 | 공식 출처 | www.eum.go.kr | [원문·수집경로](https://www.eum.go.kr/web/gs/gv/gvGosiDet.jsp?seq=643252) |
| `SRC_034` | `official_document` | 공식 공고·고시 원문 | 공식 출처 | www.molit.go.kr | [원문·수집경로](https://www.molit.go.kr/LCMS/DWN.jsp?fold=%2FN01_B%2F&fileName=%EB%B3%80%EA%B2%BD%EA%B3%A0%EC%8B%9C%EB%AC%B8_%EC%9D%B8%EC%B2%9C%EA%B3%84%EC%96%91_A17BL.pdf) |
| `SRC_035` | `official_document` | 공식 공고·고시 원문 | 공식 출처 | www.lh.or.kr | [원문·수집경로](https://www.lh.or.kr/board.es?mid=a10604010000&bid=0034&act=view&list_no=732709&tag=&nPage=2) |
| `SRC_036` | `lh_progress` | LH 블록별 실제 공정률 · 공개 상세 이력 | 공식 출처 | apply.lh.or.kr | [원문·수집경로](https://apply.lh.or.kr/lhapply/land/cwsttInfo.do?mi=1352&bzdtCd=104830&hcBlkCd=07&seBzdtNm=%EA%B3%A0%EC%96%91%EC%9E%A5%ED%95%AD&cnpNm=%EA%B2%BD%EA%B8%B0%EB%8F%84&bnm=S-1) |
| `SRC_037` | `external_officer` | external_officer | 공식 출처 | www.gwanak.go.kr | [원문·수집경로](https://www.gwanak.go.kr/site/gwanak/ex/bbs/View.do?bcIdx=79314&cateCont=25023004&cbIdx=456) |
| `SRC_038` | `official_document` | 공식 공고·고시 원문 | 공식 출처 | apply.lh.or.kr | [원문·수집경로](https://apply.lh.or.kr/lhapply/apply/noti/sp/list.do?listCo=100&mi=201523&sUppAisTpCd=05&srchY=Y) |
| `SRC_039` | `official_document` | 공식 공고·고시 원문 | 공식 출처 | cis.seoul.go.kr | [원문·수집경로](https://cis.seoul.go.kr/TotalAlimi_new/PopInfo.action?cmd=info1&pjt_cd=7042023051599&pjt_name=&menu=) |
| `SRC_040` | `official_document` | 공식 공고·고시 원문 | 공식 출처 | www.gwanak.go.kr | [원문·수집경로](https://www.gwanak.go.kr/site/gwanak/ex/bbs/View.do?bcIdx=79314&cateCont=25023004&cbIdx=456) |
| `SRC_041` | `official_document` | 공식 공고·고시 원문 | 공식 출처 | www.korea.kr | [원문·수집경로](https://www.korea.kr/briefing/policyBriefingView.do?newsId=156785506) |
| `SRC_042` | `official_document` | 공식 공고·고시 원문 | 공식 출처 | www.seoul.go.kr | [원문·수집경로](https://www.seoul.go.kr/news/news_report.do?bbsNo=158&nttNo=465574) |
| `SRC_043` | `official_document` | 공식 공고·고시 원문 | 공식 출처 | housinginfo.seoul.go.kr | [원문·수집경로](https://housinginfo.seoul.go.kr/hmpg/mabu/prst/cons/consDetail.do) |
| `SRC_044` | `official_document` | 공식 공고·고시 원문 | 공식 출처 | www.lh.or.kr | [원문·수집경로](https://www.lh.or.kr/boardDownload.es?bid=0007&list_no=654682&seq=14) |
| `SRC_045` | `external_officer` | external_officer | 비공식 출처 | dwce.co.kr | [원문·수집경로](https://dwce.co.kr/business/performance) |
| `SRC_046` | `external_officer` | external_officer | 비공식 출처 | m.go.seoul.co.kr | [원문·수집경로](https://m.go.seoul.co.kr/news/publicnews/local_govern/news_local/2026/09/08/20260908019008) |
| `SRC_047` | `external_officer` | external_officer | 비공식 출처 | go.seoul.co.kr | [원문·수집경로](https://go.seoul.co.kr/news/newsView.php?id=20251202500081) |
| `SRC_048` | `external_officer` | external_officer | 비공식 출처 | m.richgo.ai | [원문·수집경로](https://m.richgo.ai/realty/place/redevelop/d0KeBDi) |
| `SRC_049` | `external_officer` | external_officer | 비공식 출처 | nwww.newsis.com | [원문·수집경로](https://nwww.newsis.com/view/NISX20260907_0003779497) |
| `SRC_050` | `official_document` | 공식 공고·고시 원문 | 비공식 출처 | mas.smc.seoul.kr | [원문·수집경로](https://mas.smc.seoul.kr/attach/record/SEOUL/appendix/a11/A0071006.pdf) |
| `SRC_051` | `official_document` | 공식 공고·고시 원문 | 공식 출처 | www.incheon.go.kr | [원문·수집경로](https://www.incheon.go.kr/IC010205/view?curPage=1&repSeq=DOM_0000000015047612) |
| `SRC_052` | `official_document` | 공식 공고·고시 원문 | 비공식 출처 | mas.smc.seoul.kr | [원문·수집경로](https://mas.smc.seoul.kr/attach/record/SEOUL/appendix/a11/A0069855.pdf#page=79) |
| `SRC_053` | `lh_progress` | LH 블록별 실제 공정률 · 공개 상세 이력 | 공식 출처 | apply.lh.or.kr | [원문·수집경로](https://apply.lh.or.kr/lhapply/land/cwsttInfo.do?mi=1352&bzdtCd=105083&hcBlkCd=04&seBzdtNm=%EC%9D%B8%EC%B2%9C%EA%B0%80%EC%A0%952&cnpNm=%EC%9D%B8%EC%B2%9C%EA%B4%91%EC%97%AD%EC%8B%9C&bnm=B2) |
| `SRC_054` | `lh_completion_plan` | LH 공공주택 블록별 준공예정 | 공식 출처 | www.data.go.kr | [원문·수집경로](https://www.data.go.kr/data/15141761/fileData.do) |
| `SRC_055` | `official_document` | 공식 공고·고시 원문 | 공식 출처 | www.icbp.go.kr | [원문·수집경로](https://www.icbp.go.kr/headman/business/project06.jsp) |
| `SRC_056` | `official_document` | 공식 공고·고시 원문 | 공식 출처 | www.i-sh.co.kr | [원문·수집경로](https://www.i-sh.co.kr/app/lay2/program/S48T561C562/www/brd/m_244/view.do?multi_itm_seq=1&seq=307836) |
| `SRC_057` | `gh_notice` | GH 주택 공고·과거 목록 | 공식 출처 | apply.gh.or.kr | [원문·수집경로](https://apply.gh.or.kr/sb/sr/sr7150/selectPbancDetailView.do?pbancNo=790&pbancKndCd=01) |
| `SRC_058` | `lh_notice_detail` | LH 모집공고 상세 · 입주 예정월 | 공식 출처 | apply.lh.or.kr | [원문·수집경로](https://apply.lh.or.kr/lhapply/apply/wt/wrtanc/selectWrtancInfo.do?panId=2015122300020360&ccrCnntSysDsCd=03&uppAisTpCd=06&aisTpCd=07&mi=1026) |
| `SRC_059` | `external_officer` | external_officer | 공식 출처 | apply.lh.or.kr | [원문·수집경로](https://apply.lh.or.kr/lhapply/lhFile.do?fileid=67822421) |
| `SRC_060` | `external_officer` | external_officer | 공식 출처 | anyang.go.kr | [원문·수집경로](https://anyang.go.kr/main/selectBbsNttView.do?bbsNo=62&integrDeptCode=&key=259&nttNo=460096&pageIndex=1&searchCtgry=&searchKrwd=) |
| `SRC_061` | `official_document` | 공식 공고·고시 원문 | 공식 출처 | apply.lh.or.kr | [원문·수집경로](https://apply.lh.or.kr/lhapply/lhFile.do?fileid=67643046) |
| `SRC_062` | `official_document` | 공식 공고·고시 원문 | 공식 출처 | www.i-sh.co.kr | [원문·수집경로](https://www.i-sh.co.kr/app/com/file/innoFD.do?brdId=GS0401&seq=256974&fileTp=A&fileSeq=1) |
| `SRC_063` | `cheongyak` | 청약홈 분양정보 | 공식 출처 | www.data.go.kr | [원문·수집경로](https://www.data.go.kr/data/15098547/openapi.do) |
| `SRC_064` | `external_officer` | external_officer | 비공식 출처 | www.xn--3-3u6ey6lv7rsa.kr | [원문·수집경로](https://www.xn--3-3u6ey6lv7rsa.kr/kor/CMS/Board/Board.do?board_seq=466&mCode=MN024&mgr_seq=12&mode=view) |
| `SRC_065` | `external_officer` | external_officer | 비공식 출처 | partnexa.com | [원문·수집경로](https://partnexa.com/local/applyhome-pblanc-view.asp?PblancNo=6114) |
| `SRC_066` | `external_officer` | external_officer | 비공식 출처 | www.newsis.com | [원문·수집경로](https://www.newsis.com/view/NISX20261016_0003829226) |
| `SRC_067` | `external_officer` | external_officer | 비공식 출처 | info-zip.kr | [원문·수집경로](https://info-zip.kr/incheon-bupyeong-happy-housing-20261019/) |
| `SRC_068` | `official_document` | 공식 공고·고시 원문 | 공식 출처 | www.goyang.go.kr | [원문·수집경로](https://www.goyang.go.kr/news/user/bbs/BD_selectBbs.do?q_bbsCode=1030&q_bbscttSn=20261014131057264) |
| `SRC_069` | `official_document` | 공식 공고·고시 원문 | 공식 출처 | www.korea.kr | [원문·수집경로](https://www.korea.kr/common/download.do?fileId=198524780&tblKey=GMN#page=15) |
| `SRC_070` | `official_document` | 공식 공고·고시 원문 | 공식 출처 | www.anyang.go.kr | [원문·수집경로](https://www.anyang.go.kr/manan/selectBbsNttView.do?bbsNo=157&key=3315&nttNo=446074) |
| `SRC_071` | `policy_907` | 9·7 주택공급 확대방안 | 공식 출처 | eiec.kdi.re.kr | [원문·수집경로](https://eiec.kdi.re.kr/policy/materialView.do?num=271965) |
| `SRC_072` | `gh_notice` | GH 주택 공고·과거 목록 | 공식 출처 | apply.gh.or.kr | [원문·수집경로](https://apply.gh.or.kr/sb/sr/sr7150/selectPbancDetailView.do?pbancNo=793&pbancKndCd=01) |
| `SRC_073` | `lh_movein_history` | LH 연도별 입주계획 공개본 | 공식 출처 | www.lh.or.kr | [원문·수집경로](https://www.lh.or.kr/boardDownload.es?bid=0007&list_no=654827&seq=10882) |
| `SRC_074` | `external_officer` | external_officer | 공식 출처 | apply.lh.or.kr | [원문·수집경로](https://apply.lh.or.kr/lhapply/apply/wt/wrtanc/selectWrtancInfo.do?aisTpCd=48&ccrCnntSysDsCd=03&mi=1026&panId=2015122300018943&uppAisTpCd=06) |
| `SRC_075` | `external_officer` | external_officer | 공식 출처 | m.myhome.go.kr | [원문·수집경로](https://m.myhome.go.kr/hws/portal/sch/selectRsdtRcritNtcDetailView.do?pblancId=19519) |
| `SRC_076` | `official_document` | 공식 공고·고시 원문 | 공식 출처 | apply.lh.or.kr | [원문·수집경로](https://apply.lh.or.kr/lhapply/apply/wt/wrtanc/selectWrtancInfo.do?panId=0000060808&ccrCnntSysDsCd=02&uppAisTpCd=05&aisTpCd=05&mi=1027) |
| `SRC_077` | `official_document` | 공식 공고·고시 원문 | 공식 출처 | anyang.go.kr | [원문·수집경로](https://anyang.go.kr/dongan/selectBbsNttView.do?bbsNo=187&key=1170&nttNo=457028) |
| `SRC_078` | `official_document` | 공식 공고·고시 원문 | 공식 출처 | www.lh.or.kr | [원문·수집경로](https://www.lh.or.kr/boardDownload.es?bid=0007&list_no=654827&seq=10882) |
| `SRC_079` | `reb_movein_plan_file` | 한국부동산원 입주예정물량 | 공식 출처 | www.data.go.kr | [원문·수집경로](https://www.data.go.kr/data/15111714/fileData.do) |
| `SRC_080` | `external_officer` | external_officer | 비공식 출처 | xn--3-3u6ey6lv7rsa.kr | [원문·수집경로](https://xn--3-3u6ey6lv7rsa.kr/kor/CMS/Board/Board.do?board_seq=407&mCode=MN024&mgr_seq=12&mode=view&page=1) |
| `SRC_081` | `external_officer` | external_officer | 비공식 출처 | member.newspim.com | [원문·수집경로](https://member.newspim.com/news/view/20260630001004) |
| `SRC_082` | `external_officer` | external_officer | 비공식 출처 | www.newsis.com | [원문·수집경로](https://www.newsis.com/view/NISX20260702_0003694009) |
| `SRC_083` | `official_document` | 공식 공고·고시 원문 | 공식 출처 | www.i-sh.co.kr | [원문·수집경로](https://www.i-sh.co.kr/app/lay2/program/S48T561C562/www/brd/m_244/view.do?multi_itm_seq=1&seq=310750) |

## 7. 다이어그램 설명용 문안

“이 스타맵은 9·7 주택공급 정책에 연결된 232개 사업에서 어떤 항목을 어떤 출처로 확보했는지 보여 줍니다. 정책, 사업화, 인허가, 건축·착공, 건축·준공, 공급, 입주의 7단계에서 출발해 수집 항목을 거쳐 실제 출처를 따라갈 수 있습니다. 예를 들어 정책 단계의 정책명·정책 발표일·정책 목표 호수는 9·7 주택공급 확대방안 출처와 연결됩니다. 착공 단계에는 일자·호수뿐 아니라 관측 공정률과 예정 정보가 별도로 연결됩니다. 공식과 비공식 출처는 화면의 분류대로 구분합니다. 연결에 표시된 건수는 주택 호수가 아니라 해당 항목을 확보한 원천 기록 수이며, 하나의 기록이 여러 항목에 사용되므로 합산하지 않습니다.”

## 8. 원본 추적 정보

- 대상 화면: PoC 10 「the주택」 → 수집 원천 → 단계별 수집 항목과 출처.
- 화면 코드: `PoC/10-home/web/assets/collection-schema.js`.
- 집계 코드: `PoC/10-home/backend/collection_schema.py`.
- 단계 명칭: `PoC/10-home/backend/collection_exports.py`의 `STAGES`.
- 출처 구분 코드: `PoC/10-home/backend/source_authority.py`.
- 집계 API: `/poc/home/api/collection-schema`.
- 화면 CSV: `/poc/home/api/collection-schema/export.csv`.
- 이번 문서에 사용한 집계 파일: `PoC/10-home/data/runtime/collection-schema-result.json`의 `data` 객체.
- 사용한 집계 파일의 SHA-256: `fa32e91a7ade23a322730c24be0b398c4e90ffdf9fbe40db09b2f1370d452b6e`.
- 원본 집계가 갱신되면 항목·출처·건수는 달라질 수 있다. 이 문서는 위 생성 시각의 데이터를 고정한 제출용 자료다.
