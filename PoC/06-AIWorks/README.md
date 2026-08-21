# 06 · AIWorks

여러 MCP와 AI 모델을 업무 목적에 맞게 조합하는 승인 기반 AI 업무 플랫폼의 초기 PoC입니다.

현재 문서 기준 버전은 `0.30.0`입니다. 2026-08-19 수용성 검증 결과와 이후 반영 상태는
[수용성 검증 보고서](docs/ACCEPTANCE_REPORT_2026-08-19.md)를 단일 진행 현황으로 사용합니다.

프로젝트 문서 내용의 단일 원본은 불변 revision으로 저장되는 Markdown입니다. LLM은 Markdown을
생성·갱신하고, 양식 MCP가 내용과 표현 규칙을 결합한 뒤 KODAK 또는 설치형
`document.format.convert.*` 어댑터가 HWPX와 제3자 형식의 파생 산출물을 만듭니다. HWPX를
업로드하거나 RHWP에서 내용을 수정하면 텍스트·표를 다시 Markdown으로 역변환해 새 revision을
기록합니다. 이때 KODAK 표지·제목 상자·자동 날짜 같은 렌더러 장식은 제거하고 의미 본문만
복원합니다. HWPX 자체는 편집·배포용 산출물이지 프로젝트 문서 내용의 원본이 아닙니다.

## 현재 구현

- 프로젝트 문서별 `MD 원본 / HWPX·파생 형식 / 메타정보 / 변경 이력` 탭, 명시적 MD↔HWPX 승격, 문단·표 셀 Render Map, 동시 편집 충돌 저장·선택 해결과 revision/SHA 기반 편집기 캐시
- 양식 HWPX 제목·본문·목록 슬롯 시각 보정과 실렌더링 검증, Workflow/Step Run 체크포인트·재승인 재시도, exact-duplicate MD 보관, Fact 시간변화/오기 결정, 산출물 재현 관계 그래프
- 최신 구현·직접 테스트·남은 항목: [docs/ACCEPTANCE_REPORT_2026-08-19.md](docs/ACCEPTANCE_REPORT_2026-08-19.md)
- 프로젝트 멤버십/RBAC·정책·Permission Grant·보관/복원, 범용 Artifact/Version 계보와 순환 방지
- 프로젝트 선택 화면의 AIWorks JSON 가져오기와 설정→프로젝트 거버넌스의 백업 다운로드. MD revision·메타정보·HWPX·Artifact 계보·Evidence를 SHA-256 무결성 검증 후 새 프로젝트로 복원
- Artifact Evidence 원본 Version·위치·발췌·해시·신뢰도 API와 문서 변경 이력 표시
- Recipe 이름/ID/태그 검색, 설치 전 권한·비용·지연·라이선스·출처·보안 미리보기와 취약 버전 차단
- 실패 Workflow 재승인 시 동일 Run ID에 attempt를 누적하는 in-place 재개와 실행 attempt 감사 이력
- TemplateSchema 1.1 메타·결재·병합표 탐지, DOCX/XLSX 로컬 추출→RAG/Markdown 입력
- Workflow Recipe 1.0 버전 게시·공유·포크·프로젝트 설치·폐기와 설정 화면 Recipe Library
- GPT형 첫 화면에서 명령과 문서를 함께 제출하면 의도 분석 결과에 따라 업무 MCP와 편집기 MCP를 동적으로 로딩
- 파일 미첨부 질의 → 채팅 답변 → 파생 보고서 → 선택 문구 변경으로 이어지는 피드백 흐름
- 첨부 자료 → 결산 양식 보고서 → 선택 문구 법률 검토로 이어지는 피드백 흐름
- 파생 보고서를 실제 HWPX로 패키징해 자체 호스팅 RHWP 문서 세션에서 열고, 같은 화면에서 선택·수정·버전 저장
- `행안부 보고서 양식으로 바꿔줘` 요청 시 로컬 양식 MCP를 동적 로딩해 본문을 보존한 HWPX 새 revision 적용
- 하나의 범용 MCP Builder에서 양식·처리·데이터·일반 도구 유형을 선택하고 파일·유의사항·처리 절차·호출 예시를 가이드 패키지로 제작
- 게시·설치된 Builder MCP의 Capability를 Registry에 색인하고, 채팅 요청·호출 예시·등록 자료 주제를 Resolver가 비교해 서명된 고정 버전을 승인 후 Prompt/Composite/Retrieval 런타임으로 실행
- 데이터 MCP에서 여러 PDF·HWPX·텍스트 파일을 페이지 단위로 추출·청크화하고, 게시 전 RAG 검색과 게시·설치 후 자동 선택·연도별 근거 정리·페이지 인용·편집 가능한 HWPX 보고서를 제공
- 전체 폭 MCP Studio에서 4개 유형 예시를 선택해 초안→자료→검증→게시→설치를 진행하고, 설치 Registry의 호출 문구를 바로 채팅과 RHWP 산출물로 시험
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

2단계에서는 실행계획, 승인과 실행 결과가 서버 SQLite에 저장됩니다. 승인 토큰은 HMAC 서명된
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

## Solar 자동 라우팅과 전송 경계

- Solar Pro 3 Fast: 단순 조회·확인·짧은 요약
- Solar Pro 3: 문서 작성·문장 편집·RAG 근거 종합
- Solar Pro 4: 복합 비교·계산·정책·법률 검증

의도 분석 MCP는 사용자 요청을 로컬에서 먼저 분류하고 모델 관리 MCP가 위 세 모드를 자동으로
선택합니다. 새 보고서·계획서·초안을 처음 생성하는 요청은 품질을 우선해 Solar Pro 4를
기본 선택하며, Store의 `의도 분석 MCP → 환경설정`에서 Pro 4·Pro 3·Fast·자동 판단으로 바꿀 수 있습니다.
Solar 실호출이 활성화되어 있으며 실행 계획에서 `model.invoke`와 `network.send`를 명시 승인한
요청만 Upstage API로 전송합니다. 데이터 MCP 기반 최초 보고서는 검색 근거를 Solar Pro 4가
종합하고 인용 검증을 통과한 본문을 편집 가능한 HWPX로 만듭니다. 승인을 거부하거나 실행기가
비활성이면 로컬 근거 보고서로 동작하며, `confidential`·`personal` 문맥은 외부 모델로 라우팅하지 않습니다.

## 경로

- 독립 화면: /poc/aiworks/
- 포트폴리오 셸: /poc?project=aiworks
- 계약: contracts/*.schema.json
- 프로젝트 중심 플랫폼 전환 로드맵: [docs/PROJECT_PLATFORM_ROADMAP.md](docs/PROJECT_PLATFORM_ROADMAP.md)
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
백업은 Markdown revision, 메타정보, HWPX, Artifact 관계와 Evidence를 SHA-256으로 검증하고 기존
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

위 목록은 초기 실행·문서·Builder 경계의 대표 흐름입니다. 아래 경로도 모두
`/api/poc/aiworks` 아래에 있으며, 0.30.0에서 추가된 프로젝트 플랫폼 API를 다음 범주로 관리합니다.

- `GET /projects/{id}/backup`, `POST /projects/import`: SHA-256 프로젝트 백업·비파괴 복원
- `GET /projects/{id}/governance`, `POST /projects/{id}/members`, `policy`, `grants`, `status`: 멤버십·정책·권한·보관 상태
- `GET|POST /projects/{id}/artifacts`, `POST /projects/{id}/artifact-relations`, `GET|POST /projects/{id}/artifact-evidence`: 범용 산출물 계보와 근거
- `GET|POST /recipes`, `POST /recipes/search`, `POST /recipes/{id}/fork`, `deprecate`, `POST /projects/{id}/recipes/{id}/install`: Workflow Recipe 생명주기

## RHWP Windows 브리지

1. Windows에 한컴오피스와 Python을 설치하고 `py -m pip install pywin32`를 실행합니다.
2. AIWorks 서버와 브리지에 동일한 `AIWORKS_RHWP_BRIDGE_SECRET`을 지정합니다.
3. `AIWORKS_RHWP_ALLOWED_ROOTS`에는 자동화가 접근할 문서 폴더만 지정합니다.
4. `AIWORKS_RHWP_BRIDGE_COMMAND=py PoC/06-AIWorks/rhwp_windows_agent.py`로 설정합니다.
5. 설정 화면에서 `설치 v1.0.0 · Windows 연결됨`을 확인합니다.

브리지는 요청마다 HMAC, 30초 만료와 nonce 재사용 방지를 검사합니다. 매크로·쉘·네트워크·OLE
액션은 차단하며 문서 변경 도구는 `document.write` 권한과 명시적 확인이 모두 필요합니다.
고수준 도구에 없는 표·개체·글자/문단 모양·쪽/구역 기능은 `rhwp.document.action`에서
RHWP의 HAction과 HParameterSet을 그대로 사용합니다.

## MCP 제작기 사용 순서

1. MCP 제작기에서 양식·처리·데이터·일반 도구·외부 MCP 연결 유형을 고르고 이름, 업무 설명, 공개 범위와 외부 전송 여부를 입력해 새 초안을 생성합니다.
2. 기준 문서 첨부에서 HWPX, PDF, Markdown 또는 TXT 파일을 선택합니다.
   데이터 MCP는 `검색 데이터 원본` 역할로 여러 파일을 선택하고 `등록 자료 RAG 미리보기`에서 질문·근거·페이지를 확인합니다.
   양식 MCP는 HWPX의 플레이스홀더, 작성요령·예시, 완성 보고서 구조를 자동 판별해 현재 보고서 내용을 대응합니다.
3. Manifest와 문서 해시를 확인하고 샌드박스 계약 테스트를 실행합니다.
4. 검증 통과 후 스토어 등록을 누르면 공개 범위와 원본 포함 선택대로 서명 게시됩니다.
5. 스토어에서 권한을 확인하고 정확한 버전을 고정 설치합니다.
6. 스토어의 `수정`은 서명된 버전을 보존하고 다음 patch 버전 초안을 Builder에서 열며, `삭제`는 사용자 제작 버전만 확인 후 제거하고 초안은 남깁니다.
   설정 계약이 있는 MCP는 `환경설정`에서 운영값을 저장하며, 저장값은 다음 실행 계획부터 적용됩니다.
7. 외부 MCP 연결은 승인된 로컬 stdio 프로필 또는 Streamable HTTP를 선택하고 도구명·Capability·입출력 어댑터를 `tools/list`로 확인합니다. 로컬 프로필은 임의 명령을 받지 않고 고정 버전만 실행하며, 원격 실행은 매번 전송 승인을 거칩니다.
8. 기본 `integration.kordoc@1.0.0`은 `kordoc@4.7.3`을 `KORDOC_OFFLINE=1`과 작업별 임시 루트로 실행합니다. 보고서 산출 시 `generate_document`를 자동 불러 정부 보고서 HWPX로 만들고, 생성 파일의 HWPX 무결성 검사 후 RHWP 세션에서 엽니다.

## 검증

    python3 -m unittest discover -s PoC/06-AIWorks/tests -v
    python3 -m py_compile PoC/06-AIWorks/backend.py
    npm install --prefix PoC/06-AIWorks/vendor/kordoc-runtime --omit=dev --omit=optional
    .venv/bin/python PoC/06-AIWorks/tests/browser_smoke.py
    .venv/bin/python PoC/06-AIWorks/tests/builder_flow_smoke.py
    .venv/bin/python PoC/06-AIWorks/tests/data_mcp_flow_smoke.py
    .venv/bin/python PoC/06-AIWorks/tests/feedback_flow_smoke.py
    .venv/bin/python PoC/06-AIWorks/tests/project_portability_smoke.py
    .venv/bin/python PoC/06-AIWorks/tests/project_workbench_smoke.py
    .venv/bin/python PoC/06-AIWorks/tests/rhwp_toolbox_smoke.py
    .venv/bin/python PoC/06-AIWorks/tests/store_builder_smoke.py
    .venv/bin/python PoC/06-AIWorks/tests/studio_runtime_smoke.py

운영 DB에는 샘플 지식과 기준정보를 넣지 않는다. `AIWORKS_ENABLE_DEMO_SEED=0`이 기본값이며,
데모 전용 임시 DB에서만 `1`로 설정한다. 브라우저 스모크도 별도 `AIWORKS_DB_PATH` 서버에서 실행해야 한다.
`project_workbench_smoke.py`는 예외적으로 자신이 만든 문서·세션·메타 후보를 종료 시 자동 삭제하고 이전
작업공간 상태를 복원한다.

누적된 명시적 테스트 fixture는 먼저 dry-run으로 확인하고 적용 시 자동 백업 후 정리한다.

    python3 PoC/06-AIWorks/scripts/cleanup_test_data.py
    python3 PoC/06-AIWorks/scripts/cleanup_test_data.py --apply

제품명은 가칭이며 폴더는 요청대로 PoC/06-AIWorks를 사용합니다.
