# PoC 11 · 상담사례 아카이브

국민권익위원회의 [통합콜센터 상담사례 조회서비스](https://www.data.go.kr/data/15141798/openapi.do)와 [정부합동민원센터 민원상담 사례 게시판](https://counseling.go.kr/sub/notice/notice.do?boardGubun=cas)을 매일 **03:00 Asia/Seoul**에 조회합니다. 두 출처의 사례를 같은 질문·답변 JSON 구조와 RAG용 Markdown 구조로 발행합니다.

## 실행과 설정

공공데이터포털에서 해당 API 활용신청을 완료하고 [`.env`](.env)의 `POC11_SERVICE_KEY=` 뒤에 발급받은 서비스키를 입력합니다. PoC 11은 자신의 `.env`를 시작할 때 읽고, 서버 프로세스에 이미 설정된 값이 있으면 그 값을 우선합니다. 실제 키와 `.env` 파일은 Git에 저장되지 않습니다. [`.env.example`](.env.example)에 선택 설정을 정리했습니다. 새 설정을 적용하려면 루트 ASGI 서비스를 재시작합니다.

- 화면: `/poc/consultation-cases/` (단축 주소 `/counsel`)
- 상태: `/poc/consultation-cases/api/status`
- 다운로드 목록: `/poc/consultation-cases/download/current.json`, `/poc/consultation-cases/download/current.md`
- 분할 파일: `/poc/consultation-cases/download/parts/part-000001.json` 및 같은 번호의 `.md` (상태 API와 화면에 전체 목록 제공)
- 관리자 API 수동 수집: `POST /poc/consultation-cases/api/collect` (루트 관리자 세션과 동일 출처 요청 필요; 같은 날 정상 실행 후 재호출해도 추가 조회 없음)

스케줄러는 루트 ASGI의 lifespan에서 실행되며, API와 게시판을 각각 매일 조회합니다. 서비스가 03:00에 중단되어 있었으면 재시작 후 그날 미실행분을 조회합니다. 여러 앱 프로세스가 떠도 파일 잠금과 날짜 기록으로 같은 날 중복 실행을 막습니다. 프로세스가 계속 실행되고 저장 경로에 쓰기 권한이 있어야 합니다. `POC11_SCHEDULER_ENABLED=0`으로 앱 내 스케줄러를 끌 수 있습니다.

## 수집·버전 규칙

최신 Swagger의 HTTPS 경로 `.../IntegratedGovernmentCall110/searchCounsExmp`를 사용합니다. 포털의 구형 DOCX에 적힌 `NationCall110/searchCounsExmpList` 경로는 현재 폐기 응답을 반환했습니다. 날짜는 `YYYYMMDD`로 조회하며 `pageNo`, `numOfRows=100`, `basDt`, `endDt`, 선택적 `inttCode`, `q`를 요청합니다. 키는 저장하지 않습니다.

최초에는 기본 `2019-01-01`부터 월별로 진행하고 **사례 수 상한 없이, API 호출(429 재시도 포함) 최대 1,000회/일**까지 조회합니다. 공공데이터포털의 개발계정 1,000은 사례 건수가 아니라 일일 API 호출 한도입니다. 실제 계정의 다른 사용량이나 API 자체 제한으로 더 일찍 중단될 수 있습니다. 호출마다 사용량을, 페이지마다 날짜·페이지·고정 종료일을 `data/state.json`에 기록하고 다음 날 이어갑니다. 최신일까지 도달한 뒤에는 최근 7일을 매일 다시 확인해 지연 등록을 포착합니다. 더 오래된 날짜에 뒤늦게 등록된 사례는 자동 감지되지 않을 수 있으며 `POC11_LOOKBACK_DAYS`를 최대 90일까지 늘릴 수 있습니다.

게시판은 전체 목록을 매일 확인하고 새 게시글의 상세페이지와 첨부파일을 수집합니다. 기존 게시글은 7일마다 다시 확인해 변경된 첨부도 감지합니다. PDF는 `pdftotext -layout`, HWP/HWPX는 `extract-hwp`로 본문을 추출합니다. `(내용)`과 `(답변)` 구간이 여러 개면 각 쌍을 독립 사례로 저장합니다. 질문·답변 구분이 없는 문서는 게시글 제목을 `[상담 주제]`로 표시하고 추출된 전체 본문을 답변에 담습니다. 게시글 원문 주소, 게시일, 첨부 SHA-256, 추출 방식과 원문 텍스트는 `raw`에 보존하며 게시판 조회 파라미터는 `request_params`에 남깁니다. 첨부 원본과 추출 텍스트는 `data/board/`에 보관합니다. 게시판 진행 상태와 첨부 다운로드 실패 목록은 `data/board_state.json`에 기록하고, 실패한 게시글은 다음 실행에서 다시 시도합니다. 본문이 없는 게시글은 질문·답변을 임의로 만들지 않습니다. 게시판은 API 인증키 없이 조회됩니다.

같은 원본 레코드는 SHA-256으로 중복 제거합니다. 응답에 안정적인 사례 ID가 없어 **원문 내용이 변경되면 새 레코드**로 기록됩니다. JSON에는 API 원본, 질문·답변의 정규화 텍스트, 수집 시각, 해당 사례를 발견한 요청 파라미터를 함께 저장합니다. API 문서 예시의 `nobdNm`과 Swagger의 `consQustCntn` 두 질문 필드를 처리합니다. 답변의 HTML 줄바꿈은 텍스트로 변환합니다. 신규 사례가 있을 때만 버전을 올립니다. 중복 제거와 수집 중단 시 재개를 위해 사례 원본을 `data/records.sqlite3`에 보관합니다. `data/current.json`과 `data/current.md`는 현재 버전의 분할 파일 목록이며, 사례 본문은 `data/parts/part-NNNNNN.json`과 `.md`에 들어갑니다. 모든 JSON·Markdown 파일은 UTF-8 바이트 기준 10,000,000바이트 이하로 발행하고, `data/versions/vNNNNNN.*`에는 버전별 목록을 보관합니다. 기존 단일 파일 데이터는 다음 실행 때 자동 이전합니다. 생성 데이터와 키는 Git에서 제외합니다.

각 Markdown 분할 파일은 사례별 `##` 블록을 두고 긴 답변을 문단 중심으로 약 2,200자씩 나눕니다. 답변은 인용 블록으로 넣어 원문 안의 Markdown 제목이 청크 경계로 오인되지 않게 합니다. 각 블록에 질문·기관·출처·키워드·원문 주소를 반복해 헤더 기반 RAG 청킹 시 검색 문맥을 보존합니다.

## 검증

```bash
python -m unittest discover -s PoC/11-consultation-cases/tests -v
python -m py_compile main.py PoC/11-consultation-cases/service.py PoC/11-consultation-cases/board_collector.py
```

API 수집에는 승인된 `POC11_SERVICE_KEY`가 필요합니다. 게시판 수집에는 별도 키가 필요하지 않습니다. 서버에는 PDF 본문 추출용 `pdftotext` 실행 파일이 설치되어 있어야 합니다.
