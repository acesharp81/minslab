# AIWorks 프로젝트 중심 플랫폼 전환 로드맵

> 문서 역할: AIWorks의 제품 방향과 18단계 이후 구현 순서를 관리하는 기준 문서(Source of Truth)
>
> 최종 갱신: 2026-09-04
> 현재 기준선: `BUILD_PLAN.md` 1~17단계 완료
> 현재 진행 단계: AIWorks 0.31.2 / 업무 MCP 실증 1~4 완료 / 최종 보완개발 Phase 0~6 병행 안정화
> 문서 상태: Phase 0·1·3 완료 / Phase 2 서버·브라우저 완료·Windows 네이티브 실행 차단 / 단위·통합·계약 154개, Golden Workflow 58개, 실제 양식 Golden Set 3종, 격리 Firefox 실조작 14종 통과

## 진행 현황 요약

| 단계 | 상태 | 핵심 결과 |
|---|---|---|
| 1~17 | 완료 | 편집기, 승인·감사, MCP 제작·스토어, 문서 버전과 지식 계층 PoC |
| 17.5 | 완료 | 파일 선택형 첫 요청, 동적 MCP 흐름, 파생 보고서, 선택 문구·법률 요청, Solar Pro 3 기본 모델 |
| 17.6 | 완료 | 파생 보고서 HWPX 패키징, RHWP 문서 세션 로딩, 같은 편집기에서 선택 변경·버전 저장 |
| 17.7 | 완료 | 행안부 내부보고형 양식 MCP, 내용 보존 HWPX 변환, 같은 RHWP 세션 revision 적용, 로컬 전용 승인 경계 |
| 17.8 | 완료 | 양식·처리·데이터·도구 제작 프로필, 파일 역할, 유의사항·처리 절차 실행 가이드, 유형별 샌드박스 검증 |
| 17.9 | 완료 | 설치형 `mcp_capabilities` 색인, 호출 예시 Resolver, 서명·버전 고정 Binding, Prompt/Composite 격리 실행, HWPX 플레이스홀더 양식 적용 |
| 17.10 | 완료 | 전체 폭 MCP Studio, 4개 빠른 제작 프로필, 5단계 상태 표시, 게시 후 즉시 설치 승인, 설치 Registry와 호출 문구 테스트, HWPX 시작 양식 다운로드 |
| 17.11 | 완료 | 다중 PDF·HWPX·텍스트 원본 추출·청크 인덱스, 게시 전 RAG 검색, Retrieval Adapter, 데이터 의도·본문 주제 기반 자동 선택, 페이지 인용 답변 |
| 17.12 | 완료 | Solar Fast/3/4 자동 라우팅 계약, 연도·지적사항·출처 기반 로컬 근거 재구성, 데이터 조회에서 편집 가능한 HWPX 보고서 생성과 RHWP 세션 연결, Studio 빠른 검증 시나리오 |
| 17.13 | 완료 | Store 게시본→다음 버전 편집 초안·사용자 패키지 확인 삭제, 플레이스홀더/작성요령·예시/완성본 구조 양식 분석·적용, 범용 Streamable HTTP 외부 MCP 어댑터·tools/list 검증·localhost HWPX 자동 후처리 |
| 17.14 | 완료 | 승인 프로필 기반 stdio Gateway, `kordoc@4.7.3` 고정 로컬 런타임·오프라인/작업폴더 제한, `generate_document` 보고서 HWPX 자동 후처리, stdio/HTTP Builder 분기와 실제 tools/list·HWPX 생성 검증 |
| 17.15 | 완료 | 현재 RHWP 보고서의 ‘전체 내용 개조식/항목식 변환’ 의도 분리, 로컬 보고서 MCP 재구성, HWPX 패키징과 같은 문서 세션 새 revision 적용, 데이터 MCP 오분류 방지 |
| 17.16 | 완료 | 의도분석 MCP의 최초 문서 생성 기본값을 Solar Pro 4로 고정, 승인 기반 Upstage 실호출과 데이터 MCP 근거 종합 HWPX 생성, Store 환경설정 버튼·공통 Schema 폼·revision 충돌 방지 저장소, 향후 MCP가 설정 계약만 선언하면 같은 UI를 재사용하는 범용 설정 프레임워크 |
| 17.17 | 완료 | Solar Markdown 정규화, Report Document 의미 블록 계약, Project Fact 스냅샷 바인딩, 양식 MCP v2, KODAK/HWPX 단일 렌더링 경계와 `- ·` 중복 방지, 계획·산출물 재현 메타데이터 |
| 17.18 | 완료 | Markdown 불변 revision, HWPX 역변환, exact-duplicate 식별·비파괴 보관/복원, 메타정보 후보 일괄 검토 |
| 17.19 | 완료 | 문서별 MD/HWPX·메타정보·이력 탭, 명시적 동기화, revision/SHA 기반 편집기 DOM·세션 캐시 |
| 17.20 | 대체됨 | 자동 재렌더링·탭 이탈 자동 승격은 연속성과 사용자 통제를 훼손하여 폐기. 명시적 MD→HWPX/HWPX→MD 반영 계약으로 대체 |
| 17.21 | 완료 | 직전 대화 답변을 새 Markdown 원본으로 승격한 뒤 요청 양식으로 새 HWPX/RHWP를 만드는 흐름과 현재 문서 양식 전환 분리 |
| 17.22 | 완료 | 프로젝트 목록·생성·통합 작업공간 API, 최초 프로젝트 선택 강제, 기존 MD·메타·파생 파일 즉시 복원, 관찰 가능한 오케스트레이션 상태, 대화·편집 비율 드래그 조절 |
| 17.23 | 완료 | 마지막 문서·탭·화면·대화 복원, 탭 이동 무변경, 명시적 양방향 동기화, HWPX 변경 보류, 결정론적 질문-초안 품질 하네스 |
| 17.24 | 완료 | TemplateSchema 슬롯 보정, Workflow/Step Run·재승인 재시도, MD/HWPX 충돌 저장·해결, Artifact Relation 그래프, Fact 시간변화/오기 결정 |
| 18 | 완료 | 프로젝트 선택·복원, 멤버십/RBAC, 정책, 독립 대화·메시지·결정 엔터티와 portable backup 1.2 완료. 기본 삭제는 복원 가능한 보관이며 소유자는 이름 재확인 후 완전 삭제 가능 |
| 19 | 완료 | 범용 Artifact/Version 저장소, relation 순환 방지, MD/HWPX 호환 동기화, Evidence 위치·발췌·해시·신뢰도와 이력 표시 완료 |
| 20 | 진행 | Fact Value, 기준일·스냅샷, 후보 일괄 검토와 시간 변화/오기 결정 UI 구현. 독립 Fact Conflict/Decision 엔터티는 후속 |
| 21 | 부분 구현 | 서명·권한·입출력 하드 필터, 평가·선호 랭킹·후보 UI와 Capability DAG 1.0 Schema 연결 검증 완료. keyword fallback 제거와 시각 조합은 후속 |
| 22 | 완료 | Workflow/Step Run, 체크포인트, 재승인 뒤 동일 Run ID에 새 attempt를 추가하는 in-place 재개와 실행 attempt 이력 완료 |
| 23 | 완료 | Project Grant, 10분 단일 소비 JIT lease, 최종 행위 확인, 외부 모델 개인정보 마스킹과 MCP 업데이트 권한·전송 diff 해시 재승인 완료 |
| 24 | 부분 구현 | MD/HWPX 명시적 왕복, Render Map 1.2, DOCX·ODT·XLSX 의미 입출력과 PDF 실제 출력·손실 계약 완료. 복잡 배치 고충실도 어댑터는 후속 |
| 25 | 부분 구현 | TemplateSchema 1.2, scan/OCR 차단, 반복·조건·표 역할 Mapping Studio와 5종 Studio 완료. RHWP 시각적 양방향 하이라이트는 후속 |
| 26 | 완료 | Recipe 버전·공유·포크·설치·폐기, 이름/태그 검색, 권한·비용·지연·라이선스·출처·보안 미리보기와 취약 버전 설치 차단 완료 |
| 26.5 | 완료 | SHA-256 무결성 JSON으로 MD revision·메타정보·HWPX·Artifact 계보·Evidence 백업, 항상 새 프로젝트 ID로 복원 |
| 27 | 부분 구현 | backup 1.2, Prometheus·OTLP, 비파괴 RPO/RTO 복구 훈련, SBOM·감사 해시 체인 완료. 외부 경보·동시 부하·실복구 훈련은 후속 |
| 최종 보완 Phase 0~6 | 진행 | 내장 HWPX 기본화, Intent 계약, Builder 시각 매뉴얼, credential별 token/RPM 최소 정책 완료. 브라우저·물리 퇴역·운영 과금은 잔여 |
| 업무 MCP 실증 1~4 | 완료 | 실제 Data·Process·Template MCP 제작·설치·조합 실행, 대형 실양식 추출·품질 검증, 변경 블록 선택 MD↔HWPX 충돌 병합, Artifact I/O Schema 기반 자동 계획 완료 |

## 업무 MCP 실증 1~4 완료 범위 — 2026-09-01

이 네 단계는 기존 로드맵의 단계 번호나 최종 보완 Phase 번호를 대체하지 않는다. 사용자가 MCP Builder로
실제 업무 기능을 만들고 하나의 요청으로 끝까지 실행할 수 있는지를 확인하는 수직 실증 묶음이다.

| 실증 단계 | 상태 | 구현·검증 결과 |
|---|---|---|
| 1. 업무 MCP 3종 | 완료 | Data MCP는 근거 청크를 `evidence.collection`으로, Process MCP는 절차를 실제 모델 프롬프트와 `document.markdown`으로, Template MCP는 `document.semantic-blocks`를 `document.formatted`로 전달한다. 세 패키지를 제작·검증·게시·설치한 통합 테스트가 통과했다. |
| 2. 실제 HWPX 양식 | 완료 | 일반·작성요령·예시·완성본 HWPX에서 제목·본문·목록·표 prototype을 추출한다. 표 첫 셀을 제목으로 오인하지 않도록 표 밖 보고서 문단을 우선하며, 500번째 이후 슬롯도 Mapping Studio에 유지한다. 안내·예시 잔존, 제목·본문 1회, 표·리소스 보존을 실렌더링 후 재파싱한다. |
| 3. MD↔HWPX 왕복 | 완료 | 탭 이동은 변환하지 않고 명시적 승격만 허용한다. 동시 수정 충돌에서 HWPX 변경 블록을 비교해 선택한 블록만 최신 MD revision에 병합하고, 비선택 HWPX 변경은 MD 기준으로 되돌린 뒤 HWPX와 Render Map을 `synced`로 갱신한다. |
| 4. 자동 오케스트레이션 | 완료 | Builder 유형별 Artifact I/O 계약, Task Compiler, Capability Resolver와 Capability DAG를 연결했다. Resolver는 품질·비용·지연·프로젝트 선호와 Schema 연결 가능성으로 Data→Process→Quality→Template→HWPX→RHWP 단계를 고정 버전으로 계획하며 각 MCP의 선택 이유를 노출한다. |

현재 완료는 PoC 실증 기준이다. 실제 Solar 장시간 품질·timeout 시험, Windows 네이티브 RHWP,
기관별 익명화 golden 양식 확대, 기존 keyword fallback 완전 제거와 Recipe 시각 조합은 운영 전 후속 범위다.

## 최종 보완개발 확정 계획 — AIWorks 0.31.2

이 절은 기존 1~27단계 구현 이력을 폐기하거나 다시 만드는 계획이 아니다. 현재 구현을 보존하면서
최종 PoC의 책임 경계를 정리하기 위한 **신규 작업의 실행 기준**이다. 아래 Phase와 기존 단계가
충돌하면 기존 데이터·API·감사 이력의 호환성을 지키는 범위에서 이 절을 우선한다.

### 재검증 결론

1. AIWorks의 중심은 특정 문서 변환기가 아니라 Context, Intent, Planner, Resolver, Approval,
   Orchestrator와 Audit으로 이어지는 Control Plane이다.
2. 프로젝트 문서의 의미 원본은 불변 Markdown revision이다. HWPX와 다른 파일은 해당 revision에서
   만들어진 파생 산출물이며 자동으로 Markdown을 덮어쓰지 않는다.
3. 문서 생성 경계는 `Markdown Revision → ReportDocument → Template MCP/TemplateSchema →
   HWPX Renderer → HWPX Artifact → RHWP`로 통일한다.
4. KODAK/KORDOC는 Core가 아니라 교체 가능한 외부 renderer 구현이었다. 신규 자동 선택을 제거하되,
   내장 경로의 품질과 E2E를 먼저 증명한 뒤 점진적으로 퇴역한다.
5. RHWP, 예산 정책 데이터 MCP, Template MCP, 프로젝트·Artifact·Fact·Evidence·승인·감사 계층은
   보호 대상이다.
6. 범용 외부 MCP의 `initialize`, `tools/list`, `tools/call`, stdio, Streamable HTTP와 Builder는 유지한다.
   KORDOC 전용 profile, 환경변수, 입력 매핑과 제품 기본값만 제거한다.
7. API 사용량 정책은 최종 PoC 범위에 포함하되 Core 전환과 분리된 Phase에서 구현한다.

### 문서 계층의 확정 책임

```text
Markdown Revision
  = 프로젝트 문서의 의미 내용과 불변 이력

ReportDocument
  = 제목·절·문단·목록·표·근거를 표현하는 형식 독립 중간 계약

Template MCP / TemplateSchema
  = 고정 문구·의미 슬롯·스타일·배치 같은 표현 규칙

document.report-hwpx
  = ReportDocument와 선택 Template을 실제 HWPX 바이트로 렌더링

document.hwpx
  = HWPX 구조 분석, 검증, 안전한 patch와 파일·세션 처리

document.rhwp
  = 정상 HWP/HWPX의 사용자 편집과 Windows 네이티브 자동화
```

Capability ID는 구현 전에 기존 Registry와 계약을 다시 대조한다. 현재
`document.hwpx.finalize`는 `integration.kordoc` 전용이고, `document.hwpx.render`는 형식 어댑터
목록에만 노출돼 정식 설치 Capability로 확정되지 않았다. 중복 ID를 새로 만들지 않으며, 기존 의미와
충돌이 없으면 `document.hwpx.render`를 범용 렌더 계약으로 정식화하고
`document.hwpx.finalize`는 과거 KORDOC 호환 이력으로만 남기는 것을 우선안으로 한다.

### Phase 상태

상태 표기: `[ ] 미착수`, `[-] 진행 중`, `[x] 완료`, `[!] 차단`.

| Phase | 상태 | 목표 |
|---|---|---|
| 0 | [x] | 0.31.2 기준, 온라인 backup, 운영 DB 원자 교체·롤백 가능 실복원, 격리 브라우저 baseline 완료 |
| 1 | [x] | ReportDocument·내장 HWPX Renderer 계약과 실제 HWPX 양식 3종 구조·매핑 검증 완료 |
| 2 | [!] | KORDOC 없는 단위·Firefox E2E와 renderer 실패 격리 완료. Windows 한컴오피스가 없는 현재 환경에서 네이티브 왕복 실행만 차단 |
| 3 | [x] | 전용 자동 선택·seed·UI·profile/runtime 제거, DB 이력 보존형 retirement 완료 |
| 4 | [-] | Intent 1.0, Context Assembler·Task Compiler·Resolver 모듈/계약 분리 완료, keyword fallback 축소 잔여 |
| 5 | [-] | credential hash·원자 예약·token/비용·실패 정산·운영 UI 완료, workflow/step·fallback 연결 잔여 |
| 6 | [-] | 154개 회귀·Firefox 스모크 14종·README 현행화 완료, Windows RHWP·dead code 정리 잔여 |

### Phase 0 — 0.31.2 기준점 고정

- [x] 현재 미커밋 작업을 삭제·reset·checkout하지 않고 PoC 6 변경 범위와 기준 상태를 보존했다.
- [x] 실제 README·bootstrap·서버 버전이 0.31.2로 일치하는지 확인했다.
- [x] 단위·계약·통합 154개와 Store·Builder·Data MCP·Project Workbench를 포함한 Firefox 스모크 14종 baseline을 기록했다.
- [x] 운영 DB 온라인 backup을 만든 뒤 서비스 정지 상태에서 확인 경로·무결성·논리 digest를 검증하고 원자 교체하는 실복원 훈련을 수행했다. 54개 테이블·3,137행, RPO 0초, 2.90초이며 원본과 WAL/SHM을 별도 보존했다.
- [x] 일반·예산 보고서, Markdown 표, 중첩 목록, 다중 문단, title/body 슬롯과 RHWP 편집을
  포함하는 synthetic golden fixture를 고정한다.
- [x] KORDOC 비설치 내장 renderer와 제품 독립 Streamable HTTP/승인 stdio 프로필 계약을 각각 테스트한다.

완료 조건: 기존 작업을 잃지 않고 이후 변경을 비교할 수 있으며, 외부 네트워크나 유료 모델 없이
반복 가능한 기준 테스트와 fixture가 존재한다.

### Phase 1 — 문서 계약 및 내장 HWPX 경로 정석화

- [x] 기존 ReportDocument, TemplateSchema, render-map, HWPX adapter 계약을 인벤토리화했다.
- [x] Markdown↔ReportDocument 정규화 책임과 제목·중첩 목록·표·근거·Fact snapshot 구조를 고정했다.
- [x] `document.report-hwpx`, `document.hwpx`, `document.rhwp`의 입출력 Schema와 책임을 분리했다.
- [x] 범용 `document.hwpx.render` Capability와 `document.report-hwpx@0.1.0` 구현을 확정했다.
- [x] 내장 renderer를 Store/Capability Registry의 자동 설치 고정 버전 구현체로 등록했다.
- [x] 기존 Artifact 계보에 source MD, Template·renderer 버전, SHA-256과 생성 시각을 기록한다.
- [x] Template MCP가 내용·사실을 생성하지 않고 표현 규칙만 적용하는지 계약 테스트로 검증했다.
- [x] 저장소 `form-002.hwpx`와 운영 Store 게시 양식 2개 버전을 읽기 전용으로 검사하여 3종 모두 구조 바인딩, 품질, mapping/render-map coverage 100%를 확인했다.

완료 조건: Planner가 제품명이 아닌 render Capability를 요구할 수 있고, 내장 renderer가 golden
fixture를 유효한 HWPX로 만들며 표·목록·제목·의미 슬롯 재파싱 검증을 통과한다.

### Phase 2 — KORDOC 없는 E2E 검증

- [x] KORDOC 자동 후처리를 기본 경로에서 제거하고 비설치 DB 검증을 추가했다.
- [x] 일반 보고서 `요청 → 근거/LLM → MD revision → ReportDocument → HWPX → RHWP`를 통합 테스트로 검증했다.
- [x] 예산 질의 `org.mcp → RAG → 인용 답변`을 통합 테스트와 PDF Data MCP Firefox E2E로 검증했다.
- [x] 예산 보고서 `org.mcp → 근거 종합 → MD → HWPX → RHWP`를 통합 테스트와 Firefox E2E로 검증했다.
- [x] `범정부AI 공통기반`처럼 한글·영문 약어가 붙거나 띄어 쓰인 질의도 같은 업무 주제로 정규화하고, `관련된·지적·사항` 등 일반 요청어가 근거를 오염시키지 않도록 회귀 검증했다.
- [x] HWP/HWPX/RHWP 요청을 내용 지시가 아닌 산출 형식으로 분리하고, 사용법이 Markdown·HWPX 본문에 유입되지 않으며 근거형 답변에서도 RHWP 편집으로 연결되는지 Firefox E2E로 검증했다.
- [!] Template title/body, 예산 표, 다운로드·내장 RHWP 세션은 계약·Firefox에서 통과했다. Windows 전용 acceptance runner까지 구현했으나 현재 호스트에 Windows·한컴오피스·COM이 없어 실제 왕복 실행 증적은 만들 수 없다.
- [x] MD save→stale, HWPX save→diverged, 명시적 역반영→새 revision, 동시 수정→conflict를 검증했다.
- [x] HWPX 생성 실패가 검색 결과·대화 답변·저장된 Markdown을 실패시키지 않도록 격리한다.

완료 조건: KORDOC 프로세스와 npm 설치 없이 일반·예산 보고서 E2E가 통과하고 탭 이동만으로
재렌더링·revision 생성·해시 변경이 발생하지 않으며 RHWP·예산·Template MCP 회귀가 없다.

2026-09-04 서버·브라우저 범위 수행 결과는
[`PHASE2_ACCEPTANCE_2026-09-04.md`](PHASE2_ACCEPTANCE_2026-09-04.md)에 기록했다. Golden Workflow
58개 검사, 전체 회귀 154개, 실제 양식 Golden Set 3종, 격리 Firefox 14종이 통과했으며 실행 중
KORDOC/npm 프로세스는 없었다. Windows 한컴오피스·RHWP 브리지 검증은 환경 제약으로 미수행이므로
Phase 2 전체 상태는 외부환경 차단으로 표시한다. `scripts/windows_rhwp_acceptance.py`는 일반·예산
HWPX의 열기→텍스트/표 확인→HWPX 저장→재열기→PDF 내보내기와 해시 증적 생성을 강제한다.

### Phase 3 — KORDOC 점진 퇴역

- [x] Planner와 동적 binding의 `integration.kordoc` 자동 선택을 제거했다.
- [x] HWPX 어댑터 목록과 renderer metadata 기본값을 `document.report-hwpx`로 교체했다.
- [x] KORDOC seed·자동 설치와 `generate_document` 자동 mapping을 제거했다.
- [x] KORDOC built-in profile과 catalog 예시를 제거하고 기존 활성 installation은 idempotent하게 retired 처리한다.
- [x] `KORDOC_ROOT`, `KORDOC_OFFLINE`, `kordoc@4.7.3` 전용 처리를 제거하고 범용 문서 어댑터 계약만 유지한다.
- [x] UI의 KODAK 예시·기본 tool/profile·연결 문구·임의 renderer fallback을 제거한다.
- [x] DB 호환 migration으로 installation을 retired 상태로 전환하고 신규 선택을 차단한다.
- [x] 과거 package/version, 설치·감사 이력과 Artifact renderer provenance는 변경하지 않고 보존했다.
- [x] 범용 JSON-RPC 교환기와 외부 MCP Registry/Builder를 제품 독립 profile 계약으로 유지했다.
- [x] 제품 독립 외부 MCP 테스트로 교체하고 추적 중이던 `vendor/kordoc-runtime`과 전용 npm 설치 문서를 삭제한다.

완료 조건: 신규 Plan·실행·readiness·UI에서 KODAK/KORDOC가 기본 선택되지 않고, 과거 provenance와
범용 stdio/Streamable HTTP 외부 MCP 테스트는 유지된다.

2026-09-04 퇴역 패키지의 Store 숨김과 설치 미리보기·설치·롤백·수정 API 410 차단을 추가하고,
legacy migration 2회 재실행 시 퇴역 이력이 중복되지 않으며 패키지·Artifact provenance가 보존됨을
검증했다. 전용 vendor runtime 43MB를 제거했고 전체 회귀 154개와 Store·Builder Firefox 검사를
통과했다. 상세 결과는 [`PHASE3_ACCEPTANCE_2026-09-04.md`](PHASE3_ACCEPTANCE_2026-09-04.md)에 기록했다.

### Phase 4 — Core Orchestration 정석화

- [-] Context Assembler를 독립 모듈/Schema로 분리해 프로젝트·문서·첨부·Fact·등급·마스킹 문맥을 조립한다. 대화·선택·Evidence 정규화 확대는 남았다.
- [x] Intent Analysis MCP는 `intent-analysis/1.0`으로 목적·작업 유형·산출물·제약·데이터·Capability 요구조건만 구조화한다.
- [x] Task Compiler가 Step 순서, 의존성, runtime, 권한과 고정 packageRef를 독립 계약으로 구성한다.
- [-] Capability Resolver를 독립 모듈/Schema로 분리해 package/version과 선택 이유를 고정한다. 기존 keyword fallback 제거와 품질·비용·지연 점수 통합은 남았다.
- [x] Model Router는 모델이 필요한 Step별로 품질·민감도·비용·지연 정책을 적용한다.
- [x] 실행계획에 선택 이유, 데이터 범위, 변경 내용, 외부 전송, 모델, 권한과 산출물을 표시한다.
- [x] 계획 범위가 바뀌면 재승인하고 승인된 Workflow만 실행·체크포인트·재시도·감사를 남긴다.
- [-] 기존 Plan/Execution API와 DB 호환은 유지한다. 큰 `backend.py`의 물리 모듈 분리는 남았다.

완료 조건: Intent가 거대 Planner가 되지 않고 Planner가 vendor를 하드코딩하지 않으며,
계획·승인·실행·감사만으로 호출과 산출물 계보를 재현할 수 있다.

### Phase 5 — API Usage Policy

- [x] 대화형 UI actor와 `AIWORKS_RUNTIME_IDENTITY` 기반 자동 API credential identity를 분리했다.
- [-] credential 원문 대신 SHA-256 ID, principal·organization·scope·상태·만료 계약을 저장한다. 실행별 project scope 연결은 남았다.
- [-] provider/model 단가·통화·적용 시점 테이블과 환경 단가표를 제공한다. 호출별 가격 snapshot 세분화는 남았다.
- [-] provider/model별 성공·실패 호출의 token과 예상/실제 비용을 ledger에 기록한다. workflow/step 연결은 남았다.
- [-] credential별 RPM·월 token·월 비용 한도를 호출 전에 검사한다. 사용자·프로젝트·조직 합산 정책은 남았다.
- [x] 호출 전 예상 token/cost를 `BEGIN IMMEDIATE`로 원자 예약하고 호출 후 실제 사용량으로 성공/실패 정산한다.
- [-] 실패·timeout을 예약과 event에 기록한다. fallback/retry attempt와 복수 API Key scope 합산은 남았다.
- [x] `GET /operations/model-usage`와 설정 화면의 요청·실패·token·비용·예약 조회를 제공한다.

완료 조건: 동시 요청도 한도를 우회하지 못하고 실제 provider usage가 workflow/step까지 추적되며,
대화형 UI 정책과 자동 API 정책이 분리된다.

### Phase 6 — 전체 회귀, Cleanup과 Acceptance

- [x] 프로젝트 재진입의 마지막 화면·문서·탭·대화·분할 비율과 반복 탭 격리를 단위·통합·Firefox로 검증했다.
- [x] Template MCP 등록·수정·삭제·설치·사용 안내·양식 콤보와 Builder 5단계 시각 매뉴얼을 계약·Firefox 실조작으로 검증했다.
- [-] 일반 질의·보고서와 예산 질의·보고서 통합·Firefox 테스트를 검증했다. 실제 Solar 공급자 품질·timeout 장기 시험은 남았다.
- [!] MD/HWPX 상태 전이와 RHWP Web, readiness, backup/import는 단위·통합·Firefox에서 검증했다. 실 Windows RHWP만 외부환경 차단이다.
- [ ] 실행·테스트·public contract·migration/backup에 필요 없는 코드만 dead code로 제거한다.
- [x] 감사 이벤트를 삭제하지 않는 fixture 정리와 승인·온라인 백업·복구 이벤트를 강제하는 체인 복구 도구를 회귀 테스트로 고정했다.
- [x] 기존 개발 DB의 감사 체인 4개 불일치를 복구하고 1,349개 이벤트 전체 무결성과 readiness 실패 0을 확인했다.
- [x] demo 계획 4건과 고아 `project-default` 후보 메타정보 9건을 격리 DB에서 선검증한 뒤 백업·정리하고 실제 프로젝트와 예산 MCP 보존을 확인했다.
- [x] README를 실제 내장 renderer·환경변수·사용량 정책·154개 테스트·14종 Firefox 결과와 업무 MCP 실증 1~4에 맞게 갱신했다.

완료 조건: 전체 단위·계약·통합·브라우저 테스트와 KORDOC 제거 회귀가 통과하고 readiness failure가
없으며, 운영 DB에 demo seed가 생성되지 않고 미검증 기능을 완료로 표시하지 않는다.

### 변경 안전 원칙

- 기존 사용자 프로젝트, Markdown revision, HWPX, 최종 산출물, DB와 감사 데이터를 삭제하지 않는다.
- 과거 KORDOC provenance를 일괄 치환하거나 지우지 않는다.
- 기존 migration을 수정하지 않고 필요한 경우 idempotent 신규 migration을 추가한다.
- KORDOC runtime 삭제는 Phase 2 대체 E2E가 통과한 뒤에만 수행한다.
- KORDOC 제거를 이유로 범용 외부 MCP 실행 계층을 삭제하지 않는다.
- 테스트를 삭제해 통과시키지 않고 제품 독립 계약 테스트로 대체한다.
- 외부 네트워크나 유료 모델 호출 없이도 기본 회귀를 수행할 수 있어야 한다.
- unsupported 기능과 실패한 모델 호출을 성공으로 표시하지 않는다.


## 1. 제품 정의

AIWorks는 특정 업무를 미리 구현한 자동화 서비스가 아니다.

AIWorks는 프로젝트 안에 원천자료, 대화, 결정, 메타정보와 산출물의 계보를 지속적으로 축적하고,
사용자의 새로운 요청마다 필요한 Capability를 해석하여 적합한 MCP를 동적으로 로딩·조합하는
확장형 업무 운영 플랫폼이다. 사용자는 프롬프트형, 조합형 또는 코드형 MCP를 손쉽게 만들고
개인·프로젝트·조직·공개 범위로 공유하여 플랫폼의 기능을 계속 확장할 수 있어야 한다.

핵심 순환은 다음과 같다.

```text
사용자 요청
  → 프로젝트 Markdown 원본들과 확정 Fact 문맥 조립
  → 목표·산출물·필요 Capability 계획
  → MCP 탐색·정책 검사·승인·버전 고정
  → LLM Markdown 생성·갱신과 불변 revision 저장
  → 메타정보 후보 추출·충돌 처리
  → ReportDocument 구조화 → 선택적 양식 MCP 적용
  → 범용 형식 Renderer로 HWPX/제3자 파생 산출물 생성
  → RHWP/HWPX 수정 시 사용자 명시 동작으로 Markdown 새 revision 생성
  → 다음 파생 산출물에서 재사용
```

영수증 처리, 사업계획서, 예산요구서 등은 이 구조를 검증하기 위한 예시 시나리오일 뿐
Platform Core의 데이터 모델이나 실행 계획에 업무명으로 고정하지 않는다.

## 2. 변경하지 않을 제품 원칙

1. 모든 대화, 자료, 실행과 산출물은 프로젝트에 속한다.
2. 프로젝트의 확정 메타정보가 재사용 가능한 기준 데이터이고 문서는 그 시점의 스냅샷이다.
3. 프로젝트 문서 내용의 단일 원본은 Markdown 불변 version이며 HWPX·PDF·제3자 파일은 파생 산출물이다.
4. 모든 산출물은 입력 Markdown version, 메타정보, 양식 MCP, 형식 어댑터, 모델과 실행 기록으로 재현할 수 있어야 한다.
5. Core는 MCP 이름이 아니라 Capability와 입출력 계약으로 계획한다.
6. MCP는 실행 시점에 탐색·선택하며 실제 사용 버전은 실행 기록에 고정한다.
7. 권한은 기본 거부하고 프로젝트 정책과 데이터 등급 안에서만 자동 로딩한다.
8. 외부 전송, 파괴적 변경과 제출·발송 같은 확정 행위는 명시적으로 구분한다.
9. 메타정보 충돌은 임의로 덮어쓰지 않고 시점, 출처와 사용자 결정을 보존한다.
10. MCP 제작·검증·공유는 플랫폼의 부가기능이 아니라 핵심 제품 흐름이다.
11. 특정 업무는 MCP 또는 재사용 가능한 업무 레시피로 확장한다.

## 3. 현재 구조 진단과 전환 방향

| 현재 구조 | 유지할 자산 | 바꿀 부분 | 목표 구조 |
|---|---|---|---|
| `workspace_documents` 중심의 평면 문서 목록 | 문서 저장·revision 충돌 방지 | 프로젝트 귀속과 문서 외 산출물 지원 | `projects` 아래 `artifacts`와 `artifact_versions` |
| `document_versions` 중심 버전 | 원본·결과 해시와 다운로드 | 입력 스냅샷과 파생 관계 추가 | 범용 산출물 버전·계보 그래프 |
| `knowledge_nodes/sources/edges` | 출처, 기준일, 신뢰도, 관계 | 프로젝트 경계·값 상태·충돌 결정 부족 | 프로젝트 Fact Registry와 지식 그래프 읽기 모델 |
| `plans`의 고정 `_plan_steps` | 계획·승인·감사 기본 흐름 | 예산 키워드 및 고정 MCP 제거 | 목표를 Capability DAG로 만드는 동적 Planner |
| `executions`의 계획 단위 결과 | 멱등키·상태·오류 기록 | 단계별 체크포인트·입출력·재시도 부족 | `workflow_runs`와 `step_runs` |
| 일회용 `approvals` | 서명·만료·소비 처리 | 프로젝트 승인 범위와 재사용 정책 부족 | 승인 토큰 + Project Grant + 실행별 확인 |
| `mcp_packages/installations` | 서명·해시·버전 고정·롤백 | Capability 색인과 호환성·품질 정보 부족 | Capability Registry와 Resolver |
| `mcp_drafts` 제작기 | 자연어 초안·참조자료·검증·게시 | 프롬프트형/조합형 제작과 평가 흐름 강화 | MCP Studio와 Recipe Studio |
| `native_document_sessions` | RHWP 선택 편집과 원자적 변경 | 프로젝트·산출물·버전 연결 | 범용 Artifact Editing Session |
| `WORKFLOW_PRESETS` | 샘플 흐름과 로컬 파일 검사 | 업무 프리셋을 Core 라우팅 기준으로 사용하지 않음 | 선택형 Recipe/Template 패키지 |
| `web/app.js` 단일 전역 상태 | 현재 화면과 편집기 통합 | 프로젝트·실행·산출물 상태가 혼재 | 프로젝트 문맥 기준 모듈형 상태와 화면 |

### 호환성 원칙

- 기존 테이블과 API를 즉시 제거하지 않는다.
- 신규 프로젝트 모델을 먼저 추가하고 기존 문서·계획을 호환 어댑터로 연결한다.
- 데이터 마이그레이션과 회귀 테스트가 통과한 뒤 기존 경로를 단계적으로 deprecated 처리한다.
- 현재 예산요청서 수용성 테스트는 제품 모델이 아니라 범용 기능의 회귀 시나리오로 유지한다.
- `backend.py`와 `web/app.js` 분리는 새 계약이 안정된 단계부터 점진적으로 수행한다.

## 4. 목표 도메인 모델

```text
Project
 ├─ Conversation / Decision
 ├─ Source Asset
 ├─ Project Fact ─ Fact Value ─ Evidence / Conflict / Decision
 ├─ Artifact ─ Artifact Version
 │              └─ Artifact Relation (derived_from, references, summarizes...)
 ├─ Workflow Run ─ Step Run ─ Capability Binding ─ MCP Version
 ├─ Project Policy ─ Permission Grant / Approval
 └─ Audit Event
```

### 4.1 Project

프로젝트는 모든 업무 문맥의 최상위 경계다. 이름, 목적, 데이터 등급, 구성원, 정책, 기본 모델,
허용 MCP 범위와 현재 상태를 가진다. 최초 채팅은 기존 프로젝트 선택 또는 새 프로젝트 생성을
거친 뒤 시작하며 모든 후속 요청에 `project_id`가 포함되어야 한다.

### 4.2 Project Fact

프로젝트의 재사용 가능한 기준 데이터다. 각 값은 다음 속성을 가진다.

- 의미 키, 대상 엔터티, 데이터 타입, 단위와 값
- 유효시간 `valid_from/valid_to`
- 기록시간 `recorded_at/superseded_at`
- 출처 산출물 버전과 locator
- 신뢰도와 `candidate/confirmed/conflicted/rejected` 상태
- 확인한 사용자와 결정 사유

같은 시점의 상충 값은 Conflict로 등록하고, 서로 다른 시점의 값은 시간 변화로 보존한다.
산출물은 생성 당시 참조한 Fact Value ID를 저장한다.

### 4.3 Artifact

문서만이 아니라 파일, 데이터셋, 표, 이미지, 분석 결과와 외부 시스템 레코드를 하나의 산출물
개념으로 관리한다. 버전은 불변이며 최신 버전 포인터만 이동한다.

필수 관계는 `derived_from`, `references`, `summarizes`, `transforms`, `validates`,
`supersedes`, `conflicts_with`다.

### 4.4 Workflow Run

대화에서 생성된 실행 계획의 영속 인스턴스다. Step Run별 입력·출력·체크포인트·상태·오류·재시도,
선택된 MCP와 모델 버전을 저장한다. 중단 후 재개와 같은 입력에 대한 멱등 실행을 지원한다.

### 4.5 Capability와 MCP Binding

Planner는 `document.generate`, `data.query`, `artifact.save` 같은 Capability를 요구하고,
Resolver가 실행 시점에 설치 상태, 서명, 입출력 스키마, 권한, 데이터 등급, 런타임 가용성,
품질, 비용, 지연시간과 프로젝트 선호도를 비교해 실제 MCP 버전을 연결한다.

## 5. MCP vNext 계약

기존 `mcp-manifest.schema.json`을 호환 확장하여 다음 내용을 선언한다.

- 제공 Capability와 버전
- 각 도구의 입력·출력 JSON Schema 및 Artifact 유형
- 읽기·쓰기·외부 전송·모델 호출·부작용 권한
- 처리 가능한 데이터 등급과 데이터 보존 정책
- 로컬·원격·하이브리드 런타임 요구조건
- 비용·예상 지연시간·리소스 한도
- 정확히 고정된 의존 MCP와 플랫폼 호환 범위
- 테스트, 평가 결과와 품질 지표
- 제작자, 서명, 배포 범위와 소스 포함 여부
- 선택적 UI contribution

Resolver의 하드 필터는 서명, 호환 버전, Schema 연결 가능성, 권한, 데이터 등급과 런타임
가용성이다. 하드 필터를 통과한 후보만 사용자 선호, 품질, 비용과 속도로 순위를 정한다.
적합한 MCP가 없으면 스토어 검색, MCP Studio 생성 또는 수동 처리 중 하나를 제안한다.

## 6. 자동 로딩과 승인 수준

| 수준 | 조건 | 동작 |
|---|---|---|
| 자동 | 서명·버전 고정, 프로젝트 Grant 범위, 허용 데이터 등급, 비파괴적 작업 | 계획에 표시하고 자동 로딩 |
| 프로젝트 1회 승인 | 새 읽기/쓰기 범위 또는 승인된 외부 서비스 | 권한 차이를 설명한 뒤 프로젝트 Grant 저장 |
| 실행별 승인 | 민감정보 외부 전송, 새로운 목적의 네트워크·DB 쓰기 | 해당 Step 직전 승인 |
| 최종 확인 | 제출, 발송, 게시, 삭제, 결재, 확정 처리 | MCP 승인과 별도로 사용자 최종 확인 |

MCP 설치 승인과 실제 데이터 접근 승인을 분리한다. 공개 MCP라도 자동 신뢰하지 않으며,
업데이트로 권한이나 데이터 처리가 바뀌면 기존 Grant를 재사용하지 않는다.

## 7. 단계별 구현 계획

상태 표기: `[ ] 미착수`, `[-] 진행 중`, `[x] 완료`, `[!] 차단`. 단계 완료는 코드 작성뿐 아니라
계약, 마이그레이션, 자동 테스트와 완료 기준을 모두 만족한 경우에만 표시한다.

### 17.23단계 — 프로젝트 문서 생명주기 안정화

목표: 저장소에 존재하는 프로젝트·MD·파생 파일 모델과 사용자가 체감하는 실행·편집 흐름을 일치시킨다.

- [x] 프로젝트별 마지막 문서, 탭, 화면, 대화와 직전 답변 영속 상태 계약
- [x] 기존 프로젝트 선택 시 환영 화면을 거치지 않고 마지막 작업공간 복원
- [x] MD 저장 시 파생 HWPX 자동 생성 제거, `stale` 상태만 기록
- [x] HWPX 탭 클릭 시 자동 렌더 제거, 저장된 파생 파일만 로딩
- [x] 명시적 `MD → HWPX 반영`, `HWPX → MD 반영` UI와 API 경계
- [x] HWPX 편집 저장은 `diverged` 파생 상태로 보류하고 MD revision은 사용자 승격 시에만 생성
- [x] 보고서 질문·연도·주제·지적사항·대안·향후계획·근거 번호 품질 하네스와 1회 자동 보완
- [x] 운영 DB의 데모 시드 기본 비활성화, 기존 테스트 fixture 백업 정리와 브라우저 검증 자기정리
- [x] revision·artifact SHA 기반 문서별 편집기 DOM/세션 캐시로 탭 복귀 시 재마운트 제거
- [x] exact-duplicate MD 비파괴 보관·복원 UI와 메타정보 후보 일괄 확정·거부
- [x] Workflow/Step Run별 실제 입출력·오류·체크포인트와 새 승인 기반 Retry Plan 저장

완료 기준:

- 탭 이동만으로 MD/HWPX revision과 해시가 바뀌지 않는다.
- MD와 HWPX의 내용 승격은 방향별 명시적 버튼으로만 일어난다.
- 프로젝트 재진입 시 마지막 문서·탭·대화가 복원된다.
- 질문과 다른 주제·연도·필수 항목의 보고서는 확정 MD 저장 전에 차단 또는 한 번 보완된다.

### 17.24단계 — 운영 확장 P0와 계보·충돌 기반

- [x] 양식 HWPX 실제 문단의 제목·본문·목록 prototype 슬롯 보정과 실렌더링 재검증
- [x] Workflow Run과 context/execute/persist Step Run의 축약 입출력·오류·체크포인트 영속화
- [x] 실패 Run에서 기존 토큰을 재사용하지 않는 새 Plan·새 승인 기반 Retry Plan
- [x] MD/HWPX 동시 편집 충돌 저장, 양쪽 미리보기, 현재 MD 유지/HWPX 채택 명시 해결
- [x] Markdown revision·HWPX·양식·충돌의 재현 관계 그래프
- [x] Fact 후보의 중복·시간 변화·오기 검토 분류와 superseded 이력 보존
- [x] 운영 브라우저 프로젝트/양식 Builder 스모크 및 백엔드 99개 회귀 테스트

남은 확장 범위는 프로젝트 멤버십·Grant, 범용 Artifact 저장소, Step 내부 중단 재개,
Capability 품질/비용/지연시간 랭킹, TemplateSchema 메타·결재란·병합표 보정과 제3자 포맷이다.


### 18단계 — 프로젝트 컨텍스트 커널

목표: 모든 기존 기능이 프로젝트 경계 안에서 동작할 수 있는 최소 기반을 만든다.

- [x] 프로젝트·프로젝트 정책·대화·결정 JSON Schema 계약 정의
- [x] `projects`, `project_members`, `project_conversations`, `project_conversation_messages`, `project_decisions` 테이블 추가
- [x] 프로젝트 생성·목록·조회·수정·보관·복원 API와 보관 상태 전용 완전 삭제 API 추가
- [x] 기존 문서·계획·편집 세션과 대화·결정에 `project_id` 관계 연결
- [x] 기존 데이터용 기본 Legacy Project 마이그레이션
- [x] 최초 작업 전 프로젝트 선택 강제와 새 프로젝트 생성
- [x] 프론트 전역 `activeProjectId`와 마지막 문서·탭·대화 복원
- [x] 프로젝트 간 데이터 접근 차단·portable backup 1.2 테스트

완료 기준:

- 모든 새 대화, 문서, 계획과 편집 세션에 `project_id`가 존재한다.
- 기존 데이터는 손실 없이 Legacy Project에서 열린다.
- 프로젝트 전환 시 문서·채팅·MCP 권한이 섞이지 않는다.

의존성: 1~17단계 기준선
후속 영향: 19~27단계 전체

### 19단계 — 범용 산출물과 계보

목표: 평면 문서 목록을 모든 형식의 산출물과 파생 관계를 관리하는 구조로 확장한다.

- [ ] `artifact.schema.json`, `artifact-version.schema.json`, `artifact-relation.schema.json` 정의
- [ ] `artifacts`, `artifact_versions`, `artifact_relations`, `artifact_evidence` 테이블 추가
- [ ] 문서·파일·데이터셋·외부 레코드 Artifact 유형 지원
- [ ] 기존 `workspace_documents`, `document_versions` 호환 어댑터와 마이그레이션
- [ ] 버전별 content hash, 입력 스냅샷, 생성 실행과 제작자 기록
- [ ] 파생·참조·요약·변환·대체·검증·충돌 관계 API
- [ ] 프로젝트 산출물 탐색기와 계보 상세 화면
- [ ] 원본 보존, 버전 불변성과 계보 순환 방지 테스트

완료 기준:

- 임의의 산출물에서 원천자료와 파생 산출물을 양방향 추적할 수 있다.
- 동일 입력과 실행 기록으로 생성 조건을 재현할 수 있다.
- 기존 RHWP/HWPX 저장·재열기·다운로드 흐름이 유지된다.

의존성: 18단계

### 20단계 — 프로젝트 Fact Registry와 충돌 관리

목표: 문서에서 분리된 프로젝트 기준정보를 시간·출처·신뢰도와 함께 관리한다.

- [ ] `project-fact.schema.json`, `fact-value.schema.json`, `fact-conflict.schema.json` 정의
- [ ] `project_facts`, `fact_values`, `fact_evidence`, `fact_conflicts`, `fact_decisions` 테이블 추가
- [ ] 기존 `common-data` 및 지식 노드를 프로젝트 Fact로 호환 조회
- [ ] Artifact 저장 후 메타정보 후보 추출 파이프라인
- [ ] 후보 확인·거부·병합·새 시점 등록 UI
- [ ] 같은 시점의 상충 값과 다른 시점의 변경을 구분
- [ ] 산출물 버전에 사용한 Fact Value 스냅샷 연결
- [ ] 값 변경 시 영향 산출물과 재생성 후보 표시

완료 기준:

- 모든 확정값은 근거 위치와 시간 정보를 가진다.
- 충돌값을 자동 덮어쓰지 않고 사용자 결정이 감사 로그에 남는다.
- 과거 산출물이 당시 사용한 값으로 재현된다.

의존성: 18~19단계

### 21단계 — Capability 계약과 Registry

목표: MCP 이름에 고정되지 않는 검색·선택 가능한 기능 레지스트리를 만든다.

- [x] 피드백 슬라이스용 Capability ID·버전·권한·실행 Adapter 계약 정의
- [ ] MCP Manifest vNext와 기존 Manifest 호환 변환기 구현
- [x] Builder 게시 패키지의 `mcp_capabilities` 색인과 기존 패키지 백필
- [ ] `mcp_tools`, `mcp_evaluations`, `mcp_compatibility` 색인 추가
- [ ] Artifact 유형과 JSON Schema 간 연결 가능성 검사
- [x] 활성 설치·고정 버전·패키지 서명·권한 기반 후보 하드 필터
- [x] 품질·성공률·비용·지연시간·프로젝트 선호 기반 순위 정책
- [x] 버전 고정, 서명·권한·설치 상태 검사와 실행 전 계획 미리보기
- [x] Capability Registry 조회·Intent Resolver API
- [x] 후보 선택 이유·점수·제외 이유를 표시하는 비교·관리 화면

완료 기준:

- 동일 Capability를 제공하는 복수 MCP를 검색·비교할 수 있다.
- 호환되지 않거나 과도한 권한의 MCP는 실행 전에 제외된다.
- 기존 설치·업데이트·롤백과 서명 검증이 유지된다.

의존성: 18단계

### 22단계 — 동적 Planner와 영속 Workflow Runtime

목표: 고정 `_plan_steps`를 프로젝트 문맥 기반 Capability DAG와 단계 실행기로 대체한다.

- [x] `workflow-run.schema.json`에서 Workflow와 Step Run 계약 정의
- [x] `capability-binding.schema.json` 정의
- [ ] 요청에서 목표, 예상 산출물, 입력과 필요 Capability 추출
- [x] 프로젝트 Fact·Artifact·Markdown·대화 우선순위를 조립하는 Context Builder
- [x] Capability DAG 1.0 생성과 입출력 Schema 연결 검증
- [x] 기존 Plan 호환 경로에서 Resolver 기반 MCP 선택·버전 고정 피드백 슬라이스
- [x] `workflow_runs`, `workflow_step_runs`, 실행 attempt와 capability binding 영속화
- [ ] 단계별 체크포인트, 멱등키, 재시도, 취소와 중단 후 재개
- [x] 기존 `plans/executions` 호환 API 유지와 Workflow Run 연결
- [ ] 계획 타임라인, 진행률, 대기 승인과 실패 복구 UI

완료 기준:

- 업무 키워드나 특정 MCP 이름 없이 요청별 계획이 생성된다.
- 서버 재시작 뒤 실패 Step부터 안전하게 재개할 수 있다.
- 각 Step의 입력·출력과 선택된 MCP 버전을 추적할 수 있다.

의존성: 18~21단계

### 23단계 — 프로젝트 권한·정책과 동적 MCP 로딩

목표: 사전 승인 MCP는 자동으로, 권한 변화가 있는 MCP는 필요한 시점에 승인받아 로딩한다.

- [x] `project-policy.schema.json`, `permission-grant.schema.json` 정의
- [x] `project_policies`, `permission_grants`, 일회성 승인 토큰 영속화
- [x] 설치 승인, 데이터 접근 승인과 최종 행위 확인 분리
- [ ] Manifest 권한 diff와 데이터 이동 경로 설명 생성
- [x] 자동·프로젝트 Grant·실행별 single-use lease·최종 확인 정책 엔진
- [ ] MCP 업데이트 시 권한 확대와 데이터 처리 변경 감지
- [x] Step 직전 JIT 승인 검사, 격리 실행, 성공 시 lease 1회 소비·만료 처리
- [ ] 승인 거부 시 대체 MCP·로컬 처리·수동 처리 재계획

완료 기준:

- 프로젝트 Grant 범위의 MCP는 추가 팝업 없이 자동 실행된다.
- 범위를 넘는 접근은 실제 실행 전에 차단된다.
- 사용자는 어떤 데이터가 어디로 전달되는지 승인 화면에서 확인한다.

의존성: 21~22단계

### 24단계 — 범용 파생 산출물과 문맥 편집

목표: 프로젝트 문맥으로 새 산출물을 만들고 선택 영역·커서 기준으로 MCP를 조합해 수정한다.

- [ ] 새 산출물 요청 시 참조 Artifact·Fact 선택과 자동 추천
- [ ] 산출물 유형에 맞는 생성기·템플릿·검증기·편집기 Capability 조합
- [ ] `replace-selection`, `insert-at-caret`, `expand`, `simplify`, `to-table` 등 편집 Operation 표준화
- [ ] 커서 anchor, 선택 영역, 주변 구조와 프로젝트 문맥 전달 계약
- [ ] 전체 문서 교체가 아닌 구조화 Patch 적용
- [ ] Diff 미리보기, 적용·취소·Undo와 편집 위치 유지
- [ ] 생성 즉시 Artifact Version·Relation·Fact Snapshot 저장
- [ ] RHWP, HWPX, Markdown, 코드 편집기의 공통 Editing Session 연결
- [x] Markdown에서 HWPX·DOCX·ODT·XLSX 작업본과 불변 최종 산출물 생성
- [x] 형식별 source-of-truth=false, 손실·fidelity·round-trip 지원 수준 계약과 Store 표시

완료 기준:

- 특정 보고서 유형에 종속되지 않고 프로젝트 자료로 파생 산출물을 생성한다.
- 적용 후 현재 문서·페이지·선택 문맥이 유지된다.
- 편집 결과의 근거와 사용 MCP가 산출물 계보에 남는다.

의존성: 19~23단계

### 25단계 — MCP Studio vNext

목표: 비개발자도 자연어와 예제로 안전한 MCP를 만들고 시험할 수 있게 한다.

- [x] 사용자 제작 프로필을 양식·처리·데이터·일반 도구 MCP로 분리
- [x] 파일 역할, 실행 지침, 유의사항, 처리 순서와 호출 예시를 Manifest 가이드로 패키징
- [x] TemplateSchema 1.2 필수·반복·조건·기본 슬롯과 최소 플랫폼·migration 계약
- [x] Render Map 1.2 표 셀 좌표·병합 span·셀 내부 문단·구조 지문과 매핑 coverage
- [x] 스캔 중심 HWPX 감지와 OCR Capability 미연결 시 명시적 제작 차단
- [x] Mapping Studio에서 section/조건 block/표 반복자 역할 저장과 실렌더링 품질 검사
- [ ] 실행 구현 방식을 프롬프트형·조합형·코드형 Runtime Adapter로 분리
- [ ] 자연어 설명에서 Capability, 도구, Schema와 권한 초안 생성
- [ ] 프로젝트 Artifact를 참조 예제로 선택하되 원본 포함 여부 분리
- [ ] 기존 MCP를 DAG로 연결하는 조합형 편집기
- [ ] 정상·경계·권한 거부·악성 입력 테스트 자동 생성
- [ ] 결과 비교, 사용자 평가와 회귀 평가 세트 관리
- [ ] 샌드박스에서 네트워크·파일·비밀정보 접근 검사
- [ ] 버전 변경 내역, 호환성, 서명과 게시 전 체크리스트
- [ ] 제작 중인 MCP를 현재 프로젝트에서 제한적으로 시험 실행

완료 기준:

- 자연어 설명과 최소 예제만으로 프롬프트형 MCP를 게시할 수 있다.
- 조합형 MCP가 하위 MCP의 권한 합집합과 버전을 정확히 선언한다.
- 검증 실패 MCP는 설치·공유할 수 없다.

의존성: 21~24단계

### 26단계 — MCP·업무 레시피 공유 생태계

목표: 기능과 조합 방식을 안전하게 검색·공유·재사용한다.

- [ ] 개인·프로젝트·조직·공개 배포 범위와 소유권 모델
- [ ] MCP와 Recipe를 별도 패키지 유형으로 관리
- [ ] Capability·산출물 유형·업무 태그·권한으로 검색
- [ ] 설치 전 권한·비용·외부 전송·의존성 미리보기
- [ ] 평가 결과, 사용 이력, 호환 버전과 제작자 신뢰 정보 표시
- [ ] 업데이트 채널, deprecated, 취약 버전 차단과 롤백
- [ ] 복제·수정·재게시 시 출처와 라이선스 계보 유지
- [ ] 조직 관리자의 허용목록·차단목록·의무 검증 정책

완료 기준:

- 다른 사용자가 공유한 MCP나 Recipe를 검색해 프로젝트에서 실행할 수 있다.
- 공유 범위와 라이선스, 원본 포함 정책이 저장·설치·실행 전 과정에서 유지된다.
- 문제가 있는 버전을 차단하고 영향 프로젝트를 조회할 수 있다.

의존성: 21, 23, 25단계

### 27단계 — 운영 안정화와 확장성 검증

목표: 다양한 업무와 다중 사용자 환경에서도 프로젝트 격리, 재현성과 운영 안정성을 보장한다.

- [ ] 프로젝트 RBAC와 조직 격리
- [ ] 대용량 Artifact 저장소와 메타데이터 DB 분리 준비
- [ ] Workflow 동시 실행, 큐, timeout, backpressure와 보상 처리
- [ ] MCP 실행 리소스 제한과 비밀정보 격리
- [x] 프로젝트 대화·결정·문서·Fact·자료 계보의 내보내기·가져오기·SHA-256 백업·복원
- [x] 비용·지연·성공률·품질·lease·산출물·충돌 지표, Prometheus text와 OTLP JSON
- [ ] 범용 수용성 시나리오 3개 이상 구성
- [x] 감사 해시 체인 변조 탐지, MCP 업데이트 권한 확대 차단과 stale context 실패 주입
- [ ] 운영 마이그레이션·롤백·외부 경보·실복구 runbook 문서화

완료 기준:

- 서로 다른 업무 시나리오가 Core 수정 없이 MCP/Recipe 추가만으로 동작한다.
- 프로젝트를 내보내고 복원해도 산출물 계보와 실행 재현 정보가 유지된다.
- 권한, 외부 전송, MCP 변조와 프로젝트 간 정보 누출 테스트를 통과한다.

의존성: 18~26단계

## 8. 단계 의존 관계와 권장 릴리스 묶음

```text
18 프로젝트 커널
 ├─ 19 산출물 계보 ─ 20 Fact Registry ─┐
 └─ 21 Capability Registry ─ 22 Planner ─ 23 정책·로딩
                                  └────────┬──────────┘
                                           24 파생·편집
                                             │
                                           25 MCP Studio
                                             │
                                           26 공유 생태계
                                             │
                                           27 운영 안정화
```

- Release A — Project Foundation: 18~20단계
- Release B — Dynamic Runtime: 21~23단계
- Release C — Derivation Workspace: 24단계
- Release D — Extensible Ecosystem: 25~26단계
- Release E — Production Readiness: 27단계

## 9. 현재 코드의 우선 변경 순서

1. `backend.py`의 기존 테이블을 삭제하지 않고 프로젝트·산출물 FK와 신규 테이블을 추가한다.
2. 신규 계약을 먼저 추가하고 테스트에서 Schema와 호환 변환을 고정한다.
3. `workspace_documents`와 `document_versions`를 신규 Artifact Service 뒤에서 호출하도록 감싼다.
4. `knowledge_*`를 직접 쓰는 흐름을 Fact 후보·근거 저장 흐름으로 전환한다.
5. `_plan_steps`는 즉시 삭제하지 않고 Dynamic Planner의 fallback adapter로 격리한다.
6. `mcp_packages` 게시 시 Capability 색인을 함께 생성한다.
7. 프론트는 프로젝트 선택과 `activeProjectId`부터 도입한 뒤 탐색기·채팅·편집기를 순차 연결한다.
8. 계약이 안정되면 `backend.py`를 project, artifact, fact, workflow, mcp 서비스 모듈로 분리한다.
9. `web/app.js`는 project-context, artifact-explorer, workflow-monitor, mcp-studio 모듈로 분리한다.
10. 기존 예산 시나리오는 범용 회귀 테스트로만 유지하고 새 코드에 업무명을 추가하지 않는다.

## 10. 최초 통합 검증 시나리오

특정 업무의 성공이 아니라 플랫폼 순환의 성공을 검증한다.

1. 새 프로젝트를 만들고 서로 다른 형식의 원천자료를 추가한다.
2. 자료에서 메타정보 후보를 추출하고 사용자가 확정한다.
3. 사용자가 산출물 유형을 자유롭게 요청한다.
4. Planner가 필요한 Capability를 만들고 Resolver가 MCP를 선택한다.
5. 사전 승인 MCP는 자동 로딩되고 새 권한만 사용자에게 요청된다.
6. 생성 결과가 새 Artifact Version과 파생 관계로 저장된다.
7. 산출물에서 새 메타정보 후보와 기존 값 충돌이 발견된다.
8. 사용자가 시간 변화 또는 오기를 결정한다.
9. 갱신된 프로젝트 문맥으로 다른 형식의 파생 산출물을 만든다.
10. 서버 재시작 후 프로젝트, 실행 단계, 승인, 계보와 편집 위치를 복원한다.
11. 필요한 Capability가 없을 때 MCP Studio에서 새 MCP를 만들고 제한 실행한다.
12. MCP를 공유한 뒤 다른 프로젝트에서 설치·실행하고 출처·버전을 추적한다.

## 11. 진행 관리 규칙

- 작업을 시작할 때 해당 항목을 `[ ]`에서 `[-]`로 바꾼다.
- 구현, 계약 테스트, 마이그레이션과 회귀 검증이 모두 끝났을 때만 `[x]`로 바꾼다.
- 단계 완료 시 문서 상단의 `현재 진행 단계`와 `최종 갱신`을 수정한다.
- 설계가 바뀌면 아래 결정 기록에 이유와 영향 단계를 남긴다.
- 새 기능은 어느 단계·Capability·Artifact·Project Fact에 속하는지 먼저 결정한다.
- 특정 업무 전용 코드가 필요하면 Core가 아니라 MCP 또는 Recipe에 둔다.
- 완료된 단계도 회귀가 발견되면 `[-]`로 되돌리고 사유를 결정 기록에 남긴다.

## 12. 결정 기록

| 날짜 | 결정 | 이유 | 영향 |
|---|---|---|---|
| 2026-08-12 | AIWorks를 프로젝트 중심 범용 업무 플랫폼으로 정의 | 특정 업무가 아니라 지속 문맥과 파생 산출물이 제품의 핵심 | 18단계 이후 전체 |
| 2026-08-12 | Core는 MCP가 아닌 Capability를 계획 | MCP를 실행 시점에 교체·추가하고 생태계를 확장하기 위함 | 21~26단계 |
| 2026-08-12 | 예산요청서는 예시·회귀 시나리오로만 유지 | 도메인 예시가 플랫폼 구조를 고정하지 않도록 함 | 기존 테스트, 22·27단계 |
| 2026-08-12 | 기존 데이터와 API는 호환 계층을 거쳐 점진 이전 | 현재 PoC 자산과 사용자 작업을 보존하기 위함 | 18~24단계 |
| 2026-08-14 | MCP Builder를 양식 전용이 아닌 단일 범용 제작 환경으로 정의 | 모든 기능을 사용자 제작·검증·공유로 확장하고 유형은 작성 편의를 위한 프로필로만 사용 | 21·25~26단계 |
| 2026-08-16 | 공개 stdio MCP는 임의 명령 대신 고정 버전 승인 프로필로 실행 | 사용자 입력이 프로세스 실행 경계가 되지 않게 하고 외부 MCP를 재사용 가능한 안전 어댑터로 확장 | 17.14·21·23·25~26단계 |
| 2026-08-16 | MCP별 운영값은 Manifest의 선택적 `configuration` 계약으로 선언 | Core 전용 설정 화면을 늘리지 않고 새 MCP도 Store의 공통 환경설정 UI와 검증·감사를 재사용하기 위함 | 17.16·21·25~26단계 |
| 2026-08-16 | LLM 출력은 Markdown으로 받고 Report Document에서 내용·Fact·표현을 분리 | 양식 전환 시 글머리표가 본문에 누적되는 문제를 막고 같은 프로젝트 값을 완전히 다른 양식에 재사용하기 위함 | 17.17·18·20·24~25단계 |
| 2026-08-16 | 프로젝트 문서 내용의 단일 원본은 Markdown version이고 HWPX 등은 파생 산출물로 정의 | 양식·파일 형식과 내용을 분리하고 여러 문서를 종합해 새 Markdown과 메타정보를 반복 재사용하기 위함 | 17.18·18~20·24~26단계 |
| 2026-08-16 | MD→HWPX와 HWPX→MD는 각각 명시적 반영 버튼으로만 승격하고 탭 이동은 저장·생성·변환을 수행하지 않음 | 파생 파일이 탭 이동 때마다 달라지는 현상을 제거하고 내용 원본 변경을 사용자가 통제하도록 함 | 17.23·19·24단계 |
| 2026-08-16 | “이 내용으로 새 보고서”는 직전 답변을 새 MD 원본으로 승격한 뒤 요청 양식을 적용 | 기존 RHWP가 없어도 대화 결과에서 파생 보고서를 만들고 현재 문서 전환과 새 문서 생성을 혼동하지 않도록 함 | 17.21·19·22·24단계 |
| 2026-08-16 | 모든 작업은 명시적으로 선택한 프로젝트에서만 시작하고 선택 시 전체 작업공간을 복원 | 대화·메타·MD·파생 파일이 기본 프로젝트나 다른 업무에 섞이지 않고 사용자가 현재 작업 문맥을 항상 확인하도록 함 | 17.22·18·20·22~24단계 |
| 2026-08-28 | 외부 모델 경계는 공통 개인정보 마스킹을 적용하고 MCP 업데이트는 권한 diff 해시 재승인을 요구 | 계획 승인과 실제 전송 사이의 정책 우회를 막기 위함 | 21·23·27단계 |
| 2026-08-28 | ODT는 의미 왕복, PDF는 Markdown→ODT→격리 LibreOffice 출력으로 제공 | 원본 MD와 파생 형식을 분리하면서 즉시 시험 가능한 공개 형식을 제공 | 19·24·27단계 |
| 2026-08-30 | 양식 MCP는 Store·Builder·완성 문서에서 동일한 실제 사용 안내 계약을 제공 | 사용자가 설치·호출·즉시 적용·수정의 차이를 화면 안에서 이해하고 선택 양식의 정확한 버전과 결과 경계를 확인하도록 함 | 21·24~26단계 |
| 2026-08-31 | 문서 파이프라인은 Markdown→ReportDocument→Template→범용 Renderer→RHWP로 분리 | 의미 원본·중간 구조·표현 규칙·파일 생성·편집의 책임 중복을 제거하고 제3자 형식으로 확장하기 위함 | 최종 보완 Phase 1~2·4 |
| 2026-08-31 | KORDOC는 내장 renderer E2E 통과 뒤 점진 퇴역하고 과거 provenance는 보존 | 문서 출력 회귀 없이 제품 종속 자동 후처리를 제거하며 범용 외부 MCP 계층은 유지하기 위함 | 최종 보완 Phase 0~3·6 |
| 2026-08-31 | API Usage Policy는 credential identity와 원자적 비용 예약·정산으로 별도 구현 | 대화형 actor와 자동 API 주체를 분리하면서 최종 PoC의 금액·RPM 통제를 완성하기 위함 | 최종 보완 Phase 5~6 |

## 13. 이번 단계에서 하지 않는 것

| 2026-08-31 | MCP Builder는 언제든 다시 여는 5단계 시각 매뉴얼을 제품 기능으로 제공 | 초보자가 별도 문서를 읽지 않고 유형 선택부터 호출 시험까지 실제 화면으로 이동하며 완수하도록 하기 위함 | 17.10·25~26·최종 보완 Phase 6 |
| 2026-08-31 | Usage Policy는 credential별 token/RPM 최소 장치를 먼저 적용하고 비용 예약·정산은 후속으로 유지 | 실호출 과다 사용을 즉시 막되 미구현 비용 통제를 완료로 오인하지 않도록 하기 위함 | 최종 보완 Phase 5~6 |
- 특정 산업이나 행정업무 이름을 Platform Core Schema에 추가하지 않는다.
- 공개 MCP를 설치됐다는 이유만으로 자동 신뢰하지 않는다.
- 메타정보 후보를 근거나 승인 없이 확정값으로 승격하지 않는다.
- 파생 산출물을 프로젝트 기준정보의 원본으로 간주하지 않는다.
- 기존 문서·실행·감사 데이터를 일괄 삭제하거나 비가역적으로 변환하지 않는다.
