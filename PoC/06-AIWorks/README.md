# 06 · AIWorks

여러 MCP와 AI 모델을 업무 목적에 맞게 조합하는 승인 기반 AI 업무 플랫폼의 초기 PoC입니다.

## 현재 구현

- GPT형 첫 화면에서 명령과 문서를 함께 제출하면 의도 분석 결과에 따라 업무 MCP와 편집기 MCP를 동적으로 로딩
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
구조 보존을 위해 HWPX 직접 편집은 현재 텍스트 변경만 지원하며, 기본 문서는 HTML로 내보냅니다.
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

MCP 제작기는 자연어 설명과 공개 범위, 원본 포함 여부, 외부 전송 허용 여부를 서버 초안으로
저장합니다. 계약·고정 의존성·최소권한·네트워크 경계·입출력 Schema 검사를 모두 통과해야
게시할 수 있으며, 게시 시 공개 범위와 원본 포함 여부를 다시 확인합니다. 게시된 패키지는
동일한 조직 서명 검증을 거쳐 스토어에 즉시 나타나고 정확한 버전으로 설치됩니다.
기준 문서는 파일당 최대 5MB이며 브라우저에서 서버 로컬 저장소로만 전달됩니다. HWPX는 문단과
공통데이터 후보, PDF는 컨테이너·암호화 여부와 페이지 표식, Markdown·TXT는 UTF-8 구조를
검사합니다. 원본 포함을 선택한 경우에만 게시 패키지 파일로 복사되고 설치 전 해시를 다시
검증합니다. 실패한 패키지는 설치 목록에서 격리되며 운영 진단이 실패 상태가 됩니다.

지식 계층은 문서, 공통데이터와 노트를 출처 및 관계로 연결합니다. 질의 시 사용자 접근등급과
기준일을 먼저 적용하며, 연결된 원문 근거를 찾지 못하면 답변을 생성하지 않습니다. 숫자형
공통데이터는 두 시점의 값, 변화량과 변화율을 함께 반환합니다.

멀티모달 계층은 파일 확장자와 실제 바이트 형식을 함께 검사합니다. 코드 구조, PNG·JPEG 크기,
WAV 재생정보와 MP4 컨테이너 검사는 로컬에서 동작합니다. 문서와 코드 프리셋은 실행 계획
준비 상태이며 이미지 생성, 음성 전사와 영상 요약은 전용 모델·런타임이 연결될 때까지
contract-only로 차단됩니다.

운영 화면은 SQLite 무결성, MCP 패키지 서명, 출처 연결, 무료 모델 제한, 승인·스토어 키와
어댑터 준비상태를 점검합니다. E2E 수용성 테스트는 외부 모델을 호출하지 않는 합성 모드에서
HWPX 분석, 실행 계획, 서명 승인, 일회용 실행, 문단 패치, 자산 보존과 감사 추적을 검증합니다.
stale-document 실패 주입으로 원본 변경 충돌 차단도 확인할 수 있습니다.

## 무료 모델 자동 라우팅

- Google Gemma 4 26B A4B 무료: 문서 작성, 요약, 공문체와 번역
- OpenAI gpt-oss-20b 무료: 복합 추론, 계획, 계산과 근거 검증

의도 분석 MCP는 사용자 요청을 로컬에서 먼저 분류합니다. 모델 관리 MCP는 입력·출력 가격이
모두 0이고 ID가 :free로 끝나는 모델만 허용합니다. 외부 전송 체크와 model.invoke,
network.send 권한 승인이 완료된 경우에만 OpenRouter 호출을 실행합니다.

## 경로

- 독립 화면: /poc/aiworks/
- 포트폴리오 셸: /poc?project=aiworks
- 계약: contracts/*.schema.json
- 프로젝트 중심 플랫폼 전환 로드맵: [docs/PROJECT_PLATFORM_ROADMAP.md](docs/PROJECT_PLATFORM_ROADMAP.md)
- 1~17단계 PoC 구축 이력: [docs/BUILD_PLAN.md](docs/BUILD_PLAN.md)
- 서버 API: /api/poc/aiworks/bootstrap

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
26. GET·POST /api/poc/aiworks/documents/workspace
27. GET /api/poc/aiworks/documents/workspace/{workdoc_id}
28. GET /api/poc/aiworks/documents/versions/{docver_id}
29. GET /api/poc/aiworks/rhwp/capabilities
30. POST /api/poc/aiworks/rhwp/invoke
31. POST /api/poc/aiworks/documents/sessions
32. GET /api/poc/aiworks/documents/sessions/{docsession_id}
33. POST /api/poc/aiworks/documents/sessions/{docsession_id}/commands
34. GET /api/poc/aiworks/documents/sessions/{docsession_id}/artifact

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

1. MCP 제작기에서 이름, 업무 설명, 공개 범위와 외부 전송 여부를 입력하고 새 초안을 생성합니다.
2. 기준 문서 첨부에서 HWPX, PDF, Markdown 또는 TXT 파일을 선택합니다.
3. Manifest와 문서 해시를 확인하고 샌드박스 계약 테스트를 실행합니다.
4. 검증 통과 후 스토어 등록을 누르면 공개 범위와 원본 포함 선택대로 서명 게시됩니다.
5. 스토어에서 권한을 확인하고 정확한 버전을 고정 설치합니다.
6. 중단한 작업은 제작기 상단의 저장된 제작 작업에서 다시 엽니다.

## 검증

    python3 -m unittest discover -s PoC/06-AIWorks/tests -v
    python3 -m py_compile PoC/06-AIWorks/backend.py
    .venv/bin/python PoC/06-AIWorks/tests/browser_smoke.py

제품명은 가칭이며 폴더는 요청대로 PoC/06-AIWorks를 사용합니다.
