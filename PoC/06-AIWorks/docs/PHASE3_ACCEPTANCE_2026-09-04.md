# AI Work Hub Phase 3 수행 결과보고

> 기준 버전: AI Work Hub 0.31.2
> 수행일: 2026-09-04
> 수행 범위: KORDOC/KODAK 제품 종속 경로의 점진 퇴역 및 범용 MCP 경계 보존
> 종합 판정: 적합 — Phase 3 완료

## 1. 추진 개요

### 가. 목적

- 신규 계획·실행·Store·Builder·readiness에서 퇴역 renderer가 자동 선택되거나 다시 활성화되지 않도록 함.
- 보고서 HWPX 생성 경로를 내장 `document.report-hwpx@0.1.0` Capability로 일원화함.
- 과거 패키지·설치·감사·Artifact provenance는 변경하거나 삭제하지 않고 감사 이력으로 보존함.
- 범용 stdio 및 Streamable HTTP 외부 MCP 연결 계약은 특정 제품과 분리하여 유지함.

### 나. 판정 기준

- 신규 Plan과 실행 산출물에 `integration.kordoc`가 포함되지 않을 것.
- 퇴역 패키지가 Store 및 Builder의 신규 선택 대상으로 노출되지 않을 것.
- 직접 API 호출을 포함한 설치 미리보기·설치·롤백·수정 요청이 차단될 것.
- 기존 활성 설치는 재기동마다 중복 이력 없이 `retired`로 전환될 것.
- 과거 패키지 버전과 설치·퇴역 이력, 기존 Artifact renderer 값은 보존될 것.
- 전용 vendor 런타임·환경변수·npm 프로세스 없이 내장 HWPX와 범용 외부 MCP 회귀가 통과할 것.

## 2. 주요 수행 결과

| 구분 | 수행 내용 | 결과 | 확인 근거 |
|---|---|---|---|
| 신규 자동 선택 제거 | Planner·동적 binding·HWPX 기본 renderer를 내장 Capability로 전환 | 적합 | `document.report-hwpx@0.1.0` 회귀 통과 |
| Store 노출 차단 | 퇴역 패키지를 Store 목록과 신규 선택 후보에서 제외 | 적합 | Firefox `retiredRendererHidden=true` |
| 재활성화 차단 | 설치 미리보기·설치·롤백·수정 API에 공통 410 차단 적용 | 적합 | 실제 서비스 차단 응답 및 단위시험 통과 |
| migration 멱등성 | 활성 legacy installation을 한 번만 retired 처리 | 적합 | 2회 schema 재실행 후 `bootstrap→retire` 1회 유지 |
| 과거 이력 보존 | 패키지 1.0.0, 설치·퇴역 history, Artifact renderer provenance 불변 | 적합 | 격리 DB 회귀시험 및 운영 DB 읽기 점검 |
| 전용 런타임 제거 | 무시된 `vendor/kordoc-runtime` 43MB와 전용 npm 잔재 제거 | 적합 | 디렉터리 부재·실행 프로세스 0건 |
| UI 제품 독립성 | Store·Builder에서 KODAK/KORDOC 기본 문구·프로필 미노출 | 적합 | Firefox `vendorDefaultsAbsent=true` |
| 범용 외부 MCP 보존 | stdio 승인 프로필과 Streamable HTTP 계약 유지 | 적합 | Builder 기본값·계약 회귀 통과 |
| 전체 회귀 | 단위·계약·통합시험 | 적합 | 154/154 통과 |

## 3. 개선·보완 사항

### 가. 퇴역 상태 강제

- `retired`를 단순 표시 상태가 아닌 실행 차단 정책으로 정의함.
- 퇴역 패키지 ID 집합을 단일 정책 지점에서 관리하고 모든 재활성화 진입점에 동일하게 적용함.
- 과거 패키지는 DB와 SBOM·감사 근거로 보존하되 일반 Store 목록에서는 제외함.
- 직접 API 호출도 HTTP 410으로 차단하여 UI 우회 설치를 방지함.

### 나. 제품 종속 제거

- 문서 변환 시 `_KODAK` 파일명 접미사를 특별 처리하던 잔여 로직을 제거함.
- 전용 로컬 runtime 디렉터리와 npm 설치물을 삭제함.
- 신규 보고서 생성·양식 적용은 `document.hwpx.render` Capability 계약만 사용하도록 유지함.
- 범용 외부 MCP의 전송·권한·도구 계약은 renderer 퇴역과 분리하여 보존함.

### 다. 회귀 방지

- legacy 설치를 넣은 뒤 schema migration을 두 번 실행하여 퇴역 이력이 중복되지 않는지 검증함.
- Store 숨김, API 차단, 패키지·Artifact provenance 보존을 하나의 수직 회귀시험으로 고정함.
- 정적 계약시험에서 전용 환경변수·제품명·vendor runtime 경로 재유입을 차단함.
- Firefox 수용성 검사에 Store 숨김과 Builder 제품 독립성 확인을 추가함.

## 4. 시사점

- `retired` 상태만 DB에 기록하고 설치 API를 열어 두면 운영자가 과거 패키지를 다시 활성화할 수 있으므로 상태와 행위 권한을 함께 통제해야 함.
- 과거 기록 삭제는 감사 추적성을 훼손하므로 실행 후보에서 제외하는 것과 provenance 보존을 별도 정책으로 관리해야 함.
- 특정 vendor 제거 시 renderer만 삭제하면 파일명 보정·환경변수·UI 예시·로컬 설치물에 결합이 남을 수 있어 코드·설정·데이터·프로세스를 함께 점검해야 함.
- 외부 MCP 실행 계층까지 함께 제거하면 플랫폼 확장성이 훼손되므로 제품별 구현과 표준 transport 계약을 분리해야 함.
- 퇴역 정책은 UI 검사만으로 충분하지 않으며 직접 API 호출과 재기동 migration을 포함한 수직 검증이 필요함.

## 5. 향후 개선방향

### 가. 단기 조치

- 현재 단일 퇴역 ID 집합을 `retired_packages` 정책 테이블로 일반화하고 퇴역 사유·일시·대체 Capability를 관리함.
- Store 운영 화면에 일반 사용자에게는 숨김, 감사 권한자에게는 읽기 전용 이력 조회를 제공함.
- CI에서 전용 vendor 경로·환경변수·문구 정적 검사와 Store·Builder Firefox 검사를 릴리스 게이트로 고정함.
- 퇴역 패키지 직접 설치 시 410 응답과 대체 Capability 안내가 API·감사 로그에 함께 남도록 보완함.

### 나. 중장기 조치

- 패키지 lifecycle을 `active→deprecated→retired→blocked`로 표준화하고 단계별 설치·실행·조회 권한을 정책화함.
- 대체 Capability migration을 dry-run으로 제공하여 영향받는 계획·Recipe·Artifact 계보를 사전 산출함.
- SBOM과 감사 화면에서 퇴역 구성요소의 과거 사용 범위와 현재 비활성 상태를 함께 증적화함.
- Windows 한컴오피스 호환성 검증은 Phase 2의 별도 출시 게이트로 계속 관리하되 Phase 3 제품 퇴역과 혼합하지 않음.

## 6. 검증 명령

```bash
.venv/bin/python3 -m unittest discover -s PoC/06-AIWorks/tests -v
.venv/bin/python3 PoC/06-AIWorks/tests/store_builder_smoke.py
curl -sS http://127.0.0.1:8000/api/poc/aiworks/operations/readiness
```
