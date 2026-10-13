# Codex 실행 지시서 — HOME 공식 데이터 검증 · 정규화 사업원장 · 공급집계 · 지도 API 개선

> **적용대상:** 기존 HOME(Housing Operations Monitoring & Execution) 저장소 내부에서 실행하는 변경 작업  
> **작성일:** 2026-10-10 (Asia/Seoul)  
> **성격:** 구현 지시서. 현재 운영 DB에 있는 사실과 향후 논리 설계는 반드시 구분한다.  
> **완료 목표:** 공식 원천의 실제 수집 가능성을 증거로 확인하고, 기존 관리자 승인·감사·원천 판본·공개 API를 보존하면서 **정책→프로그램→실제 사업↔법적 계획, 블록·공급묶음, 단계별 목표·일정·실적, 독립된 지역 공식통계**를 단계적으로 구축한다.

## 0. Codex에 제공할 자료 및 작업 방법

**사용자가 HOME 저장소 루트 혹은 `docs/research/`에 다음 파일을 복사해 제공할 것:**

- `PLAN.md`: 최초 구현계획 및 **SCOPE_BASELINE / SUPPLY_COHORT / count_flag / PROJECT_SCHEDULE / ORG_MASTER / FIELD_RESOLUTION_RULE / Tree** 기준.
- `HOME_GPT_REVIEW_BRIEF.md`: 2026-10-10 기준 서비스/현재 물리 DB 5개 테이블/원천 36개/source ID/마이그레이션 금지 조건.
- `HOME_source_verification.json`: 기존 36개+후보 19개, **55개 검토 항목**의 경로·상태·남은 검증; **V2는 공식 제공 경로 확인이지 API 실수집 완료 아님**.
- `HOME_데이터확보_검증보고서.md`: 공식 원천 교차검증·데이터 의미·갭·우선순위·검증 절차.
- `HOME_시스템아키텍처_설명.html`: 발표·협의용 논리 모델과 ERD, 출력계약. UI 설명자료이지 현재 물리 DB 정의서가 아님.

**실제 저장소가 접근 가능하면 다음부터 읽기:**

- `backend/db.py`, `backend/sources.py`, `backend/service.py`, `backend/collectors.py`, `backend/app.py`
- Alembic revisions, `.env.example`(이름만), 테스트·운영 스크립트, README, 기존 DATA_SHARING/REFS_INTEGRATION_REVIEW 및 수집 이력 문서
- 운영 DB 자체는 접근 권한이 있는 경우에 한해 **읽기 전용 preflight**. 관리자 승인·키 등 개인정보가 출력·코드에 포함되지 않게 할 것.

**가장 중요한 전제:** 브리프는 2026-10-07 공유 스냅샷 기준 등록 원천 36개, `home_revision`·`home_batch`·`home_mapping`·`home_program_mapping`·`home_audit`의 **5개 현재 물리 테이블**을 보고한다. PLAN의 다수 Master/Fact 테이블은 아직 **목표 설계**다. 현행 DB를 확인하지 않은 상태에서 목표 테이블이 존재한다고 가정하지 말 것.

**작업 방식:** 아래 PHASE를 순서대로 실행하되, 작업 간 공통 의존성이 없으면 수집 소량 검증과 논리 모델 설계를 병렬 수행할 수 있다. 각 단계는 코드를 수정하고 테스트하며 결과를 문서로 남긴다. 이 지시서를 ‘제안서’로만 되풀이하거나 빈 TODO만 추가하는 것은 완료가 아니다. 인증키/원천 권한 부족으로 실데이터에 접근할 수 없는 경우 해당 GATE를 `BLOCKED`로 남기고 **실제 수집했다고 주장하지 않는다.** 대신 fixture/test/collector 계약과 검증 가능한 다음 실행 커맨드를 완성한다.

---

## 1. 불가역적인 금지사항 및 안전 경계

1. 운영 DB Drop/Truncate, 기존 승인 `CONFIRMED`/해제 `RELEASED`를 임의로 변경, 감사이력 제거, 현재 raw 및 성공 판본 삭제, 기존 `home_revision.entity_id` 재발급/대량 교체 **금지**.
2. 신규 수집값으로 관리자 계획목표 `kind=goal`과 관리자 정책 매핑을 자동 overwrite 금지.
3. 정책 발표·원천 사업명 유사성만으로 정책 귀속 또는 같은 실사업을 `CONFIRMED` 자동 처리 금지. `REVIEW`가 기본이며 담당자 승인/거절을 감사에 남길 것.
4. 원천상 물량 없는 날짜에 인위적으로 연도별 실적을 배분하거나 공정률을 준공 호수로 바꾸지 말 것.
5. 모집공고·허가·착공·준공·입주·기존 재고·멸실·수요·전망은 단위와 역할이 다르며, **동일 공급 실적으로 합산하거나 대체하지 말 것**.
6. `policy_907` 등 정책 목표에 적힌 지표가 ‘착공’이면 준공/입주 실적을 분자로 넣지 말 것. 수도권 목표를 인천 제외 서울+경기 전체 목표인 것처럼 표시 금지.
7. 실제 0호(`CONFIRMED_ZERO`)와 값 없음/원천 없음/수집 실패/미연계/일정 미정/비적용을 동일하게 취급하지 말 것. LH 준공예정 원천은 `0 또는 NULL = 미확정` 가능성 문서화.
8. 건축물대장 기존 재고를 해당 정책 발표 후 신규 준공으로 자동 인정 금지. 국토부 주택건설실적의 지역 합계를 개별 정책 사업 실적으로 자동 귀속 금지.
9. GIS의 공식 폴리곤, 주소 매핑 대표점, LH 블록 라벨, 화면용 가상 3D 형상을 구분하고 **정확하지 않은 위치/경계를 만들어내지 말 것**.
10. `upisRebuild`를 법적 효력이 있는 원고시로 간주하지 말 것. 2026-10-10 웹 조회/색인 판본에 서울시 데이터의 이용허락 표기가 **제4유형 vs 자유이용으로 상충**했으므로, 최신 라이선스 승인 전 가공자료 외부 배포 기능을 활성화하지 말 것.
11. API 키/비밀번호/사용자 식별/승인 담당자의 개인 인적정보를 Raw URL, 로그, 문서, HTML, 공개 API, 데이터 내보내기에 기재 금지. 필요한 비밀은 환경변수/비밀관리 저장소로만 관리.
12. PLAN에 있는 대규모 신규 스키마를 한 번에 만들거나 기존 서비스 공개 API를 파괴적으로 교체하지 말 것. **Additive migration→backfill→shadow comparison→승인된 전환**으로 진행.
13. 결과 화면에서 `확정 사업 연결 물량`, `검토 포함 후보`, `공식 확인 단계별 실적`, `지역 전체 공식 실적`을 서로 다른 이름·출처·집계 범위로 표시할 것.
14. `SCOPE_BASELINE`의 관측 사업 후보 수를 승인된 정책 물량 달성률의 분모로 자동 사용하지 말 것.

---

## 2. PHASE 0 — READ-ONLY 사전 점검 및 복구 기준선

### 2.1 실제 코드와 DB 스키마 확인

1. Git 작업 트리를 확인한다. 수정사항이 있으면 보호하고 새 feature branch에서 작업한다. 저장소 실제 커맨드를 확인하여 최초 테스트를 실행한다.
2. `backend/db.py`, Alembic head, 물리 테이블과 인덱스, 공개 API 응답 스키마, 배치·원본 저장 경로를 확인하고 **브리프와의 차이**를 `docs/home_rebuild/00_preflight.md`에 기록한다.
3. 현재 소스 registry **36개가 맞는지 실제 코드로** 확인한다. 숫자가 달라도 브리프가 틀렸다고 자동 수정하지 말고 최신 상태·추가/삭제 이유를 기록한다.
4. 다음 자료의 대상/건수/상태를 저장한다: 전체 `home_revision` 유효/과거 행, `home_batch` 성공·실패, `home_mapping` REVIEW/CONFIRMED/RELEASED, `home_program_mapping`, `kind=goal` 수량/근거, `home_audit`. 관리자 개별 ID·비밀값은 공개 산출물에서 마스킹한다.
5. DB는 가능한 경우 **운영 환경과 분리된 백업/스테이징 복원본**에서 작업한다. 롤백 가능한 백업 방식, 원본 manifest 위치, RPO/RTO 미확정 사항 기록.
6. 각 기존 공개 API endpoint에 대해 Golden Response fixture 또는 JSON schema snapshot을 준비한다. 후속 개발에서 기존 필드의 의미/호출이 깨지면 실패다.

### 2.2 `entity_id` 충돌 조사

브리프는 `kind[:3] + sha256(source_id+':'+origin_key)[:24]` 형식이라고 설명한다. `project` / `project_report`, `policy` / `policy_event`는 접두부가 같을 수 있으므로 충돌 가능성이 있다. 단 **실제 충돌 여부는 미확인**이다.

실제 PostgreSQL에서는 테이블·컬럼을 검증한 뒤 다음처럼 읽기만 한다.

```sql
-- 현재 및 과거 Revision에 같은 entity_id를 가진 상이한 kind가 있는지 확인
SELECT entity_id,
       COUNT(DISTINCT kind) AS kind_count,
       ARRAY_AGG(DISTINCT kind) AS kinds,
       COUNT(*) AS revision_rows
FROM home_revision
GROUP BY entity_id
HAVING COUNT(DISTINCT kind) > 1
ORDER BY kind_count DESC, revision_rows DESC;
```

위 쿼리에 충돌이 없더라도 기존 수집 로직이 기록을 덮어서 이력이 사라진 경우는 탐지하지 못한다. 실제 파서의 `source_id, origin_key, kind`를 **fixture/원본 manifest**와 비교해 재현 시험한다. 해시 충돌과 의미적 원천키 중복을 구분한다.

**수정 방향:** 새로운 원천 객체 ID 계산에는 `kind + source_id + original_key`를 이름공간 구분자로 넣는다. 그러나 **레거시 ID는 재작성하지 않고** `legacy_entity_id → canonical_source_object_id` 교차표를 생성한다. `home_revision.id`는 판본 ID로 유지하며 실사업의 영구 ID가 아니다.

### PHASE 0 완료 조건

- `00_preflight.md`, `00_compatibility_inventory.json`, `00_migration_risk.md`, 백업/복원 테스트 기록.
- 수정 전 모든 테스트의 기준선을 확보하고 기존 승인건·감사건·goal 수치의 재현 가능성 확인.
- 기본 조건을 충족하지 못하면 운영 마이그레이션을 하지 말고 fixture·샌드박스 작업까지만 수행.

---

## 3. PHASE 1 — 원천 수집수단의 실행 검증 (G1→G4)

### 3.1 Registry를 기계 판독용으로 매핑

- `HOME_source_verification.json`에서 기존 36개 `source_id`와 신규 19개 **비교 후보**를 읽는다.
- 특정 신규 후보가 기존 `lh_movein_history`, `molit_statistics` 등과 같은 물리 원천이면 새로운 `source_id`를 무조건 발급하지 않고 `source_alias`/동일 카탈로그 연결로 중복을 해소한다.
- 공통 최소 항목: `source_id`, `catalog_id`, `endpoint`, `format`, `auth_env_var_name`, `update_cycle`, `license`, `source_as_of`, `period_coverage`, `geography`, `pagination`, `rate_limit_verified`, `schema_version`, `parser_version`, `record_key_rule`, `raw_manifest_ref`, `verification_level`, `verified_at`, `blocker`, `owner`.
- **G1(명세확인), G2(실제 1~3 페이지/파일 확보), G3(전수 범위 확인), G4(정합성·주기 재검증) 별도 boolean/status**로 만들 것. ‘명세 확인’을 ‘수집 완료’로 승격시키지 말 것.

### 3.2 우선 실증 대상, 수집 방법 및 의미

| P | source/공식 제공 위치 | 실행해야 할 작업 | 완료 판정 |
|---|---|---|---|
| **P0** | 건축HUB 주택인허가 `data.go.kr/data/15136560/openapi.do`, 기존 `building_hub` | 현재 기본개요 `getHpBasisOulnInfo` 외 `getHpDongOulnInfo` 및 `getHpPlatPlcInfo` 2개 엔드포인트 도입. 공식 명세의 URI/파라미터를 확인한 뒤 서울·경기 **샘플 법정동**에서 페이징·조인키·PNU·유형·날짜를 검증 | 키 승인/실호출 후 G2; 실호출 실패 시 fixture+`BLOCKED_AUTH`만 표기. 3종 PK 연결 테스트 |
| **P0** | 국토교통통계누리 인허가 `hRsId=31`, 착공 `471`, 준공 `468` | 월별·연도별 공식 공개 파일을 내려받는 방법을 확인. 실제 통계표가 제공하는 지역 단위(시도/시군구)를 읽고 정의·잠정/확정·수정판본 적재 | `home_region_stat` 독립 영역. 다운로드 확인한 정확한 URL·SHA·단위·범위·지역 개수를 기록. 시군구 미제공 시 `NOT_AVAILABLE` |
| **P0** | LH 준공예정 CSV `data.go.kr/data/15141761/fileData.do` | 실제 다운로드 가능 여부와 파일 컬럼 확인, 기존 LH 공급·입주 계획과 지구/블록/공급유형 중복 검토 | `PLANNED_COMPLETION`, `estimated_date_precision`, `UNCONFIRMED_UNITS` 명시. **actual 준공 이벤트 생성 금지** |
| **P0** | 국토부 지정·변경 원고시: `molit.go.kr/USR/I0204/m_45/dtl.jsp?gubun=4&idx=18272&lcmspage=20` | 고양창릉(고시 제2024-372호)→이전 고시 제2022-618호 체인 확인. 고시번호, 지구코드, 효력일, 변경 전후, 고시 PDF manifest 저장 | 단일 지구 사례로 `HOME_PLAN_EVENT` 생성 fixture. 전체 지구 자동 확대는 전수 가능성 확인 후 |
| **P1** | 서울 `OA-20281` upisRebuild, `OA-20283` 고시 연계, 서울 분기 현황 `OA-22856` | 최신 이용허락/공개 API, 고시관리코드 조인, 원고시 원문 재조회, 서울 정비사업 골든셋 후보 수집 | 권리 확인 전 2차배포/가공 공개 사용 비활성. 법적 상태는 원고시로만 CONFIRMED |
| **P1** | 경기도 온누리 `gg.go.kr/onnuri/index.do`, 경기도/시군 고시 | 실제 사업장검색·다중페이지·공개파일 존재 여부, 원고시 링크, 자료범위 확인. 민간정비와 공공택지 범위 분리 | 웹 존재는 G1, 전수 API 등 미확인 부분을 `V1`로 유지 |
| **P1** | 기존 LH/SH/GH 공고 및 입주 자료 | 공고 유형별(본청약/사전/잔여/정정), 계획 vs 실제, 기관별 특정 파일의 작은 모집단 문제를 명시 | 데이터셋 정의상 범위 밖 사업을 HOME 전체 모집단으로 보충하지 않음 |
| **P2** | KOSIS/SGIS/행안부 인구·가구·재고 및 한국부동산원 입주전망 | 통계표/행정구역/시점/관측·추계를 고정, 공공임대별 비교 가능성 조사 | 지역 맥락/forecast reference 계층만; 정책 실적 분자에서 제외 |
| **P3** | 멸실·철거의 순증호수, 사업별 병목·공사중단 원인 | 55개 검증대장 `N` 항목으로 보존, 공식/수기 관리 수단 제안 | 구체적 전수 원천·사업 연결·허용 조건 미검증 시 자동 추론 금지 |

URL 전체·남은 주의사항은 `HOME_source_verification.json`과 `HOME_데이터확보_검증보고서.md`를 참조하라. URL 하나가 리디렉션/차단되면 임의의 다른 비공식 미러로 넘어가지 말고 공식 대체 경로를 확인하며 교체 이력을 기록하라.

### 3.3 Collector, 원본/manifest, 완결성

기존 수집기(가능하면 그대로 사용)에서 다음 **명시적 진입 지점**을 제공한다. 실제 호출 API signature는 저장소를 확인한 뒤 정한다.

- `probe --source <ID> --region <CODE> --period <PERIOD> --max-pages 2`: 공식 원천을 **소량** 조회하고, HTTP 상태/인증/응답 스키마·원천 total/page와 원본 hash를 저장.
- `collect --source <ID> --region ... --period ... --resume`: 허용된 호출량 안에서 체계적으로 수집. 종료 페이지 또는 totalCount까지 확인; 중단시 checkpoint, 재시도/백오프·중복 제거.
- `verify-coverage --source <ID>`: requested vs completed region/period/endpoint/page, 원천 건수, loaded 행수, 연결 후보건수, 실패 사유, 마지막 성공 시각을 출력.
- `verify-provenance --revision <ID>`: 화면 값 → measure → source_revision → batch manifest → raw hash(현재 raw 보관 여부 포함) 재현.

**의도적 예외:** 인증키 미발급 등으로 실호출이 안 되면 `BLOCKED_AUTH`, 원본 다운로드 제한이면 `BLOCKED_DOWNLOAD`, 라이선스 확인 불가면 `BLOCKED_LICENSE`, 지역별 집계 부재면 `NO_GRANULARITY`. `G2/G3/G4=PASS`로 허위 기재 금지.

검증 상태코드 예: `NOT_ATTEMPTED | PARTIAL | COMPLETE | CONFIRMED_ZERO | FAILED | BLOCKED_AUTH | BLOCKED_LICENSE | SOURCE_UNAVAILABLE | STALE`; `value_status`는 별도 열(`AVAILABLE | UNVERIFIED | DATE_UNKNOWN | NOT_MAPPED | NOT_APPLICABLE | CONFIRMED_ZERO`).

### PHASE 1 완료 조건

- `docs/home_rebuild/01_source_probe_results.md`, `01_coverage_matrix.csv`, `01_source_registry_verified.json`.
- P0 수집원 4그룹 각각 공식 명세·샘플 원본/fixture·구조/키/기간/지리 단위와 실패 상태가 기록됨.
- 키/다운로드 권한이 없을 때는 collector 테스트와 GATE 차단 이유를 남긴다.

---

## 4. PHASE 2 — 목표 논리 ERD와 점진적 물리 모델 구현

### 4.1 반드시 유지할 개념

**주요 엔터티와 관계:**

```text
HOME_POLICY <-> POLICY_PROGRAM_LINK <-> HOME_PROGRAM
HOME_PROGRAM <-> PROGRAM_PROJECT_LINK <-> HOME_PROJECT --< HOME_BLOCK
HOME_PLAN --< HOME_PLAN_EVENT         HOME_PLAN <-> PLAN_PROJECT_LINK <-> HOME_PROJECT
HOME_PROJECT --< SUPPLY_COHORT (parent_cohort_id, leaf/residual)
SUPPLY_COHORT --< SUPPLY_MEASURE
HOME_PROJECT / SUPPLY_COHORT --< HOME_MILESTONE
HOME_PROJECT --< IDENTITY_ALIAS / PROJECT_EVIDENCE --> HOME_REVISION
SCOPE_BASELINE --< SCOPE_BASELINE_ITEM (policy/project 포함·제외·근거)
HOME_REGION_STAT (별도 지역×월×지표×통계표, 원천 판본)
HOME_COVERAGE (source×endpoint×region×period×partition/page)
```

**절대 혼합하면 안 되는 개념:**

- **정책:** 대책·업무계획의 발표와 목표, 정책 시행 전 존재한 사업은 후속 귀속을 자동 허용하지 않음.
- **프로그램:** 사업 유형/집행체계. 초기 정책 가설(`seed_policy_id`)로 안정 ID 생성하지 않음.
- **법적 계획:** 정비구역·공공택지 지정·변경·해제의 독립 생애주기. 모든 사업의 필수 부모는 아님.
- **실제 사업:** HOME가 발급하는 고유 `HPR_*` 영구 ID. 기관별 `kind=project` 후보/건축허가/공고는 이 ID가 아님.
- **블록:** 사업 하위 단위, 공식 경계 없으면 좌표/대표점으로만 표시.
- **공급묶음:** 같은 실물 공급물량을 여러 단계/상위·하위에서 한 번만 세는 `SUPPLY_COHORT`.
- **원천 Revision:** 원본 판본/기록시각. 사업의 PK가 아님.
- **지역 공식통계:** 별도 팩트. 개별 사업에 임의 귀속하지 않음.

### 4.2 초기 구현 구조와 FK/unique/index 설계

- **첫 마이그레이션(append only):** `home_coverage`, `home_project`, `home_identity_alias`, `home_project_evidence`, `home_scope_baseline`, `home_scope_baseline_item`, `home_supply_cohort`의 최소 세트를 샌드박스에 작성한다. FK/유일성·기간제약을 실제 데이터 충돌 검사한 뒤 점진적으로 강화한다.
- **법적 사건 파일럿:** `home_plan`, `home_plan_event`, `home_plan_project_link`를 골든셋과 **병행** 추가한다. 계획이 모든 사업의 부모라는 필수 FK는 만들지 않는다.
- **공급/시계열:** `home_supply_measure`, `home_milestone`, 관련 시간 수정·선택 판본, `home_region_stat`. 기존 `PROJECT_SCHEDULE`와 개념 중복이므로 두개의 독립 사실표를 무분별하게 중복 구현하지 말고 명세를 비교해 정합한 물리 설계를 채택한다.
- **관계/관리 이관:** 독립 정책/프로그램 ID 및 다대다 링크, 기관 역할·이슈원장은 테스트가 안정화된 뒤 도입. 레거시 `home_program_mapping.id`가 `name+seed_policy_id`와 묶여 있는지 **실제 코드로** 확인하고 새 고유 `program_id`와 alias mapping을 생성. 정책–프로그램과 프로그램–사업의 기존 2단계 검토 UI를 유지.

**인덱스·무결성(실제 dialect/스키마에 맞게 설계):**

1. 논리 객체 PK는 UUID/안정 문자열; revision PK와 분리. 외부 `source_id/key`는 `source_object_alias` 고유 복합키, 이전 키 충돌 이력은 별도 conflict table.
2. `(project_id, role, org_id, effective_period)` 및 `(plan_id, project_id, relation_type, valid_period)` 등 N:M 링크의 의미와 시간중복 제약을 문서화.
3. `supply_cohort`에 `project_id`, `parent_cohort_id`, housing/tenure/type, planned units, valid/recorded span; **부모-자식 순환 금지** 및 중복 집계 context guard.
4. `(policy_id, supply_cohort_id, metric_type, aggregation_context, effective interval)`에서 활성 counting allocation 한 번만 허용. **정책별 1회 집계가 전체 지역 총량의 중복 방지를 뜻하지 않음을 구현**.
5. `region_code`는 행정동/법정동/시군구 구분과 `geometry_version`·유효기간 동반. 정책 사업이 여러 지역에 걸치는데 공식 배분이 없으면 `REVIEW`로 남김.
6. `home_supply_measure`는 `metric_type`, `metric_semantics` (`STOCK`/`INCREMENT`), stage, date precision, source_kind (`OFFICIAL`/`ADMIN`/`ESTIMATE`), scope, units, base date, evidence revision, `value_status` 보관. `NULL` vs `0` 명확.
7. 날짜는 `effective_at`, `source_base_date`, `original_plan_date`, `current_plan_date`, `actual_date`, `recorded_at`, `superseded_at` 의미를 구분. 월/년 정밀도 미보존 시 변환 금지.
8. `home_audit`의 현재 entity_type 부재 문제가 있으면 **기존 감사 보존 후** `target_type`을 확장/추론가능한 legacy mapping/view 생성. 기존 값 유실 금지.
9. Raw snapshot·parse fixture는 별도 보관하며 DB migration은 Alembic만 사용. 마이그레이션 반대방향/복구 방안을 기록.
10. 신규 데이터 조회 View는 원천 후보의 `REVIEW`와 공식 확인 사실을 명시적인 다른 SQL 경로로 구현한다.

### 4.3 공급 Cohort 이중집계 검증

**설명용 가상 사례:** 어떤 지구 총계획 33,000호, 하위 A1 12,000호/A2 8,000호이면 합계 53,000호로 계산하면 안 된다. 

- `home_supply_cohort`에서 부모-자식 관계·중복 영역과 기준 stage를 식별한다.
- 검증된 하위 블록 합계 20,000호와 상위 총계획 33,000호는 두 개의 다른 지표(상위 목표와 식별 하위)를 각각 보존.
- **미배정 잔여 13,000호**는 지구 내 미확보 하위 범위를 나타내는 *계산상 계획 잔여값*, 가상 실물 블록이나 완료 실적으로 생성하지 않는다.
- 하위가 포괄한 지역/계획 범위와 상위 범위가 불일치하면 잔여도 계산 불가 상태로 표시한다.
- 부분 준공·분할 공고는 서로 다른 하위 cohort, 부분 범위 ID 또는 증분(`INCREMENT`) 의미가 검증될 때만 합산. `최신 event 하나`라는 단순 규칙이 여러 독립 부분 준공을 누락시키지 않도록 한다.
- 동일 cohort 단계(공고·착공·준공·입주)를 **주택호수로 횡단 합산하지 않는다**.
- 하나의 cohort가 여러 정책에 등장해도 `region_total`을 정책별 결과 재합산으로 만들지 않는다. 정책별 집계와 고유 지역 공급 집계는 독립 `aggregation_context`/할당 규칙을 쓴다.

### 4.4 정책 달성률 표시 계약

정책의 완료율/진행률은 반드시 **공식 지표·기간·지역·집계범위가 일치**해야 계산한다. `as_of_date`, `baseline_id`, `metric_type`, numerator evidence, denominator evidence, comparability_reason 필수.

- `official_policy_progress`: `official_confirmed_actual_units / official_policy_target_units`, 실제 비교가능한 경우만. 비정합은 `rate=null`, `reason=NON_COMPARABLE`.
- `mapped_target_units`: 승인된 **정책 연결 사업의 계획 물량**, 공식 완료 실적과 별도.
- `review_inclusive_units`: 확정 연결 + 미확정 REVIEW 후보 **중복 제거 합계**를 관리자 탐색 화면에만. 정식 공식 실적에서는 제외.
- `mapping_coverage`: 기준선에서 승인된 대상 사업 중 연결된 사업건/물량 비율. 정책 공표 목표 대비 실적률과 다른 이름 사용.
- `schedule_coverage`: 일정이 있는 관리대상 사업/물량 비율. 날짜 정밀도가 연/월이면 exact-date rate로 취급하지 않음.
- `region_official_stat`: 전체 지역 시장 흐름. 정책 사업·원천 목록과 정의가 다른 경우 ‘사업 확인 포괄률’을 단순 나눗셈으로 계산하지 말 것.

### PHASE 2 완료 조건

- `docs/home_rebuild/02_logical_er.md`, `02_physical_schema.md`, 실제 적용한 Alembic revision, fixture/테스트.
- 성북구형(정비구역의 과거 지정/해제)·경기 지구/블록형 데이터가 논리 모델에 담김.
- 기존 관리자 매핑·감사·goal·공개 API의 의미가 손상되지 않음.

---

## 5. PHASE 3 — 서울 정비형 + 경기 공공택지형 골든셋

### 대표 모집단

`PLAN.md`의 Seed 최소 기준을 따른다: **최소 2개 정책, 3개 프로그램, 실제 사업 10건, 블록/단지/공급묶음 10개 이상**. 서울 성북구의 정비사업과 경기 공공택지·3기 신도시 등 서로 다른 절차유형을 포함. 목표 물량·일정과 고시번호·원본 링크 없는 fixture는 **`UNVERIFIED`** 처리한다. 규모 여건이 되면 20~30건까지 확장하되 최소 사업도 끝까지 검증되지 않으면 확장을 중단한다.

### 사업별 증거열(각 승인 필수사항)

`정책 발표원문 → 정책/프로그램 REVIEW 연결 → 사업 고유 증거 → 법적 구역 지정/변경고시(해당 시) → 블록/필지/허가 대응 → 계획·승인·착공·모집·준공·입주(확보한 단계만) → 각 단계별 원천 revision/일자/물량 → 관리자 확정/해제와 감사`.

- 건축허가 단일 관리번호에서 여러 동·필지가 나오는 것과 동일 사업 다수 인허가가 존재하는 것을 분리한다.
- 해제된 계획과 동일 이름의 신규 계획·사업을 자동 병합하지 않는다.
- `policy→program`, `program→project`, `plan↔project`, `project↔source` 링크별 검토상태/근거/유효기간 독립 보존.
- 자동 매칭은 **공식 일치 ID > 기관·허가번호·필지/경계·시기 조합 > 텍스트 유사도** 순서. 유사도만으로 CONFIRMED 금지. 규칙/모델 버전을 기록한다.
- 정비/택지/매입임대 등 서로 다른 법적 절차는 process template(`pipeline_type`)으로 관리. 공통 UI stage는 파생 규칙만 사용.

### 골든셋 완료 조건

- 최소 10건의 실제 사업에 대해 공식근거·식별·정정/검토 상태가 완결되거나 **미확보가 명확히 표시**된다.
- 정책·사업·지역 집계의 상위 합계가 Leaf/cohort에 의해 재현된다.
- false-positive match(다른 사업을 하나로 잘못 묶음)를 검토할 수 있는 별도 수작업 샘플/오류 리포트.
- 데이터 범위가 미달인 사업은 완료 대신 `PARTIAL_EVIDENCE`.

---

## 6. PHASE 4 — 시계열·지역 공식 통계·지도/Tree Adapter

### 독립 통계 Fact (`home_region_stat`)

권장 필드: `source_id`, `table_id`, `region_code`, `region_code_system`, `geometry_version`, `reference_period`, `period_precision`, `published_at`, `stat_revision`, `preliminary_or_final`, `metric_type`(PERMIT/START/COMPLETION/SALE 등), `unit`, `value`, `coverage_scope`, `definition_version`, `raw_revision_id`.

통계표를 먼저 열어 실제 시군구 열이 있는지 확인. 없다면 도 단위까지 제공한 계열임을 기록하고 시군구 별 0으로 보간하지 말 것. 통계구조가 바뀌면 당월 잠정/확정 재공표를 revision으로 보존.

### 지도 중심 공통 계약

실제 API namespace는 기존 서비스와 충돌하지 않는 `/api/v2/...` 또는 `?schema_version=2` 등을 평가하여 선택. v1은 유지한 상태에서 Dual Read를 검증한다.

**필수 DTO(개념):**

```json
{
  "object_id":"HPR_TEST_ONLY",
  "object_type":"PROJECT",
  "as_of_date":"2026-10-10",
  "scope_baseline_id":"SCOPE_TEST_ONLY",
  "geometry":null,
  "geometry_status":"NOT_MAPPED",
  "plan_units":{"value":null,"value_status":"UNVERIFIED","basis":"OFFICIAL_PLAN"},
  "stage_metrics":[{"stage":"START","actual_units":null,"status":"NOT_MAPPED"}],
  "schedule":{"original_plan":null,"current_plan":null,"actual":null,"date_precision":null},
  "risk":{"status":"NOT_ASSESSED","reason":null},
  "provenance":[],
  "mapping_status":"REVIEW"
}
```

**위의 ID/값은 테스트 계약 예시이고 실제 공급사업이 아님.** 법적 계획 없는 사업에도 사용할 수 있어야 한다.

API 후보(기존 경로에 대한 호환성 확보 후 구현):

- `GET /api/v2/overview?as_of=...&scope_baseline=...` — 시도/시군구 정책·전체 지역 통계를 구분해 제공.
- `GET /api/v2/map/features?zoom=...&region=...` — 지도 줌 수준별 지구/블록/실사업 위치·경계 상태·계획/검토/확정/실적 분리.
- `GET /api/v2/projects/{id}/timeline?basis=...` — 해당 사업의 최초계획/변경/실제와 date_precision.
- `GET /api/v2/policy-progress?policy_id=...` — 분모·분자·metric type·범위·검토·공식 실적·비교가능성 사유.
- `GET /api/v2/region-stats?metric=...&region=...&period=...` — 시도·시군구 공식통계; 해당 표가 제공하는 해상도만.
- `GET /api/v2/sources/coverage` — 인증 없이 공개 가능한 집계 품질 정보만.
- `GET /api/v2/provenance/{measure_id}` — 개인정보·비밀키 제거한 출처/판본/원고시 추적.
- `GET /api/v2/supply-tree` — 원본 Tree 기능과 대응, 기간 버킷(1년/2년/3년/3년 이후/시점미정) 및 중복 제거.

실제 라우터/접두경로는 기존 FastAPI에서 확인할 것. 위 URI는 임의로 v1 라우터를 교체하라는 지시가 아니다.

### 검토/내부 데이터 처리

- 공개 API `PUBLIC` 승인 데이터만 반환. 법적 원문 공개인 경우에도 내부 예상일·관리자의 지연 원인·담당자 개인식별 정보는 공개심사를 통과하지 않았으면 제외.
- 관리자 수기 수정은 권한 확인·충돌(409)·감사 append-only. AI 브리핑은 검증된 관련 사업·원천값을 URL/Revision으로 역추적 가능한 경우만 출력.

### PHASE 4 완료 조건

- 지도/Tree/시계열이 같은 `cohort` 기반 집계 서비스를 사용하고 정책·지역별 sum이 일치하거나 **정의가 달라 비교 불가로 설명**된다.
- 서울·경기 인구·가구/통계 맥락은 `reference/statistical` 데이터로 출력되어 official policy progress와 합쳐지지 않는다.
- 수치/일정/위치의 provenance와 확인 상태가 화면·CSV/API에서 유지된다.

---

## 7. PHASE 5 — 마이그레이션 전환·복구 및 확대

1. 운영 DB가 아닌 복원본에서 Alembic upgrade → 신규 원장 backfill → 관리자 매핑 이관 후보 작성 → 구·신 조회 동일 범위 비교.
2. 기존 `home_mapping.project_id`가 원천 `home_revision.entity_id`라는 사실을 보존한 `legacy_project_id ↔ canonical_project_id` 교차표 유지. 정책-프로그램 seed key 충돌·여러 후보 병합 시 관리자 목표/공식 연결 차이가 나면 자동 하나를 고르지 말고 `MIGRATION_CONFLICT`에 둔다.
3. 승인 마이그레이션만 실제 참조를 전환하되 rollback용 구 참조·샘플 수·감사 행 수를 보존. 기존 `/api/*`를 파괴적으로 삭제하지 않는다.
4. 이전 DB/Raw의 backup hash를 새로운 데이터 저장소와 연결하고 임의 삭제/덮어쓰기 없이 검증한다.
5. 수집 대상 확장은 실제 P0 실증결과와 호출비용/사용권한에 따라 서울의 다른 정비사업→경기도 관련 유형→나머지 법적 계획 순으로 수행한다. 해당 지역·기간 수집이 완료되기 전 `coverage=100%` 표시 금지.

**전환 금지조건:** 관리자 승인/goal/audit 유실 또는 변경, 정책 총량 이중합산, 기존 공개 조회 응답 회귀, 원천 재현 불가, 허가되지 않은 자료 외부 공개, DB 롤백 미실행.

---

## 8. 자동화 테스트 명세 — 반드시 코드로 작성할 것

1. **Identity/Revision:** `project`/`project_report`와 `policy`/`policy_event` 원천 객체 키가 같아도 새 ID 충돌 없음; 레거시 ID/감사 보존; 수집 재실행 idempotent.
2. **Plan Lifecycle:** 고시 2024-372처럼 선행 고시번호와 변경 관계 보존. `recorded_at`만 새롭다고 과거 효력일 변경 불가. 해제↔재지정 동명이인 계획 구분.
3. **Baseline:** 한 번 승인한 기준선 항목은 후속 수집으로 조용히 추가/제외되지 않음. 변경은 새 버전에서만. 국외/인천 물량 서울·경기에 자동 산입되지 않음.
4. **Cohort aggregate:** 가상 지구 33,000/블록 12,000+8,000 사례: **합계 33,000**이며 53,000 금지; 미배정 13,000은 실제 사업 이벤트 아님. 상하위 범위가 불명확하면 비교 불가.
5. **Multiple policy:** 한 실제 cohort가 여러 정책에 매핑되어도 `(policy_id, cohort_id, context)` 기준 정책별 중복 제거, 지역 전체 고유 공급은 다시 한 번만 세기. 서로 다른 공급 단계 횡단 합계 금지.
6. **Partial events:** 단일 cohort의 복수 부분 준공이 비중첩임이 확인된 경우 부분 실적 합산 가능; 중첩 또는 재공표이면 자동합산 금지. `STOCK` vs `INCREMENT` 처리 분리.
7. **Review/status:** REVIEW 후보는 탐색용만; CONFIRMED 정책 연결이 `official_actual`을 자동 생성하지 않음; NULL/0/불능/미연계/비적용 각각 API 표현.
8. **Policy target:** 착공 분자÷착공 분모만. 서울+경기 확인량÷전국·수도권 목표는 `NON_COMPARABLE`. 실제 상호 비교가능한 경우만 rate.
9. **Realization:** LH 준공예정 날짜와 0 세대수는 완료 실적으로 간주되지 않음; 원천 기존 대장 재고≠신규 준공.
10. **Regional statistics:** 통계 잠정→확정 변경 시 과거 판본 보존; 실제 지역 분류가 없는 표에서 시군구 숫자를 만들지 않음; 사업 합계/지역 통계의 분모가 다르면 직접 포괄률 계산하지 않음.
11. **Coverage:** API가 1페이지만 성공한 경우 COMPLETE 금지; 빈 성공 응답 CONFIRMED_ZERO와 오류 FAILED·키 오류 BLOCKED_AUTH는 다른 상태.
12. **Security:** 키/담당자 인적정보/비공개 계획 공개 API·manifest·CSV·로그 유출 테스트.
13. **Conflict/governance:** 관리자의 승인/해제와 수기 목표가 후속 수집에 의해 변경되지 않음; 관리자 변경은 optimistic lock/409와 audit append-only.
14. **UI/contract:** 기존 endpoint snapshot 유지; `/api/v2` fixture json schema 검증; 지도/Tree/연도별 숫자의 provenance 역추적 및 date precision.
15. **Recovery:** 새 Alembic 적용 전후 row-count/ref-integrity, backup→격리 DB 복원, 롤백 또는 backward-compatible cutover 검증.

테스트 실행 커맨드는 프로젝트가 실제 사용하는 `pytest`, `alembic`, Docker Compose 또는 개발 스크립트를 확인한 뒤 최종 보고서에 **그대로 재현 가능한 명령**으로 기재한다. 존재하지 않는 커맨드를 작동했다고 보고하지 말 것.

---

## 9. 매 단계 Codex가 남길 산출물

다음 경로는 권장 기본 위치이며 기존 repo conventions에 맞춰 조정 가능하다.

```text
docs/home_rebuild/
  00_preflight.md
  00_compatibility_inventory.json
  00_migration_risk.md
  01_source_probe_results.md
  01_source_registry_verified.json
  01_coverage_matrix.csv
  02_logical_er.md
  02_physical_schema.md
  02_aggregation_rules.md
  03_golden_set.md
  03_identity_conflicts.csv
  04_api_contract.md
  04_reconciliation.md
  05_migration_and_rollback.md
  05_security_and_license.md
  99_delivery_report.md
```

구현 코드는 실제 repo 구조에 따라 `backend/`, `scripts/`, `tests/`, Alembic revision에 반영. 빈 문서 또는 사실 없는 가상 ‘완료’를 쓰지 말 것.

**각 phase 보고 형식:**

| 항목 | 내용 |
|---|---|
| 현재 코드/DB에서 확인 | 실제 읽은 테이블·API·코드·원천 fixture·날짜 |
| 변경 | 파일별 수정사항, 비파괴 migration ID, 테스트 |
| 실제 원천 검증 | official URL, G1~G4, 인증 여부, 응답 code, raw hash(민감값 제외) |
| 성공/차단 | PASS / PARTIAL / BLOCKED / NOT_ATTEMPTED |
| 품질·이관 | 보존된 승인건, alias/conflict 건수, 중복 합계 검사 |
| 미완료 사유 | 키 미발급, 데이터 부재, 고시 누락, 라이선스 확인, 배치 불완전 |
| 사용자 확인 필요 | 권한·원천약관·대량 API 호출/배포 승인이 필요한 실제 행위만 |

### 최종 인수 기준

- [ ] 기존 HOME 서비스와 관리 이력의 read/write 기능 회귀 없음.
- [ ] 실제 코드를 확인한 현행 구조와 목표 구조의 차이를 명확히 기록.
- [ ] 55항목 catalog(기존 36+후보 19)의 G1~G4와 남은 과제 관리.
- [ ] P0 우선자료의 **실제 응답/다운로드 결과** 또는 권한/환경 차단 근거를 충실히 기록.
- [ ] 최소 골든셋의 사업ID·plan·cohort·물량·근거를 검증하고 중복집계 테스트 통과.
- [ ] 승인 기준선·비교가능한 분자/분모·정확한 `0` vs 결측을 구현.
- [ ] 지역 전체 공식 통계와 정책 사업 실적이 별도 자료계층/DTO로 존재.
- [ ] 1차 공개/지도 API의 source lineage와 검토상태 검증 통과.
- [ ] 감사·goal·원천 raw/manifest·이력·보안·복구 검증.
- [ ] `99_delivery_report.md`에 수행/미수행/차단, 결과, 스크립트·커밋/마이그레이션, 다음 실행 명령을 빠짐없이 기재.

## 10. 작업 착수 시 Codex가 먼저 할 일 (구체적 순서)

1. **이 지시서 / PLAN / BRIEF / verification JSON을 열고 실제 기존 코드·테스트를 조사한다.** 현재 상태 검증 전 스키마 생성부터 시작하지 않는다.
2. `PHASE 0` preflight 및 복구 검증 문서를 작성한다.
3. P0 원천의 실호출 가능성과 라이선스·표본·전수수집 범위를 검사하고 JSON의 판정을 **증거가 있을 때만** 승격한다.
4. 기존 서비스에 영향 없는 additive schema와 골든셋 fixture를 구현한다.
5. 실사업/법적 계획/공급 cohort/승인 기준선 및 지역 통계 분리 집계를 테스트한다.
6. 지도·시계열 계약을 기존 API와 함께 검증한다.
7. 성공한 결과만 합산하여 `99_delivery_report.md`를 작성한다.

> **핵심 원칙: ‘없는 값은 없는 것으로, 다른 모집단은 다른 것으로, 같은 공급물량은 한 번만’ 처리한다. 증거 없는 완료·달성률·사업/정책 연결을 생성하지 않는다.**
