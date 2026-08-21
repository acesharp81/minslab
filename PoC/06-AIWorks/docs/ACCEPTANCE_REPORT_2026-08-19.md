# AIWorks 수용성 검증 보고서 — 2026-08-19

> 범위: 프로젝트 중심 문서 생명주기, 데이터 MCP, 양식 MCP, MCP Store/Studio, HWPX/RHWP 연동
> 결과: 핵심 피드백 슬라이스 통과. 운영 확장 항목은 아래 후속 개발 목록으로 관리한다.

## 0.30.0 잔여 개발 반영

- 프로젝트를 MD revision·메타정보·파생 HWPX·Artifact 계보·Evidence까지 포함한 SHA-256 무결성 JSON으로 내려받고, 원본을 덮어쓰지 않는 새 프로젝트로 복원한다.
- Artifact Evidence는 원본 Artifact/Version, 위치, 발췌문, 발췌 SHA-256과 신뢰도를 저장하며 문서 변경 이력 탭에 표시한다.
- Recipe Library는 이름·ID·태그를 검색하고 설치 전 권한·비용·지연·라이선스·출처·위험 플래그를 보여주며 취약 버전 설치를 차단한다.
- 실패 Workflow의 재승인 실행은 새 Run을 만들지 않고 같은 Run ID에 attempt 2를 추가하며 실행 attempt 이력을 보존한다.
- 프로젝트 멤버십 역할(owner/admin/editor/viewer), 프로젝트 정책 revision, MCP Permission Grant와 비파괴 보관·복원 API/UI를 추가했다.
- Markdown/HWPX 호환 저장과 함께 모든 파일·데이터·분석을 담는 범용 Artifact/Version 저장소와 relation 쓰기·순환 방지를 추가했다.
- Capability Resolver에 권한·입출력 Artifact 하드 필터와 품질·성공률·비용·지연·프로젝트 선호 가중 랭킹을 추가했다.
- 실패 Workflow의 실제 실패 Step과 체크포인트를 새 승인 실행에 전달하고 원 Run/재개 Step을 기록한다.
- TemplateSchema 1.1에서 부서·작성자·문서번호·결재 메타 슬롯, 표·병합 셀·결재 블록을 탐지하고 시각 보정 응답에 표 위치를 제공한다.
- DOCX/XLSX를 서버 로컬에서 추출해 RAG 자료와 프로젝트 Markdown 원본으로 열 수 있다. 외부 전송은 발생하지 않는다.
- Workflow Recipe 1.0의 버전 게시, 개인·조직·공개 범위, 포크, 프로젝트 설치, 폐기와 설정 화면 Recipe Library를 추가했다.
- 프로젝트 선택 화면에서 보관된 프로젝트를 다시 복원할 수 있다.


## 이번에 완성도를 높인 부분

### 1. 양식 MCP 원본 관리

- 양식 기준 HWPX는 초안당 1개만 허용한다.
- 첨부 목록에서 기준 파일을 삭제할 수 있으며, 삭제 후 Manifest 참조와 검증 상태도 함께 갱신한다.
- 일반 HWPX를 제목·본문 슬롯이 있는 양식용 HWPX로 변환하고 같은 초안의 유일한 기준 파일로 반영한다.
- 일부 슬롯만 있는 HWPX는 완성 양식으로 오인하지 않고 변환 또는 RHWP 확인을 요구한다.
- 복잡한 표/도형 기반 HWPX에서도 표 안 제목과 표 밖 본문 prototype을 구분한다.
- 제목은 정확히 한 번 유지하고 본문 슬롯은 표 정리 과정에서 덮어쓰지 않는다.

### 2. 양식 구조 렌더링과 품질검사

- ReportDocument의 heading, paragraph, list, table을 HWPX prototype에 구조적으로 바인딩한다.
- Markdown 레벨을 HWPX 문단 스타일과 들여쓰기 단계로 변환한다.
- 표 prototype이 있으면 실제 행·셀을 복제하고 Markdown 표 구분자가 평문으로 남지 않게 한다.
- 날짜와 원본 파일명 보조 슬롯도 구조 렌더러에서 치환한다.
- `구조 실검증`은 테스트 ReportDocument를 실제 렌더링한 뒤 재파싱한다.
- 제목 1회, 본문 1회, 목록/제목 블록, 실제 표 셀, 잔여 플레이스홀더 0건, 매핑률 95% 이상을 검사한다.
- 실검증 실패 양식은 RHWP 반영과 게시 검증을 통과하지 못한다.

### 3. 프로젝트 문서 생명주기

- 시작 시 새 프로젝트 생성 또는 기존 프로젝트 선택을 요구한다.
- 마지막 HWPX를 백그라운드 복원하는 동안 사용자가 MCP 제작기 등 다른 화면을 선택해도 편집 화면으로 되돌리지 않는다.
- 기존 프로젝트는 마지막 문서, 탭, 화면, 대화와 직전 답변을 복원한다.
- 프로젝트 문서의 내용 원본은 Markdown 불변 revision이다.
- HWPX는 파생 산출물이며 탭을 누르는 것만으로 다시 생성하지 않는다.
- `MD → HWPX 반영`과 `HWPX → MD 반영`으로만 명시적으로 승격한다.
- HWPX 직접 편집은 `diverged/MD 반영 필요` 상태로 보류한다.
- Markdown, HWPX, 메타정보, 이력 탭과 대화/편집 영역 드래그 비율 조절을 제공한다.

### 4. 데이터 MCP와 보고서

- PDF/HWPX/MD/TXT 원본을 로컬에서 추출·청크화하고 SHA-256으로 관리한다.
- 게시 전 RAG 검색, 원문 위치 인용, 게시·설치 후 의도 기반 자동 선택을 지원한다.
- 검색 청크를 그대로 노출하는 데서 끝나지 않고 요청에 따라 연도별 종합 또는 보고서 artifact를 생성한다.
- RHWP 선택 문구 제안은 채팅 포커스 이동 뒤에도 선택 원문을 보존하고 새 문서 revision으로 저장한다.
- 데이터 근거→ReportDocument→Markdown/HWPX→RHWP 편집 흐름을 제공한다.
- Solar Pro 3 Fast/3/4를 속도·문서작성·복합추론 용도에 따라 라우팅한다.
- 최초 문서 생성 기본값은 Store의 의도분석 MCP 환경설정에서 Solar Pro 4로 관리한다.
- 질문-초안 품질 하네스의 주제 토큰을 원문 순서로 고정해 실행마다 판정이 달라지던 문제를 제거했다.

### 5. MCP Store와 Studio

- 양식, 처리, 데이터, 일반 도구, 외부 MCP 5종 제작 흐름을 제공한다.
- 사용자 MCP의 수정은 다음 SemVer 초안으로 이어지고 사용자 패키지는 확인 후 삭제할 수 있다.
- MCP별 설정 Schema가 있으면 공통 환경설정 UI를 재사용한다.
- Capability 색인, 설치 버전 Resolver, 서명·권한 검증, 게시 후 설치와 호출 문구 테스트를 제공한다.
- KODAK/kordoc 고정 stdio 프로필과 범용 Streamable HTTP 외부 MCP 매핑 틀을 제공한다.

## 자동 검증 결과

| 검증 | 결과 | 확인 범위 |
|---|---|---|
| 자동 회귀 테스트 109개 | 통과 | 프로젝트 백업 왕복, Artifact Evidence, Recipe 안전 미리보기, 동일 Workflow Run 재개, Store, RAG, Solar, 양식·충돌 동기화 |
| 양식 MCP Firefox 스모크 | 통과 | `form-002.hwpx` 첨부→변환→구조 실검증→샌드박스 |
| 프로젝트 워크벤치 Firefox 스모크 | 통과 | 프로젝트 강제 선택, 마지막 상태 복원, MD↔HWPX, 메타/이력, 리사이저 |
| 프로젝트 이식성 Firefox 스모크 | 통과 | 첫 화면 백업 가져오기, 거버넌스 백업, SHA-256 API, Recipe 검색·빈 결과 |
| 데이터 MCP Firefox 스모크 | 통과 | PDF 인덱싱, RAG, 게시·설치, 근거 답변, RHWP 보고서 |
| Store/Builder Firefox 스모크 | 통과 | 10개 Store 카드, Solar Pro 4 설정, 5종 Builder, KODAK 프리셋 |
| 대화·편집 피드백 Firefox 스모크 | 통과 | 예산 MCP 답변, RHWP 보고서, 선택 수정 revision, 행안부 양식 적용 |
| RHWP 도구상자 Firefox 스모크 | 통과 | 기본 해제, 서식 활성, 전체 문서 개조식 변환 |
| Python/JavaScript 문법 검사 | 통과 | `backend.py`, 스모크 파일, `web/app.js` |
| 운영 서비스 | 정상 | `/health`, AIWorks 0.30.0, app v62, styles v53 |

데이터 MCP와 Store 게시 검증은 임시 SQLite DB의 격리 서버에서 실행했고 종료 후 DB를 삭제했다. 프로젝트 워크벤치 스모크는 만든 문서와 후보 Fact를 지우고 이전 작업공간 상태를 복원한다.

## 사용자가 직접 테스트하는 방법

### A. 프로젝트와 문서 왕복

1. 첫 화면에서 기존 프로젝트를 선택한다.
2. 마지막 문서·탭·대화가 그대로 복원되는지 확인한다.
3. Markdown 탭에서 문구를 수정하고 revision 저장을 기다린다.
4. HWPX가 자동 변경되지 않았는지 확인한 뒤 `MD → HWPX 반영`을 누른다.
5. HWPX 탭에서 문구를 수정하고 `MD 반영 필요` 상태를 확인한다.
6. `HWPX → MD 반영`을 눌러 새 Markdown revision에 반영되는지 확인한다.

### B. 데이터 MCP

1. `MCP 만들기`에서 `데이터 MCP`를 선택한다.
2. 출처 설명을 넣고 `게시 패키지에 원본 포함`을 확인한 뒤 초안을 만든다.
3. 텍스트 추출 가능한 공개 PDF를 첨부한다.
4. RAG 미리보기에서 질문하고 답변의 파일명·쪽수 인용을 확인한다.
5. 샌드박스 검증→게시→설치 후 일반 대화에서 같은 주제로 질문한다.
6. `보고서 작성` 요청 시 청크 나열이 아니라 종합 Markdown/HWPX가 열리는지 확인한다.

### C. 양식 MCP

1. `MCP 만들기`에서 `양식 MCP`를 선택하고 초안을 만든다.
2. 일반 HWPX를 `양식 원본`으로 첨부한다. 기준 파일은 한 개만 유지한다.
3. `일반 HWPX → 양식용 변환·반영`을 누른다.
4. `구조 실검증`에서 제목·본문·표·매핑률이 통과하는지 확인한다.
5. 필요하면 `양식 수정 (RHWP로 편집)`에서 서식을 고친 뒤 초안에 반영한다.
6. 샌드박스 검증→게시→설치한다.
7. 프로젝트 Markdown 보고서에서 해당 양식 전환을 요청하고 HWPX 결과의 제목, 개조식 들여쓰기, 실제 표를 확인한다.

### D. Store와 외부 MCP

1. Store의 사용자 MCP에서 `수정`을 눌러 다음 버전 초안으로 이어지는지 확인한다.
2. 사용자 MCP의 `삭제`는 확인 대화상자 후 실행되는지 확인한다. Core 패키지는 삭제 대상이 아니다.
3. 의도분석 MCP `환경설정`에서 최초 문서 모델을 확인한다.
4. 외부 MCP Builder에서 KODAK stdio 또는 HTTP 매핑을 선택하고 런타임 검사를 실행한다.

## 이번 후속 개발에서 완료한 부분

- 양식 HWPX 문단 목록에서 제목·본문·○/-/※ 목록 원형을 직접 지정하고 실렌더링 검증 후 반영하는 슬롯 보정 UI.
- context→execute→persist Workflow/Step Run, 축약 입출력·오류·체크포인트 조회, 기존 토큰을 재사용하지 않는 새 승인 Retry Plan.
- HWPX 표 셀까지 연결된 Render Map과 MD/HWPX 동시 편집 충돌 저장, 양쪽 미리보기, 현재 MD 유지/HWPX 채택 해결 UI.
- revision·artifact SHA 기반 MD/HWPX 편집기 DOM·세션 캐시와 프로젝트 전환 시 캐시 정리.
- 내용 SHA-256이 같은 Markdown의 exact-duplicate 표시와 삭제 없는 보관·복원 API.
- 메타정보 후보 일괄 확정·거부, 시간 변화/오기 검토 분류, 시점값 및 superseded 이력 보존.
- Markdown revision, HWPX, 양식, 충돌의 derived_from·supersedes·formatted_by·compares 재현 관계 화면.

### 추가 테스트 시나리오

1. 양식 MCP 기준 HWPX를 변환한 뒤 `슬롯 시각 보정`에서 제목·본문을 바꾸고 반영한다. 실검증 통과와 다운로드 결과를 확인한다.
2. MD 탭→HWPX 탭→메타정보 탭→MD 탭으로 돌아온다. 원본이 바뀌지 않았다면 상태 표시가 `캐시 복원 · 재마운트 없음`인지 확인한다.
3. HWPX를 수정해 MD 반영 대기 상태로 만든 뒤 다른 탭에서 MD도 수정한다. HWPX→MD 반영 시 자동 덮어쓰지 않고 변경 이력에 충돌 카드가 생기는지 확인한다.
4. 변경 이력의 충돌 카드에서 현재 MD 유지 또는 HWPX 변경 채택을 선택하고 새 revision·artifact 상태와 재현 관계를 확인한다.
5. 내용이 완전히 같은 MD가 둘 이상이면 데이터 화면 문서 카드의 `중복 보관`을 누른다. revision과 파생 파일이 삭제되지 않는지 확인한다.
6. 메타정보 탭에서 후보 전체 확정/거부를 시험하고, 기존값과 다른 후보는 오기 수정/시간 변화 버튼과 현재값·기준일 비교가 보이는지 확인한다.

## 남은 개발 항목

- TemplateSchema 결재·병합표 셀을 캔버스에서 직접 재구성하는 편집기와 스타일 병합.
- 새 승인 Retry Run이 아니라 동일 Workflow Run/Step 프로세스 안에서 중단·재개하는 실행기.
- 제출·발송·게시·삭제 최종 확인 정책 실행, JIT MCP lease와 업데이트 권한 diff.
- Artifact Evidence 전용 엔터티·계보 탐색기와 프로젝트 내보내기·가져오기·백업.
- 이미지 OCR 런타임과 DOCX/XLSX/HWPX 외 제3자 출력 포맷 어댑터.
- Recipe 태그 검색·비용/권한 미리보기·라이선스/출처 계보·취약 버전 차단.
- 다중 사용자 부하, 리소스 격리, 장애·권한 확대·정보 누출 보안 수용성 검증.

### 운영 환경에서 추가 설정할 부분

- 운영용 승인 서명 키와 MCP 패키지 서명 키를 개발 파생 키 대신 별도 Secret으로 설정.
- Windows 네이티브 RHWP 브리지가 필요하면 전용 Bridge URL/인증을 설정. 현재 웹 RHWP는 동작한다.
- KODAK 실제 자동 후처리는 승인된 `kordoc@4.7.3` 런타임 설치 상태를 확인.
- 데이터 MCP를 설치하기 전 Knowledge 출처 0개 경고는 정상이며, 실제 자료 게시 후 readiness를 다시 확인.

## 재현 명령

```bash
python3 -m unittest PoC/06-AIWorks/tests/test_backend.py
.venv/bin/python PoC/06-AIWorks/tests/builder_flow_smoke.py
.venv/bin/python PoC/06-AIWorks/tests/project_workbench_smoke.py
.venv/bin/python PoC/06-AIWorks/tests/data_mcp_flow_smoke.py
.venv/bin/python PoC/06-AIWorks/tests/store_builder_smoke.py
node --check PoC/06-AIWorks/web/app.js
```

게시·설치형 브라우저 테스트는 운영 DB 대신 `AIWORKS_DB_PATH`를 임시 SQLite 파일로 지정한 격리 서버에서 실행하는 것을 권장한다.
