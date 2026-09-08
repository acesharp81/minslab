# AI Work Hub Phase 0~3 과업 점검 및 완료 결과보고

> 기준 버전: AI Work Hub 0.31.2
> 점검일: 2026-09-04
> 점검 범위: 최종 보완개발 Phase 0~3 전체 과업
> 종합 판정: Phase 0·1·3 완료, Phase 2 서버·브라우저 과업 완료, Windows 네이티브 검증 1건 외부환경 차단

## 1. 점검 개요

### 가. 목적

- Phase 0~3의 계획 대비 누락 과업과 완료 표기의 적정성을 재검증함.
- 단위시험만이 아니라 운영 DB 복원, 실제 양식, 브라우저 사용 흐름, 퇴역 패키지 차단을 수직 검증함.
- 미수행 항목을 완료로 간주하지 않고 외부환경 차단과 제품 결함을 구분하여 관리함.

### 나. 점검 기준

- 구현 코드, 공개 API, DB migration, UI, README와 로드맵의 설명이 서로 일치할 것.
- 테스트가 운영 프로젝트나 고정 fixture에 의존하지 않고 전용 프로젝트·격리 DB에서 재현될 것.
- 백업은 생성 여부가 아니라 실제 운영 DB 교체·재기동까지 검증할 것.
- HWPX 양식은 synthetic fixture 외에 실제 게시 양식을 포함해 구조·매핑 품질을 검증할 것.
- Windows 네이티브 결과는 Windows·한컴오피스에서 생성된 증적이 없으면 완료로 표시하지 않을 것.

## 2. 종합 점검 결과

| Phase | 계획 과업 | 최초 점검 | 보완 결과 | 최종 상태 |
|---|---:|---|---|---|
| 0. 기준점 고정 | 6개 | 운영 DB 실복원 미수행 | 온라인 backup→서비스 정지→원자 교체→무결성 대조→재기동 완료 | 완료 |
| 1. 문서·렌더 계약 | 8개 | 실제 양식 확대 증적 부족 | 저장소 1종과 운영 Store 게시 양식 2개 버전의 구조·매핑 100% 검증 | 완료 |
| 2. KORDOC 없는 E2E | 9개 | Windows 네이티브 미수행, 일부 브라우저 시험 상태 의존 | 서버·Firefox 전 과업과 후속 HWP 주제 유지 결함 보완, Windows runner 제공 | 외부환경 차단 1건 |
| 3. KORDOC/KODAK 퇴역 | 10개 | 완료 상태 재확인 필요 | Store 숨김·API 410·migration 멱등성·provenance 보존·vendor runtime 제거 재검증 | 완료 |

## 3. 세부 수행 결과

### 가. Phase 0 — 기준점 및 복구성

- 운영 SQLite 54개 테이블, 3,137행에 대해 Online Backup API로 일관된 snapshot을 생성함.
- 정확한 절대경로 재확인, 서비스 포트 닫힘 확인, `quick_check`, schema digest, 논리 행/BLOB digest 통과 후에만 원자 교체함.
- 복원 전·backup·복원 후 schema SHA-256은 `9a3244d656b368743a834a1d7e059f11f9fc68b04ee7cd75734f135bb5f27641`로 일치함.
- 논리 SHA-256은 `1e6225de94cbacda1de17c945763c8cec5b99bfe2cb1c6fa9587cfc71e1ff154`로 일치함.
- RPO 0초, 수행시간 2,899.19ms로 확인했으며 교체 전 원본 DB와 WAL/SHM을 복구 가능 상태로 보존함.
- 도구가 실행 중 서비스 포트를 감지하면 실교체를 거부하고, 실패 시 원본으로 자동 롤백하도록 구현함.

### 나. Phase 1 — 문서 계약 및 실제 양식

- `ReportDocument→TemplateSchema→document.report-hwpx→HWPX→RHWP` 책임 경계를 유지함.
- 저장소 `form-002.hwpx` 1종과 운영 Store의 게시 양식 `org.mcp-04fa131ba1` 0.1.0·0.1.1을 읽기 전용으로 검증함.
- 3종 모두 구조 바인딩 준비, 렌더 품질, mapping coverage, render-map coverage 100%를 통과함.
- 양식 내용은 로그에 남기지 않고 참조 ID, SHA-256, 문단·표·셀 수, 구조 지표만 증적화함.

### 다. Phase 2 — KORDOC 없는 E2E

- 새 데모-seed 격리 DB에서 Firefox 실조작 14종을 모두 통과함.
- 프로젝트 생성·복원·백업·자료 등록·완전삭제, Builder 5종, Data MCP, MCP Studio, Store, RHWP, MD↔HWPX, 주제 검색→HWP 후속 생성을 확인함.
- 각 시험은 전용 프로젝트·패키지·문서를 생성하고 종료 시 보관 후 완전 삭제하도록 보완함.
- `범정부AI 공통기반` 관련 자료와 무관한 A-WEB 자료를 함께 등록한 뒤 관련 근거만 선택되는지 확인함.
- 첫 검색 답변 뒤 `보고서를 HWP로 만들어줘` 요청 시 프로젝트 자료 MCP가 짧은 후속 문장으로 다시 검색해 직전 주제를 덮어쓰는 결함을 발견함.
- `previous-answer` 우선 보고서에는 자료 MCP 재바인딩을 금지하여 직전 답변을 그대로 새 Markdown/HWPX로 승격하도록 수정함.
- HWP 사용법·편집 링크·다운로드 안내가 최종 Markdown/HWPX 본문에 유입되지 않음을 확인함.
- Windows 전용 runner는 일반·예산 HWPX 열기, 텍스트·표 확인, HWPX 저장, 재열기, PDF 내보내기, 파일 해시와 증적 해시 생성을 강제함.
- 현재 호스트는 Linux이며 Windows·한컴오피스·COM·브리지 설정이 없어 네이티브 runner는 `blocked`로 종료함. 이는 코드 실패가 아닌 외부 실행환경 미충족임.

### 라. Phase 3 — 제품 종속 경로 퇴역

- 신규 Planner·Resolver·Artifact 기본값에서 KORDOC/KODAK 선택을 제거함.
- Store 일반 목록에서 퇴역 패키지를 숨기고 설치 미리보기·설치·롤백·수정 직접 API를 HTTP 410으로 차단함.
- legacy installation migration을 반복 실행해도 퇴역 이력이 중복되지 않도록 검증함.
- 과거 package/version, 설치·감사 이력과 Artifact renderer provenance는 삭제하거나 변경하지 않음.
- 추적 중이던 전용 vendor runtime 43MB와 전용 환경변수·npm 처리를 제거함.
- 제품 독립적인 stdio·Streamable HTTP·JSON-RPC MCP 경계는 그대로 유지함.

## 4. 최종 검증 결과

| 검증 항목 | 결과 |
|---|---|
| Python 단위·통합·계약 | 154/154 통과 |
| Golden Workflow | 58/58 통과 |
| 실제 HWPX 양식 Golden Set | 3/3 통과, mapping/render-map 100% |
| Firefox 격리 E2E | 14/14 통과 |
| 범정부 AI 검색→HWP 후속 | 관련 근거 유지, A-WEB 제외, 사용법 본문 제외 |
| 프로젝트 완전삭제 | 복원 가능 보관→복원→비가역 재확인→영구 제거 통과 |
| 운영 DB 실복원 | 무결성·schema·논리 digest 일치, RPO 0초 |
| Windows RHWP 네이티브 | 외부환경 차단, 자동 증적 runner 준비 완료 |

- 최종 서비스 재기동 후 `/health`는 `healthy`, readiness는 실패 0·통과 7·경고 6의 `ready-with-warnings`임.
- Store에는 11개 활성 패키지가 노출되며 KORDOC/KODAK 문자열과 퇴역 패키지는 노출되지 않음.
- readiness 경고는 개발용 승인·서명키, Windows 브리지, stdio 승인 프로필, 선택형 미디어 어댑터 및 지식 출처 미등록으로 확인됨.

## 5. 시사점

- 단위시험이 통과해도 브라우저 시험이 운영 DB의 기존 프로젝트·양식에 의존하면 빈 환경에서 실제 배포 결함을 놓칠 수 있음.
- 후속 요청은 짧고 일반적이므로 `현재 문서`, `직전 답변`, `새 자료 검색`의 우선순위를 명시적 계약으로 고정해야 주제 오염을 방지할 수 있음.
- “HWP로”는 내용 지시가 아니라 출력 형식이므로 사용법 문구를 모델 프롬프트와 저장 직전 검증 양쪽에서 차단해야 함.
- 백업 파일 생성만으로는 복구 준비를 입증할 수 없으며 서비스 중지, 원자 교체, 재기동, 논리 digest 대조가 함께 필요함.
- 실제 행정 양식은 문단 수와 표 구조 편차가 크므로 synthetic fixture와 운영 게시 양식을 함께 관리해야 함.
- 퇴역 제품은 UI 숨김만으로 충분하지 않고 직접 API, migration, 런타임 파일, 환경변수와 신규 Resolver 후보를 함께 차단해야 함.
- Linux RHWP 웹 편집 성공은 Windows 한컴오피스 호환성의 대체 증적이 될 수 없으므로 별도 출시 게이트가 필요함.

## 6. 향후 개선방향

### 가. 출시 전 필수

- Windows 11·운영 대상 한컴오피스 버전에서 `scripts/windows_rhwp_acceptance.py`를 실행함.
- 일반·예산 HWPX 표본을 각각 열어 텍스트·중첩 목록·표·결재란을 확인하고 HWPX 저장→재열기→PDF 내보내기를 완료함.
- 생성된 JSON evidence, 원본·왕복 HWPX·PDF SHA-256, 시험자·앱 버전·시각을 변경 승인 자료에 첨부함.
- Windows 게이트 통과 전에는 Phase 2 전체를 완료로 승격하지 않음.

### 나. 단기 개선

- 154개 회귀, 58개 Golden, 실제 양식 3종, Firefox 14종을 CI 릴리스 게이트로 편성함.
- 브라우저 시험의 fixture 미정리와 운영 DB 연결을 자동 탐지하여 즉시 실패 처리함.
- 기관별 익명화 양식을 추가하여 병합 셀, 머리말·꼬리말, 쪽번호, 결재란 보존 검사를 확대함.
- 완전삭제는 보존기간·법적 보존·감사정책과 연계하여 조직별 허용 여부와 이중승인 옵션을 추가함.

### 다. 중기 개선

- Phase 4의 keyword fallback 제거와 Capability Resolver의 품질·비용·지연 점수 통합을 완료함.
- Phase 5의 workflow/step별 모델 비용·실패·fallback 정산과 조직·프로젝트 합산 한도를 완료함.
- 원격 암호화 백업, 보존주기, 자동 복구훈련과 복구 목표 초과 경보를 운영체계에 편입함.

## 7. 증적 위치

- 실복원 manifest: `data/backups/aiworks-restore-drill-20260904T095230017689Z.json`
- 실복원 online backup: `data/backups/aiworks-online-backup-20260904T095230017689Z.sqlite3`
- 실복원 교체 전 원본: `data/backups/aiworks-displaced-original-20260904T095230017689Z.sqlite3`
- Phase 2 결과: `docs/PHASE2_ACCEPTANCE_2026-09-04.md`
- Phase 3 결과: `docs/PHASE3_ACCEPTANCE_2026-09-04.md`
- 기준 로드맵: `docs/PROJECT_PLATFORM_ROADMAP.md`
