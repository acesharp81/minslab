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
    supabase_url: str
    supabase_service_role_key: str
    user_agent: str
    article_body_limit: int
    per_run_article_limit: int
    request_timeout_seconds: int
    raw_retention_days: int
    metadata_retention_days: int
    rss_feeds: list[str]

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
        }
