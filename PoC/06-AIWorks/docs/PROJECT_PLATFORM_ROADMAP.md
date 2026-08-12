# AIWorks 프로젝트 중심 플랫폼 전환 로드맵

> 문서 역할: AIWorks의 제품 방향과 18단계 이후 구현 순서를 관리하는 기준 문서(Source of Truth)
>
> 최종 갱신: 2026-08-12
> 현재 기준선: `BUILD_PLAN.md` 1~17단계 완료
> 현재 진행 단계: 18단계 준비
> 문서 상태: 확정된 방향 / 구현 전

## 진행 현황 요약

| 단계 | 상태 | 핵심 결과 |
|---|---|---|
| 1~17 | 완료 | 편집기, 승인·감사, MCP 제작·스토어, 문서 버전과 지식 계층 PoC |
| 18 | 준비 | 프로젝트 컨텍스트 커널 |
| 19 | 미착수 | 범용 산출물과 계보 |
| 20 | 미착수 | 프로젝트 Fact Registry와 충돌 관리 |
| 21 | 미착수 | Capability 계약과 Registry |
| 22 | 미착수 | 동적 Planner와 영속 Workflow Runtime |
| 23 | 미착수 | 프로젝트 권한·정책과 동적 MCP 로딩 |
| 24 | 미착수 | 범용 파생 산출물과 문맥 편집 |
| 25 | 미착수 | MCP Studio vNext |
| 26 | 미착수 | MCP·업무 레시피 공유 생태계 |
| 27 | 미착수 | 운영 안정화와 확장성 검증 |

## 1. 제품 정의

AIWorks는 특정 업무를 미리 구현한 자동화 서비스가 아니다.

AIWorks는 프로젝트 안에 원천자료, 대화, 결정, 메타정보와 산출물의 계보를 지속적으로 축적하고,
사용자의 새로운 요청마다 필요한 Capability를 해석하여 적합한 MCP를 동적으로 로딩·조합하는
확장형 업무 운영 플랫폼이다. 사용자는 프롬프트형, 조합형 또는 코드형 MCP를 손쉽게 만들고
개인·프로젝트·조직·공개 범위로 공유하여 플랫폼의 기능을 계속 확장할 수 있어야 한다.

핵심 순환은 다음과 같다.

```text
사용자 요청
  → 프로젝트 문맥 조립
  → 목표·산출물·필요 Capability 계획
  → MCP 탐색·정책 검사·승인·버전 고정
  → 실행·검증·산출물 저장
  → 메타정보 후보 추출·충돌 처리
  → 프로젝트 문맥과 산출물 계보 갱신
  → 다음 파생 산출물에서 재사용
```

영수증 처리, 사업계획서, 예산요구서 등은 이 구조를 검증하기 위한 예시 시나리오일 뿐
Platform Core의 데이터 모델이나 실행 계획에 업무명으로 고정하지 않는다.

## 2. 변경하지 않을 제품 원칙

1. 모든 대화, 자료, 실행과 산출물은 프로젝트에 속한다.
2. 프로젝트의 확정 메타정보가 재사용 가능한 기준 데이터이고 문서는 그 시점의 스냅샷이다.
3. 모든 산출물은 입력 자료, 메타정보, MCP, 모델과 실행 기록으로 재현할 수 있어야 한다.
4. Core는 MCP 이름이 아니라 Capability와 입출력 계약으로 계획한다.
5. MCP는 실행 시점에 탐색·선택하며 실제 사용 버전은 실행 기록에 고정한다.
6. 권한은 기본 거부하고 프로젝트 정책과 데이터 등급 안에서만 자동 로딩한다.
7. 외부 전송, 파괴적 변경과 제출·발송 같은 확정 행위는 명시적으로 구분한다.
8. 메타정보 충돌은 임의로 덮어쓰지 않고 시점, 출처와 사용자 결정을 보존한다.
9. MCP 제작·검증·공유는 플랫폼의 부가기능이 아니라 핵심 제품 흐름이다.
10. 특정 업무는 MCP 또는 재사용 가능한 업무 레시피로 확장한다.

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

### 18단계 — 프로젝트 컨텍스트 커널

목표: 모든 기존 기능이 프로젝트 경계 안에서 동작할 수 있는 최소 기반을 만든다.

- [ ] `project.schema.json`과 프로젝트 정책 계약 정의
- [ ] `projects`, `project_members`, `project_conversations`, `project_decisions` 테이블 추가
- [ ] 프로젝트 생성·목록·조회·수정·보관 API 추가
- [ ] 기존 `workspace_documents`, `plans`, `native_document_sessions`에 `project_id` 연결
- [ ] 기존 데이터용 기본 Legacy Project 마이그레이션
- [ ] 최초 채팅에서 프로젝트 선택 또는 자동 생성
- [ ] 프론트 전역 상태에 `activeProjectId` 도입 및 새로고침 복원
- [ ] 프로젝트 간 데이터 접근 차단 테스트

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

- [ ] Capability ID·버전·입출력·부작용 표준 정의
- [ ] MCP Manifest vNext와 기존 Manifest 호환 변환기 구현
- [ ] `mcp_capabilities`, `mcp_tools`, `mcp_evaluations`, `mcp_compatibility` 색인 추가
- [ ] Artifact 유형과 JSON Schema 간 연결 가능성 검사
- [ ] 서명·런타임·데이터 등급·권한 기반 후보 하드 필터
- [ ] 품질·비용·지연시간·프로젝트 선호 기반 순위 정책
- [ ] 버전 고정, 의존성 해석과 설치 전 계획 미리보기
- [ ] Capability 검색·비교 API와 관리 화면

완료 기준:

- 동일 Capability를 제공하는 복수 MCP를 검색·비교할 수 있다.
- 호환되지 않거나 과도한 권한의 MCP는 실행 전에 제외된다.
- 기존 설치·업데이트·롤백과 서명 검증이 유지된다.

의존성: 18단계

### 22단계 — 동적 Planner와 영속 Workflow Runtime

목표: 고정 `_plan_steps`를 프로젝트 문맥 기반 Capability DAG와 단계 실행기로 대체한다.

- [ ] `workflow-run.schema.json`, `step-run.schema.json`, `capability-binding.schema.json` 정의
- [ ] 요청에서 목표, 예상 산출물, 입력과 필요 Capability 추출
- [ ] 프로젝트 Fact·Artifact·대화·정책을 최소 범위로 조립하는 Context Builder
- [ ] Capability DAG 생성과 입출력 Schema 연결 검증
- [ ] Resolver를 통한 실행 시점 MCP 선택 및 버전 고정
- [ ] `workflow_runs`, `step_runs`, `step_inputs`, `step_outputs`, `capability_bindings` 테이블 추가
- [ ] 단계별 체크포인트, 멱등키, 재시도, 취소와 중단 후 재개
- [ ] 기존 `plans/executions` 호환 API 및 단계적 deprecated 표시
- [ ] 계획 타임라인, 진행률, 대기 승인과 실패 복구 UI

완료 기준:

- 업무 키워드나 특정 MCP 이름 없이 요청별 계획이 생성된다.
- 서버 재시작 뒤 실패 Step부터 안전하게 재개할 수 있다.
- 각 Step의 입력·출력과 선택된 MCP 버전을 추적할 수 있다.

의존성: 18~21단계

### 23단계 — 프로젝트 권한·정책과 동적 MCP 로딩

목표: 사전 승인 MCP는 자동으로, 권한 변화가 있는 MCP는 필요한 시점에 승인받아 로딩한다.

- [ ] `project-policy.schema.json`, `permission-grant.schema.json` 정의
- [ ] `project_policies`, `permission_grants`, `approval_requests` 테이블 추가
- [ ] 설치 승인, 데이터 접근 승인과 최종 행위 확인 분리
- [ ] Manifest 권한 diff와 데이터 이동 경로 설명 생성
- [ ] 자동·프로젝트 1회·실행별·최종 확인 정책 엔진
- [ ] MCP 업데이트 시 권한 확대와 데이터 처리 변경 감지
- [ ] Step 직전 JIT 로딩, 격리 실행, 종료 후 lease 해제
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

완료 기준:

- 특정 보고서 유형에 종속되지 않고 프로젝트 자료로 파생 산출물을 생성한다.
- 적용 후 현재 문서·페이지·선택 문맥이 유지된다.
- 편집 결과의 근거와 사용 MCP가 산출물 계보에 남는다.

의존성: 19~23단계

### 25단계 — MCP Studio vNext

목표: 비개발자도 자연어와 예제로 안전한 MCP를 만들고 시험할 수 있게 한다.

- [ ] 제작 유형을 프롬프트형·조합형·코드형으로 분리
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
- [ ] 프로젝트 내보내기·가져오기·백업·복원
- [ ] 비용·지연시간·성공률·MCP 품질 관측성
- [ ] 범용 수용성 시나리오 3개 이상 구성
- [ ] 장애·변조·권한 확대·stale context 실패 주입
- [ ] 운영 마이그레이션·롤백·재해복구 문서화

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

## 13. 이번 단계에서 하지 않는 것

- 특정 산업이나 행정업무 이름을 Platform Core Schema에 추가하지 않는다.
- 공개 MCP를 설치됐다는 이유만으로 자동 신뢰하지 않는다.
- 메타정보 후보를 근거나 승인 없이 확정값으로 승격하지 않는다.
- 파생 산출물을 프로젝트 기준정보의 원본으로 간주하지 않는다.
- 기존 문서·실행·감사 데이터를 일괄 삭제하거나 비가역적으로 변환하지 않는다.
