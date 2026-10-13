# HOME → 주택파동 공통규격 v1.4: 1단계 분석·매핑안

분석 기준: 2026-10-10 HOME 로컬 공유 스냅샷 `data/exports/home-20261010-live-v3/` 및 `docs/common_form/`의 README·CSV 8종. 구현과 CSV 생성은 아직 하지 않았다.

## 규격 확인 범위

`docs/common_form/README_제출안내.md`와 CSV 8종의 실제 첫 행을 확인했다. 모두 UTF-8 BOM이 있는 헤더 전용 파일이다. 지시문에 명시된 `주택파동_조원배포_재가공양식_v1_4_CSV.zip` 원본 파일은 HOME 디렉터리에서 찾지 못했다. 현재 매핑은 압축 해제본을 기준으로 하며, ZIP과의 바이트 단위 동일성은 확인할 수 없다.

README에 명시된 값: `project_unit` = `BLOCK` / `INDEPENDENT` / `AREA_UNKNOWN`; `review_status` = `CONFIRMED` / `REVIEW_REQUIRED`; `quantity_type` = `PROJECT_PLAN` / `PUBLIC_PLAN` / `SUPPLY_PLAN` / `NOTICE` / `MOVE_IN_ACTUAL`. 날짜는 `YYYY-MM-DD` 또는 `YYYY-MM`이며 모르면 공란이다. 정책→프로그램→사업 계층과 정책→사업화→인허가→건설→공급→입주 단계는 별개다.

## 확인된 HOME 원천과 관계

- 운영 DB 모델은 `backend/db.py`의 `home_revision`, `home_batch`, `home_coverage`, `home_project`, `home_identity_alias`, `home_project_evidence`, `home_plan`, `home_plan_event`, `home_plan_project_link`, `home_mapping`, `home_program_mapping`, `home_audit`이다. `home_revision.entity_id`는 원천 객체 논리 ID, `id`는 판본 ID이며 `superseded_at IS NULL`만 현재 판본이다. `home_mapping.policy_id`는 과거 직접 제안이므로 현재 정책 연결은 `home_mapping.program_id → home_program_mapping.policy_id`를 따른다.
- 최신 로컬 공유본은 2026-10-10 05:02:48 UTC에 DB 읽기 전용 일관 스냅샷으로 생성됐다. `manifest.json`, `source_registry.json`, `revisions/*.json.gz`, `current_projects.json`, 연결·식별 JSON과 배치 이력이 있다. 원천 등록 42종. `data/home.db`는 0바이트이며 변환 입력으로 쓰지 않는다. `data/raw`는 원본 증빙용이다.
- 현재 판본: `project` 266건(원천별: `policy_129` 47, `urban_930` 51, `lh_sale` 34, `lh_rent` 18, `lh_construction` 87, `lh_progress` 9, `sh_inventory` 18, `gh_supply_plan` 2), `policy` 3건, HOME 프로그램 16건, 프로그램→사업 266건, 정책→프로그램 16건. 두 종류의 연결은 모두 `REVIEW`다. `project_report` 1,199건 중 `current_project_id`가 있는 행은 733건이며 그 관계도 `REVIEW`다.
- 원천 보조 자료: `lh_supply` 76, `lh_movein_plan` 217, `lh_completion_plan` 181, `sh_plan` 20, `sh_project` 16, `notice` 1,110, `lh_notice` 3,050, `gh_notice` 442, `renewal_inventory` 885. 인허가 `permit` 180,541건과 건축물대장 `register` 676,746건은 주택공급사업 확정 목록이 아니다. 숫자는 현재 판본 행 수이며 호수나 최종 제출 건수가 아니다.
- `home_project` 266건과 `home_identity_alias` 371건은 모두 `REVIEW`다. alias 중 266건은 `SOURCE_ANCHOR`, 105건은 `lh_completion_plan`의 `REGION_DISTRICT_BLOCK` 후보 연결이다. `home_plan` 2건과 `home_plan_event` 2건은 있으나 `home_plan_project_link`는 0건이다.
- `backend/sources.py`, `backend/service.py`, `backend/collectors.py` 등 수집·정제 코드와 `scripts/export_json.py`가 원천·배치·판본·비밀값 제거 방식을 정의한다. `backend/data/urban930_progress.json`은 공식 PDF 대조용 보조 자료다. `refs/seongbuk_public_housing.json`은 다른 조원의 참고 자료로 HOME 제출 입력에서 제외한다.
- HOME의 `sample_mode=TEST_SAMPLE`은 공식 원천의 일부를 시험 수집했다는 뜻이며 DEMO와 동일하지 않다. 실제 DEMO 표기가 있는 행은 제외한다. `availability=PUBLIC`은 공개 접근 가능성을 뜻하며 공공주택 여부의 증거로 사용하지 않는다.

## 제출 후보와 제외 원칙

`project` 266건은 HOME 사업 후보의 시작 집합이다. 이 중 `MULTI_SITE_CONTRACT` 9건은 복수 현장 계약일 수 있으므로 단일 사업·물량으로 확정하지 않고 검토한다. `TOTAL_CONFLICT` 3건, `JOINT_QUANTITY_UNALLOCATED` 2건도 물량을 보류한다. `UNITS_UNKNOWN` 35건은 호수를 0으로 채우지 않는다. 이 경고는 한 사업에 중복될 수 있어 더해서 제외 건수로 계산하지 않는다. 최종 사업 행 수는 사업 단위와 공공 범위 검토 뒤 확정한다.

`lh_supply`의 블록·유형별 공고 물량, LH/SH/GH의 공공 계획, HOME 사업 자체의 계획·실제 공정은 변환 후보이다. 동일 블록의 공급 유형은 한 사업 아래 물량 행으로 관리한다. `lh_movein_plan`은 예정이고 실제 입주가 아니다. `lh_stock`, `agency_stock`, `register`는 기존 재고이며 신규 공급·입주 실적으로 변환하지 않는다. `renewal_inventory`의 전체 재개발 세대수와 청약홈의 민간 분양은 공공 호수로 변환하지 않는다. 공공분이 별도로 확인되는 경우만 검토 대상으로 둔다. LH/GH 공고 목록 가운데 토지·상가·결과 발표·단순 재공고와 물량이 없는 행은 공급물량에서 제외한다.

SH 공공재개발 원천 `sh_project` 16건의 전체 세대수는 10,392호, `rental_units`가 있는 행은 12건·합계 3,211호다. 전체 세대수를 공공 호수로 제출하지 않는다. 임대 부분도 공공주택 성격을 원문으로 확인해야 `PUBLIC_PLAN`에 넣는다. 2023년 기준 현황을 현재 실적으로 표기하지 않는다.

## CSV별 필드 매핑안

아래의 `source_ref`는 해당 원천 행을 가리키는 결정적 로컬 참조값으로 만들고 `원천_sources.csv`에 반드시 등록한다. 한 데이터셋에도 원천 기준일이 다를 수 있으므로 필요한 경우 레코드·판본 단위로 원천 행을 만든다. HOME의 원래 ID를 별도 식별자로 보존한다. `REVIEW` 및 자동 후보는 `REVIEW_REQUIRED`로만 옮긴다.

### `원천_sources.csv`

| 공통 필드 | HOME 필드·규칙 |
|---|---|
| `source_ref` | 입력 레코드/연결 ID로부터 재실행 시 동일한 로컬 참조값 생성 |
| `source_owner` | `HOME` |
| `provider` | `source_registry.org`; HOME 연결 테이블은 `HOME` |
| `dataset_name` | `source_registry.name` 또는 실제 HOME 연결 테이블명 |
| `source_url` | 키 제거된 `payload.evidence_url` 또는 `source_registry.url` |
| `source_record_key` | `payload.source_object_id`; 없으면 `home_revision.entity_id`; 연결은 원본 연결 ID |
| `data_as_of` | `source_date_label`로 자료 기준일임이 확인된 `payload.source_date`, 공개본 `dataset_version`, 의미가 확인된 `payload.base_date`/보고서 기준일. 공고일·입주예정월 같은 사건일만 있으면 별도 기준일은 공란 |
| `collected_at` | 대응 `home_batch.started_at`의 날짜. 배치 확인이 불가능하면 공란; `recorded_at`을 실제 수집일로 오인하지 않음 |
| `original_filename` | 배치 manifest의 안전한 상대 파일명/공유본 파일명. 알 수 없으면 공란 |
| `notes` | 원천의 기준일 의미, HOME 적재 시각, 공개본 버전, 검토 제약 등 |

### `정책_policies.csv`

| 공통 필드 | HOME 필드·규칙 |
|---|---|
| `local_policy_id` | `kind=policy`의 `payload.id` (`POL_...`), HOME에서 이미 쓰는 로컬 정책 ID |
| `policy_name` | `payload.name` |
| `announcement_date` | `payload.announced_at` |
| `scope_region` | `payload.target_scope` 그대로; 인천 포함 수도권 목표를 서울·경기로 바꾸지 않음 |
| `source_ref` | 해당 정책 revision의 원천 |
| `review_status` | `payload.lifecycle_status=REVIEW`이면 `REVIEW_REQUIRED`; 확인 근거 있을 때만 `CONFIRMED` |

`urban_930`은 현재 독립 정책 `kind=policy` 행이 아니라 후속조치/사업 근거이므로 새 정책 ID를 만들지 않는다.

### `프로그램_programs.csv`

| 공통 필드 | HOME 필드·규칙 |
|---|---|
| `local_program_id` | `home_program_mapping.id` (`PRG_...`) |
| `program_name` | `home_program_mapping.name` |
| `program_definition` | 정의 원문이 별도로 확인되지 않으면 공란; `basis`를 정의로 오인하지 않음 |
| `source_ref` | HOME 프로그램 매핑 행의 출처 |
| `review_status` | `status=REVIEW → REVIEW_REQUIRED`, `CONFIRMED → CONFIRMED`; `RELEASED`는 유효 연결에서 제외 |

### `사업_projects.csv`

| 공통 필드 | HOME 필드·규칙 |
|---|---|
| `local_project_id` | 기본 사업은 `home_revision.entity_id` / `current_projects[].id`. 다른 원천에서 별도 사업 행을 만들 때에도 원천 로컬 ID를 보존하고 동일 사업으로 임의 병합하지 않음 |
| `project_name` | `payload.name` |
| `project_unit` | 확인된 지구·블록은 `BLOCK`, 독립 사업 근거가 있으면 `INDEPENDENT`, 범위가 불명확하면 `AREA_UNKNOWN` |
| `parent_area_name`, `block_name` | 명시적 `payload.district`/`district_name`, `payload.block`. 이름 문자열만으로 추출하면 검토 필요 |
| `region`, `sigungu` | `payload.region`, `payload.municipality`; `지역 상세 확인 필요` 같은 안내 문구는 공란 |
| `organization` | 명시적 `payload.developer`/`agency`; `시행기관 확인 필요`는 공란 |
| `public_scope` | 공공주택 범위가 원천으로 확인될 때만 `PUBLIC`; 공개 여부인 `availability`와 혼동하지 않음. 혼합/불명확한 범위의 허용값은 규격 확인 전 공란·검토 |
| `project_status` | 검증된 원천 `stage_label`/`source_stage`; 계획·예정·실제를 혼용하지 않음 |
| `is_demo` | 검증된 실제 원천 행은 `false`; DEMO는 제출 파일에서 제외 |
| `source_ref` | 해당 사업의 원천 revision |

### `정책사업연결_links.csv`

| 공통 필드 | HOME 필드·규칙 |
|---|---|
| `link_type` | HOME의 프로그램→정책, 사업→프로그램, 계획→사업 관계. 허용 문자열은 규격에서 정의하지 않아 구현 전 확인 필요 |
| `from_local_id`, `to_local_id` | 정책 ID→프로그램 ID, 프로그램 ID→사업 `entity_id`; 방향을 명시해 참조 무결성 검사 |
| `evidence` | `home_program_mapping.basis` 또는 `home_mapping.basis` 및 근거 URL |
| `review_status` | HOME `REVIEW → REVIEW_REQUIRED`, 담당자 `CONFIRMED → CONFIRMED` |
| `source_ref` | 각 HOME 연결 원본 행 |

`home_mapping.policy_id`를 유효 정책 연결로 사용하지 않는다. `home_plan_project_link`는 현재 0건이므로 계획→사업 링크는 헤더만 가능하다. 2번 조원의 `P-` 코드를 정책 ID로 해석하지 않는다.

### `사업식별자_identifiers.csv`

| 공통 필드 | HOME 필드·규칙 |
|---|---|
| `local_project_id` | 실제 제출한 사업 행의 ID |
| `id_type`, `id_value` | HOME `entity_id`, 원천 `source_object_id`, 확인된 지구·블록, 청약 `house_manage_no`, 원천 인허가 관리번호, 명시적 PNU 등을 각각 행으로 보존. 임의 조합 PNU는 금지 |
| `id_issuer` | ID 발급 기관 또는 `HOME` |
| `source_ref` | ID를 제공한 원천 |
| `match_status` | 원천 동일성 검토 상태를 반영. 허용 문자열은 규격에서 정의하지 않아 구현 전 확인 필요 |

`home_project.id` (`HPR_...`)와 `home_identity_alias`는 검토 후보 ID다. 105개 LH 준공예정 연결을 확정 동일 사업으로 간주하지 않는다. `permit_parcel`의 코드 조각만으로 PNU를 생성하지 않는다.

### `진행이력_events.csv`

| 공통 필드 | HOME 필드·규칙 |
|---|---|
| `local_project_id` | 확정된 해당 사업 ID만 참조; 불확실한 보고서/공고 매칭은 검토 대장으로 이동 |
| `event_type` | 원천의 정책·사업화·인허가·건설·공급·입주 단계에 맞는 사건. 구체 허용 문자열은 규격 확인 필요 |
| `date_type` | 원천의 실제일과 예정일을 구분. 구체 허용 문자열은 규격 확인 필요 |
| `event_date`, `event_month` | 일까지 확인되면 `YYYY-MM-DD` / 월만 확인되면 `YYYY-MM`; 임의로 1일을 붙이지 않음 |
| `progress_pct` | `project.progress_pct`, 검토된 `project_report.progress_pct`의 실제 관측치만 사용 |
| `event_detail` | 원천 `stage_label`, `schedule_basis`, 계약 공정/고시/공고 설명 등. 준공예정과 입주예정을 명시적으로 구분 |
| `source_ref`, `review_status` | 해당 사건 원천과 링크 검토 상태 |

`project.start_actual_date`와 `start_plan_date`, `completion_plan_date`, LH `move_in_plan_month`, 허가/착공 원천 날짜를 분리한다. LH 공사 공개본 `report_date`/`base_date`는 자료 기준일이지 현장 측정일이라고 단정하지 않는다.

### `공급물량_units.csv`

| 공통 필드 | HOME 필드·규칙 |
|---|---|
| `local_project_id` | 검증된 해당 사업 ID |
| `quantity_type` | 전체 사업 계획=`PROJECT_PLAN`; 공공 부분 계획=`PUBLIC_PLAN`; 연간/유형별 공급계획=`SUPPLY_PLAN`; 모집공고 물량=`NOTICE`; 실제 입주 검증치만 `MOVE_IN_ACTUAL` |
| `housing_type` | `payload.tenure` / `housing_type`; `유형 확인 필요`는 공란 |
| `unit_count` | 해당 유형·기준의 `planned_units`, `supply_units`, `units`, `rental_units` 중 의미가 확인된 값 하나. `0`은 원천에서 유효한 명시적 0일 때만 사용 |
| `reference_period` | 계획 자료 기준연월·공고일 등 원천에 있는 기간. 일정 예정월과 혼동하지 않음 |
| `unit_scope` | 원천의 전체/공공부분/공급유형 범위. 허용 문자열은 규격에서 정의하지 않아 구현 전 확인 필요 |
| `source_ref`, `review_status` | 해당 물량 원천과 검토 상태 |

HOME `project.planned_units`는 원천별 정책 계획/공사 계약 규모/공급계획으로 의미가 달라 `unit_basis`를 확인한 뒤 유형을 선택한다. `project.supply_units`와 `planned_units`가 같은 원천 수치면 이중 기록·합산하지 않는다. 모집공고와 계획도 합산하지 않는다. 현재 사업별 실제 입주 호수 근거가 없어 `MOVE_IN_ACTUAL`은 헤더만 남을 수 있다.

## 미해결 문제와 공통규격 보완 제안

1. ZIP 원본이 작업공간에 없어 압축 해제본과의 동일성 검증이 불가능하다. 확인 시 ZIP 원본 또는 해당 파일이 현재 양식과 같다는 확인이 필요하다.
2. README는 `link_type`, `id_type`, `match_status`, `event_type`, `date_type`, `unit_scope`, `public_scope`, `project_status`의 허용값을 명시하지 않는다. 제안 문자열을 구현에서 임의로 확정하지 않도록 값 목록 또는 자유 텍스트 허용 여부를 확인해야 한다.
3. `quantity_type`에는 **입주예정 호수**와 **준공예정 호수**의 구분값이 없다. 이를 `MOVE_IN_ACTUAL`로 바꾸거나 `SUPPLY_PLAN`에 섞지 않는다. 공통규격 차기 버전에 `MOVE_IN_PLAN`·`COMPLETION_PLAN` 같은 별도 유형을 제안한다. 현 v1.4에서는 해당 날짜를 events에 기록하고 호수는 검토 대장/원천에 남긴다.
4. `projects`에는 검토 상태 열이 없다. 공공주택 여부·사업 단위가 불확실하면 `review_required.csv`에 기록하고 불확실한 물량은 제출하지 않는다. 차기 규격에서 사업 행 자체의 검토 상태를 검토할 수 있다.
5. `sources`는 원천 기준일·실제 수집일을 담지만 `events`에는 공정 관측 기준일 전용 필드가 없다. 공정률 공개본 기준일을 현장 측정일로 승격하지 않고 `source_ref`로 추적한다.

## 구현 전 확인할 선택

- HOME 제출 결과의 위치: `PoC/10-home/exports/housing_wave_common_v1_4/`.
- 변환 입력: 고정된 `data/exports/home-20261010-live-v3/`를 기본값으로 하여 동일 입력 재실행을 보장한다. 라이브 DB는 읽지 않고 공유본의 이미 제거된 비밀값을 다시 검증한다.
- 주 입력은 현재 `project` 판본이다. 기타 공공 원천의 독립 사업 행은 원천 식별정보로 사업 단위가 입증되고 HOME 기존 사업과 확정 중복이 아닐 때만 추가한다. 불확실한 동일성은 `review_required.csv`에 별도 기록한다.
- 5~10건 시험 변환은 정책 계획, LH 블록 공사, 공공 임대 계획, SH 공공재개발 부분 물량, 공고/입주예정 사례를 섞어 선정한다. 필수 컬럼·날짜·숫자·로컬 ID·source_ref·링크 참조를 검사한 뒤 전체 변환을 진행한다.
