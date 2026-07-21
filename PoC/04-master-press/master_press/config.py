from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]


def load_env() -> None:
    """Load optional project overrides, then the homepage's shared root .env."""
    candidates = [PROJECT_DIR / ".env", PROJECT_DIR.parents[1] / ".env"]
    for path in candidates:
        if not path.is_file():
            continue
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
                value = value[1:-1]
            if key and key not in os.environ:
                os.environ[key] = value


def env(*names: str, default: str = "") -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return default


def env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        return max(minimum, min(maximum, int(env(name, default=str(default)))))
    except ValueError:
        return default


def env_json(name: str, default):
    try:
        return json.loads(env(name, default=json.dumps(default)))
    except json.JSONDecodeError:
        return default


@dataclass(frozen=True)
class Settings:
    project_dir: Path
    data_dir: Path
    database_path: Path
    token_encryption_key: str
    naver_client_id: str
    naver_client_secret: str
    kakao_rest_api_key: str
    kakao_client_secret: str
    kakao_redirect_uri: str
    ollama_base_url: str
    embedding_model: str
    llm_model: str
    groq_api_key: str
    groq_base_url: str
    groq_common_model: str
    groq_daily_request_soft_limit: int
    groq_daily_token_soft_limit: int
    groq_minute_token_soft_limit: int
    openrouter_api_key: str
    openrouter_base_url: str
    openrouter_case_model: str
    openrouter_daily_soft_limit: int
    worker_ai_key: str
    worker_ai_account_id: str
    worker_ai_base_url: str
    worker_ai_model: str
    worker_ai_daily_neuron_soft_limit: int
    worker_ai_daily_request_soft_limit: int
    gemini_api_key: str
    gemini_base_url: str
    gemini_model: str
    gemini_daily_request_soft_limit: int
    gemini_daily_token_soft_limit: int
    supabase_url: str
    supabase_service_role_key: str
    user_agent: str
    article_body_limit: int
    per_run_article_limit: int
    request_timeout_seconds: int
    raw_retention_days: int
    metadata_retention_days: int
    rss_feeds: list[str]
    press_release_rss_url: str
    press_release_sync_minutes: int
    press_release_per_sync: int
    press_release_match_window_days: int
    press_release_match_threshold: float

    @classmethod
    def from_env(cls) -> "Settings":
        load_env()
        data_dir = Path(env("MASTER_PRESS_DATA_DIR", default=str(PROJECT_DIR / "data"))).expanduser()
        return cls(
            project_dir=PROJECT_DIR,
            data_dir=data_dir,
            database_path=Path(env("MASTER_PRESS_DB_PATH", default=str(data_dir / "master_press.sqlite3"))).expanduser(),
            token_encryption_key=env("MASTER_PRESS_TOKEN_ENCRYPTION_KEY"),
            naver_client_id=env("MASTER_PRESS_NAVER_CLIENT_ID", "NAVER_CLIENT_ID"),
            naver_client_secret=env("MASTER_PRESS_NAVER_CLIENT_SECRET", "NAVER_CLIENT_SECRET"),
            kakao_rest_api_key=env("MASTER_PRESS_KAKAO_REST_API_KEY", "KAKAO_REST_API_KEY"),
            kakao_client_secret=env("MASTER_PRESS_KAKAO_CLIENT_SECRET", "KAKAO_CLIENT_SECRET"),
            kakao_redirect_uri=env("MASTER_PRESS_KAKAO_REDIRECT_URI"),
            ollama_base_url=env("OLLAMA_BASE_URL", default="http://127.0.0.1:11434").rstrip("/"),
            embedding_model=env("MASTER_PRESS_EMBEDDING_MODEL", default="nomic-embed-text:latest"),
            llm_model=env("MASTER_PRESS_LLM_MODEL", default="qwen2.5:1.5b"),
            groq_api_key=env("MASTER_PRESS_GROQ_API_KEY", "GROQ_API_KEY"),
            groq_base_url=env("MASTER_PRESS_GROQ_BASE_URL", default="https://api.groq.com/openai/v1").rstrip("/"),
            groq_common_model=env("MASTER_PRESS_GROQ_COMMON_MODEL", default="llama-3.1-8b-instant"),
            groq_daily_request_soft_limit=env_int("MASTER_PRESS_GROQ_DAILY_REQUEST_SOFT_LIMIT", 900, 1, 14000),
            groq_daily_token_soft_limit=env_int("MASTER_PRESS_GROQ_DAILY_TOKEN_SOFT_LIMIT", 450000, 1000, 500000),
            groq_minute_token_soft_limit=env_int("MASTER_PRESS_GROQ_MINUTE_TOKEN_SOFT_LIMIT", 5400, 500, 6000),
            openrouter_api_key=env(
                "MASTER_PRESS_OPENROUTER_API_MYKEY", "OPENROUTER_API_MYKEY",
                "MASTER_PRESS_OPENROUTER_API_KEY", "OPENROUTER_API_KEY",
            ),
            openrouter_base_url=env("MASTER_PRESS_OPENROUTER_BASE_URL", default="https://openrouter.ai/api/v1").rstrip("/"),
            openrouter_case_model=env("MASTER_PRESS_OPENROUTER_CASE_MODEL", default="google/gemma-4-26b-a4b-it:free"),
            openrouter_daily_soft_limit=env_int("MASTER_PRESS_OPENROUTER_DAILY_SOFT_LIMIT", 1000, 1, 1000),
            worker_ai_key=env("MASTER_PRESS_WORKER_AI_KEY", "WORKER_AI_KEY", "WORKER_AI_API_KEY", "WORKERS_AI_KEY", "CLOUDFLARE_API_TOKEN", "CLOUDFLARE_WORKERS_AI_TOKEN", "CF_API_TOKEN"),
            worker_ai_account_id=env("MASTER_PRESS_WORKER_AI_ACCOUNT_ID", "WORKER_AI_ACCOUNT_ID", "WORKER_AI_ACOUNT_ID", "WORKERS_AI_ACCOUNT_ID", "CLOUDFLARE_ACCOUNT_ID", "CF_ACCOUNT_ID"),
            worker_ai_base_url=env("MASTER_PRESS_WORKER_AI_BASE_URL", default="https://api.cloudflare.com/client/v4").rstrip("/"),
            worker_ai_model=env("MASTER_PRESS_WORKER_AI_MODEL", default="@cf/google/gemma-4-26b-a4b-it"),
            worker_ai_daily_neuron_soft_limit=env_int("MASTER_PRESS_WORKER_AI_DAILY_NEURON_SOFT_LIMIT", 10000, 1, 1000000),
            worker_ai_daily_request_soft_limit=env_int("MASTER_PRESS_WORKER_AI_DAILY_REQUEST_SOFT_LIMIT", 3000, 1, 100000),
            gemini_api_key=env("MASTER_PRESS_GEMINI_API_KEY", "Google_AI_STUDIO_API_KEY", "GOOGLE_AI_STUDIO_API_KEY", "GEMINI_API_KEY"),
            gemini_base_url=env("MASTER_PRESS_GEMINI_BASE_URL", default="https://generativelanguage.googleapis.com/v1beta").rstrip("/"),
            gemini_model=env("MASTER_PRESS_GEMINI_MODEL", default="gemini-3.5-flash-lite"),
            gemini_daily_request_soft_limit=env_int("MASTER_PRESS_GEMINI_DAILY_REQUEST_SOFT_LIMIT", 1000, 1, 100000),
            gemini_daily_token_soft_limit=env_int("MASTER_PRESS_GEMINI_DAILY_TOKEN_SOFT_LIMIT", 0, 0, 100000000),
            supabase_url=env("SUPABASE2_URL", "MASTER_PRESS_SUPABASE_URL").rstrip("/"),
            supabase_service_role_key=env("SUPABASE2_SERVICE_ROLE_KEY", "MASTER_PRESS_SUPABASE_SERVICE_ROLE_KEY"),
            user_agent=env(
                "MASTER_PRESS_USER_AGENT",
                default="MasterPressPoC/0.1 (+news-monitor; contact=admin)",
            ),
            article_body_limit=env_int("MASTER_PRESS_ARTICLE_BODY_LIMIT", 15000, 2000, 50000),
            per_run_article_limit=env_int("MASTER_PRESS_PER_RUN_ARTICLE_LIMIT", 20, 1, 100),
            request_timeout_seconds=env_int("MASTER_PRESS_REQUEST_TIMEOUT", 10, 3, 30),
            raw_retention_days=env_int("MASTER_PRESS_RAW_RETENTION_DAYS", 7, 1, 30),
            metadata_retention_days=env_int("MASTER_PRESS_METADATA_RETENTION_DAYS", 90, 7, 3650),
            rss_feeds=[str(item).strip() for item in env_json("MASTER_PRESS_RSS_FEEDS_JSON", []) if str(item).strip()],
            press_release_rss_url=env(
                "MASTER_PRESS_MOIS_PRESS_RSS_URL",
                default="https://www.mois.go.kr/gpms/view/jsp/rss/rss.jsp?ctxCd=1012",
            ),
            press_release_sync_minutes=env_int("MASTER_PRESS_PRESS_SYNC_MINUTES", 30, 5, 1440),
            press_release_per_sync=env_int("MASTER_PRESS_PRESS_PER_SYNC", 8, 1, 30),
            press_release_match_window_days=env_int("MASTER_PRESS_PRESS_MATCH_WINDOW_DAYS", 45, 1, 365),
            press_release_match_threshold=max(
                0.0,
                min(100.0, float(env("MASTER_PRESS_PRESS_MATCH_THRESHOLD", default="65"))),
            ),
        )

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.chmod(0o700)

    def readiness(self) -> dict[str, bool]:
        return {
            "naver_news": bool(self.naver_client_id and self.naver_client_secret),
            "kakao_login": bool(self.kakao_rest_api_key and self.kakao_redirect_uri),
            "token_encryption": bool(self.token_encryption_key),
            "supabase": bool(self.supabase_url and self.supabase_service_role_key),
            "ollama": bool(self.ollama_base_url),
            "groq": bool(self.groq_api_key and self.groq_common_model),
            "openrouter": bool(self.openrouter_api_key and self.openrouter_case_model),
            "cloudflare_workers_ai": bool(self.worker_ai_key and self.worker_ai_account_id and self.worker_ai_model),
            "gemini": bool(self.gemini_api_key and self.gemini_model),
        }
