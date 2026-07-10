# MinsLab

오늘의 기록으로 내일의 가능성을 실험하는 곳. Python ASGI 기반의 Local AI chat, portfolio archive, and hands-on RAG/chunking comparison labs.

## What This App Includes

- Local AI chat UI backed by Ollama, with conversation history support through Supabase.
- Portfolio and PoC archive pages for Python, ASGI, data analysis, RAG, and disaster-safety experiments.
- Responsive desktop, tablet, and mobile layout with drawer menus for chat history and project navigation.
- `02. 청킹실습(과제)` lab for document upload, chunking, embedding, and RAG answer comparison.
- `.hwpx` text extraction from `Contents/section*.xml` files.
- Naive RAG vs Advanced RAG comparison with sequential answer generation, live progress cards, citations, and an evaluation summary card.
- `01. AI Safe Agent` PoC for GPS-based disaster risk lookup, KMA rainfall trends, nearby shelters, and LLM safety reports.

## Project 01: AI Safe Agent PoC

The first PoC project combines live weather, spatial disaster records, and selectable LLM reporting for a user-selected location.

Workflow:

1. Open `/poc` and select `01. AI Safe Agent`.
2. Allow GPS location access, click the map, choose a saved preset, or enter coordinates manually.
3. Review the 500m radius map markers, compact risk/shelter counters, and legal-dong label when reverse geocoding is configured.
4. Run analysis to fetch KMA rainfall data and generate an AI disaster-safety report.

AI Safe Agent UI includes:

- Initial GPS-based map positioning with graceful fallback to the default Seoul City Hall coordinates.
- First map/project selection scroll behavior that centers the map for faster mobile use.
- A single-line rainfall trend graph from 6 hours ago through 6 hours ahead, sampled hourly.
- Compact counters for nearby risk history and shelters.
- Expandable analysis data for flood traces, landslide records, human-casualty risk zones, and shelters.
- Detail rows that include event dates for risk history and straight-line distance for shelters.
- A server-side knowledge-base build endpoint that generates dated PKL files from public data sources.

Generated PoC datasets such as CSV snapshots and `integrated_disaster_kb_*.pkl` files are intentionally ignored by Git. Rebuild them locally with the in-app `기초 데이터 만들기` action or the `PoC/01-AISafeAgent/import.py` script.

## Project 02: Chunking / Embedding / RAG Lab

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
- `OPENROUTER_BASE_URL`, defaults to `https://openrouter.ai/api/v1`
- `OPENROUTER_EMBEDDING_MODEL`, defaults to `openai/text-embedding-3-small`
- `COHERE_API_KEY`, required for Cohere reranking
- `COHERE_RERANK_MODEL`, defaults to `rerank-v4.0-fast`
- `HF_API_KEY`, `KMA_AUTH_KEY`, and public-data keys for full AI Safe Agent functionality
- `KAKAO_REST_API_KEY` or `VWORLD_API_KEY` for AI Safe Agent legal-dong reverse geocoding
- `DISASTER_KB_PATH` to pin a specific AI Safe Agent knowledge-base PKL

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
- `GET /api/models`: Ollama model list
- `POST /api/chat`: streaming chat response
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
- `POST /api/poc/ai-safe-agent/analyze`: run rainfall, spatial lookup, and AI report generation

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

## Current Publishing Status

The latest local feature work is committed in this repository, but pushing to GitHub requires GitHub authentication on the server.

If credentials are configured, publish with:

```bash
git push origin main
```
