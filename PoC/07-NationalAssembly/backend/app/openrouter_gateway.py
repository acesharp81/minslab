from __future__ import annotations

import hmac
import json
import os
import sqlite3
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse, Response


UPSTREAM_BASE_URL = os.getenv(
    "OPENROUTER_UPSTREAM_BASE_URL", "https://openrouter.ai/api/v1"
).rstrip("/")
API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
METER_TOKEN = os.getenv("OPENROUTER_METER_TOKEN", "").strip()
DB_PATH = Path(os.getenv("OPENROUTER_GATEWAY_DB", "/app/data/openrouter_gateway.sqlite3"))
OFFICIAL_LIMIT = max(1, min(int(os.getenv("OPENROUTER_OFFICIAL_DAILY_LIMIT", "1000")), 1000))
OPERATIONAL_LIMIT = max(
    1, min(int(os.getenv("OPENROUTER_OPERATIONAL_DAILY_LIMIT", "950")), OFFICIAL_LIMIT)
)
RPM_LIMIT = max(1, min(int(os.getenv("OPENROUTER_RPM_LIMIT", "18")), 20))
MAX_INFLIGHT = max(1, min(int(os.getenv("OPENROUTER_MAX_INFLIGHT", "4")), 20))
REQUEST_TIMEOUT = max(30.0, float(os.getenv("OPENROUTER_REQUEST_TIMEOUT_SECONDS", "180")))
STALE_INFLIGHT_SECONDS = max(
    REQUEST_TIMEOUT * 2 + 60,
    float(os.getenv("OPENROUTER_STALE_INFLIGHT_SECONDS", "420")),
)
FREE_MODELS = tuple(
    value.strip() for value in os.getenv(
        "OPENROUTER_FREE_MODELS",
        "nvidia/nemotron-3-super-120b-a12b:free,liquid/lfm-2.5-2.6b:free,"
        "dots-studio/dots-3-note-preview:free",
    ).split(",") if value.strip().endswith(":free")
)


class AdmissionController:
    def __init__(self, *, rpm: int, max_inflight: int) -> None:
        self.rpm = rpm
        self.max_inflight = max_inflight
        self.condition = threading.Condition()
        self.starts: deque[float] = deque()
        self.inflight = 0
        self.sequence = 0
        self.waiting: list[tuple[int, int, str]] = []

    def acquire(self, priority: int, timeout: float) -> str:
        ticket = uuid.uuid4().hex
        deadline = time.monotonic() + timeout
        with self.condition:
            self.sequence += 1
            self.waiting.append((priority, self.sequence, ticket))
            while True:
                now = time.monotonic()
                while self.starts and now - self.starts[0] >= 60.0:
                    self.starts.popleft()
                self.waiting.sort(key=lambda item: (item[0], item[1]))
                is_next = bool(self.waiting and self.waiting[0][2] == ticket)
                if is_next and self.inflight < self.max_inflight and len(self.starts) < self.rpm:
                    self.waiting.pop(0)
                    self.inflight += 1
                    self.starts.append(now)
                    return ticket
                remaining = deadline - now
                if remaining <= 0:
                    self.waiting = [item for item in self.waiting if item[2] != ticket]
                    self.condition.notify_all()
                    raise TimeoutError("openrouter_gateway_queue_timeout")
                rate_wait = 0.25
                if len(self.starts) >= self.rpm:
                    rate_wait = max(0.05, 60.0 - (now - self.starts[0]))
                self.condition.wait(timeout=min(remaining, rate_wait))

    def release(self) -> None:
        with self.condition:
            self.inflight = max(0, self.inflight - 1)
            self.condition.notify_all()

    def snapshot(self) -> dict[str, int]:
        with self.condition:
            now = time.monotonic()
            while self.starts and now - self.starts[0] >= 60.0:
                self.starts.popleft()
            return {
                "rpm": len(self.starts),
                "rpm_limit": self.rpm,
                "inflight": self.inflight,
                "max_inflight": self.max_inflight,
                "queued": len(self.waiting),
            }


controller = AdmissionController(rpm=RPM_LIMIT, max_inflight=MAX_INFLIGHT)
app = FastAPI(title="Minslab OpenRouter Gateway", docs_url=None, redoc_url=None)
_schema_lock = threading.Lock()
_schema_ready_path: Path | None = None


def _initialize_schema(connection: sqlite3.Connection) -> None:
    global _schema_ready_path
    resolved = DB_PATH.resolve()
    with _schema_lock:
        if _schema_ready_path == resolved:
            return
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute(
        """
        CREATE TABLE IF NOT EXISTS gateway_requests (
            id TEXT PRIMARY KEY,
            idempotency_key TEXT UNIQUE,
            usage_date TEXT NOT NULL,
            project TEXT NOT NULL,
            workload TEXT NOT NULL,
            priority INTEGER NOT NULL,
            model TEXT NOT NULL,
            status TEXT NOT NULL,
            http_status INTEGER,
            upstream_provider TEXT,
            upstream_request_id TEXT,
            response_body BLOB,
            error TEXT,
            started_at TEXT NOT NULL,
            finished_at TEXT
        )
        """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS gateway_requests_day_idx "
            "ON gateway_requests(usage_date, status, started_at)"
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS external_usage_events (
                event_id TEXT PRIMARY KEY,
                usage_date TEXT NOT NULL,
                project TEXT NOT NULL,
                workload TEXT NOT NULL,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                status TEXT NOT NULL,
                http_status INTEGER NOT NULL,
                input_tokens INTEGER NOT NULL,
                output_tokens INTEGER NOT NULL,
                cost_usd REAL,
                recorded_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS external_usage_events_day_idx "
            "ON external_usage_events(usage_date, provider, project, model)"
        )
        connection.commit()
        _schema_ready_path = resolved


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=15.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout=15000")
    connection.execute("PRAGMA synchronous=NORMAL")
    _initialize_schema(connection)
    return connection


def _utc_day() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _usage(connection: sqlite3.Connection, day: str | None = None) -> dict[str, int]:
    row = connection.execute(
        """
        SELECT COUNT(*) AS reserved,
               SUM(CASE WHEN status='INFLIGHT' THEN 1 ELSE 0 END) AS inflight,
               SUM(CASE WHEN status='COMPLETED' THEN 1 ELSE 0 END) AS completed,
               SUM(CASE WHEN status='FAILED' THEN 1 ELSE 0 END) AS failed
        FROM gateway_requests WHERE usage_date=?
        """,
        (day or _utc_day(),),
    ).fetchone()
    return {key: int((row[key] if row else 0) or 0) for key in (
        "reserved", "inflight", "completed", "failed"
    )}


def _admission_error(used: int, priority: int) -> str:
    if used >= OPERATIONAL_LIMIT:
        return "global_daily_operational_limit"
    if used >= 850 and priority > 30:
        return "essential_workloads_only"
    if used >= 700 and priority >= 50:
        return "booster_and_backfill_paused"
    return ""


def _requests_structured_json(payload: dict[str, Any]) -> bool:
    response_format = payload.get("response_format")
    return (
        isinstance(response_format, dict)
        and response_format.get("type") == "json_schema"
    )


def _has_valid_structured_json(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return False
    first = choices[0]
    message = first.get("message") if isinstance(first, dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip():
        return False
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].strip().lower() in {"```", "```json"}:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        decoded = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return False
    return isinstance(decoded, dict)


def _cached(
    idempotency_key: str, *, require_structured_json: bool = False,
) -> tuple[int, bytes] | None:
    if not idempotency_key:
        return None
    with _connect() as connection:
        row = connection.execute(
            "SELECT id,http_status,response_body,status FROM gateway_requests "
            "WHERE idempotency_key=?", (idempotency_key,),
        ).fetchone()
        # Older gateway versions cached HTTP 200 even when a json_schema
        # response contained truncated JSON. Invalidate those entries lazily
        # so the same logical request can reach upstream again.
        body = bytes(row["response_body"] or b"") if row else b""
        if row and row["status"] == "COMPLETED" and require_structured_json:
            try:
                parsed = json.loads(body)
            except (TypeError, json.JSONDecodeError):
                parsed = None
            if not _has_valid_structured_json(parsed):
                connection.execute(
                    "UPDATE gateway_requests SET status='FAILED',error=? WHERE id=?",
                    ("invalid_structured_output", row["id"]),
                )
                return None
    # A transient upstream or structured-output failure must be retryable.
    if not row or row["status"] != "COMPLETED":
        return None
    return int(row["http_status"] or 500), body


def _reserve(
    *, project: str, workload: str, priority: int, model: str,
    idempotency_key: str,
) -> tuple[str, int]:
    request_id = str(uuid.uuid4())
    with _connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "UPDATE gateway_requests SET status='FAILED',error=?,finished_at=? "
            "WHERE status='INFLIGHT' "
            "AND julianday(started_at) < julianday('now', ?)",
            (
                "stale_inflight_reclaimed",
                _now(),
                f"-{STALE_INFLIGHT_SECONDS} seconds",
            ),
        )
        usage = _usage(connection)
        reason = _admission_error(usage["reserved"], priority)
        if reason:
            connection.rollback()
            raise PermissionError(reason)
        try:
            if idempotency_key:
                connection.execute(
                    "UPDATE gateway_requests SET idempotency_key=NULL "
                    "WHERE idempotency_key=? AND status='FAILED'",
                    (idempotency_key,),
                )
            connection.execute(
                """
                INSERT INTO gateway_requests(
                    id,idempotency_key,usage_date,project,workload,priority,model,
                    status,started_at
                ) VALUES(?,?,?,?,?,?,?,?,?)
                """,
                (
                    request_id, idempotency_key or None, _utc_day(), project,
                    workload, priority, model, "INFLIGHT", _now(),
                ),
            )
        except sqlite3.IntegrityError:
            connection.rollback()
            raise FileExistsError("duplicate_idempotency_key")
        usage_after = usage["reserved"] + 1
        connection.commit()
    return request_id, usage_after


def _finish(
    request_id: str, *, status: int, body: bytes,
    upstream_provider: str = "", upstream_request_id: str = "",
    upstream_model: str = "", cacheable: bool = True,
    error_code: str = "",
) -> None:
    state = "COMPLETED" if 200 <= status < 300 and cacheable else "FAILED"
    error = "" if state == "COMPLETED" else (
        error_code or body.decode("utf-8", "replace")[:1000]
    )
    with _connect() as connection:
        connection.execute(
            """
            UPDATE gateway_requests
            SET status=?,http_status=?,upstream_provider=?,upstream_request_id=?,
                model=CASE WHEN ?<>'' THEN ? ELSE model END,
                response_body=?,error=?,finished_at=? WHERE id=?
            """,
            (
                state, status, upstream_provider[:120], upstream_request_id[:160],
                upstream_model[:180], upstream_model[:180],
                body, error, _now(), request_id,
            ),
        )


def _gateway_error(status: int, message: str, *, used: int | None = None) -> JSONResponse:
    headers = {"X-Minslab-OpenRouter-Limit": str(OPERATIONAL_LIMIT)}
    if used is not None:
        headers["X-Minslab-OpenRouter-Used"] = str(used)
    return JSONResponse(
        status_code=status,
        content={"error": {"code": status, "message": message,
                           "metadata": {"limit_source": "minslab_global_gateway"}}},
        headers=headers,
    )


@app.get("/health")
def health() -> dict[str, Any]:
    with _connect() as connection:
        usage = _usage(connection)
    return {"status": "ok", "configured": bool(API_KEY), "free_models": list(FREE_MODELS),
            **usage, **controller.snapshot()}


def _external_breakdown(connection: sqlite3.Connection, period: str) -> list[dict[str, Any]]:
    where = "usage_date=?" if period == "day" else "substr(usage_date,1,7)=?"
    value = _utc_day() if period == "day" else _utc_day()[:7]
    rows = connection.execute(
        f"""SELECT provider,project,workload,model,status,
                   COUNT(*) AS count,SUM(input_tokens) AS input_tokens,
                   SUM(output_tokens) AS output_tokens,SUM(cost_usd) AS cost_usd
            FROM external_usage_events WHERE {where}
            GROUP BY provider,project,workload,model,status
            ORDER BY provider,project,workload,model,status""", (value,),
    ).fetchall()
    return [dict(row) for row in rows]


@app.post("/internal/usage-events")
def record_external_usage(
    request: Request, x_minslab_meter_token: str = Header(default=""),
) -> Response:
    if not METER_TOKEN or not hmac.compare_digest(x_minslab_meter_token, METER_TOKEN):
        return _gateway_error(403, "meter_token_required")
    try:
        payload = json.loads(request.scope.get("_body", b"") or b"{}")
        if not isinstance(payload, dict):
            raise ValueError("object_required")
        event_id = str(payload["event_id"])
        project = str(payload["project"])
        workload = str(payload["workload"])
        provider = str(payload["provider"])
        model = str(payload["model"])
        status = str(payload["status"])
        http_status = int(payload.get("http_status") or 0)
        input_tokens = int(payload.get("input_tokens") or 0)
        output_tokens = int(payload.get("output_tokens") or 0)
        raw_cost = payload.get("cost_usd")
        cost_usd = float(raw_cost) if raw_cost is not None else None
        if not (8 <= len(event_id) <= 100 and 1 <= len(project) <= 40
                and 1 <= len(workload) <= 60 and 1 <= len(model) <= 180
                and provider in {"openrouter", "groq", "gemini", "upstage", "openai", "nvidia", "mistral"}
                and status in {"COMPLETED", "FAILED"}
                and 0 <= http_status <= 599
                and 0 <= input_tokens <= 10000000 and 0 <= output_tokens <= 10000000
                and (cost_usd is None or 0 <= cost_usd <= 100)):
            raise ValueError("invalid_usage_event")
    except (KeyError, TypeError, ValueError, OverflowError):
        return _gateway_error(400, "invalid_usage_event")
    with _connect() as connection:
        cursor = connection.execute(
            """INSERT OR IGNORE INTO external_usage_events
            (event_id,usage_date,project,workload,provider,model,status,http_status,
             input_tokens,output_tokens,cost_usd,recorded_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (event_id, _utc_day(), project, workload, provider, model, status,
             http_status, input_tokens, output_tokens, cost_usd, _now()),
        )
    return JSONResponse({"recorded": bool(cursor.rowcount)}, status_code=201 if cursor.rowcount else 200)


@app.get("/internal/status")
def internal_status() -> dict[str, Any]:
    with _connect() as connection:
        usage = _usage(connection)
        external_today = _external_breakdown(connection, "day")
        external_month = _external_breakdown(connection, "month")
        rows = connection.execute(
            """
            SELECT project,workload,model,status,COUNT(*) AS count
            FROM gateway_requests WHERE usage_date=?
            GROUP BY project,workload,model,status ORDER BY project,workload,model,status
            """, (_utc_day(),),
        ).fetchall()
    return {
        "provider": "openrouter", "period": "UTC_DAY", "usage_date": _utc_day(),
        "official_limit": OFFICIAL_LIMIT, "operational_limit": OPERATIONAL_LIMIT,
        "safety_reserve": OFFICIAL_LIMIT - OPERATIONAL_LIMIT,
        "remaining": max(0, OPERATIONAL_LIMIT - usage["reserved"]),
        **usage, **controller.snapshot(),
        "breakdown": [dict(row) for row in rows],
        "external_breakdown": external_today,
        "external_monthly_breakdown": external_month,
    }


@app.get("/api/v1/key")
def key_status() -> Response:
    if not API_KEY:
        return _gateway_error(503, "gateway_api_key_missing")
    try:
        response = requests.get(
            f"{UPSTREAM_BASE_URL}/key",
            headers={"Authorization": f"Bearer {API_KEY}", "Accept": "application/json"},
            timeout=30,
        )
    except requests.RequestException as exc:
        return _gateway_error(502, type(exc).__name__)
    return Response(response.content, status_code=response.status_code,
                    media_type=response.headers.get("Content-Type", "application/json"))


@app.get("/api/v1/models")
def models() -> Response:
    try:
        response = requests.get(f"{UPSTREAM_BASE_URL}/models", timeout=30)
    except requests.RequestException as exc:
        return _gateway_error(502, type(exc).__name__)
    return Response(response.content, status_code=response.status_code,
                    media_type=response.headers.get("Content-Type", "application/json"))


@app.post("/api/v1/chat/completions")
def chat_completions(
    request: Request,
    x_minslab_project: str = Header(default="unknown"),
    x_minslab_workload: str = Header(default="unknown"),
    x_minslab_priority: int = Header(default=40),
    x_minslab_data_class: str = Header(default=""),
    x_idempotency_key: str = Header(default=""),
) -> Response:
    if not API_KEY:
        return _gateway_error(503, "gateway_api_key_missing")
    if x_minslab_data_class not in {"public_official", "public_web_news"}:
        return _gateway_error(403, "public_data_class_required")
    try:
        payload = json.loads(request.scope.get("_body", b"") or b"{}")
    except (TypeError, json.JSONDecodeError):
        payload = None
    if payload is None:
        return _gateway_error(400, "invalid_json")
    require_structured_json = _requests_structured_json(payload)
    # Starlette does not populate scope body for sync endpoints. Read through
    # the private cache only after the middleware below has stored it.
    model = str(payload.get("model") or "")[:180]
    if not FREE_MODELS:
        return _gateway_error(503, "gateway_free_model_allowlist_empty")
    ordered_models = ([model] if model in FREE_MODELS else []) + [
        item for item in FREE_MODELS if item != model
    ]
    if x_minslab_workload == "meeting_brief_lineage" and model in FREE_MODELS:
        ordered_models = [model]
    payload.pop("model", None)
    payload["models"] = ordered_models
    # Only the two public data classes above can reach this point. Enforce the
    # explicitly approved free-provider policy at the single network boundary
    # and discard any conflicting policy supplied by a worker.
    payload["provider"] = {
        "data_collection": "allow",
        "allow_fallbacks": True,
        "require_parameters": True,
    }
    priority = max(1, min(int(x_minslab_priority), 100))
    cached = _cached(
        x_idempotency_key, require_structured_json=require_structured_json,
    )
    if cached is not None:
        status, body = cached
        return Response(body, status_code=status, media_type="application/json",
                        headers={"X-Minslab-Idempotent-Replay": "1"})
    try:
        controller.acquire(priority, REQUEST_TIMEOUT)
    except TimeoutError:
        return _gateway_error(503, "gateway_queue_timeout")
    request_id = ""
    used = None
    try:
        try:
            request_id, used = _reserve(
                project=x_minslab_project[:40], workload=x_minslab_workload[:60],
                priority=priority, model=ordered_models[0],
                idempotency_key=x_idempotency_key[:200],
            )
        except PermissionError as exc:
            with _connect() as connection:
                current = _usage(connection)["reserved"]
            return _gateway_error(429, str(exc), used=current)
        except FileExistsError:
            replay = _cached(
                x_idempotency_key,
                require_structured_json=require_structured_json,
            )
            if replay is not None:
                return Response(replay[1], status_code=replay[0], media_type="application/json",
                                headers={"X-Minslab-Idempotent-Replay": "1"})
            return _gateway_error(409, "idempotency_request_inflight")
        try:
            upstream = requests.post(
                f"{UPSTREAM_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {API_KEY}",
                    "Content-Type": "application/json", "Accept": "application/json",
                    "HTTP-Referer": "https://www.minslab.kr",
                    "X-Title": f"Minslab {x_minslab_project[:40]}",
                },
                json=payload, timeout=REQUEST_TIMEOUT,
            )
            body = upstream.content
            try:
                parsed = upstream.json()
            except ValueError:
                parsed = {}
            effective_status = upstream.status_code
            if effective_status < 400 and parsed.get("error") and not parsed.get("choices"):
                error_code = (parsed.get("error") or {}).get("code")
                effective_status = int(error_code) if str(error_code).isdigit() and int(error_code) >= 400 else 502
            structured_output_valid = (
                not require_structured_json or _has_valid_structured_json(parsed)
            )
            _finish(
                request_id, status=effective_status, body=body,
                upstream_provider=str(parsed.get("provider") or ""),
                upstream_request_id=str(parsed.get("id") or ""),
                upstream_model=str(parsed.get("model") or ""),
                cacheable=structured_output_valid,
                error_code=(
                    "invalid_structured_output"
                    if effective_status < 300 and not structured_output_valid
                    else ""
                ),
            )
            headers = {
                "X-Minslab-OpenRouter-Used": str(used),
                "X-Minslab-OpenRouter-Limit": str(OPERATIONAL_LIMIT),
            }
            for name in ("Retry-After", "X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset"):
                if upstream.headers.get(name):
                    headers[name] = upstream.headers[name]
            return Response(body, status_code=effective_status,
                            media_type=upstream.headers.get("Content-Type", "application/json"),
                            headers=headers)
        except requests.RequestException as exc:
            body = json.dumps({"error": {"code": 502, "message": type(exc).__name__}}).encode()
            _finish(request_id, status=502, body=body)
            return Response(body, status_code=502, media_type="application/json")
    finally:
        controller.release()


@app.middleware("http")
async def cache_request_body(request: Request, call_next):
    if request.method == "POST":
        request.scope["_body"] = await request.body()
    return await call_next(request)
