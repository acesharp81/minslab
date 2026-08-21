# 07 · 지금 우리 국회에선

청와대·국무회의의 국정 주제·발언·관련 부처와 국회의 회의·의안·표결을 공식 원문에 연결해 탐색하는 국정활동 지식관리 PoC입니다.

## 현재 상태

- 프로젝트 ID: `POC-07`
- 단계: 공식 국무회의 ↔ 대상 국회 위원회 공통 정책 흐름 화면 구현
- 대상 위원회: 행정안전위원회, 예산결산특별위원회, 법제사법위원회
- 공식 API: 8종 endpoint/응답 contract 검증 완료, 일정 수집 활성
- 데이터베이스: provenance·일정·회의·회의록·의안·의안 상세 버전 migration과 idempotent repository 구현
- 국무회의: 정책브리핑 최근 공식본 10건·명시 소관 안건 49건 수집, 추가 API 신청 없음

현재 화면은 정책브리핑의 최근 공식 국무회의와 행안위·예결위·법사위의 공식 회의록·정책 신호·의안·표결을 함께 표시합니다. 국무회의 소관 부처에서 국회 위원회로 이어지는 항목은 공식 연결이 아닌 RULE LINK로 명시합니다.

`국정 연결 인사이트`는 양쪽 공식 원문에서 동일한 정책 taxonomy와 공통 핵심 단어가 확인된 경우만 대조합니다. 행정부 안건과 국회 발언은 각각 OFFICIAL 근거로 표시하되, 두 근거의 관계 자체는 `PROVISIONAL · DRAFT` 공통 정책 신호이며 직접 인과·동일 안건 관계가 아닙니다. 화면에서 날짜 순서와 양쪽 원문 위치를 확인할 수 있습니다.

최근 10회 중 날짜·회차가 모두 일치하는 청와대 공식 브리핑 6건을 연결하고, 대통령의 당부·지시·강조 문단 35개를 OFFICIAL MESSAGE로 원문 위치와 함께 표시합니다.

청와대 자료 시각화의 `공식 소관 부처`와 `공식 안건 검색`은 최근 10회 공식본의 명시 부처·안건명·공식 내용만 대상으로 서버에서 필터링합니다. 추정 부처나 생성 요약은 검색 결과에 섞지 않습니다.

현재 화면은 가짜 국회 데이터를 표시하지 않습니다. API가 검증되고 수집된 데이터만 사용자 화면에 노출하는 것이 원칙입니다.

공공데이터포털에서 신청한 개인/프로젝트 서비스키는 `.env`의 `NATIONAL_ASSEMBLY_API_KEY`에만 저장합니다. source별 신청 링크는 [DATA_SOURCES.md](docs/DATA_SOURCES.md)에 있습니다.

## 핵심 원칙

1. 회의 생명주기와 자료 확정 상태를 분리합니다.
2. 공식 사실과 AI 해석을 별도 모델로 저장합니다.
3. 모든 구조화 결과와 AI 결과는 원문으로 역추적할 수 있어야 합니다.
4. 원본 응답을 보존하고 변경 시 덮어쓰지 않습니다.
5. 이 폴더만으로 개발·테스트·실행·운영 방법을 파악할 수 있어야 합니다.

## 빠른 실행

### Docker Compose

```bash
cp .env.example .env
docker compose up --build
```

브라우저에서 `http://127.0.0.1:8070`을 엽니다.

### Python 개발 실행

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements-dev.txt
uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8070 --reload
```

### 테스트

```bash
python3 -m unittest discover -s backend/tests -v
```

### 합성 LIVE 재생 실험

```bash
python3 scripts/replay_live_simulation.py --trace
```

합성 자막의 partial/final revision을 시간순 재생해 주제·소관을 분류하고 `web/data/live_magazine.json`에 `PROVISIONAL · SIMULATION` 결과를 저장합니다. 이 결과는 공식 데이터베이스에 쓰지 않습니다.

### 공식 LIVE source probe

```bash
python3 scripts/probe_live_sources.py
```

국회 대상 위원회의 공식 생중계 상태와 KTV 플레이어 계약을 확인하고 원본·manifest를 `data/raw/`, 정규화 상태를 `data/processed/live_status.json`에 저장합니다.

국회 공식 LIVE 목록을 30초마다 감시하려면 다음 worker를 실행합니다. 대상 방송이 감지되면 `live_play.asp`의 검증된 필드로 자막 WebSocket 준비 상태까지 기록하며, 화면은 같은 주기로 LIVE/OFF AIR 전환을 반영합니다.

```bash
PYTHONPATH=backend python3 -m app.ingestion.live_monitor --interval 30
```

중간 입장자는 `/api/live/transcript/snapshot`에서 현재 방송의 저장 자막과 cursor를 받은 뒤 `/api/live/transcript/delta?after={cursor}`로 이후 revision만 이어 받습니다. 현재 통합 프록시의 streaming buffering을 고려해 화면은 2초 cursor polling을 사용합니다.

방송 종료 60초 후 `review-worker`가 final 자막을 규칙 기반 주제로 묶고 대표 발언 원문을 `AUTO REVIEW · PROVISIONAL` 카드로 저장합니다. 실제 리뷰가 있으면 해당 기관의 시뮬레이션 카드를 대체하며, 생성형 요약은 사용하지 않습니다.

`official-minutes-worker`는 종료 방송의 날짜를 기준으로 공식 위원회 회의록 API를 1시간마다 다시 수집합니다. 같은 위원회·서울 날짜에 공식 `CONF_ID`가 하나일 때만 연결한 뒤 공식 회의록 HTML 원본과 문장별 발언 위치를 저장합니다. 임시회의록은 `PROVISIONAL`, 정본은 `OFFICIAL` 새 버전으로 유지하며, LIVE final 자막은 20자 이상 단일 exact 후보일 때만 자동 일치 처리합니다.

방송 기록이 없는 과거 대상 위원회 회의도 같은 worker가 `Meeting` 기준으로 공식 본문을 수집합니다. 위원회 회의 행의 `공식 발언 N` 버튼을 누르면 발언자·직위·문장과 국회 회의록의 문장 source span을 확인할 수 있습니다.

상세창의 주제·부처 chip은 공식 문장에 대한 자동 탐색 분류입니다. 원문과 별도 annotation으로 저장되며 검토 전에는 항상 `AUTO CLASSIFICATION · DRAFT`로 표시합니다.

분류 v2는 위원회 명칭을 keyword 근거에서 제외하고 각 태그의 실제 일치 단어를 함께 표시합니다. 위원회 회의 행의 핵심 흐름은 POLICY 발언만 집계하며 부처 표시는 공식 소관 확정이 아닌 `관련 · DRAFT`입니다.

위원회 자료 상단의 통합 정책 흐름은 최신 공식 본문의 POLICY 발언을 주제별로 비교합니다. 카드를 펼치면 생성 요약이 아닌 대표 공식 발언과 source span이 표시되고, 관심 분야를 선택하면 해당 위원회 자료만 다시 집계합니다.

공식 발언의 `itemN`과 같은 회의의 의안 순번 `N.`가 정확히 일치하면 정책 카드 아래에 의안 처리 결과와 본회의 표결을 이어 표시합니다. 번호 근거가 없는 경우 제목이 비슷해도 자동 연결하지 않습니다.

## 디렉터리

```text
PoC/07-NationalAssembly/
├── project.json             # MinsLab PoC 등록 메타데이터
├── README.md
├── AGENTS.md
├── CHANGELOG.md
├── .env.example
├── docker-compose.yml
├── backend/
│   ├── app/                 # 독립 FastAPI 애플리케이션
│   ├── tests/
│   ├── requirements.txt
│   └── Dockerfile
├── web/                     # 의존성 없는 초기 웹 화면
├── docs/                    # 설계·개발·운영·평가 문서
├── prompts/                 # 승인된 AI 프롬프트의 향후 위치
├── scripts/                 # 수집·재처리·운영 명령의 향후 위치
├── tests/fixtures/          # 검증·승인된 최소 응답 fixture
└── data/                    # Git에 넣지 않는 raw/processed 데이터
```

## 환경변수

전체 목록과 안전한 예시는 [.env.example](.env.example)에 있습니다. 비밀값은 `.env`에만 저장하며 Git에 커밋하지 않습니다.

## 문서

- [프로젝트 배경](docs/PROJECT_CONTEXT.md)
- [아키텍처](docs/ARCHITECTURE.md)
- [국무회의 × 국회 실행 플랜](docs/EXECUTION_PLAN.md)
- [데이터 모델](docs/DATA_MODEL.md)
- [데이터 출처](docs/DATA_SOURCES.md)
- [개발 방법](docs/DEVELOPMENT.md)
- [운영 방법](docs/OPERATIONS.md)
- [POC 평가](docs/POC_EVALUATION.md)
- [설계 결정](docs/DECISIONS.md)

## 홈페이지 연결

`project.json`은 루트 `portfolio_loader.py`가 PoC 목록에 자동 등록하며 현재 홈페이지 iframe/proxy로 실행 화면을 제공합니다. 독립 서비스는 기본적으로 `127.0.0.1:18070`에서 실행하고, 부모 서비스의 `NATIONAL_ASSEMBLY_UPSTREAM`으로 다른 주소를 지정할 수 있습니다. 사용자는 같은 출처의 `/poc/national-assembly/`로 접속하며 루트 ASGI가 GET/HEAD 요청을 전달합니다.

NationalAssembly 자체 실행은 부모 저장소의 Python 모듈·가상환경·`.env`에 의존하지 않습니다. API 키와 PostgreSQL 설정은 이 폴더의 `.env`에서만 관리하고, 루트 프록시에는 독립 서비스 주소 외의 프로젝트 비밀값을 전달하지 않습니다.
