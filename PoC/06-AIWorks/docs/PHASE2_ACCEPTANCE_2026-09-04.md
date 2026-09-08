# AI Work Hub Phase 2 수행 결과보고

> 기준 버전: AI Work Hub 0.31.2
> 수행일: 2026-09-04
> 수행 범위: KORDOC 없는 보고서 생성·편집 E2E 및 회귀 검증
> 종합 판정: 서버·브라우저 범위 적합, Windows RHWP 네이티브 확인은 출시 전 별도 게이트

## 1. 추진 개요

### 가. 목적

- 특정 문서 렌더러 제품에 자동 결합되지 않는 내장 HWPX 생성 경로를 검증함.
- 일반 보고서와 예산 근거 보고서가 Markdown 원본, HWPX 파생본, RHWP 편집 세션으로 끊김 없이 연결되는지 확인함.
- Markdown과 HWPX의 양방향 수정이 자동 덮어쓰기 없이 명시적 승격·충돌 상태로 관리되는지 확인함.
- 사용자의 기존 프로젝트·자료에 영향을 주지 않도록 브라우저 시험을 매회 임시 프로젝트로 격리하고 종료 후 완전 삭제함.

### 나. 판정 기준

- KORDOC 프로세스 및 KORDOC 전용 npm 설치 없이 일반·예산 보고서 E2E가 통과할 것.
- 예산 질의 결과에 원문 근거와 페이지 인용이 포함될 것.
- Markdown 저장, HWPX 저장, 명시적 역반영, 동시 수정 충돌이 계약한 상태 전이로 동작할 것.
- 탭 이동만으로 재렌더링, 새 revision 또는 해시 변경이 발생하지 않을 것.
- HWPX 렌더러 실패가 검색 결과·대화 답변·저장된 Markdown을 훼손하지 않을 것.

## 2. 주요 수행 결과

| 구분 | 수행 내용 | 결과 | 확인 근거 |
|---|---|---|---|
| Golden Workflow | 근거 검색→계획/DAG→1회 승인→Markdown r1→HWPX→RHWP 수정→Markdown r2→감사체인 | 적합 | 58/58 검사 통과 |
| 일반 보고서 회귀 | 요청 문맥→근거/모델→Markdown revision→ReportDocument→HWPX→RHWP | 적합 | `test_workspace_flows`, `test_backend` 통과 |
| 예산 질의 | PDF Data MCP 생성·게시→의도 해석→RAG→페이지 인용 답변 | 적합 | 격리 Firefox E2E 통과 |
| 예산 보고서 | RAG 근거 종합→보고서 생성→HWPX→RHWP 열기 | 적합 | 격리 Firefox E2E 통과 |
| 범정부 AI 주제 적합성 | 붙여 쓴 `범정부AI`를 `범정부 인공지능`과 동등하게 탐색하고 무관한 A-WEB 근거 제외 | 적합 | 관련·무관 자료를 함께 등록한 격리 Firefox E2E 통과 |
| HWP 산출 형식 격리 | HWP 요청→Markdown/HWPX 본문에서 사용법 제거→근거형 답변의 RHWP 편집 | 적합 | `topic_hwp_flow_smoke.py` 통과 |
| 문서 상태 전이 | MD save→stale, HWPX save→pending/diverged, 양방향 명시적 승격, conflict | 적합 | Project Workbench Firefox E2E 및 단위시험 통과 |
| 탭 격리 | 반복 탭 이동 시 문서 상태·revision 불변 | 적합 | `repeatedTabIsolation=true` |
| 렌더러 실패 격리 | HWPX 생성 실패 시 Markdown·답변·워크플로 결과 보존 | 적합 | `test_renderer_failure_preserves_markdown_and_completes_workflow` 통과 |
| KORDOC 독립성 | 신규 Store·Artifact에 KORDOC 자동 결합 없음, 실행 프로세스 없음 | 적합 | 비설치 DB 회귀시험 및 프로세스 점검 통과 |
| 전체 회귀 | 단위·계약·통합시험 | 적합 | 154/154 통과 |
| 연속 질의 격리 | A 보고서가 열린 상태에서 B 답변 후 일반 보고서 작성 요청 | 적합 | B 답변 우선·A 내용 제외 회귀시험 통과 |
| 검색 후 HWP 후속 요청 | 범정부 AI 검색 답변 후 `보고서를 HWP로 만들어줘` | 적합 | 프로젝트 자료 MCP 재검색 없이 직전 답변을 HWPX로 승격 |
| 운영 준비상태 | DB·서명·모델·PDF 추출기·감사체인·PDF renderer | 조건부 적합 | 실패 0, 통과 7, 경고 6 |
| Windows RHWP | 실제 한컴오피스에서 열기·저장·재열기·PDF 내보내기 | 차단 | Windows·한컴오피스·COM 부재. 전용 acceptance runner 제공 |

## 3. 개선·보완 사항

### 가. 시험 격리 강화

- `browser_smoke.py`가 운영 프로필에서 삭제된 `project-default`를 전제로 하던 문제를 해소함.
- 일반 보고서 시험은 실행 시 임시 프로젝트를 생성하고 종료 시 보관 후 완전 삭제하도록 변경함.
- Data MCP Firefox 시험도 첫 번째 실제 프로젝트를 임의 선택하지 않고 전용 임시 프로젝트만 사용하도록 변경함.
- Project Workbench 시험도 고정 프로젝트 대신 전용 프로젝트와 문서를 생성·정리하도록 변경함.

### 나. 사용자 편집 반영 강화

- RHWP 결과확인 화면의 실제 수정본을 base64 HWPX로 회수하여 양식 확인 API에 전달함.
- 원본 양식과 렌더 결과의 SHA-256을 함께 검증하여 오래되거나 다른 미리보기의 저장을 차단함.
- 확인된 RHWP 수정본을 재사용 가능한 양식 원본으로 변환·커밋하고 감사 이벤트를 남김.
- 원본/결과 화면 전환 중에도 사용자가 편집한 결과를 유지하도록 보완함.

### 다. 검색 주제 및 산출 형식 격리

- `관련된`, `지적`, `사항`, `보고서` 등 일반 요청어를 업무 주제어에서 제외하여 무관한 근거가 우선되는 현상을 보완함.
- `범정부AI`, `범정부 AI`, `범정부 인공지능`의 표기 차이를 동일 주제로 정규화하여 PDF 원문과 질의의 띄어쓰기·약어 차이를 흡수함.
- HWP/HWPX/RHWP 요청은 산출 형식으로만 전달하고 사용·편집·저장 안내가 보고서 본문에 들어오지 않도록 생성 프롬프트와 최종 산출물 양쪽에서 차단함.
- 일반 모델 답변뿐 아니라 Data MCP 근거형 답변에도 RHWP 편집 진입점을 제공하여 검색→보고서→실문서 흐름을 일관되게 함.
- 직전 답변을 HWP로 승격하는 후속 요청에서는 프로젝트 자료 MCP를 다시 바인딩하지 않도록 하여, 짧은 후속 문장이 새 검색어가 되어 주제를 덮어쓰는 문제를 차단함.

## 4. 시사점

- 문서 내용 원본을 Markdown으로 고정하고 HWPX를 버전이 있는 파생 산출물로 관리하는 구조가 실제 왕복 편집에서도 유효함.
- 자동 동기화보다 `stale`, `diverged`, `conflict`를 노출하고 사용자가 승격 방향을 선택하게 하는 방식이 문서 유실 방지에 적합함.
- 보고서 품질은 모델 호출 자체보다 근거 수집, 인용, ReportDocument 정규화, 양식 적용의 단계별 계약에서 좌우됨.
- 자연어 질의의 일반 요청어를 핵심 주제로 오인하면 정확한 자료가 존재해도 무관 문서가 선택될 수 있으므로, 주제어·행위어·산출 형식을 분리해야 함.
- HWP 사용법과 같은 UI 안내를 모델 본문 생성에 맡기면 실제 문서에 혼입될 수 있으므로, 산출 형식은 구조화 메타데이터로 처리하고 최종 저장 전에도 검증해야 함.
- 브라우저 E2E가 고정 데모 프로젝트를 사용하면 운영 데이터 오염과 시험 결과 왜곡 위험이 있으므로 임시 프로젝트 격리가 필수임.
- KORDOC 제거 후에도 범용 외부 MCP 경계와 과거 provenance는 유지할 수 있어 제품 종속성 제거와 감사 추적성을 함께 달성할 수 있음.
- Linux RHWP 웹 편집 성공만으로 Windows 한컴오피스 호환성을 단정할 수 없으므로 네이티브 확인은 독립 출시 게이트로 관리해야 함.

## 5. 향후 조치

### 가. 출시 전 필수

- Windows 한컴오피스에서 일반 보고서와 예산 보고서 HWPX를 각각 열어 제목·본문·중첩 목록·예산 표·결재란을 육안 확인함.
- Windows RHWP 브리지 명령과 비밀키를 운영 환경에 설정하고 저장→재열기→재다운로드 왕복을 검증함.
- 동일 문서를 웹 RHWP와 Windows에서 각각 수정하여 conflict 표시와 선택적 역반영을 재확인함.
- 확인 결과를 화면 캡처, 파일 SHA-256, 앱 버전, 시험자, 시험 시각과 함께 증적화함.

### 나. 후속 고도화

- Firefox E2E 3종을 CI의 비-KORDOC 릴리스 게이트로 편성하고 임시 프로젝트 정리 실패를 별도 경고로 수집함.
- readiness의 `rhwp.runtime` 경고를 Windows 브리지 배포 상태와 연계하여 운영 대시보드에 표시함.
- 행정안전부 실양식 표본을 확대하여 병합 셀, 머리말·꼬리말, 쪽번호, 결재란 보존 회귀를 추가함.
- 실패 주입 시험을 데이터 MCP 검색, HWPX 렌더링, RHWP 저장 단계별로 확대하여 부분 성공 산출물의 복구 절차를 고정함.
- 행정·정책 분야의 주요 약어와 정식 명칭 사전을 확장하고, 실제 운영 질의별 기대 문서·페이지를 golden set으로 누적하여 검색 적합성 저하를 배포 전에 차단함.

## 6. 재현 명령

```bash
python3 PoC/06-AIWorks/golden_workflows/runner.py
.venv/bin/python3 -m unittest discover -s PoC/06-AIWorks/tests -v
.venv/bin/python3 PoC/06-AIWorks/tests/project_workbench_smoke.py
.venv/bin/python3 PoC/06-AIWorks/tests/data_mcp_flow_smoke.py
curl -sS http://127.0.0.1:8000/api/poc/aiworks/operations/readiness
```
