# PoC 08 · 나라장터 AI 공통기반 활용 가능 사업 레이더

나라장터 사전규격과 용역 본공고의 공개자료를 수집하고, 첨부 원문에 근거해 범정부 AI 공통기반 활용 가능성이 있는 사업을 **후보로 선별**하는 독립 실행형 FastAPI PoC입니다. 이 서비스의 A~E 등급은 위반·미사용 여부를 확정하는 행정판단이 아닙니다.

## 현재 구현 범위

- 사전규격·본공고 목록 및 e발주 첨부정보 OpenAPI 어댑터, 페이지네이션·재시도·중복 upsert
- 허용 도메인·HTTPS·확장자·크기 제한을 적용한 다운로드와 SHA-256 중복 저장 방지
- PDF, DOCX, TXT, HWPX, ZIP 본문 추출 및 바이너리 HWP 안전 미지원 처리
- ZIP path traversal와 실행파일 차단, 파일 단위 실패 격리 및 재처리
- YAML 규칙 필터, OpenAI-compatible 분석기, 키 없이 동작하는 결정론적 mock 분석기
- 근거 인용 원문 일치 검증, A~E 판정, 확인 질문, 조치상태와 감사로그
- 대시보드, 공고 목록·상세, Markdown/HTML 일일 리포트, REST API와 CLI
- 기존 Supabase 2 Data API 운영 저장소, PoC08 전용 SQLite 장애 캐시와 시작 시 재동기화

## 3분 실행

Docker만 있으면 이 폴더 밖의 파일이나 상위 저장소가 필요하지 않습니다.

```bash
cp .env.example .env
docker compose up --build -d
curl http://localhost:18080/health
```

`http://localhost:18080`을 열면 mock 공고 5건이 자동 적재됩니다. 종료는 `docker compose down`입니다. 데이터는 이 폴더의 `data/`에 남습니다.

Linux 계정 UID/GID가 1000이 아니면 `.env`의 `LOCAL_UID`, `LOCAL_GID`를 `id -u`, `id -g` 결과로 바꾸십시오. 이는 bind mount의 SQLite·리포트 쓰기 권한을 맞추기 위한 값입니다.

로컬 Python 실행:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python scripts/seed_sample.py
python scripts/preflight.py
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

모든 경로는 `app/config.py`의 실제 프로젝트 위치를 기준으로 해석하므로 다른 이름·위치로 폴더를 복사해도 동작합니다. 테스트 데이터 위치를 분리하려면 `DATA_DIR=/tmp/radar-data`처럼 지정할 수 있습니다.

## 실데이터 전환 준비

1. 공공데이터포털에서 아래 두 서비스의 활용신청을 완료하고 **Decoding(원본) 서비스키**를 준비합니다.
   - 조달청_나라장터 사전규격정보서비스
   - 조달청_나라장터 입찰공고정보서비스
2. `.env`에서 다음 값을 변경합니다.

```env
G2B_MODE=live
G2B_SERVICE_KEY=발급받은_원본_키
AUTO_SEED_SAMPLE=false
```

현재 공공데이터포털 Swagger에서 확인한 기본값은 다음과 같습니다.

- 사전규격: `https://apis.data.go.kr/1230000/ao/HrcspSsstndrdInfoService/getPublicPrcureThngInfoServc`
- 용역 본공고: `https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoServc`
- e발주 첨부: `getBidPblancListInfoEorderAtchFileInfo`

공공 API 명세나 게이트웨이 경로 변경에 대비해 base URL과 operation은 모두 환경변수입니다. 개발계정 기본 트래픽은 일 1,000건이므로 목록을 먼저 받고, e발주 첨부 API는 규칙상 검토할 공고에만 호출합니다. 운영 전에는 실제 키로 `--lookback-days 1 --no-analyze` 스모크 테스트를 수행하고 `pipeline_runs`의 수신 건수와 원천 JSON 필드 매핑을 확인하십시오.

```bash
python scripts/run_collector.py --lookback-days 3
python scripts/reparse_failed.py
python scripts/run_daily_report.py --date 2026-09-11
```

## LLM 분석

기본 3단계 provider 값은 `mock`이어서 키 없이도 판정 스키마와 사용자 흐름을 검증합니다. 실운영 구성은 Gemini 2차 선별, GPT-5.4 mini 3차 심층분석, NVIDIA Nemotron 3 Super 장애 대체입니다.

```env
STAGE2_PROVIDER=gemini
STAGE2_MODEL=gemini-2.5-flash-lite
GEMINI_API_KEY=...

STAGE3_PRIMARY_PROVIDER=openai
STAGE3_PRIMARY_MODEL=gpt-5.4-mini
OPENAI_API_KEY=...

STAGE3_FALLBACK_PROVIDER=nvidia
STAGE3_FALLBACK_MODEL=nvidia/nemotron-3-super-120b-a12b
NVIDIA_API_KEY=...
```

2차 입력은 기본 8,000자, 3차 입력은 100,000자로 분리합니다. 3차는 하루 10건·동시 1건으로 제한하며 OpenAI 3회 실패 시 NVIDIA로 자동 전환합니다. 서버로 보내는 내용은 수집한 공개 메타데이터와 공개 첨부 추출문으로 제한됩니다. 프롬프트는 `app/prompts/`, 스키마는 `app/schemas.py`에 있습니다. A/B/C 등급은 원문 인용이 필수이며 인용문이 입력에 없으면 분석 실패로 저장됩니다.

키 발급 위치와 입력 방법은 [docs/API_KEYS.md](docs/API_KEYS.md)에 정리했습니다.

키 입력 후 아래 명령은 각 LLM에 작은 공개 샘플을 한 번씩 보내 연결·모델 접근·JSON 스키마를 점검합니다. 키 값은 출력하지 않습니다.

```bash
python scripts/preflight.py
python scripts/probe_llm.py --target all
```

## Supabase Data API

운영 원본은 기존 서비스와 같은 Supabase REST Data API에 저장합니다. 필요한 값은 이미 보유한 `SUPABASE2_URL`과 `SUPABASE2_SERVICE_ROLE_KEY` 두 개뿐이며 DB 비밀번호나 Pooler URI는 필요하지 않습니다. 키는 서버에서만 사용하고 브라우저에는 노출하지 않습니다.

```env
SUPABASE2_URL=https://PROJECT_REF.supabase.co
SUPABASE2_SERVICE_ROLE_KEY=...
DATABASE_URL=sqlite:///./data/supabase-cache.db
```

최초 한 번 [Supabase 마이그레이션](supabase/migrations/20260911000000_poc08_radar.sql)을 Dashboard의 SQL Editor에서 실행합니다. 모든 테이블은 `poc08_` 접두사와 RLS를 사용하며 anon/authenticated 접근은 허용하지 않습니다. 앱은 커밋 후 변경을 REST로 반영하고, 일시 장애 때는 PoC08 전용 SQLite 캐시에 보존한 뒤 다음 시작 시 원격과 재조정합니다.

## 주요 화면과 API

| 경로 | 기능 |
| --- | --- |
| `/` | 오늘 지표, 우선 조치, 누적 등급 분포 |
| `/notices` | 단계·기관·등급·조치상태·키워드 필터 |
| `/notices/{id}` | 첨부 본문, 판정 근거, 질문, 조치 관리 |
| `/reports/daily` | 일일 Markdown/HTML 리포트 |
| `/health` | DB·수집모드·LLM·설정 준비상태 |
| `POST /api/collect/run` | 수집·다운로드·파싱·분석 실행 |
| `POST /api/notices/{id}/parse` | 해당 공고 첨부 재파싱 |
| `POST /api/notices/{id}/analyze/simple` | 간소화 검증 |
| `POST /api/notices/{id}/analyze/deep` | 심층 검증 |
| `PATCH /api/actions/{id}` | 조치상태·담당자·메모 변경 |

FastAPI 자동 명세는 `/docs`에서 볼 수 있습니다.

## 환경변수

전체 목록과 안전한 기본값은 `.env.example`에 있습니다. 핵심 항목은 다음과 같습니다.

| 항목 | 설명 |
| --- | --- |
| `SUPABASE2_URL`, `SUPABASE2_SERVICE_ROLE_KEY` | 운영 Data API 주소와 서버 전용 키 |
| `DATABASE_URL`, `DATA_DIR` | 장애 복구용 로컬 캐시 및 원문·추출문·리포트 위치 |
| `G2B_MODE`, `G2B_SERVICE_KEY` | mock/live 선택 및 공공데이터포털 키 |
| `G2B_PAGE_SIZE`, `G2B_MAX_PAGES` | 호출량과 한 실행의 최대 수집 범위 |
| `STAGE2_*`, `STAGE3_*` | 단계별 provider·모델·한도·동시성 |
| `GEMINI_API_KEY`, `OPENAI_API_KEY`, `NVIDIA_API_KEY` | 서버 전용 LLM 인증정보 |
| `MAX_FILE_SIZE_MB`, `DOWNLOAD_ALLOWED_HOSTS` | 다운로드 보안 경계 |
| `ADMIN_USERNAME/PASSWORD`, `ADMIN_TOKEN` | HTTP Basic 또는 Bearer 인증 |

`APP_ENV=production`에서는 인증정보가 없으면 `/health`가 `degraded`를 반환합니다. 외부 공개 배포는 리버스 프록시 TLS와 기관 인증체계를 추가해야 합니다.

## 판정 등급

| 등급 | 의미 | 기본 조치 |
| --- | --- | --- |
| A | 문서에 공통기반 활용이 명시됨 | 실제 이용 여부 후속 확인 |
| B | AI 적합성이 높으나 활용 문구 미확인 | 최우선 담당자 확인 |
| C | LLM API·RAG·GPU 등 일부 활용 가능 | 부분 적용 가능성 안내 |
| D | 공개자료만으로 판단 곤란 | 질문을 제시하고 수동 검토 |
| E | 문서에 특수환경 등 명확한 부적합 근거 | 사유 기록 후 종료 |

“활용 문구 미확인”은 “미사용”과 다릅니다. 자료에 없는 보안등급·망구성·실제 구축방식은 추정하지 않습니다.

## 테스트

```bash
pytest -q
```

파일명, 20건 이상의 필터 사례, 중복 upsert, SHA 중복 저장 방지, JSON 스키마와 원문 근거, ZIP traversal, 인코딩, HWP 미지원, 공고 단위 실패 격리를 검증합니다.

## 운영과 데이터 보안

- `data/raw`, `data/parsed`, `data/reports`, DB와 로그는 Git에서 제외됩니다.
- 수동 업로드 기능은 없으며 공개 나라장터 URL만 다운로드합니다.
- 다운로드는 HTTPS와 허용 도메인만 사용하고 redirect, 비표준 포트, 실행·스크립트 확장자를 거부합니다.
- 수집/필터/분석/조치 변경은 `pipeline_runs`, `analysis_runs`, `audit_logs`에 기록합니다.
- 바이너리 HWP는 검증된 변환기 격리구성이 생길 때까지 `unsupported`로 남겨 전체 파이프라인을 멈추지 않습니다.
- SQLite 백업은 서비스 쓰기를 잠시 멈춘 뒤 `data/app.db`와 `data/`를 함께 보관하십시오. 운영 규모가 커지면 PostgreSQL, Alembic, 작업 큐와 객체 저장소를 도입합니다.

보완된 구축계획과 운영 전 게이트는 [docs/PLAN_REVIEW.md](docs/PLAN_REVIEW.md)에 정리했습니다.
