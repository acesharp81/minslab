# Minslab Local AI Portfolio

Python ASGI app for a local AI chat page, portfolio archive, and RAG/chunking comparison labs.

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
- `OPENROUTER_EMBEDDING_MODEL`
- `COHERE_API_KEY`
- `COHERE_RERANK_MODEL`

## Run

```bash
uvicorn main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`.

## Public Repository Notes

Before pushing to GitHub, check:

- `.env` is not tracked.
- `.venv/`, `__pycache__/`, `analysis/`, generated report JSON files, and local `.hwpx` source documents are not tracked.
- Service-role Supabase keys stay only on the backend runtime.
