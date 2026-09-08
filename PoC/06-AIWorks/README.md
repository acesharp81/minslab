# 06 · AI Work Hub

여러 MCP와 AI 모델을 업무 목적에 맞게 조합하는 승인 기반 AI 업무 실행 허브의 초기 PoC입니다.

`AI Work Hub`는 현재 표시용 가칭입니다. 제품명이 다시 바뀌더라도 기존 프로젝트와 연동을 깨뜨리지
않도록 `aiworks` 프로젝트 ID, `/poc/aiworks`, `/api/poc/aiworks`, `AIWORKS_*` 환경변수,
`.aiworks.json` 백업 포맷, 계약 ID와 과거 감사·Artifact provenance는 호환 식별자로 유지합니다.

현재 실행 기준 버전은 `0.31.2`, README 기준일은 `2026-09-01`입니다. 이 README는 현재 코드의
제품 구조·사용법·운영·검증 기준을 설명하며, 다른 문서가 없어도 현재 시스템의 책임과 데이터
흐름, 실행 조건, 운영상 제약을 분석할 수 있도록 작성했습니다. 단계별 이력은
[프로젝트 플랫폼 로드맵](docs/PROJECT_PLATFORM_ROADMAP.md), 2026-08-19 당시 결과는
[수용성 검증 보고서](docs/ACCEPTANCE_REPORT_2026-08-19.md)를 참고합니다.

프로젝트 문서 내용의 단일 원본은 불변 revision으로 저장되는 Markdown입니다. LLM은 Markdown을
생성·갱신하고, ReportDocument가 제목·문단·목록·표를 구조화하며, 양식 MCP가 표현 규칙을
결합합니다. 기본 `document.report-hwpx` renderer가 HWPX 파생 산출물을 만들고 설치형
`document.format.convert.*` 어댑터는 제3자 형식을 확장합니다. HWPX를
처음 가져오면 텍스트·표를 Markdown 원본으로 변환하고, RHWP에서 기존 파생 HWPX를 수정한
경우에는 변경을 보류합니다. 사용자가 명시적으로 `HWPX → MD 반영`할 때만 새 revision을
기록합니다. 이때 표지·제목 상자·자동 날짜 같은 renderer 장식은 제거하고 의미 본문만
복원합니다. HWPX 자체는 편집·배포용 산출물이지 프로젝트 문서 내용의 원본이 아닙니다.

## 이 문서의 사용법

| 독자 | 먼저 볼 곳 | 이 문서에서 확인할 수 있는 내용 |
|---|---|---|
| 업무 사용자 | `5분 빠른 시작`, `사용자 업무 가이드` | 프로젝트 시작, 질의·문서 작성, 파생 문서 생성, 충돌 복구 |
| MCP 제작자 | `양식 MCP 현재 동작`, `MCP 제작기 사용 순서` | 데이터·양식·처리·외부 MCP 제작, 검증, 게시, 설치 |
| 운영자 | `설치와 기동`, `환경변수 기준표`, `운영 Runbook`, `문제 해결` | 의존성, 보안 설정, 상태 점검, 백업·복원, 장애 대응 |
| 개발자·분석가 | `시스템 아키텍처`, `데이터 모델`, `실행 및 보안 계약`, `서버 실행 흐름` | 모듈 책임, 저장 구조, 상태 전이, API와 확장 지점 |
| 제품 책임자 | `현재 구현`, `현재 제약과 운영 경계`, `향후 해야 할 일` | 구현 범위, PoC 한계, 운영 전 필수 과제와 완료 기준 |

### 빠른 목차

- [현재 제품 구조](#현재-제품-구조)
- [5분 빠른 시작](#5분-빠른-시작)
- [사용자 업무 가이드](#사용자-업무-가이드)
- [시스템 아키텍처](#시스템-아키텍처)
- [데이터 모델과 소유 관계](#데이터-모델과-소유-관계)
- [실행 및 보안 계약](#실행-및-보안-계약)
- [설치와 기동](#설치와-기동)
- [환경변수 기준표](#환경변수-기준표)
- [운영 Runbook](#운영-runbook)
- [문제 해결](#문제-해결)
- [현재 제약과 운영 경계](#현재-제약과-운영-경계)
- [향후 해야 할 일](#향후-해야-할-일)
- [검증](#검증)

## 현재 제품 구조

```text
Project
 ├─ Project Metadata / Fact / Evidence
 ├─ Markdown Document A ─ Markdown Revision 1..N
 │                       └─ Derived Output: HWPX/PDF/제3자 형식
 ├─ Markdown Document B ─ Markdown Revision 1..N
 │                       └─ Derived Output: HWPX/PDF/제3자 형식
 ├─ Conversation / Workflow Run / Approval / Audit
 └─ Installed MCP / Recipe / Project Policy
```

- 프로젝트에는 메타정보와 여러 Markdown 문서가 종속됩니다.
- 각 Markdown 문서는 독립적인 내용 원본과 불변 revision을 가집니다.
- 파생 문서는 프로젝트의 또 다른 원본 문서가 아니라 `MD 문서 버전 + 양식 MCP + 형식 어댑터`로
  만든 최종 산출물입니다. 프로젝트에서는 출처 문서의 계보를 통해 조회합니다.
- MD를 고치면 기존 파생 산출물을 자동으로 덮어쓰지 않고 `stale` 상태로 표시합니다. 사용자가
  명시적으로 새 파생 산출물을 만들 때만 다시 렌더링합니다.
- RHWP에서 수정한 HWPX는 곧바로 MD를 변경하지 않습니다. `HWPX → MD 반영`을 선택해야 새 MD
  revision이 생기며, MD와 HWPX가 각각 변경된 경우 충돌 해결을 요구합니다.
- 프로젝트를 다시 열면 마지막 문서·탭·대화·편집 비율을 복원하며, 탭 전환만으로 문서나
  파생 산출물을 다시 생성하지 않습니다.

### 업무 MCP 실증 1~4 현재 상태

MCP Builder로 만든 실제 업무 기능을 끝까지 시험하기 위한 네 단계는 PoC 기준으로 연결되어 있습니다.

1. Data·Process·Template MCP를 각각 만들고 검증·게시·고정 버전 설치할 수 있습니다.
2. Data MCP 검색 근거에 Process MCP의 작성 절차를 실제 모델 프롬프트로 적용한 뒤, 질문·근거·초안을
   품질 하네스로 비교합니다.
3. 결과 Markdown을 선택된 Template MCP의 HWPX로 렌더링하고 RHWP에서 엽니다. 작성요령·예시는
   제거되며 제목·본문·표·리소스 보존을 렌더링 후 재파싱으로 검증합니다.
4. Resolver는 각 MCP의 Artifact I/O Schema와 품질·비용·지연·프로젝트 선호를 비교해
   `Data → Process → Quality → Template → HWPX → RHWP` 계획과 선택 이유를 표시합니다.

MD와 HWPX를 동시에 수정해 충돌하면 변경 이력에서 HWPX 변경 블록을 선택해 최신 MD revision에
부분 병합할 수 있습니다. 매핑되지 않은 복잡 개체는 자동 추정하지 않고 전체 채택 또는 MD 유지로
검토를 요구합니다.

## 5분 빠른 시작

전제는 운영자가 AIWorks를 기동하고 `operations/readiness`에서 치명적 실패가 없음을 확인한
상태입니다. 로컬 기본 주소는 `http://127.0.0.1:8000/poc/aiworks/`입니다.

1. 첫 화면에서 새 프로젝트를 만들거나 기존 프로젝트를 선택합니다. 프로젝트 없이 대화나 문서
   작업을 시작할 수 없습니다.
2. 새 프로젝트라면 이름과 데이터 등급을 지정합니다. 실제 비밀자료를 시험할 때는 외부 모델
   전송이 차단되는지 승인 화면에서 다시 확인합니다.
3. Orchestrator에 요청을 입력합니다. 예: `첨부 자료의 핵심 지적사항과 대안을 근거와 함께
   개조식 보고서로 작성해줘`.
4. 실행 확인 창에서 먼저 사용자가 이해할 수 있는 처리 순서와 읽을 프로젝트 자료, 외부 전송
   범위·모델 제공자를 확인합니다. MCP 이름·버전·권한은 `기술 정보 보기`에서 펼쳐 봅니다.
   승인 토큰은 기본 10분, 일회용입니다.
5. 생성 결과는 먼저 `문서 내용`에 Markdown으로 저장합니다. 제목·본문·표와 인용을 검토하고 필요한 부분을
   직접 고치거나 문구를 선택해 다시 지시합니다.
6. `완성 문서` 상단의 `양식` 콤보에서 설치된 양식 MCP를 고릅니다. 선택 즉시 현재 MD revision을
   해당 양식으로 다시 렌더링하며, 의도 분석기가 먼저 고른 양식이 있으면 그 버전이 기본값으로
   표시됩니다. 생성된 HWPX는 원본 문서가 아니라 해당 MD revision에서 만든 최종 산출물입니다.
7. RHWP에서 HWPX를 수정했다면 `문서 원본에 반영`을 명시적으로 실행합니다. 양쪽이 모두 바뀌면
   자동 병합하지 않고 비교·충돌 해결 화면을 표시합니다.

정상 결과는 새 MD revision, 실행 및 승인 감사 기록, 사용한 데이터 근거, 양식 MCP 버전과
출처 MD version이 함께 남는 것입니다. 탭을 이동하는 것만으로 새 산출물이 생기거나 내용이
바뀌면 정상 동작이 아닙니다.

## 사용자 업무 가이드

### 프로젝트와 문서

- 프로젝트는 대화와 문서의 작업 경계입니다. 메타정보·근거·설치 MCP·정책은 프로젝트에
  종속되고 프로젝트 안에는 여러 Markdown 문서가 존재할 수 있습니다.
- 기존 프로젝트를 열면 마지막으로 선택한 문서, 탭, 대화와 좌우 패널 비율을 복원합니다.
- 첫 화면의 `삭제`는 복구 가능한 `보관`입니다. 보관 프로젝트 목록에서 `복원`하거나, 소유자가
  프로젝트 이름을 다시 입력하고 비가역성을 확인한 뒤 `완전 삭제`할 수 있습니다. 완전 삭제 후에는
  UI·API·DB 어디에서도 복원할 수 없고, 감사 로그에는 내용 대신 삭제 건수와 참조 해시만 남습니다.
- 프로젝트 백업은 설정의 프로젝트 거버넌스에서 `.aiworks.json`으로 내려받습니다. 가져오기는
  기존 프로젝트를 덮어쓰지 않고 항상 새 프로젝트 ID를 만듭니다.
- `자료`에서는 PDF·HWPX·DOCX·ODT·XLSX·MD·TXT를 여러 개 추가할 수 있습니다. 원본과 검색 청크는
  프로젝트에 영속 저장되고 체크한 자료만 다음 요청의 검색 범위가 됩니다. 동일 파일은 SHA-256으로
  중복 등록하지 않으며, 삭제와 `검색 다시 구성`을 지원합니다.

### 대표 업무 흐름

| 상황 | 요청 예시 | 기대 동작 |
|---|---|---|
| 파일 미첨부 조회 | `우리부 예산 현황을 확인해줘` | 의도 분석 → 설치된 데이터 MCP 검색 → 근거가 있는 답변 |
| 조회 결과를 문서화 | `시사점과 향후 계획을 추가해 보고서로 작성해줘` | 근거 종합 → 품질 확인 → 새 MD 문서/revision 저장 |
| 첨부 문서 기반 작성 | `첨부 문서를 기준으로 올해 결산 보고서 초안을 작성해줘` | 로컬 추출 → 데이터 근거화 → MD 초안 생성 |
| 양식 적용 | `행안부 보고서 양식 MCP를 적용해줘` | 설치된 정확한 MCP 버전 선택 → 현재 MD로 HWPX 파생 산출물 생성 |
| 선택 문구 수정 | `선택한 문구의 당위성을 강화해줘` | 선택 범위만 제안 → 전후 비교 → 승인 후 MD revision 저장 |
| 법률·데이터 보강 | `선택한 내용의 관련 법 조항과 근거를 찾아줘` | 허용된 법률/데이터 MCP 검색 → 출처와 함께 제안 |

데이터 MCP에서 근거를 찾지 못한 경우에는 청크를 임의로 일반화하거나 사실을 만들어내지 않고,
자료 추가 또는 검색 범위 수정을 요청하는 것이 정상입니다. 검색 결과가 있으면 단순 청크 나열이
아니라 질문의 연도·대상·출력 형식에 맞춰 모델이 종합하되 각 판단을 원문 근거와 연결합니다.

### 작업대 탭과 문서 상태

| 화면·상태 | 의미 | 사용자가 할 일 |
|---|---|---|
| `문서 내용` | 의미 내용의 단일 Markdown 원본 | 제목·본문·목록·표를 검토하고 revision 저장 |
| `완성 문서` | MD와 양식/어댑터로 만든 HWPX 작업본 | 내려받거나 RHWP로 열고 필요할 때 다시 생성 |
| `내보낸 파일` | 특정 revision과 양식으로 확정한 불변 결과 | 다운로드·전달용으로 사용 |
| `기준정보` | 프로젝트 기준 사실과 시점별 값·근거 | 후보를 확인·확정하거나 오기/시간 변경을 판단 |
| `변경 이력` | MD revision, 파생 계보와 동기화 기록 | 이전 버전·생성 근거·충돌 원인을 확인 |
| `최신` (`synced`) | 완성 문서가 현재 MD revision과 일치 | 바로 사용 가능 |
| `완성 문서 다시 만들기 필요` (`stale`) | MD가 완성 문서보다 새로움 | 필요하면 완성 문서를 다시 생성 |
| `완성 문서에서 수정됨` (`diverged`) | RHWP/HWPX 쪽만 수정됨 | 비교 후 `문서 원본에 반영` 또는 변경 폐기 |
| `conflict` | MD와 HWPX 양쪽이 모두 수정됨 | 변경 블록을 선택해 명시적으로 해결 |

`완성 문서`의 `양식` 콤보에는 Store에 설치되어 활성화된 `template` 유형 MCP만 나타납니다.
글꼴을 바꾸듯 다른 양식을 선택하면 별도 실행 버튼 없이 즉시 HWPX를 다시 만들고, 선택한
`package@version`을 작업본과 불변 내보낸 파일에 함께 기록합니다. RHWP에만 반영된 수정이 있으면
덮어쓰기 전에 확인하며, 이전 내보낸 파일은 삭제하지 않습니다. 현재 적용 양식이 제거되었거나
과거 버전이어도 `현재 적용 · package@version`으로 표시하여 문서의 출처를 잃지 않습니다.

### MCP 만들기와 Store

상단 `MCP 만들기`는 범용 제작기로 이동하고, `Store`는 게시된 패키지의 설치·수정·삭제·환경설정을
관리합니다. 양식 MCP는 HWPX 하나, 데이터 MCP는 여러 자료를 받을 수 있습니다. 양식의 새 기준
HWPX를 올리면 이전 기준 파일은 교체되어야 하며, 여러 기준 파일이 누적되면 오류입니다. 제작
절차와 품질 게이트는 [MCP 제작기 사용 순서](#mcp-제작기-사용-순서)를 따릅니다.

### 파일 형식과 기본 한도

| 목적 | 형식 | 현재 처리 |
|---|---|---|
| 양식 기준 | HWPX | 구조·스타일·고정 문구·슬롯 추출, 기준 파일 1개 |
| 데이터 원본 | PDF, HWPX, DOCX, ODT, XLSX, MD, TXT | 로컬 텍스트 추출·청크·근거 검색 |
| 프로젝트 자료 | PDF, HWPX, DOCX, ODT, XLSX, MD, TXT | 원본 영속 저장·로컬 추출·검색·재색인·삭제 |
| 문서 편집/가져오기 | HWP, HWPX, HWT, HML, DOCX, XLSX, MD, TXT | RHWP/WASM 또는 Markdown 작업대로 로드 |
| 파생 산출물 | 현재 HWPX 중심 | 설치형 `document.format.convert.*`로 확장 예정 |

기본 HWPX 한도는 10MB, `.env.example`의 일반 Builder 자산 한도는 5MB이며 요청 본문 전체 한도는
15MB입니다. 프로젝트 백업의 압축 해제 후 한도는 50MB입니다. 이미지 스캔 PDF는 OCR MCP가
연결되기 전에는 검색 청크를 만들 수 없습니다.

## 시스템 아키텍처

AIWorks 0.31.2은 하나의 Python ASGI 프로세스, 정적 SPA, 로컬 MCP 런타임과 SQLite를 결합한
단일 노드 PoC입니다. 별도 마이크로서비스나 작업 큐가 있다고 가정하면 안 됩니다.

```text
Browser SPA
  ├─ Project Gate / Orchestrator / Approval UI
  ├─ MD Workbench / Metadata / History
  ├─ Derived Output / embedded RHWP Studio
  └─ MCP Builder / Store / Settings
          │ JSON over /api/poc/aiworks
          ▼
main.py · ASGI host/router
          ▼
backend.py · application service + SQLite repository
  ├─ Intent / Planner / Resolver / Approval / Workflow executor
  ├─ Project / Document / Fact / Artifact services
  ├─ MCP Registry / Builder / Recipe / Runtime
  ├─ ReportDocument / built-in HWPX renderer / optional format adapters / RHWP bridge
  └─ Solar·OpenRouter·Ollama adapters and local retrieval
          │
          ├─ SQLite WAL + local package/document bytes
          ├─ optional Upstage/OpenRouter HTTP
          ├─ optional local Ollama
          └─ optional Windows RHWP agent
```

### 구성요소와 책임

| 경로 | 책임 | 분석 시 주의점 |
|---|---|---|
| `main.py` | ASGI 진입점, 정적 화면 제공, 요청 크기 제한, AIWorks API 라우팅 | 업무 규칙은 대부분 `backend.py`로 위임 |
| `PoC/06-AIWorks/backend.py` | 스키마 migration, 서비스 로직, API dispatch, SQLite 접근 | 현재 큰 단일 모듈이므로 변경 영향 범위가 넓음 |
| `PoC/06-AIWorks/web/index.html` | SPA 문서 구조 | 서버 템플릿이 아니라 정적 UI 셸 |
| `PoC/06-AIWorks/web/app.js` | 프로젝트·대화·편집기·Builder·Store 상태와 API 호출 | 탭 전환과 생성 동작을 분리해야 함 |
| `PoC/06-AIWorks/web/styles.css` | 전체 UI와 분할 패널 스타일 | RHWP 내부 스타일과 책임이 다름 |
| `PoC/06-AIWorks/mcp/` | 의도 분석, 모델 관리, 작업공간, 보고서, 양식, RHWP 도구 | MCP 간 연결은 계약 ID와 고정 버전으로 해석 |
| `PoC/06-AIWorks/contracts/` | API·Artifact·MCP·문서 JSON Schema의 원본 | UI 모양보다 이 계약과 revision이 호환성 기준 |
| `PoC/06-AIWorks/web/vendor/rhwp-editor/` | 자체 호스팅 RHWP Studio/WASM | 외부 CDN 없이 브라우저 문서 편집 제공 |
| `PoC/06-AIWorks/rhwp_windows_agent.py` | 한컴오피스 네이티브 자동화 브리지 | Windows 사용자 세션, 한컴오피스, pywin32 필요 |
| `PoC/06-AIWorks/tests/` | 단위·통합·브라우저 회귀 테스트 | 운영 DB가 아닌 별도 DB로 실행 |

### 주요 처리 흐름

일반 보고서 작성은 다음 순서를 따릅니다.

```text
사용자 요청/첨부
  → 로컬 의도 분석
  → 설치 MCP 탐색·Capability 조합
  → 실행계획과 데이터/권한/모델 설명
  → 사용자 승인
  → 데이터 검색·LLM 초안·질문 대비 품질 확인
  → Markdown revision 저장
  → 메타정보 후보와 근거 연결
  → 선택한 양식 MCP 적용
  → 기본 document.report-hwpx 또는 명시적으로 선택한 형식 어댑터로 HWPX 생성
  → RHWP 열기·다운로드·선택적 역반영
```

데이터 MCP는 `원본 등록 → 로컬 추출 → 페이지/청크 색인 → 질의 후보 검색 → LLM 종합 → 출처
인용` 순서입니다. 양식 MCP는 `HWPX 1개 등록 → 재사용 구조와 슬롯 추출 → MD/HWPX 매핑 →
실렌더링 재검증 → 서명 게시·설치` 순서입니다. 둘 다 설치된 고정 package version만 실행계획에
포함됩니다.

## 데이터 모델과 소유 관계

소유 관계의 핵심은 `프로젝트 → 여러 MD 문서 → 여러 불변 revision → 필요할 때 생성한 파생
산출물`입니다. 메타정보는 프로젝트에 속하고, 파생 문서는 프로젝트의 독립 원본 문서가 아니라
출처 MD version으로 추적되는 최종 산출물입니다.

| 영역 | 주요 SQLite 테이블 | 역할 |
|---|---|---|
| 프로젝트 | `projects`, `project_members`, `project_policies`, `permission_grants`, `project_workspace_states` | 프로젝트 경계, RBAC·정책, 마지막 화면 상태 |
| Markdown 문서 | `project_markdown_documents`, `project_markdown_versions` | 여러 문서와 불변 내용 revision |
| 파생·네이티브 문서 | `project_document_artifacts`, `document_final_outputs`, `native_document_sessions` | HWPX 등 생성물, 출처 revision, RHWP 세션 |
| 동기화·충돌 | `project_document_sync_events`, `project_document_conflicts` | MD↔HWPX 승격, stale/diverged/conflict 기록 |
| 메타·근거 | `project_facts`, `project_fact_values`, `report_fact_snapshots`, `knowledge_*` | 프로젝트 기준 사실, 시점 값, 문서 스냅샷, 출처 그래프 |
| 범용 산출물 | `artifacts`, `artifact_versions`, `artifact_relations`, `artifact_evidence` | 형식 독립 계보, 버전, 관계, 원문 근거 |
| 계획·실행 | `plans`, `approvals`, `executions`, `workflow_runs`, `workflow_step_runs`, `audit_events` | 설명 가능한 계획, 승인, 재시도, 감사 |
| MCP | `mcp_drafts`, `mcp_packages`, `mcp_installations`, `mcp_configurations`, `mcp_capabilities`, `mcp_reference_chunks` | 제작 초안, 서명 패키지, 설치·설정, 검색 청크 |
| Recipe | `workflow_recipes`, `workflow_recipe_versions`, `workflow_recipe_installations` | 재사용 가능한 조합 업무의 버전과 설치 |

SQLite는 `foreign_keys=ON`, `journal_mode=WAL`로 열리고 앱 시작 시 호환 migration을 적용합니다.
기본 DB는 `PoC/06-AIWorks/data/aiworks.sqlite3`이며 `AIWORKS_DB_PATH`로 분리할 수 있습니다.

### 변경 불변조건

1. MD revision은 수정하지 않고 새 revision을 추가합니다.
2. 파생 산출물은 생성 시점의 MD version, 양식 MCP package/version, 어댑터와 해시를 기록합니다.
3. MD 저장은 기존 HWPX를 자동 덮어쓰지 않고 `stale`로 만듭니다.
4. RHWP 저장은 MD를 자동 갱신하지 않고 `diverged`로 만들며, 명시적 역반영만 새 MD revision을
   생성합니다.
5. 양쪽 변경이 감지되면 자동 우선순위를 정하지 않고 `conflict`를 기록합니다.
6. 프로젝트 메타정보는 후보와 확정값을 구분하고, 값이 바뀌면 오기인지 시점 변화인지 결정과
   근거를 남깁니다.
7. 프로젝트 백업 가져오기는 기존 ID나 데이터를 덮어쓰지 않고 새 프로젝트를 생성합니다.

## 실행 및 보안 계약

### 계획·승인·실행

모든 변경·외부 전송 실행은 `plan → approval → execution` 경계를 따릅니다. 계획에는 MCP 이름만
나열하지 않고 역할, 선택 이유, 입력·출력, 읽거나 쓸 데이터, 요구 권한, 외부 전송과 예상 모델을
포함해야 합니다. 승인은 HMAC 서명된 일회용 토큰이며 기본 TTL은 600초입니다. 실패한 Workflow를
재시도할 때는 기존 Run에 attempt를 추가하되 새 계획·승인을 발급합니다.

대표 위험 권한은 문서 읽기/쓰기, `model.invoke`, `network.send`, 외부 MCP 호출과 RHWP 자동화입니다.
권한이나 데이터 범위가 계획 이후 바뀌면 실행을 중단하고 재승인해야 합니다. 실행 결과와 오류,
선택 MCP 버전, approval 사용 여부는 감사 이벤트에 기록됩니다.

### 모델과 외부 전송

- 의도 분류와 검색 후보 선정은 우선 로컬에서 수행합니다.
- Solar/OpenRouter 호출은 API 키, live 플래그, 계획의 `model.invoke`·`network.send` 권한과 사용자
  승인이 모두 있어야 합니다.
- `confidential` 프로젝트 문맥은 외부 모델로 보내지 않습니다.
- 외부 호출 실패 시 근거가 있는 로컬 결과로 대체 가능한 단계만 폴백합니다. 품질이 필요한 문서
  생성을 성공으로 위장하지 않습니다.
- 첨부 원본 포함, 패키지 공개 범위와 외부 전송 허용은 서로 다른 설정입니다.

### 신뢰 경계

HWPX는 ZIP 경로, XML 외부 엔터티, 압축 해제 크기와 SHA-256을 검사합니다. MCP 설치는 Manifest,
권한 allowlist, 정확한 의존 버전, 번들 해시와 서명을 다시 검증합니다. 다만 현재 패키지 서명은
서버 비밀키 기반 HMAC이고, API의 `actor`는 인증된 SSO 주체가 아니라 요청 값에 의존합니다.
따라서 현재 RBAC은 제품 동작 검증용이며 신뢰할 수 없는 네트워크에 직접 공개하는 보안 경계가
아닙니다. 운영 전 인증 프록시/SSO, KMS 기반 게시자별 비대칭 서명과 조직 단위 격리가 필요합니다.

## 현재 구현

- 운영 프로필에서는 예제 프로젝트·예산·민원 문서를 만들지 않는 빈 기준선. 테스트 fixture는
  `AIWORKS_ENABLE_DEMO_SEED=1`인 격리 환경에서만 생성
- 프로젝트 자료의 다중 첨부, 원본·검색 청크 영속 저장, SHA-256 중복 방지, 선택 검색, 삭제·재색인,
  백업·복원과 내장 `core.project-sources` 데이터 MCP 자동 결합
- 기본 화면을 `자료 / AI 작업 / 문서 / 완성 문서` 업무 언어로 구성하고 MCP Builder·Store는 고급
  확장 영역으로 유지. 승인 창은 처리 순서·정확한 자료명·Solar 제공자와 외부 전송 범위를 먼저 표시
- 프로젝트 문서별 `MD 원본 / HWPX·파생 형식 / 메타정보 / 변경 이력` 탭, 명시적 MD↔HWPX 승격, 문단·표 셀 Render Map, 동시 편집 충돌 저장·선택 해결과 revision/SHA 기반 편집기 캐시
- 완성본·작성요령·빈칸·기존 플레이스홀더 HWPX를 첨부 즉시 자동 판별하고, 단일 기준 양식의
  제목·본문·목록·표 슬롯으로 추출하는 양식 MCP 등록 흐름
- 왼쪽 MD 내용 계약과 오른쪽 RHWP HWPX를 동시에 보여주는 양식 매핑 Studio, 수정본·슬롯 동시
  저장, ReportDocument 실렌더링·재파싱 품질 검증
- Workflow/Step Run 체크포인트·재승인 재시도, exact-duplicate MD 보관, Fact 시간변화/오기 결정,
  산출물 재현 관계 그래프
- 단계별 최신 상태와 남은 항목: [docs/PROJECT_PLATFORM_ROADMAP.md](docs/PROJECT_PLATFORM_ROADMAP.md)
- 프로젝트 멤버십/RBAC·정책·Permission Grant·보관/복원과 소유자 이름 재확인 기반 완전 삭제,
  범용 Artifact/Version 계보와 순환 방지
- 프로젝트 선택 화면의 AIWorks JSON 가져오기와 설정→프로젝트 거버넌스의 백업 다운로드. MD revision·메타정보와 프로젝트 자료 Artifact/검색 인덱스·관계·Evidence를 SHA-256 무결성 검증 후 새 프로젝트로 복원. 재생성 가능한 HWPX 작업본·내보낸 파일은 제외
- Artifact Evidence 원본 Version·위치·발췌·해시·신뢰도 API와 문서 변경 이력 표시
- Recipe 이름/ID/태그 검색, 설치 전 권한·비용·지연·라이선스·출처·보안 미리보기와 취약 버전 차단
- 실패 Workflow 재승인 시 동일 Run ID에 attempt를 누적하는 in-place 재개와 실행 attempt 감사 이력
- TemplateSchema·Render Map 1.2의 필수/반복/조건 슬롯, 표 셀·병합 좌표와 구조 지문,
  스캔 전용 HWPX의 OCR 필요 차단, DOCX/XLSX 로컬 추출→RAG/Markdown 입력
- 프로젝트 대화·메시지·사용자 결정의 독립 영속화와 portable backup 1.2, 문서 revision·승인
  근거·양식 선택 결정의 관계 복원
- Resolver 후보의 품질·성공률·지연·비용·프로젝트 선호 비교, 10분 단일 실행 승인 lease와
  제출·발송·게시·삭제 직전 별도 확인
- Markdown 원본에서 DOCX·ODT·PDF·XLSX 작업본/불변 최종 산출물을 만드는 의미 기반 형식 어댑터와
  형식별 손실 계약. ODT는 의미 기반 재입력, PDF는 격리 LibreOffice 렌더러로 실제 생성
- Store의 버전별 평가·라이선스·보존·보안·호환성 표시와 실행·Workflow·lease·산출물·충돌
  운영 지표 화면 및 `/operations/metrics` 계약
- Workflow Recipe 1.0 버전 게시·공유·포크·프로젝트 설치·폐기와 설정 화면 Recipe Library
- GPT형 첫 화면에서 명령과 문서를 함께 제출하면 의도 분석 결과에 따라 업무 MCP와 편집기 MCP를 동적으로 로딩
- 파일 미첨부 질의 → 채팅 답변 → 파생 보고서 → 선택 문구 변경으로 이어지는 피드백 흐름
- 첨부 자료 → 결산 양식 보고서 → 선택 문구 법률 검토로 이어지는 피드백 흐름
- 파생 보고서를 실제 HWPX로 패키징해 자체 호스팅 RHWP 문서 세션에서 열고, 같은 화면에서 선택·수정·버전 저장
- `행안부 보고서 양식으로 바꿔줘` 요청 시 로컬 양식 MCP를 동적 로딩해 본문을 보존한 HWPX 파생 최종 산출물 생성
- 하나의 범용 MCP Builder에서 양식·처리·데이터·일반 도구·외부 MCP 연결 유형을 선택하고 파일·유의사항·처리 절차·호출 예시를 가이드 패키지로 제작
- 게시·설치된 Builder MCP의 Capability를 Registry에 색인하고, 채팅 요청·호출 예시·등록 자료 주제를 Resolver가 비교해 서명된 고정 버전을 승인 후 Prompt/Composite/Retrieval 런타임으로 실행
- 데이터 MCP에서 여러 PDF·HWPX·텍스트 파일을 페이지 단위로 추출·청크화하고, 게시 전 RAG 검색과 게시·설치 후 자동 선택·연도별 근거 정리·페이지 인용·편집 가능한 HWPX 보고서를 제공
- 전체 폭 MCP Studio에서 5개 유형 예시를 선택해 초안→자료→검증→게시→설치를 진행하고, 설치 Registry의 호출 문구를 바로 채팅과 RHWP 산출물로 시험
- 플레이스홀더가 포함된 HWPX 시작 양식을 내려받아 실제 양식 MCP 제작 자료로 재업로드
- Solar 전용 자동 라우팅: 빠른 조회는 `upstage:solar-pro3-fast`, 문서·RAG 종합은 `upstage:solar-pro3`, 복합 비교·검증은 `upstage:solar-pro4`; 외부 전송 승인 전에는 로컬 근거 보고서로 실행
- 체험 절차와 현재 데이터 커넥터 범위: [docs/FEEDBACK_SLICE_0.20.md](docs/FEEDBACK_SLICE_0.20.md)
- 범용 제작기 제품 기준과 후속 실행 계층: [docs/MCP_BUILDER_VNEXT.md](docs/MCP_BUILDER_VNEXT.md)
- 좌측 Orchestrator와 우측 편집기 MCP의 공통 작업공간, 선택 영역 컨텍스트와 변경 전·후 제안·적용 흐름
- MIT 오픈소스 [rhwp](https://github.com/edwardkim/rhwp) 0.8.2 Studio/WASM 자체 호스팅: HWP/HWPX/HWT/HML 네이티브 UI 직접 편집 및 원본 형식 내보내기
- Markdown 분할 편집·미리보기와 코드 편집기 플러그인, 공통 revision 저장·다운로드 계약
- VS Code형 탐색기, 문서 편집기, AI 채팅, 미리보기, 공통데이터, MCP 관리 패널
- 제목·본문·표 직접 편집, 안전한 기본 서식, 실시간 미리보기, 서버 문서 저장·재열기와 Ctrl+S
- HWPX 전체 문단 직접 편집, 변경 문단별 원문·해시 충돌 검사, 새 버전 저장·재열기·다운로드
- RHWP 전체 기능 MCP 21개 도구: 세션·본문·필드·찾기/바꾸기·저장·PDF·인쇄·실행취소, HAction/HParameterSet과 원본 변환
- HWPX 구조 렌더러: 원문 순서, 표·행·셀, 행/열 병합, 셀 내부 문단과 개체 경계를 유지한 편집 화면
- MCP 네이티브 문서 세션: 의도·형식 분석, RHWP 우선 선택, revision 명령, 원본 산출물과 PDF 스냅샷
- 편집기·사이드바·채팅·모든 관리 화면의 독립 세로 스크롤
- 예산요청서 샘플에서 값 추출 → 실행 계획 → 권한 승인 → 변경 제안 → 적용/되돌리기
- 자연어 기반 MCP 초안 영속 저장, Manifest/Schema 생성, 샌드박스 계약 검증과 서명 게시
- 실제 HWPX·PDF·Markdown·TXT 기준 문서의 로컬 저장·구조 검사·SHA-256 무결성 검증
- 저장된 제작 작업 재개, 원본 선택 포함, 변조 패키지 격리와 readiness 실패 표시
- 조직 MCP 스토어 검색·서명 검증·권한 승인·버전 고정·롤백
- 공통데이터 시점 이력과 원문 위치 추적
- 출처 기반 질의응답, 기준일 조회, 값 변화 비교와 노트 관계 그래프
- 문서·코드·이미지·음성·영상 업무 프리셋과 실제 바이트 기반 로컬 파일 검사
- 운영 readiness와 예산요청서 전체 승인 E2E 수용성 테스트
- 실행별 감사 로그

## 양식 MCP 현재 동작

양식 MCP는 일반 HWPX 파일을 그대로 보관하는 파일 등록 기능이 아니라, HWPX에서 재사용 가능한
표현 구조를 추출하여 이름으로 호출할 수 있는 설치형 Capability로 만드는 기능입니다.

```text
HWPX 첨부
  → 원본 유형 판별(sample-structure / guided-fields / explicit-placeholders)
  → 고정 문구·문단 스타일·목록 prototype·표 구조 보존
  → {{title}}·{{content}}와 선택 메타 슬롯 자동 추출
  → MD↔HWPX 매핑 Studio에서 동시 검토·수정
  → 테스트 ReportDocument 렌더링·재파싱
  → 검증·게시·설치
  → “<MCP 이름> 적용해줘”로 현재 프로젝트 MD에 적용
  → 또는 완성 문서의 양식 콤보에서 즉시 선택·전환
  → HWPX 파생 최종 산출물 생성
```

화면의 `실제 사용법` 안내는 선택한 양식 MCP의 고정 버전과 원본 HWPX, 프로젝트·MD·설치
준비상태, 실제 변환 흐름과 호출 문구를 함께 보여줍니다.

- Store의 양식 MCP 카드에서 `사용법`을 누르면 설치 전에도 사용 조건을 확인할 수 있습니다.
- MCP Builder의 `양식 MCP` 영역에서 `실제 사용법`을 누르면 선택한 등록 양식을 기준으로 안내합니다.
- 완성 문서 상단 양식 콤보 옆 `? 사용법`에서는 현재 적용 양식을 기본으로 표시합니다.
- 안내창의 `호출 문구 입력`, `현재 문서에 적용`, `Builder에서 수정`으로 다음 작업을 바로 시작할 수 있습니다.

- 양식 기준 HWPX는 초안마다 하나만 유지하며 새 파일을 올리면 기존 기준 파일을 교체합니다.
- 완성된 보고서, 예시 데이터가 든 양식, 작성요령이 든 양식, 빈 입력란 양식과 이미
  플레이스홀더가 있는 양식을 지원합니다.
- 첨부 즉시 원본 유형·신뢰도·원본 SHA-256·추론한 제목/본문 위치를 기록하고 재사용 슬롯을
  포함한 기준 HWPX로 저장합니다.
- `MD↔HWPX 매핑 수정` 화면의 왼쪽은 문서마다 바뀌는 MD 계약, 오른쪽은 고정 서식과 문구를
  관리하는 실제 RHWP 편집기입니다.
- 저장할 때 MD에 `{{title}}`과 `{{content}}` 또는 `{{body}}`가 있는지 확인하고, 편집한 HWPX와
  선택한 문단·목록·메타·결재 매핑을 함께 반영합니다.
- 게시된 양식 MCP에는 MCP 이름 기반 호출 예시가 자동으로 포함됩니다. Resolver가 설치된 정확한
  버전을 찾은 뒤 활성 프로젝트 Markdown을 읽고 HWPX를 생성하며, 결과에는 원본 MD version과
  양식 MCP package reference가 기록됩니다.
- 의도 분석기에서 선택된 양식과 사용자가 완성 문서 콤보에서 선택한 양식은 같은 명시적
  `package@version` 렌더 계약을 사용합니다. 따라서 다시 열어도 실제 적용된 양식이 기본 선택됩니다.
- 탭 전환이나 HWPX 조회는 재생성 조건이 아닙니다. 사용자가 양식 적용을 요청할 때만 새로운
  파생 최종 산출물을 만듭니다.

실행 계층에서는 실행계획, 승인과 실행 결과가 서버 SQLite에 저장됩니다. 승인 토큰은 HMAC 서명된
일회용 토큰이며 기본 유효시간은 10분입니다. 실행기는 외부 네트워크를 사용하지 않는 로컬
샌드박스로 유지됩니다.

HWPX 어댑터는 ZIP/XML 구조, 압축 해제 크기와 외부 엔터티를 검사한 뒤 문단과 사업명·사업기간·
총사업비 후보를 추출합니다. 원본 SHA-256과 기존 문장을 다시 확인한 후 지정 문단만 교체하고,
나머지 ZIP 항목을 보존한 새 HWPX 버전을 생성해 다운로드할 수 있습니다. RHWP는
document.rhwp@1.0.0 MCP와 Windows 네이티브 에이전트로 구현했습니다. Linux 서버에서는 도구
계약·권한·서명·감사 경계를 검증하며, 실제 한글 조작은 한컴오피스와 pywin32가 설치된 같은
사용자 Windows 세션에서 실행합니다.

기본 예산요청서는 제목, 본문과 표 셀을 클릭해 바로 편집할 수 있습니다. 700ms 후 브라우저
복구 초안으로 자동 저장되며 저장 버튼 또는 Ctrl+S로 서버 작업 문서와 revision을 확정합니다.
굵게·기울임·목록 서식은 허용된 HTML만 저장하고 미리보기와 즉시 동기화됩니다. HWPX를 열면 모든
본문 문단이 편집 목록으로 전환되고, 저장 시 실제로 변경된 문단만 순서대로 원문과 SHA-256을
재확인한 뒤 새 HWPX에 반영합니다. 저장된 HWPX 산출물은 서버에서 다시 열 수 있습니다. 원본
구조 보존을 위해 HWPX 직접 편집은 현재 텍스트 변경만 지원합니다. 새 빈 작업공간의 레거시
샘플 문서만 HTML 초안으로 유지하며, 대화에서 생성하는 파생 보고서는
`document.report-hwpx@0.1.0`이 HWPX로 패키징하고 `document.rhwp@1.0.0` 편집기에서 엽니다.
브라우저 구조 렌더러는 표와 병합 셀을 선택 가능한 구조 미리보기로 표시합니다. 그림·수식·OLE 개체는
텍스트와 섞지 않고 위치를 알 수 있는 개체 블록으로 표시하며, 정확한 글꼴·도형 좌표·페이지
나눔은 Windows RHWP 원본 미리보기에서 확인합니다.

가져온 한글 문서는 HTML `contenteditable`로 수정하지 않습니다. 파일을 열면 Core
Orchestrator가 로컬에서 의도와 형식을 분석하고 `document.rhwp@1.0.0`을 우선 요청합니다.
Windows 브리지가 연결되어 있으면 RHWP가 원본을 열고 PDF 스냅샷을 반환하며, 선택 교체·필드·
HAction·실행취소 명령을 원본에 적용합니다. Windows가 없고 파일이 HWPX이면 동일한 세션 계약의
`document.hwpx@1.2.0`이 안전 대체로 선택됩니다. 화면은 요청 어댑터→실제 선택 어댑터와
revision을 표시하며 모든 변경은 서버 MCP 명령을 거쳐 즉시 새 산출물로 저장됩니다. 바이너리
HWP/HWT/HML은 Windows 브리지가 없으면 AIWorks 내부에 자체 호스팅한 `document.rhwp-web@0.8.2`
WASM 편집기로 열립니다. HWPX도 RHWP 원본 편집 화면을 기본으로 사용하며 문단·표 구조 확인용
AI 선택 모드를 함께 제공합니다. AIWorks 커스텀 `selection-edit-v1` 임베드 계약은 RHWP 원본
편집창의 실제 텍스트 선택을 좌측 Orchestrator로 읽고, 비교 제안을 한 번의 Undo 가능한
`ReplaceSelectionCommand`로 적용합니다. 적용 직후 HWP/HWPX/HML 원본 산출물을 새 revision으로
저장합니다. 편집기·어댑터·WASM은 모두 같은 서비스에 자체 호스팅되어 외부로 문서를 전송하지 않습니다.

조직 스토어는 Manifest 계약, 권한 allowlist, 의존성의 정확한 버전 고정, 번들 SHA-256과
게시자 서명을 설치 전에 다시 검증합니다. 설치·업데이트·롤백은 모두 감사 로그에 남고 이후
실행 계획은 현재 고정 설치된 MCP 버전을 사용합니다. PoC 서명은 서버 비밀키 기반
HMAC-SHA256이며, 운영 배포에서는 게시자별 비대칭 서명과 KMS로 교체해야 합니다.
Manifest가 선택적 `configuration` 계약을 선언하면 설치된 Store 카드에 `환경설정` 버튼이
자동으로 나타납니다. 문자열·숫자·체크박스·선택값을 공통 폼으로 렌더링하고 타입·허용값을
서버에서 다시 검증하며, revision 충돌 방지와 변경 감사 기록을 적용합니다.

MCP 제작기는 자연어 설명과 공개 범위, 원본 포함 여부, 외부 전송 허용 여부를 서버 초안으로
저장합니다. 계약·고정 의존성·최소권한·네트워크 경계·입출력 Schema 검사를 모두 통과해야
게시할 수 있으며, 게시 시 공개 범위와 원본 포함 여부를 다시 확인합니다. 게시된 패키지는
동일한 조직 서명 검증을 거쳐 스토어에 즉시 나타나고 정확한 버전으로 설치됩니다.
기준 문서는 파일당 최대 10MB이며 브라우저에서 서버 로컬 저장소로만 전달됩니다. HWPX는 문단과
공통데이터 후보, PDF는 암호화 여부를 검사한 뒤 페이지별 텍스트를 추출·청크화하고, Markdown·TXT는 UTF-8 구조를
검사합니다. 원본 포함을 선택한 경우에만 게시 패키지 파일로 복사되고 설치 전 해시를 다시
검증합니다. 실패한 패키지는 설치 목록에서 격리되며 운영 진단이 실패 상태가 됩니다.

지식 계층은 문서, 공통데이터와 노트를 출처 및 관계로 연결합니다. 질의 시 사용자 접근등급과
기준일을 먼저 적용하며, 연결된 원문 근거를 찾지 못하면 답변을 생성하지 않습니다. 숫자형
공통데이터는 두 시점의 값, 변화량과 변화율을 함께 반환합니다.

멀티모달 계층은 파일 확장자와 실제 바이트 형식을 함께 검사합니다. 코드 구조, PNG·JPEG 크기,
WAV 재생정보와 MP4 컨테이너 검사는 로컬에서 동작합니다. 문서와 코드 프리셋은 실행 계획
준비 상태이며 이미지 생성, 음성 전사와 영상 요약은 전용 모델·런타임이 연결될 때까지
contract-only로 차단됩니다.

운영 화면은 SQLite 무결성, MCP 패키지 서명, 출처 연결, 모델 레지스트리, 승인·스토어 키와
어댑터 준비상태를 점검합니다. E2E 수용성 테스트는 외부 모델을 호출하지 않는 합성 모드에서
HWPX 분석, 실행 계획, 서명 승인, 일회용 실행, 문단 패치, 자산 보존과 감사 추적을 검증합니다.
stale-document 실패 주입으로 원본 변경 충돌 차단도 확인할 수 있습니다.

## 설치와 기동

### 실행 전제

- Linux 기준 Python 3.12 환경. 런타임 Python 패키지는 저장소 루트 `requirements.txt`의
  `uvicorn`, `cryptography`, `trafilatura`입니다.
- PDF 데이터 MCP를 사용하려면 Poppler의 `pdftotext`가 필요합니다. Ubuntu/Debian에서는
  `sudo apt install poppler-utils`로 설치하거나 `AIWORKS_PDFTOTEXT_PATH`에 실행 파일을 지정합니다.
- 기본 보고서 HWPX 생성은 Python 내장 renderer로 동작하며 Node.js/npm이 필요하지 않습니다.
  특정 vendor 문서 변환 런타임은 제품에 포함하지 않습니다. 로컬 stdio MCP가 필요하면
  [승인 프로필 예제](docs/external-mcp-profiles.example.json)를 복사해 실행 파일·허용 도구를
  지정하고 `AIWORKS_EXTERNAL_MCP_PROFILE_PATH`로 연결합니다.
- Firefox, geckodriver와 Selenium은 브라우저 회귀 테스트 전용이며 기본 서버 실행에는 필요하지
  않습니다.
- Windows 네이티브 RHWP 자동화는 별도 조건이며 [RHWP Windows 브리지](#rhwp-windows-브리지)를
  참고합니다.

### 로컬 설치

저장소 루트에서 다음과 같이 준비합니다. 기존 `.env`가 있으면 덮어쓰지 말고 필요한 AIWorks
항목만 반영합니다.

```bash
cd /home/ubuntu/apps/myservice
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
test -e .env || cp .env.example .env
```

`.env`에서 최소한 `AIWORKS_APPROVAL_SECRET`과 `AIWORKS_STORE_SIGNING_SECRET`을 서로 다른 강한
임의값으로 바꿉니다. 실제 Solar 호출이 필요할 때만 Upstage 키와 live 플래그를 설정합니다.
`.env`는 루트의 `env_utils.py`가 읽으며 이미 프로세스 환경에 있는 값은 덮어쓰지 않습니다.

### 개발 서버 기동

```bash
cd /home/ubuntu/apps/myservice
.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000
```

- 사용자 화면: `http://127.0.0.1:8000/poc/aiworks/`
- 호스트 생존 확인: `http://127.0.0.1:8000/health`
- AIWorks bootstrap: `http://127.0.0.1:8000/api/poc/aiworks/bootstrap`
- AIWorks 준비 상태: `http://127.0.0.1:8000/api/poc/aiworks/operations/readiness`

저장소에는 AIWorks 전용 systemd unit이나 nginx 운영 설정이 포함되어 있지 않습니다. 운영자는
선택한 프로세스 감독 도구에서 위 Uvicorn 명령과 로그, 비밀정보, 재시작 정책을 별도로 관리해야
합니다. 인증 계층을 추가하기 전에는 `127.0.0.1` 바인딩을 유지하고 외부에 직접 노출하지 않습니다.

## 환경변수 기준표

`값 없음`은 기능 비활성 또는 개발용 fallback을 뜻합니다. 비밀값은 README·Git·로그에 남기지
않습니다.

### 저장소·승인·파일

| 변수 | 기본값 | 의미와 운영 기준 |
|---|---|---|
| `AIWORKS_DB_PATH` | `PoC/06-AIWorks/data/aiworks.sqlite3` | SQLite DB 위치. 테스트·운영 DB를 반드시 분리 |
| `AIWORKS_ENABLE_DEMO_SEED` | `0` | 샘플 자료 생성. 운영은 항상 `0` |
| `AIWORKS_APPROVAL_SECRET` | 값 없음 | 승인 토큰 HMAC 키. 없으면 호스트/DB 기반 개발 키와 readiness 경고 |
| `AIWORKS_STORE_SIGNING_SECRET` | 값 없음 | 패키지 HMAC 키. 승인 키와 다른 값 사용 |
| `AIWORKS_APPROVAL_TTL_SECONDS` | `600` | 승인 토큰 수명, 허용 범위 60~3600초 |
| `AIWORKS_MAX_HWPX_BYTES` | `10000000` | HWPX 입력 한도, 허용 범위 1~30MB |
| `AIWORKS_MAX_ASSET_BYTES` | 코드 10MB, `.env.example` 5MB | 일반 Builder 자산 한도, 허용 범위 1~10MB |
| `AIWORKS_PDFTOTEXT_PATH` | 자동 탐색 | `pdftotext` 실행 파일의 절대 경로 |
| `AIWORKS_SOFFICE_PATH` | 자동 탐색 | PDF 파생 산출물용 `soffice`/LibreOffice 실행 파일 |
| `AIWORKS_RPO_TARGET_SECONDS` | `86400` | 비파괴 복구 훈련의 목표 RPO |
| `AIWORKS_RTO_TARGET_SECONDS` | `300` | 비파괴 복구 훈련의 목표 RTO |

ASGI 요청 본문은 15MB로 제한되고 프로젝트 백업은 압축 해제 후 50MB를 넘으면 거부됩니다. 이
두 값은 현재 환경변수로 조정하지 않습니다.

### 모델·검색

| 변수 | 기본값 | 의미와 운영 기준 |
|---|---|---|
| `UPSTAGE_API_KEY` 또는 `UPSTAGE_SECRET_KEY` | 값 없음 | Solar API 자격 증명 |
| `UPSTAGE_BASE_URL` | `https://api.upstage.ai/v1` | Upstage 호환 API 기준 URL |
| `AIWORKS_SOLAR_LIVE` | `0` | `1`일 때만 실제 Solar 호출 허용 |
| `AIWORKS_SOLAR_TIMEOUT_SECONDS` | `120` | Solar 읽기 제한, 허용 범위 5~180초 |
| `AIWORKS_MODEL_ROUTING_MODE` | `auto` | `auto` 또는 `manual` |
| `AIWORKS_DEFAULT_MODEL` | 값 없음 | manual 모드 모델 ID. 없거나 잘못된 값이면 registry 기본값 |
| `AIWORKS_RUNTIME_IDENTITY` | `service:aiworks` | 외부 모델 호출을 UI actor와 분리해 집계하는 credential identity |
| `AIWORKS_MODEL_RPM_LIMIT` | `120` | credential identity별 최근 1분 성공 호출 한도 |
| `AIWORKS_MODEL_MONTHLY_TOKEN_LIMIT` | `5000000` | credential identity별 월간 성공 token 한도 |
| `OPENROUTER_API_KEY` | 값 없음 | OpenRouter fallback 자격 증명 |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | OpenRouter 호환 API 기준 URL |
| `AIWORKS_OPENROUTER_LIVE` | `0` | `1`일 때만 실제 OpenRouter 호출 허용 |
| `AIWORKS_OPENROUTER_TIMEOUT_SECONDS` | `45` | OpenRouter 호출 제한시간 |
| `AIWORKS_HTTP_REFERER` | 값 없음 | 외부 모델 요청의 식별용 Referer |
| `AIWORKS_LOCAL_RAG_LLM` | `0` | 로컬 검색 결과를 Ollama로 종합할지 여부 |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | 로컬 Ollama 주소 |
| `AIWORKS_OLLAMA_RAG_MODEL` | `qwen2.5:1.5b` | 로컬 RAG 종합 모델 |
| `AIWORKS_OLLAMA_TIMEOUT_SECONDS` | `45` | Ollama 호출 제한시간 |

지원 Solar 모델 ID는 `upstage:solar-pro3-fast`, `upstage:solar-pro3`,
`upstage:solar-pro4`입니다. 외부 호출을 켜도 승인 계획에 `model.invoke`와 `network.send`가 없으면
전송하지 않습니다. 이전 설정 호환을 위해 `AIWORKS_SOLAR_LIVE`가 아예 없으면
`AIWORKS_OPENROUTER_LIVE` 값을 Solar live 판단에도 사용하므로, 새 환경에서는 두 플래그를 모두
명시하는 것이 안전합니다.

### MCP·RHWP

| 변수 | 기본값 | 의미와 운영 기준 |
|---|---|---|
| `AIWORKS_LOCAL_MCP_LIVE` | `1` | 승인된 고정 로컬 MCP 프로필 실행 |
| `AIWORKS_EXTERNAL_MCP_LIVE` | `0` | 외부 MCP 실호출 전역 스위치 |
| `AIWORKS_EXTERNAL_MCP_URL` | 값 없음 | Streamable HTTP 외부 MCP 주소 |
| `AIWORKS_EXTERNAL_MCP_TOKEN` | 값 없음 | 외부 MCP 인증 토큰 |
| `AIWORKS_RHWP_BRIDGE_SECRET` | 값 없음 | 서버와 Windows 브리지 공유 HMAC 키 |
| `AIWORKS_RHWP_BRIDGE_COMMAND` | 값 없음 | 예: `py PoC/06-AIWorks/rhwp_windows_agent.py` |
| `AIWORKS_RHWP_BRIDGE_TIMEOUT` | `30` | 브리지 명령 제한시간 |
| `AIWORKS_RHWP_ALLOWED_ROOTS` | 값 없음 | Windows 자동화가 접근할 허용 폴더 목록 |

브라우저 테스트는 추가로 `AIWORKS_BROWSER_URL`, `AIWORKS_API_URL`, `AIWORKS_GECKODRIVER`,
`AIWORKS_TEST_PROJECT_ID`를 사용할 수 있습니다. 이 값들은 제품 런타임 설정이 아닙니다.

## 운영 Runbook

### 기동·상태 확인

1. `.env`와 DB 경로, 저장 공간, `pdftotext`를 확인합니다.
2. Uvicorn을 시작한 뒤 다음 세 응답을 순서대로 확인합니다.

```bash
curl -sS http://127.0.0.1:8000/health
curl -sS http://127.0.0.1:8000/api/poc/aiworks/bootstrap
curl -sS http://127.0.0.1:8000/api/poc/aiworks/operations/readiness
curl -sS http://127.0.0.1:8000/api/poc/aiworks/operations/model-usage
```

`/health`의 `healthy`는 ASGI 호스트만 살아 있다는 뜻입니다. 운영 판정은 readiness의 다음 검사를
기준으로 합니다.

| readiness 검사 | 실패/경고 의미 | 조치 |
|---|---|---|
| `database.integrity` | SQLite `quick_check` 실패 | 쓰기 중지, 최근 백업 보존, 별도 DB로 복원 시험 |
| `approval.secret` | 개발용 승인 키 사용 | 운영 비밀값 설정 후 재시작 |
| `store.signing-secret` | 개발용 패키지 키 사용 | 별도 운영 비밀값 설정 후 재시작 |
| `store.signatures` | 설치/게시 패키지 변조 또는 검증 실패 | 해당 패키지 격리, 원본 버전 재게시·재설치 |
| `data-mcp.pdf-extractor` | `pdftotext` 없음 | Poppler 설치 또는 경로 지정 |
| `rhwp.runtime` | Windows 브리지 없음 | 브라우저 RHWP/HWPX fallback은 가능, 네이티브 작업만 제한 |
| `adapters.runtime` | 제3자 어댑터가 계약만 존재 | 해당 출력 형식 사용 차단 또는 어댑터 설치 |
| `knowledge.sources` | 등록 근거가 없음 | 데이터 MCP 자료 등록. 서비스 자체는 경고 상태로 기동 가능 |

`ready=false`는 하나 이상의 실패가 있다는 뜻이고, 실패 없이 경고만 있으면
`ready-with-warnings`입니다.

`operations/model-usage`는 비밀키나 프롬프트 원문 없이 credential identity·provider·model별
성공 호출 수와 입력·출력 token을 보여줍니다. 현재 한도는 RPM과 월 token의 최소 안전장치입니다.

### 프로젝트 논리 백업·복원

1. 프로젝트 설정의 거버넌스에서 백업을 내려받습니다.
2. 파일 형식이 `aiworks-project-backup`, schema version이 `1.2`이고 integrity SHA-256이 있는지
   확인합니다.
3. 복원은 프로젝트 선택 화면에서 가져오기로 수행합니다. 복원 결과는 항상 새 프로젝트 ID입니다.
4. MD revision, 메타정보, 파생/범용 Artifact, 관계와 Evidence 수를 원본과 비교합니다.

논리 백업은 다른 환경으로 프로젝트를 옮길 때 권장됩니다. 비밀키, 서버 환경변수와 전체 감사
운영 이력은 프로젝트 백업에 포함된다고 가정하지 않습니다.

### 전체 SQLite 백업·복원

WAL 모드 DB 파일 하나만 실행 중에 복사하면 최신 트랜잭션이 빠질 수 있으므로
`scripts/sqlite_live_restore_drill.py`의 SQLite Online Backup API 기반 절차를 사용합니다.

1. 온라인 백업만 만들 때는 `python3 PoC/06-AIWorks/scripts/sqlite_live_restore_drill.py --db <절대경로> --backup-dir <접근제한경로>`를 실행합니다.
2. 실복원 훈련은 새 쓰기 요청을 막고 Uvicorn을 정상 종료한 뒤 `--apply-live-swap --confirm-path <동일한 절대경로>`를 추가합니다.
3. 도구는 포트가 열려 있으면 덮어쓰기를 거부하고, 원본·백업의 `quick_check`, schema digest,
   논리 행/BLOB digest를 대조한 뒤에만 원자 교체합니다.
4. 교체 전 원본 DB와 WAL/SHM은 `aiworks-displaced-original-*` 및 시각 표시 사본으로 보존되며,
   실패하면 원본으로 자동 롤백합니다.
5. 서버를 다시 시작하고 readiness, 대표 프로젝트, manifest의 `restored` digest와 RPO/RTO를 확인합니다.

2026-09-04 운영 DB 실복원 훈련은 54개 테이블·3,137행, RPO 0초, 2.90초로 완료했고 schema 및
논리 digest가 복원 전후 일치했습니다. 원격 복제와 객체 저장소 백업은 아직 별도 운영 범위입니다.

### 배포 전후 점검

1. 프로젝트 논리 백업과 전체 DB 백업을 확보합니다.
2. 별도 테스트 DB로 단위·통합 테스트와 필요한 브라우저 smoke를 실행합니다.
3. 변경된 `contracts/*.schema.json`의 호환성과 DB migration을 확인합니다.
4. 서버 재기동 후 health, bootstrap version, readiness를 확인합니다.
5. 프로젝트 복원, 기존 MD 열기, 탭 이동 무변경, 데이터 MCP 검색, MD→HWPX, HWPX→MD 충돌
   흐름을 대표 프로젝트로 확인합니다.
6. Uvicorn stdout/stderr와 `audit_events`에서 반복 오류나 승인 우회를 점검합니다.

## 문제 해결

| 증상 | 우선 확인 | 조치 |
|---|---|---|
| `PDF 추출기가 설치되지 않음` | readiness의 `data-mcp.pdf-extractor` | Poppler 설치 또는 `AIWORKS_PDFTOTEXT_PATH` 지정 후 재기동 |
| PDF를 올렸지만 검색 청크 0개 | 암호화, 이미지 스캔, 추출 가능 텍스트 | 텍스트 PDF로 바꾸거나 OCR MCP 연결. 빈 데이터 MCP는 게시하지 않음 |
| Solar read timeout | 키, live 플래그, 네트워크, 120초 기본 제한 | 제한을 최대 180초 안에서 조정하고 새 계획·승인으로 재시도 |
| `현재 RHWP 문서 세션이 없음` | 프로젝트와 활성 MD/HWPX 세션 | 프로젝트를 선택하고 MD를 열거나 생성한 뒤 양식/수정 실행 |
| 양식 적용 결과에 예시 문구·기호가 남음 | 슬롯 매핑, 목록 prototype, quality gate | 매핑 Studio에서 고정/가변 영역을 수정하고 실렌더링 재검증 후 새 버전 게시 |
| 양식 기준 파일이 여러 개 보임 | 현재 draft의 `template-source` | 새 업로드가 이전 기준을 교체하는지 확인하고 불필요 reference를 삭제 |
| 매핑 저장 불가 | `{{title}}`, `{{content}}`/`{{body}}`, 서로 다른 슬롯 | 필수 슬롯과 실제 HWPX 위치를 지정하고 quality 결과 확인 |
| `동일 MCP가 이미 게시됨` | package ID·version, Store 기존/사용자 제작 패키지 | 기존 패키지를 `수정`해 다음 patch 초안을 만들거나 새 ID/version 사용 |
| Store에서 삭제가 보이지 않음 | 기본 내장/사용자 제작 여부와 권한 | 사용자 제작 버전만 삭제 가능. 내장 MCP는 버전 고정/비활성으로 관리 |
| 프로젝트 삭제 후 사라짐 | 보관 프로젝트 목록 | 다시 사용할 경우 `복원`, 모든 데이터를 지울 경우 프로젝트 이름을 입력하고 `완전 삭제` 실행 |
| 탭 이동 후 문서가 바뀌거나 누적됨 | revision/SHA, 브라우저 캐시, 네트워크의 생성 API | 탭 전환은 GET만 발생해야 함. 새 생성 요청을 중단하고 마지막 정상 revision 재선택 |
| `stale` | MD가 파생 문서보다 최신 | 현재 MD에서 새 파생 산출물 생성 |
| `diverged` | RHWP 변경이 MD에 미반영 | 전후 비교 후 HWPX→MD 반영 또는 HWPX 변경 폐기 |
| `conflict` | 양쪽 revision 모두 변경 | 블록별로 선택 해결. 자동 덮어쓰기 금지 |
| 승인 만료·재사용 오류 | 10분 TTL, 토큰 일회성 | 동일 토큰 재사용 없이 계획과 승인을 다시 생성 |
| readiness `not-ready` | `checks`의 failure 항목 | 실패 항목을 먼저 해결. 경고만 있는 상태와 구분 |

## 현재 제약과 운영 경계

- 현재 배포 단위는 단일 프로세스·단일 노드 SQLite PoC입니다. 다중 인스턴스 동시 쓰기, 작업 큐,
  객체 저장소, 자동 failover를 제공하지 않습니다.
- AIWorks API 자체에는 인증된 사용자/SSO 경계가 없습니다. 요청의 actor 기반 RBAC을 신뢰할 수
  없는 외부 사용자 권한 통제로 사용하면 안 됩니다.
- 보관 프로젝트의 즉시 완전 삭제는 지원하지만, 법적 보존기간·파기 승인·보존 예외를 자동 집행하는
  운영용 레코드 보존 워크플로는 아직 없습니다.
- 전체 DB 온라인 백업, 자동 백업 스케줄, RPO/RTO 보장은 없습니다.
- HMAC 패키지 서명은 PoC 공급망 검증용입니다. 게시자 신원과 키 회전을 보장하는 운영 서명이
  아닙니다.
- PDF 입력은 텍스트 추출, 출력은 격리 LibreOffice 렌더링을 지원하지만 OCR은 아직 없습니다. 복잡한 HWPX의 도형·글상자·머리말·꼬리말, 중첩 목록과 병합표는 의미 왕복 시 손실 가능성이 있습니다.
- 브라우저 RHWP는 자체 호스팅 fallback입니다. 한컴오피스와 완전히 동일한 레이아웃·HAction이
  필요하면 Windows 브리지가 필요합니다.
- DOCX·ODT·XLSX는 의미 기반 입출력이며 PDF는 출력 전용입니다. 부유 개체, 추적 변경, 각주·주석까지 보존하는 모든 제3자 형식의 고충실도 양방향 변환은 아직 구현되지 않았습니다.
- 이미지 생성·음성 전사·영상 요약 일부는 계약만 있고 런타임이 없어 readiness 경고 또는 실행
  차단이 정상입니다.
- 실제 외부 모델은 네트워크·제공자 지연과 요금 정책에 영향을 받습니다. timeout을 성공 결과로
  처리하지 않으며 민감 프로젝트는 외부 전송하지 않습니다.
- 저장소에는 운영용 reverse proxy, TLS, systemd unit, 중앙 로그·메트릭·경보 설정이 없습니다.
  운영 배포 전에 조직 표준 인프라로 보완해야 합니다.

## Solar 자동 라우팅과 전송 경계

- Solar Pro 3 Fast: 단순 조회·확인·짧은 요약
- Solar Pro 3: 문서 작성·문장 편집·RAG 근거 종합
- Solar Pro 4: 복합 비교·계산·정책·법률 검증

의도 분석 MCP는 사용자 요청을 로컬에서 먼저 분류하고 모델 관리 MCP가 위 세 모드를 자동으로
선택합니다. 새 보고서·계획서·초안을 처음 생성하는 요청은 품질을 우선해 Solar Pro 4를
기본 선택하며, Store의 `의도 분석 MCP → 환경설정`에서 Pro 4·Pro 3·Fast·자동 판단으로 바꿀 수 있습니다.
Solar 실호출은 `AIWORKS_SOLAR_LIVE=1`과 Upstage 키가 설정되고 실행 계획에서 `model.invoke`와
`network.send`를 명시 승인한 요청만 Upstage API로 전송합니다. 기본 환경 예시는 비활성입니다.
데이터 MCP 기반 최초 보고서는 검색 근거를 Solar Pro 4가
종합하고 인용 검증을 통과한 본문을 편집 가능한 HWPX로 만듭니다. 승인을 거부하거나 실행기가
비활성이면 로컬 근거 보고서로 동작하며, `confidential`·`personal` 문맥은 외부 모델로 라우팅하지 않습니다.

## 경로

- 독립 화면: /poc/aiworks/
- 포트폴리오 셸: /poc?project=aiworks
- 계약: contracts/*.schema.json
- 프로젝트 중심 플랫폼 전환 로드맵: [docs/PROJECT_PLATFORM_ROADMAP.md](docs/PROJECT_PLATFORM_ROADMAP.md)
- Phase 3 KORDOC/KODAK 퇴역 수행 결과: [docs/PHASE3_ACCEPTANCE_2026-09-04.md](docs/PHASE3_ACCEPTANCE_2026-09-04.md)
- 현재 구조·호환 경계: [docs/CURRENT_ARCHITECTURE_AND_BOUNDARIES.md](docs/CURRENT_ARCHITECTURE_AND_BOUNDARIES.md)
- 대표 업무 Golden Workflow: [docs/GOLDEN_WORKFLOW_SPEC.md](docs/GOLDEN_WORKFLOW_SPEC.md)
- Golden Workflow 실행기: [golden_workflows/README.md](golden_workflows/README.md)
- 2026-08-19 구현·수용성 검증과 테스트법: [docs/ACCEPTANCE_REPORT_2026-08-19.md](docs/ACCEPTANCE_REPORT_2026-08-19.md)
- 양식 MCP 정석화 진행상태: [docs/TEMPLATE_MCP_STANDARD_PLAN.md](docs/TEMPLATE_MCP_STANDARD_PLAN.md)
- 1~17단계 PoC 구축 이력: [docs/BUILD_PLAN.md](docs/BUILD_PLAN.md)
- 서버 API: /api/poc/aiworks/bootstrap

## 주요 계약과 모듈

- 프로젝트·문서: `project-policy`, `project-backup`, `project-markdown-document`, `project-document-workbench`
- 범용 산출물: `artifact`, `artifact-relation`, `artifact-evidence`와 불변 Version 계보
- 실행·권한: `workflow-recipe`, `workflow-run`, `capability-binding`, `permission-grant`
- 문서 변환: `report-document`, `document-format-adapter`, `document-session`
- MCP 패키지: `mcp-manifest`, `mcp-draft`와 선택적 환경설정 계약
- Python 구현: `mcp/workspace_orchestration.py`, `report_document.py`, `report_hwpx.py`,
  `rewrite_output.py`, `template_mois_report.py`, `template_report_style.py`

JSON Schema는 `contracts/`가 원본이며 API·UI는 같은 계약의 ID와 revision을 사용합니다. 프로젝트
백업은 Markdown revision, 메타정보, 프로젝트 자료 Artifact·검색 인덱스·관계와 Evidence를 SHA-256으로 검증하고 기존
프로젝트를 덮어쓰지 않는 새 ID로 복원합니다.

## 서버 실행 흐름

1. POST /api/poc/aiworks/plans
2. POST /api/poc/aiworks/approvals
3. POST /api/poc/aiworks/executions
4. GET /api/poc/aiworks/audit
5. POST /api/poc/aiworks/routing/test
6. POST /api/poc/aiworks/documents/analyze-hwpx
7. POST /api/poc/aiworks/documents/apply-hwpx
8. GET /api/poc/aiworks/documents/versions
9. GET /api/poc/aiworks/store/packages
10. POST /api/poc/aiworks/store/install
11. POST /api/poc/aiworks/store/rollback
12. GET /api/poc/aiworks/knowledge/graph
13. POST /api/poc/aiworks/knowledge/query
14. POST /api/poc/aiworks/knowledge/compare
15. POST /api/poc/aiworks/knowledge/notes
16. GET /api/poc/aiworks/workflows/presets
17. POST /api/poc/aiworks/workflows/plan
18. POST /api/poc/aiworks/assets/inspect
19. GET /api/poc/aiworks/operations/readiness
19-a. GET /api/poc/aiworks/operations/model-usage
20. POST /api/poc/aiworks/acceptance/budget-request
21. GET /api/poc/aiworks/acceptance/runs
22. GET·POST /api/poc/aiworks/builder/drafts
23. POST /api/poc/aiworks/builder/drafts/{draft_id}/validate
24. POST /api/poc/aiworks/builder/drafts/{draft_id}/publish
25. POST /api/poc/aiworks/builder/drafts/{draft_id}/references
26. POST /api/poc/aiworks/builder/drafts/{draft_id}/rag/query
27. GET·POST /api/poc/aiworks/documents/workspace
28. GET /api/poc/aiworks/documents/workspace/{workdoc_id}
29. GET /api/poc/aiworks/documents/versions/{docver_id}
30. GET /api/poc/aiworks/rhwp/capabilities
31. POST /api/poc/aiworks/rhwp/invoke
32. POST /api/poc/aiworks/documents/sessions
33. GET /api/poc/aiworks/documents/sessions/{docsession_id}
34. POST /api/poc/aiworks/documents/sessions/{docsession_id}/commands
35. GET /api/poc/aiworks/documents/sessions/{docsession_id}/artifact
36. GET·POST /api/poc/aiworks/builder/drafts/{draft_id}/template-mapping
37. GET /api/poc/aiworks/builder/drafts/{draft_id}/template-quality
38. GET /api/poc/aiworks/builder/drafts/{draft_id}/template-sample
39. POST /api/poc/aiworks/builder/drafts/{draft_id}/template-authoring/session
40. POST /api/poc/aiworks/builder/drafts/{draft_id}/template-authoring/commit

위 목록은 초기 실행·문서·Builder 경계의 대표 흐름입니다. 아래 경로도 모두
`/api/poc/aiworks` 아래에 있으며, 0.31.2에서 추가된 프로젝트 플랫폼 API를 다음 범주로 관리합니다.

- `GET /projects/{id}/backup`, `POST /projects/import`: SHA-256 프로젝트 백업·비파괴 복원
- `GET|POST /projects/{id}/sources`, `DELETE /projects/{id}/sources/{sourceId}`, `POST .../reindex`,
  `POST /projects/{id}/sources/query`: 프로젝트 자료 원본·검색 인덱스 생명주기와 근거 검색
- `GET /projects/{id}/governance`, `POST /projects/{id}/members`, `policy`, `grants`, `status`: 멤버십·정책·권한·보관 상태
- `GET|POST /projects/{id}/artifacts`, `POST /projects/{id}/artifact-relations`, `GET|POST /projects/{id}/artifact-evidence`: 범용 산출물 계보와 근거
- `GET|POST /recipes`, `POST /recipes/search`, `POST /recipes/{id}/fork`, `deprecate`, `POST /projects/{id}/recipes/{id}/install`: Workflow Recipe 생명주기
- `POST /store/install-preview`: 설치 버전과 현재 버전의 권한·외부전송·보존정책 diff와 승인 해시
- `POST /projects/{id}/documents/{documentId}/quality-review`: 현재 MD의 block별 품질 점검·선택 보완 계획
- `GET /operations/metrics/prometheus`, `GET /operations/metrics/otlp`: Prometheus text·OTLP JSON exporter
- `POST /operations/projects/{id}/recovery-drill`, `GET /operations/sbom`, `GET /audit/integrity`: 비파괴 복구 훈련·CycloneDX SBOM·감사 해시 체인 검증

## RHWP Windows 브리지

1. Windows에 한컴오피스와 Python을 설치하고 `py -m pip install pywin32`를 실행합니다.
2. AIWorks 서버와 브리지에 동일한 `AIWORKS_RHWP_BRIDGE_SECRET`을 지정합니다.
3. `AIWORKS_RHWP_ALLOWED_ROOTS`에는 자동화가 접근할 문서 폴더만 지정합니다.
4. `AIWORKS_RHWP_BRIDGE_COMMAND=py PoC/06-AIWorks/rhwp_windows_agent.py`로 설정합니다.
5. 설정 화면에서 `설치 v1.0.0 · Windows 연결됨`을 확인합니다.
6. 출시 전 Windows에서 `py PoC/06-AIWorks/scripts/windows_rhwp_acceptance.py --ordinary <일반.hwpx> --budget <예산.hwpx> --ordinary-term <기대문구> --budget-term <기대문구> --output-dir <증적폴더>`를 실행하고 `windows-rhwp-acceptance.json`의 `status=passed`와 증적 SHA-256을 보존합니다.

브리지는 요청마다 HMAC, 30초 만료와 nonce 재사용 방지를 검사합니다. 매크로·쉘·네트워크·OLE
액션은 차단하며 문서 변경 도구는 `document.write` 권한과 명시적 확인이 모두 필요합니다.
고수준 도구에 없는 표·개체·글자/문단 모양·쪽/구역 기능은 `rhwp.document.action`에서
RHWP의 HAction과 HParameterSet을 그대로 사용합니다.
MCP 제작기 상단의 `◎ 처음부터 따라하기`를 누르면 언제든 5단계 시각 안내를 열 수 있습니다.
유형 카드 선택, 파일 놓기와 입력, 실제 검증, 게시·설치, 자연어 호출 시험을 화면 모형으로 한
단계씩 보여줍니다. `예시로 시작`은 안전한 일반 도구 초안을 채우고, `이 화면에서 해보기`는
안내를 닫은 뒤 현재 단계의 실제 입력란으로 이동하여 초보자도 설명서를 외우지 않고 진행할 수
있습니다.


## MCP 제작기 사용 순서

1. MCP 제작기에서 양식·처리·데이터·일반 도구·외부 MCP 연결 유형을 고르고 이름, 업무 설명, 공개 범위와 외부 전송 여부를 입력해 새 초안을 생성합니다.
2. 기준 문서 첨부에서 HWPX, PDF, DOCX, ODT, XLSX, Markdown 또는 TXT 파일을 선택합니다.
   데이터 MCP는 `검색 데이터 원본` 역할로 여러 파일을 선택하고 `등록 자료 RAG 미리보기`에서 질문·근거·페이지를 확인합니다.
   양식 MCP는 `양식 원본` HWPX 한 개를 받으며, 기존 기준 파일을 교체하고 플레이스홀더,
   작성요령·예시, 빈칸 또는 완성 보고서 구조를 즉시 자동 추출합니다.
3. 양식 MCP는 `MD↔HWPX 매핑 수정`을 열어 왼쪽 MD 내용 계약과 오른쪽 RHWP HWPX를 함께
   확인합니다. 제목·본문은 필수이며 목록·담당부서·작성자·문서번호·결재란은 필요할 때
   지정합니다. 저장 시 실제 보고서를 렌더링하고 다시 파싱하여 양식 구조를 검증합니다.
4. Manifest와 문서 해시를 확인하고 샌드박스 계약 테스트를 실행합니다.
5. 검증 통과 후 스토어 등록을 누르면 공개 범위와 원본 포함 선택대로 서명 게시됩니다.
6. 스토어에서 권한을 확인하고 정확한 버전을 고정 설치합니다. 설치된 양식 MCP는
   `<MCP 이름> 적용해줘`라는 요청으로 활성 프로젝트 MD에 적용할 수 있습니다.
7. 등록된 양식을 고칠 때는 MCP 제작기에서 `양식 MCP`를 선택한 뒤 `등록된 양식 MCP 수정`
   콤보에서 대상을 고르고 `수정 초안 열기`를 누릅니다. 원본 HWPX, MD 매핑, 구조 역할과
   실검증 결과를 보존한 다음 patch 버전 초안이 열립니다. 이미 열린 수정 초안이 있으면 새로
   만들지 않고 그대로 재개합니다. 스토어 카드의 `수정`도 같은 경로를 사용합니다.
   `삭제`는 사용자 제작 버전만 확인 후 제거하고 초안은 남깁니다.
   설정 계약이 있는 MCP는 `환경설정`에서 운영값을 저장하며, 저장값은 다음 실행 계획부터 적용됩니다.
8. 외부 MCP 연결은 승인된 로컬 stdio 프로필 또는 Streamable HTTP를 선택하고 도구명·Capability·입출력 어댑터를 `tools/list`로 확인합니다. 로컬 프로필은 임의 명령을 받지 않고 고정 버전만 실행하며, 원격 실행은 매번 전송 승인을 거칩니다.
9. 기본 HWPX 출력은 설치된 `document.report-hwpx@0.1.0`이 ReportDocument의 제목·목록·표 구조를
   보존해 생성합니다. 외부 formatter는 코어 경로에서 자동 실행하지 않으며, 운영자 승인 프로필
   또는 Streamable HTTP Manifest를 Builder에서 별도로 등록·검증한 경우에만 사용할 수 있습니다.

## 향후 해야 할 일

아래 항목은 현재 PoC에서 아직 운영 수준으로 닫히지 않은 범위입니다. 세부 단계 상태의 기준 문서는
[프로젝트 플랫폼 로드맵](docs/PROJECT_PLATFORM_ROADMAP.md)이며, README에는 제품 검증 순서에 따른
우선순위만 유지합니다.

### P0 · 다음 검증 단계

완료된 안정화 기준선: 프로젝트 자료 영속·검색·삭제·재색인·백업, 독립 대화·결정 복원, 첫 화면
다중 첨부, 기본/고급 화면 계층, 후보 MCP 비교, 단일 실행 lease와 최종 행위 확인, 실제 외부 전송
자료명·제공자 표시. 아래 항목은 그 위에 쌓을 문서·양식 정밀화 범위입니다.

- [ ] **복잡한 HWPX 양식 추출 정확도 강화**: 다중 section, 머리말·꼬리말, 글상자·도형 내부
  텍스트, 배경 이미지, 여러 표와 결재표가 섞인 실문서 fixture를 확대하고 잘못 지운 예시 문구가
  없는지 자동 비교합니다. 기능 inventory와 스캔 이미지 중심 문서 OCR 차단은 구현됐고, 익명화된
  실문서 fixture 확대가 남아 있습니다.
- [ ] **매핑 Studio 정밀 보정**: 현재 문단 선택형 매핑을 RHWP 문단·표 셀 하이라이트와 양방향
  선택 연동으로 확장합니다. 반복 section·조건부 영역·표 반복자와 병합 셀 좌표 저장은 구현됐고,
  RHWP 캔버스의 시각적 양방향 하이라이트가 남아 있습니다.
- [x] **TemplateSchema 1.2와 호환성 선언**: 필수/선택 슬롯, 반복자, 조건부 block, 기본값,
  플랫폼 최소 버전·migration·scan/OCR 경계와 독립 JSON Schema 계약을 구현했습니다.
- [-] **MD↔HWPX 의미 왕복 손실 최소화**: 매핑된 문단·표 셀의 변경 블록 비교와 선택 승격은
  구현했습니다. 중첩 목록, 병합표, 셀 내부 여러 문단, 각주·주석·캡션, 링크와 메타 필드까지
  Render Map을 확장하는 작업이 남아 있습니다.
- [ ] **실무 양식 평가 세트 구축**: 서로 다른 기관·부서의 완성본/빈칸/작성요령 HWPX를 익명화한
  golden set으로 만들고 제목·본문·목록·표 매핑률, 예시 잔존, 내용 손실, 재현성을 release gate로
  측정합니다.
- [x] **문서 품질 하네스 고도화**: 질문·주제·연도·대상·근거·숫자·메타 충돌을 block 단위로 설명하고 repair plan을 생성합니다. 변경 이력 탭에서 실패 항목과 블록을 선택하면 표준 승인·Solar 흐름으로 새 MD revision을 만듭니다.

### P1 · 플랫폼 핵심 고도화

- [-] **동적 Planner/Resolver 완성**: Builder 유형별 Artifact I/O 계약과 Capability DAG를 이용한
  Data·Process·Template 자동 조합, 후보 MCP의 품질·비용·지연·데이터 등급·프로젝트 선호 비교와
  선택 이유 표시는 구현했습니다. 남은 범위는 기존 keyword fallback 완전 제거와 Recipe 시각 조합입니다.
- [x] **프로젝트 대화·결정 독립 엔터티화**: 대화, 메시지, 사용자 결정, 승인 근거와 문서 revision의
  관계를 영속화하고 backup 1.2로 다른 환경에서도 복원합니다.
- [ ] **제3자 형식 양방향 어댑터**: DOCX·PDF·XLSX·ODF 등 `document.format.convert.*` MCP를
  동일한 Artifact 계약으로 설치합니다. DOCX·XLSX·ODT 의미 입출력과 PDF 실제 출력·손실 계약이 구현됐습니다. 남은 범위는 복잡한 부유 개체·추적 변경까지 보존하는 고충실도 외부 어댑터입니다.
- [x] **권한 실행기 고도화**: 프로젝트 Grant, 10분 단일 소비 JIT lease, 개인정보·비밀값 자동 마스킹, 최종 행위 확인과 MCP 업데이트 권한·외부전송 diff 해시 재승인을 구현했습니다.
- [x] **MCP 평가·운영 정보 표준화**: 성공률, 평균 지연, 모델·도구 비용, 회귀 테스트, 라이선스,
  데이터 보존·보안·호환성 결과를 패키지 버전별로 저장하고 Resolver와 Store에 반영했습니다.
- [-] **Core 모듈 분리**: Context Assembler, Task Compiler, Capability Resolver를 독립 순수 모듈과
  JSON Schema로 분리했습니다. 남은 큰 `backend.py`와 `web/app.js`의 도메인별 이전을 계속합니다.

### P2 · 운영 배포와 생태계

- [ ] **다중 사용자 운영 저장소**: SQLite·로컬 blob 기반 PoC를 트랜잭션 DB, 객체 저장소와 작업
  queue로 분리하고 조직·프로젝트 단위 격리, 동시 편집 부하와 장애 복구를 검증합니다.
- [ ] **운영 보안**: CycloneDX SBOM endpoint와 감사 이벤트 SHA-256 해시 체인·무결성 검증은 구현했습니다. 남은 범위는 HMAC 패키지 서명을 게시자별 비대칭 서명/KMS로 교체하고 외부 MCP sandbox, 취약점 DB 연동과 비밀정보 회전을 운영 인프라에 연결하는 일입니다.
- [ ] **관찰성·복구**: Workflow/Step trace, 모델·MCP 지연과 비용, 실패 재시도, 백업·복원 RPO/RTO,
  대용량 문서 처리 한계와 장기 실행 취소를 운영 대시보드와 경보로 검증합니다. 로컬 운영 지표 API와
  화면, Prometheus text, OTLP JSON, 프로젝트별 비파괴 복구 훈련과 RPO/RTO 측정은 구현됐습니다. 외부 경보 연결과 동시 부하·장애 복구 시험은 배포 과제입니다.
- [ ] **MCP/Recipe 공유 생태계**: 사용자 제작 UI contribution, 조합형 Recipe 시각 편집, 조직 승인
  워크플로, 공개 패키지 검증·평가·포크·폐기 정책을 완성합니다.

### 완료 판단 기준

- 기능 구현뿐 아니라 계약·마이그레이션·권한·감사·회귀 테스트와 실패 복구가 함께 완료되어야 합니다.
- 대표 실문서 golden set과 브라우저 E2E를 통과하지 않은 항목은 완료로 표시하지 않습니다.
- 자동 변환 결과가 불확실하면 조용히 잘못 적용하지 않고 사용자 검토 또는 명시적 차단으로 전환합니다.
- 운영 단계 전에는 프로젝트 간 데이터 격리, 외부 전송 승인, 패키지 공급망 검증과 백업 복원을
  별도 보안·부하 시험으로 통과해야 합니다.

## 검증

2026-09-04 현재 백엔드 단위·통합·계약 테스트 154개가 통과합니다. 별도의 Golden Workflow 실행기는
예산·사업 검토 시나리오의 계획, 승인, 로컬 실행, 근거 검색, Markdown, HWPX, 명시적 왕복 동기화와
감사 해시 체인을 58개 검사로 검증합니다. 기존 회귀 테스트에는 vendor 런타임 없이
내장 ReportDocument→HWPX renderer가 표와 중첩 목록을 보존하는 검사, renderer 실패 시 Markdown
안전 저장, Intent/Context/Task/Resolver 계약 경계, credential 해시별 호출 전 token·비용 예약과
성공·실패 정산, Builder 시각 매뉴얼 정적 계약이 포함됩니다. 추가된 수직 통합 검사는 사용자 제작
Data·Process·Template MCP의 한 요청 조합 실행, 작성요령·예시 제거, 실제 `form-002.hwpx`의 표 첫
셀 제목 오인 방지와 500번째 이후 슬롯 보존, 선택 HWPX 변경 블록만 최신 MD에 병합하는 흐름을 포함합니다.
양식 MCP 사용법, Solar Pro 4 설정, 5단계 초보자 매뉴얼, 양식 수정 진입과 5개 Builder 유형을
실제 DOM에서 확인했습니다. `project_workbench_smoke.py`도 격리 프로젝트를 대상으로 통과하여
마지막 문서·대화·분할 비율 복원, 정적 탭 격리, 양식 기본값, 명시적 MD→HWPX/HWPX→MD와 최종
산출물 저장을 확인한 뒤 테스트 데이터를 정리했습니다. `builder_flow_smoke.py`는 일반 HWPX의
양식 자동 추출, 실제 내용 확인 화면의 RHWP 수정본 전송·초안 반영, 분할 매핑·실렌더링·샌드박스
검증을, `data_mcp_flow_smoke.py`는 PDF 색인·RAG
미리보기·Resolver·게시·설치·근거 답변·RHWP 보고서 열기를 통과했습니다. 전체 Firefox 스모크
14종을 새 데모-seed 격리 DB에서 통과했습니다. `범정부AI 공통기반` 질의는 관련·무관 근거를 함께
등록한 독립 fixture에서 관련 근거만 선택하고, 이어지는 일반형 `보고서를 HWP로 만들어줘` 요청이
새 검색으로 재바인딩되지 않고 직전 답변을 HWPX로 승격하는 것까지 확인했습니다. HWP/HWPX/RHWP
요청은 보고서 내용이 아닌 산출 형식으로만 처리하며 사용법 문구는
최종 Markdown과 HWPX에서 제외됩니다. 테스트가 만든 업무 fixture는 종료 시 정리하지만 감사 이벤트는 해시 체인
보존을 위해 삭제하지 않습니다. Windows RHWP 실환경 검증은 별도 release gate로 남아 있으므로
이 결과만으로 운영 완료를 뜻하지는 않습니다.

같은 날 새 격리 DB의 readiness는 `ready-with-warnings`(통과 10, 경고 3, 실패 0)이었습니다.
기존 개발 DB의 과거 스모크 정리로 생긴 감사 체인 불일치 4건은 승인된 유지보수로 복구했고,
1,349개 이벤트 전체 무결성과 readiness `ready-with-warnings`(통과 7, 경고 6, 실패 0)을
확인했습니다. 이어서 `demo-user` 테스트 계획 4건과 존재하지 않는 `project-default`의 후보
메타정보 9건만 백업 후 정리했으며 실제 프로젝트와 설치된 예산 MCP는 보존했습니다.
개발 DB 경고는 지식 출처 미등록, 개발용 키, Windows RHWP·승인 stdio 프로필
미설정과 이미지·오디오·비디오 어댑터의 계약 전용 상태입니다. 이는 핵심 PoC를 시험할 수 있다는
뜻이지 운영 보안 준비가 끝났다는 뜻은 아닙니다.

    python3 -m unittest discover -s PoC/06-AIWorks/tests -v
    python3 -m py_compile PoC/06-AIWorks/backend.py
    node --check PoC/06-AIWorks/web/app.js
    .venv/bin/python PoC/06-AIWorks/tests/browser_smoke.py
    .venv/bin/python PoC/06-AIWorks/tests/builder_flow_smoke.py
    .venv/bin/python PoC/06-AIWorks/tests/data_mcp_flow_smoke.py
    .venv/bin/python PoC/06-AIWorks/tests/feedback_flow_smoke.py
    .venv/bin/python PoC/06-AIWorks/tests/project_portability_smoke.py
    .venv/bin/python PoC/06-AIWorks/tests/project_workbench_smoke.py
    .venv/bin/python PoC/06-AIWorks/tests/project_delete_smoke.py
    .venv/bin/python PoC/06-AIWorks/tests/project_source_smoke.py
    .venv/bin/python PoC/06-AIWorks/tests/mcp_plan_explanation_smoke.py
    .venv/bin/python PoC/06-AIWorks/tests/rhwp_embedded_recovery_smoke.py
    .venv/bin/python PoC/06-AIWorks/tests/rhwp_toolbox_smoke.py
    .venv/bin/python PoC/06-AIWorks/tests/store_builder_smoke.py
    .venv/bin/python PoC/06-AIWorks/tests/studio_runtime_smoke.py

운영 DB에는 샘플 지식과 기준정보를 넣지 않는다. `AIWORKS_ENABLE_DEMO_SEED=0`이 기본값이며,
데모 전용 임시 DB에서만 `1`로 설정한다. 브라우저 스모크도 별도 `AIWORKS_DB_PATH` 서버에서 실행해야 한다.
`project_workbench_smoke.py`는 예외적으로 자신이 만든 문서·세션·메타 후보를 종료 시 자동 삭제하고 이전
작업공간 상태를 복원하되 감사 이벤트는 삭제하지 않는다.

누적된 명시적 테스트 fixture는 먼저 dry-run으로 확인하고 적용 시 자동 백업 후 정리한다.

    python3 PoC/06-AIWorks/scripts/cleanup_test_data.py
    python3 PoC/06-AIWorks/scripts/cleanup_test_data.py --apply

감사 이벤트는 fixture 정리에서도 삭제하지 않습니다. 사고로 체인이 손상된 경우에만 운영자 명시
승인과 백업을 거쳐 아래 break-glass 도구를 사용합니다. 기본 실행은 읽기 전용 dry-run이며
`--apply`는 온라인 백업 후 기존 이벤트의 본문·순서·ID를 보존한 채 체인 해시만 복구하고
`audit.chain_repaired` 이벤트를 추가합니다.

    python3 PoC/06-AIWorks/scripts/repair_audit_chain.py
    python3 PoC/06-AIWorks/scripts/repair_audit_chain.py --apply

제품명은 가칭이며 폴더는 요청대로 PoC/06-AIWorks를 사용합니다.
