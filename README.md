# MinsLab

오늘의 기록으로 내일의 가능성을 실험하는 곳. Python ASGI 기반의 Local AI chat, portfolio archive, and hands-on RAG/chunking comparison labs.

## 저장소 한눈에 보기

MinsLab은 Python ASGI 애플리케이션을 중심으로 로컬·원격 AI 채팅, 포트폴리오 실습 4개, 실행형 PoC 7개, 관리자 통계를 함께 제공하는 실험 저장소입니다. 공통 `main.py`가 HTML, 정적 빌드 결과, JSON/NDJSON API를 라우팅하고, 독립 런타임이 필요한 PoC 07만 같은 출처 경로로 reverse proxy합니다.

| 구분 | 프로젝트 | 실행 화면 | 상세 문서 |
| --- | --- | --- | --- |
| Home | Local AI Chat | `/` | 이 문서의 Local AI Chat 섹션 |
| Portfolio 01 | 청킹 실습 | `/portfolio?project=chunking-lab` | [projects/01-chunking-lab](projects/01-chunking-lab/README.md) |
| Portfolio 02 | 청킹·임베딩·RAG 과제 | `/portfolio?project=chunking-rag-lab` | [projects/02-chunking-rag-lab](projects/02-chunking-rag-lab/README.md) |
| Portfolio 03 | 계층형 멀티에이전트 하네스 | `/portfolio?project=multiagent-harness` | [projects/03-multiagent-harness](projects/03-multiagent-harness/README.md) |
| Portfolio 04 | 행정 회신 초안 생성 | `/portfolio?project=report-draft` | [projects/04-report-draft](projects/04-report-draft/README.md) |
| PoC 01 | AI Safe Agent / AI 안전비서 | `/poc?project=ai-safe-agent` | [PoC/01-AISafeAgent](PoC/01-AISafeAgent/README.md) |
| PoC 02 | 현장점검플랫폼 | `/poc?project=field-inspection-platform` | [PoC/02-field-inspection-platform](PoC/02-field-inspection-platform/README.md) |
| PoC 03 | 통합 업무관리시스템 | `/poc?project=mois-kms` | [PoC/03-mois-kms](PoC/03-mois-kms/README.md) |
| PoC 04 | AI 언론동향 비서 | `/poc?project=master-press` | [PoC/04-master-press](PoC/04-master-press/README.md) |
| PoC 05 | 북한 야간조명 3D 지도 | `/poc?project=north-korea-night-lights` | [PoC/05-north-korea-night-lights](PoC/05-north-korea-night-lights/README.md) |
| PoC 06 | AIWorks | `/poc?project=aiworks` | [PoC/06-AIWorks](PoC/06-AIWorks/README.md) |
| PoC 07 | 지금 우리 국회에선 | `/poc?project=national-assembly` | [PoC/07-NationalAssembly](PoC/07-NationalAssembly/README.md) |

포트폴리오 등록 규칙은 [projects/README.md](projects/README.md), PoC 등록·배포 규칙은 [PoC/README.md](PoC/README.md)에 정리되어 있습니다.

## 전체 아키텍처

```text
Browser
  ├─ Home / Portfolio / PoC HTML
  ├─ React SPA: Field Inspection, MoIS KMS
  ├─ deck.gl player: North Korea Night Lights
  ├─ static workspace: AIWorks
  ├─ proxied independent app: National Assembly
  └─ Streaming clients: Chat, RAG compare, AI Safe Assistant
          │ HTTPS
          ▼
Nginx
          │ localhost:8000
          ▼
Uvicorn + main.py (minimal ASGI)
  ├─ Ollama/Upstage chat and NDJSON streaming
  ├─ Supabase REST/Auth boundary
  ├─ Upstage / OpenRouter / Hugging Face / Cohere / KMA integrations
  ├─ project module loader
  ├─ static/dist file serving
  └─ SQLite analytics and system metrics
          │
          ├─ Ollama localhost:11434
          ├─ Supabase PostgreSQL + pgvector
          ├─ data/analytics.sqlite3
          └─ external provider APIs

systemd minslab-monitor.timer
          └─ public HTTPS /health probe → SQLite availability history
```

`main.py`는 프레임워크 라우터 대신 ASGI `scope/receive/send`를 직접 처리합니다. CPU 또는 블로킹 I/O 작업은 `asyncio.to_thread`로 넘기고, 토큰 스트림은 NDJSON으로 브라우저에 전달합니다. 프로젝트 모듈은 파일 수정 시 mtime을 비교해 다시 로드하므로 서비스 재시작 후 최신 코드를 사용합니다.

## 저장소 구조

```text
.
├── main.py                    # HTML, 공통 API, 정적 SPA 라우팅
├── chunking_compare.py        # 청킹·임베딩·검색·RAG 공용 엔진
├── portfolio_loader.py        # projects/ 및 PoC/ project.json 자동 검색
├── env_utils.py               # 루트 .env 로딩과 다중 이름 설정 조회
├── supabase_store.py          # 채팅 기록 Supabase/로컬 fallback
├── analytics_store.py         # SQLite 방문 통계·LLM 호출 수·시스템 지표
├── admin_auth.py              # 관리자 암호·서명 세션·요청 제한
├── admin_page.py              # 관리자 화면
├── system_metrics.py          # Linux CPU·메모리·디스크·PSI 측정
├── runtime_monitor.py         # HTTP 요청·5xx·p95 지연 집계
├── monitor_probe.py           # 독립 공개 HTTPS 가용성 프로브
├── deploy/systemd/            # 1분 주기 모니터 서비스·타이머 유닛
├── supabase_schema.sql        # 채팅/청킹 공통 참고 스키마
├── projects/                  # 포트폴리오 01~04
├── PoC/                       # 실행형 PoC 01~07
├── static/                    # 루트 페이지 공개 정적 파일
├── data/                      # 루트 공통 SQLite·채팅 fallback
├── analysis/                  # 로컬 분석 산출물, Git 제외
└── tests/                     # 공통 ASGI·통계 회귀 테스트
```

## 공통 런타임 원칙

- 공통 비밀값은 루트 `.env`, 프로젝트 전용 비밀값은 해당 PoC의 `.env`에 두며 실제 값은 커밋하지 않습니다.
- 변수 이름과 공개 기본값은 가장 가까운 `.env.example`에 기록합니다.
- 브라우저에는 Supabase publishable key만 전달할 수 있으며 service-role, LLM API key, 관리자 비밀값은 서버에만 둡니다.
- React PoC는 개발 시 Vite를 사용하지만 운영에서는 빌드된 `dist/`를 기존 ASGI가 제공합니다.
- 브라우저는 Ollama나 Upstage에 직접 접근하지 않고 백엔드의 통합 모델 목록과 스트리밍 API를 사용합니다.
- 생성형 AI 출력은 자동 발송·확정 자료가 아니라 담당자 검토 전 초안입니다.
- 생성 CSV, PKL, SQLite, 대화 기록, 분석 결과와 실제 환경파일은 Git 추적에서 제외합니다.

## What This App Includes

- Local AI chat UI backed by Ollama and optional Upstage Solar modes, with conversation history support through Supabase.
- Portfolio and PoC archive pages for Python, ASGI, data analysis, RAG, and disaster-safety experiments.
- Responsive desktop, tablet, and mobile layout with drawer menus for chat history and project navigation.
- `02. 청킹실습(과제)` lab for document upload, chunking, embedding, and RAG answer comparison.
- `.hwpx` text extraction from `Contents/section*.xml` files.
- Naive RAG vs Advanced RAG comparison with sequential answer generation, live progress cards, citations, and an evaluation summary card.
- `01. AI Safe Agent` PoC for GPS-based disaster risk lookup, KMA rainfall trends, nearby shelters, and LLM safety reports.
- `02. 현장점검플랫폼` PoC for Supabase-backed inspection tasks, assets, field results, administration, CSV export, and statistics.
- `03. 통합 업무관리시스템` PoC for Supabase Auth, organization-scoped workflows, approval, administration, and Local/Hugging Face/OpenRouter reports.
- `04. 마스터언론` PoC for NAVER News/RSS collection, hybrid relevance scoring, encrypted Kakao OAuth tokens, and per-recipient delivery.
- `05. 북한 야간조명 3D 지도` PoC for monthly VIIRS collection, compact time-series data, and deck.gl visualization.
- `06. AIWorks` PoC for approval-based document automation, MCP creation/distribution, and auditable execution.
- `07. 지금 우리 국회에선` PoC for provenance-first Cabinet/National Assembly meetings, bills, votes, and policy-flow exploration.

## Local AI Chat

홈 채팅은 `/api/models`에서 사용 가능한 모델을 하나의 목록으로 제공합니다. `UPSTAGE_API_KEY`가
있으면 Solar Pro 4, Solar Pro 3, Solar Pro 3 Fast가 Ollama 모델보다 먼저 표시되고 Solar Pro 4가
기본값이 됩니다. 키가 없으면 설치된 Ollama 채팅 모델만 사용합니다. API 모델은 최대 출력 선택지를
4,096~65,536으로, Ollama는 128~1,024로 분리하며 모델별 시스템 프롬프트와 출력 설정을
브라우저에 저장합니다.

모든 공급자는 같은 `/api/chat` NDJSON 계약으로 토큰을 스트리밍합니다. Solar Pro 4/3 요청에는
중간 추론 때문에 최종 답변 예산이 지나치게 줄지 않도록 `UPSTAGE_REASONING_MIN_TOKENS` 하한을
적용하고, Pro 3 Fast에는 별도의 reasoning effort를 요청하지 않습니다. API 키와 공급자 오류는
브라우저에 노출하지 않고 서버 경계에서 정규화합니다.

## Project 01: AI Safe Agent PoC

The first PoC project combines live weather, spatial disaster records, and selectable LLM reporting for a user-selected location.

Workflow:

1. Open `/poc` and select `01. AI Safe Agent`.
2. Allow GPS location access, click the map, choose a saved preset, or enter coordinates manually.
3. Review the 500m radius map markers, compact risk/shelter counters, and legal-dong label resolved through Kakao, VWorld, or the rate-limited OpenStreetMap fallback.
4. Run analysis to fetch KMA rainfall data and generate an AI disaster-safety report.

AI Safe Agent UI includes:

- Initial GPS-based map positioning with graceful fallback to the default Seoul City Hall coordinates.
- A map-centered GPS progress popup that remains visible until positioning succeeds or falls back.
- First map/project selection scroll behavior that centers the map for faster mobile use.
- A dual-axis rainfall and temperature graph from 6 hours ago through 6 hours ahead, with actual timestamps, weather icons, and missing-value gaps.
- Compact counters for nearby risk history and shelters.
- Expandable analysis data for flood traces, landslide records, human-casualty risk zones, and shelters.
- Detail rows that include event dates for risk history and straight-line distance for shelters.
- A server-side knowledge-base build endpoint that generates dated PKL files from public data sources.
- Streaming AI Safe Assistant output with the same stop-and-live-feedback pattern as the home chat.
- Reuse of the already fetched KMA rainfall payload, compact LLM context, and bounded local-model output for lower latency.

Generated PoC datasets such as CSV snapshots and `integrated_disaster_kb_*.pkl` files are intentionally ignored by Git. Rebuild them locally with the in-app `기초 데이터 만들기` action or the `PoC/01-AISafeAgent/import.py` script.

## PoC 02: Field Inspection Platform

The second PoC imports the Lovable-based `acesharp81/ndmsinsptest` application as an independent Vite/React SPA. It is served by the existing ASGI process, so it does not start another web server or open another port.

- Archive entry: `/poc?project=field-inspection-platform`
- Direct application: `/poc/field-inspection-platform/`
- Supabase tables: `tasks`, `assets`, and `results`
- Public PoC mode currently keeps anonymous CRUD and the administrator menu enabled.
- Before production use, add Supabase Auth and user/organization/role-based RLS.
- Source and build notes: `PoC/02-field-inspection-platform/README.md`

## PoC 03: Integrated Work Management System

The third PoC imports `acesharp81/moiskms` as a static Vite/React SPA served by the existing ASGI process. It adds isolated KMS tables to the existing MinsLab Supabase project, preserving Supabase Auth and RLS, while the original fixed Lovable AI Gateway call is replaced with selectable Local LLM, Hugging Face, and OpenRouter providers.

- Archive entry: `/poc?project=mois-kms`
- Direct application: `/poc/mois-kms/`
- User and workflow data: Supabase Auth, `profiles`, `user_roles`, `divisions`, `teams`, `tasks`
- Shared database: existing `SUPABASE2_URL` with KMS tables added by `20260710000000_minslab_kms.sql`
- AI options: model, temperature, max output tokens, and editable system prompt
- No additional Node server or public port
- Source and security notes: `PoC/03-mois-kms/README.md`

## PoC 04: AI 언론동향 비서

The fourth PoC is an AI-assisted Korean press-monitoring service. It collects institution-level NAVER News/RSS articles, runs one shared common analysis per article, creates local embeddings, evaluates only candidate cases with hybrid vector/LLM scoring, connects MOIS press releases through RAG-style matching, sends qualifying items through KakaoTalk `Send to me`, and publishes scheduled CaseON magazine editions.

Current user-facing modules include period-aware dashboard monitoring, explicit include/exclude judgment feedback with multi-select reasons, persisted similar-article grouping, neural topic analysis with a two-week case delivery trend, press-release trends, CaseON 07:00/12:00/18:00 magazines, browser-based magazine read-aloud, Kakao case and magazine subscriptions, an anonymous case-request board with OpenAI Clean AI moderation, and parallel model workers across Cloudflare Workers AI, Groq, OpenRouter, OpenAI, NVIDIA NIM, and local Ollama.

- Archive entry: `/poc?project=master-press`
- Direct dashboard: `/poc/master-press/`
- User menu: `매뉴얼`, `구독 및 케이스 신청`, `대시보드`, `보도자료 동향`, `신경망 분석`, `매거진`
- Admin menu: member auto/bulk approval and subscription editing, organization/case management, model settings, notices, thresholds, reanalysis controls, non-blocking GPT-5.4 mini shadow comparison, unreviewed disagreements, and text feedback history
- Magazine read-aloud: Web Speech API with play/pause/stop, `x1`–`x2` speed controls, PC `x1.5`/mobile `x1.25` defaults, per-organization local case/speed preferences, current-issue highlighting, sticky-header-aware mobile scrolling, an always-accessible mobile `▶`/`Ⅱ` control, and Screen Wake Lock while speaking
- Browser limitation: installed Korean voices are preferred, but voice gender is not standardized; reliable lock-screen/background audio requires server-generated audio with `<audio>` and Media Session instead of browser `speechSynthesis`
- Shared homepage administrator session; no separate web service or port
- SQLite operational queue/cache with optional Supabase metadata mirror; the main pipeline and GPT shadow evaluator run in isolated low-priority systemd services, short-retention cleanup runs only after successful Supabase history verification, and magazine publication performs a fresh edition-scoped grouping pass before snapshotting results
- Detailed user manual, reproducible read-aloud architecture, lifecycle rules, test commands, and background-audio migration design: [PoC/04-master-press/README.md](PoC/04-master-press/README.md)

## PoC 05: 북한 야간조명 3D 지도

The fifth PoC collects monthly VIIRS night-light observations inside the North Korean boundary and serves compact gzip datasets through a shared deck.gl player.

- Archive entry: `/poc?project=north-korea-night-lights`
- Direct map: `/poc/north-korea-night-lights/map`
- Data APIs: `/api/poc/north-korea-night-lights/maps`, `/api/poc/north-korea-night-lights/data/YYYY-MM`
- Collection: Google Earth Engine `NOAA/VIIRS/DNB/MONTHLY_V1/VCMCFG`
- Reproducible collection, observation-quality rules, and map controls: [PoC/05-north-korea-night-lights/README.md](PoC/05-north-korea-night-lights/README.md)

## PoC 06: AIWorks

The sixth PoC combines document editing, MCP creation and installation, explicit permission approval, versioned artifacts, and audit logs in one local-first workspace.

- Archive entry: `/poc?project=aiworks`
- Direct workspace: `/poc/aiworks/`
- Server boundary: `/api/poc/aiworks/*`
- Current baseline: AIWorks 0.30.0 with immutable Markdown source revisions, derived HWPX, project backup/restore, Artifact/Evidence lineage, Recipe Library, RBAC, permission grants, and resumable workflow attempts
- Model/runtime boundary: approval-gated Solar routing plus fixed local stdio or explicitly approved Streamable HTTP MCP execution
- Implementation and operations: [PoC/06-AIWorks/README.md](PoC/06-AIWorks/README.md)
- Product roadmap: [PoC/06-AIWorks/docs/PROJECT_PLATFORM_ROADMAP.md](PoC/06-AIWorks/docs/PROJECT_PLATFORM_ROADMAP.md)

## PoC 07: 지금 우리 국회에선

The seventh PoC is an independent FastAPI/PostgreSQL service that connects official Cabinet material with National Assembly committee meetings, minutes, bills, and votes while preserving source versions and separating official facts from provisional relationships.

- Archive entry: `/poc?project=national-assembly`
- Same-origin application: `/poc/national-assembly/`
- Independent runtime: defaults to `http://127.0.0.1:18070`, configured with `NATIONAL_ASSEMBLY_UPSTREAM`
- Scope: 행정안전위원회, 예산결산특별위원회, 법제사법위원회 and the latest verified Cabinet records
- Provenance policy: raw-first ingestion, SHA-256 versions, source spans, and explicit `OFFICIAL` / `PROVISIONAL` / `SIMULATION` labels
- Development, ingestion, LIVE workers, and operations: [PoC/07-NationalAssembly/README.md](PoC/07-NationalAssembly/README.md)

## Portfolio 02: Chunking / Embedding / RAG Lab

The second portfolio project is the main RAG experiment page.

Workflow:

1. Paste text or upload a supported document, including `.hwpx`.
2. Select one to three chunking strategies.
3. Run chunking to preview chunks and strategy pros/cons.
4. Run embedding to store selected chunks in Supabase tables.
5. Ask a question and compare RAG answers.

Supported chunking strategies:

- Fixed length chunking
- Paragraph-first recursive chunking
- Sentence-window semantic chunking

RAG modes:

- `Naive RAG`: single query embedding, vector search, Top-K context, LLM answer.
- `Advanced RAG`: query variants, expanded candidate retrieval, best-effort Cohere reranking, context compression, LLM answer.
- `Naive + Advanced`: runs both modes sequentially for each embedded chunking strategy.

Comparison output includes:

- Retrieval scores and searched chunks
- Rerank scores when available
- Query variants for Advanced RAG
- Context compression badge
- Citation labels such as `[검색 조각 1]`
- Answer length, elapsed time, and cited evidence count
- Naive vs Advanced evaluation card using a lightweight heuristic score

The evaluation card is only a lab aid. Final quality should still be judged by reading the answer and its source chunks.

## Local Setup

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Fill `.env` with your own values. Do not commit `.env`.

Required for full functionality:

- `OPENROUTER_API_KEY`
- `SUPABASE2_URL`
- `SUPABASE2_SERVICE_ROLE_KEY`

Optional:

- `OLLAMA_BASE_URL`, defaults to `http://127.0.0.1:11434`
- `UPSTAGE_API_KEY`, enables Solar Pro 4, Solar Pro 3, and Solar Pro 3 Fast in the main chat
- `UPSTAGE_BASE_URL`, defaults to `https://api.upstage.ai/v1`
- `UPSTAGE_REASONING_MIN_TOKENS`, defaults to `4096` so reasoning does not consume the final answer budget
- `NATIONAL_ASSEMBLY_UPSTREAM`, defaults to `http://127.0.0.1:18070` for the PoC 07 same-origin proxy
- `OPENROUTER_BASE_URL`, defaults to `https://openrouter.ai/api/v1`
- `OPENROUTER_EMBEDDING_MODEL`, defaults to `openai/text-embedding-3-small`
- `COHERE_API_KEY`, required for Cohere reranking
- `COHERE_RERANK_MODEL`, defaults to `rerank-v4.0-fast`
- `HF_API_KEY`, `KMA_AUTH_KEY`, and public-data keys for full AI Safe Agent functionality
- `KAKAO_REST_API_KEY` or `VWORLD_API_KEY` for AI Safe Agent legal-dong reverse geocoding
- `DISASTER_KB_PATH` to pin a specific AI Safe Agent knowledge-base PKL
- `VITE_FIELD_INSPECTION_SUPABASE_URL` and `VITE_FIELD_INSPECTION_SUPABASE_PUBLISHABLE_KEY` for the public field-inspection client build
- `SUPABASE2_PUBLISHABLE_KEY` for the browser-safe PoC 03 runtime configuration

## Run Locally

```bash
uvicorn main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`.

For the current server deployment, the app is managed by the `myservice` systemd service and served behind Nginx.

## Chat History Storage

Chat history is scoped by device while there is no login system. The browser stores a stable `minslab.deviceId` in localStorage and sends it as `client_id` to `/api/history`.

If Supabase `chat_history` exists, history is stored there. If the table is missing or unavailable, the backend falls back to `data/chat_history.json`, which is ignored by git.

The API already accepts optional `account_id` and `scope_type` fields so a future login flow can switch history ownership from device-scoped to account-scoped without changing the chat UI contract.

## Site Analytics and Administration

Page views are stored in the server-local `data/analytics.sqlite3` database through Python's built-in SQLite driver; no separate database server is required. Daily rollups remain available when raw IP visit events pass the configured retention period.

Configure the administrator only in the untracked `.env` file:

```bash
MINSLAB_ADMIN_PASSWORD=CHANGE_THIS_ADMIN_PASSWORD
MINSLAB_ADMIN_SESSION_SECRET=YOUR_RANDOM_SESSION_SECRET
MINSLAB_ANALYTICS_RETENTION_DAYS=90
MINSLAB_MONITOR_URL=https://YOUR_DOMAIN/health
# 시스템 지표 수집 주기는 현재 main.py의 SYSTEM_METRICS_INTERVAL_SECONDS(60초)를 사용합니다.
```

When `MINSLAB_ADMIN_PASSWORD` is exactly `MULTI_AGENT_LIVE_ENABLED_key`, the administrator uses the value stored under that environment variable. Optional outer quotes in `.env` are removed and are not part of the password entered in the browser.

Open `/admin` to inspect today's IP addresses, visited pages, referrers, and user agents. The password is never included in browser code. Authentication uses a signed, expiring `HttpOnly`, `Secure`, `SameSite=Strict` cookie. `Total` means cumulative page views, while `Today` uses the `Asia/Seoul` calendar date.

The admin dashboard stores Linux resource samples every 60 seconds and graphs the most recent 48 hours. The five graphs intentionally cover only CPU, host memory, web-service memory, HTTP p95 latency, and root-disk usage. The compact health strip additionally checks an independent public HTTPS probe, HTTP 5xx rate, inode usage, I/O PSI, and systemd restart count. `HOST MEMORY` uses Linux `MemAvailable` and includes every PoC, Ollama, and desktop process; `WEB SERVICE` uses the `myservice.service` cgroup so application growth can be inspected separately. The operational verdict also checks available memory, Swap usage, memory PSI `avg10`, new OOM kills, and six-hour web-service growth. Samples older than seven days are removed automatically.

The public HTTPS probe runs outside the web process through `minslab-monitor.timer`, so a stopped or wedged application can still leave a failure sample in SQLite. Install the units from `deploy/systemd/`, reload systemd, and enable `minslab-monitor.timer`; its default interval is one minute.

Total, Today, and Visitors cards draw a subtle seven-day SQLite trend sparkline behind the current number.
The status popover distinguishes web-service uptime (the current Uvicorn process) from physical-server uptime (Linux `/proc/uptime`).
`Local LLM calls` is a persistent SQLite counter of actual Ollama generation attempts; model-list and health checks are excluded, and counting starts when this feature is deployed.

## Supabase Tables

Project 02 expects three pgvector-backed tables for selected chunking strategies:

- `chucking_test1`
- `chucking_test2`
- `chucking_test3`

The app also supports legacy misspelled aliases when resolving existing tables.

Rows written by the lab include:

- `id`
- `content`
- `metadata`
- `embedding`

Metadata stores strategy, rank, token count, embedding provider, and run information.

## API Overview

Important local API routes:

- `GET /api/health`: service health summary
- `POST /api/analytics/visit`: record a public page view
- `POST /api/admin/login`: create an administrator session
- `POST /api/admin/logout`: clear an administrator session
- `GET /api/admin/session`: inspect the current administrator session
- `GET /api/admin/analytics`: list protected visit details and rollups
- `GET /api/models`: configured Upstage Solar modes followed by available Ollama chat models
- `POST /api/chat`: provider-normalized streaming chat response
- `GET /api/history`: load chat history
- `POST /api/history`: save chat history
- `POST /api/hwpx-extract`: extract text from `.hwpx`
- `POST /api/chunking-plan`: create chunking plans
- `POST /api/chunking-embed`: embed a selected plan into Supabase
- `POST /api/chunking-compare`: run Naive or Advanced RAG comparison
- `GET /api/portfolio/report-draft/models`: list installed local Ollama models and report options
- `POST /api/portfolio/report-draft/generate`: generate a report draft with the selected local model
- `GET /api/poc/ai-safe-agent/kb/status`: inspect AI Safe Agent knowledge-base status
- `POST /api/poc/ai-safe-agent/kb/build`: build AI Safe Agent public-data knowledge base
- `GET /api/poc/ai-safe-agent/models`: list AI Safe Agent model options
- `POST /api/poc/ai-safe-agent/reverse-geocode`: resolve legal-dong labels for coordinates
- `POST /api/poc/ai-safe-agent/spatial`: return nearby risk/shelter details without LLM execution
- `POST /api/poc/ai-safe-agent/rain`: return KMA hourly rainfall trend data
- `POST /api/poc/ai-safe-agent/analyze-stream`: stream prepared analysis context and AI report tokens as NDJSON
- `POST /api/poc/ai-safe-agent/analyze`: run rainfall, spatial lookup, and AI report generation
- `GET /api/poc/mois-kms/models`: list Local, Hugging Face, and OpenRouter report models
- `POST /api/poc/mois-kms/report`: generate an authenticated AI report
- `/api/poc/mois-kms/auth/*`: resolve login, signup metadata, ID checks, and signup
- `POST /api/poc/mois-kms/admin/delete-user`: delete a user through the protected service-role boundary

Example comparison payload:

```json
{
  "prompt": "이 문서의 핵심 내용을 요약해줘",
  "model": "openai/gpt-4o-mini",
  "tables": ["chucking_test1"],
  "rag_mode": "advanced",
  "temperature": 0.2,
  "top_k": 5,
  "reranking": true,
  "rerank_model": "rerank-v4.0-fast"
}
```

## Public Repository Notes

Before pushing to GitHub, check:

- `.env` is not tracked.
- `.venv/`, `__pycache__/`, `analysis/`, generated report JSON files, local `.hwpx` source documents, PoC CSV snapshots, and generated PKL files are not tracked.
- Service-role Supabase keys stay only on the backend runtime.
- If any key was ever committed or pasted publicly, rotate it before publishing.

Useful checks:

```bash
git status --short
git add --dry-run .
python3 -m py_compile main.py chunking_compare.py
```

## 운영과 배포

현재 운영 구조는 Nginx → `myservice` systemd → Uvicorn `127.0.0.1:8000`입니다. React PoC의 `dist/`를 갱신한 경우에도 최종적으로 Python 서비스를 재시작해 정적 파일과 동적 모듈 상태를 함께 확인합니다.

```bash
python3 -m py_compile main.py chunking_compare.py
python3 -m unittest tests.test_site_api tests.test_site_analytics -v
sudo systemctl restart myservice
systemctl status myservice --no-pager
curl -fsS http://127.0.0.1:8000/health
```

프런트엔드를 수정한 프로젝트는 해당 폴더에서 추가로 실행합니다.

```bash
npm run typecheck
npm run build
```

GitHub 배포 전에는 `git diff --check`, 비밀값 미추적 여부, 생성 데이터 제외 여부를 확인합니다. 확인 후 현재 브랜치를 커밋하고 `git push origin main`으로 게시합니다.
