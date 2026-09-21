from __future__ import annotations

import os
import hashlib
import hmac
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_local_env() -> None:
    configured = os.getenv("RADAR_ENV_FILE", "").strip()
    path = Path(configured) if configured else PROJECT_ROOT / ".env"
    if not path.is_absolute():
        path = (PROJECT_ROOT / path).resolve()
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _first_env(*names: str, default: str = "") -> str:
    for name in names:
        value = os.getenv(name)
        if value is not None and value.strip():
            return value.strip()
    return default


def _provider_api_key(provider: str, explicit_name: str) -> str:
    explicit = os.getenv(explicit_name, "").strip()
    if explicit:
        return explicit
    aliases = {
        "gemini": ("GEMINI_API_KEY", "GOOGLE_AI_STUDIO_API_KEY", "Google_AI_STUDIO_API_KEY"),
        "openai": ("OPENAI_API_KEY", "OpenAI_API_KEY"),
        "nvidia": ("NVIDIA_API_KEY", "NGC_API_KEY"),
        "kimi": ("KIMI_API_KEY",),
        "cohere": ("COHERE_API_KEY",),
        "mistral": ("MISTRAL_API_KEY",),
        "upstage": ("UPSTAGE_API_KEY", "UPSTAGE_SECRET_KEY"),
        "openai_compatible": ("LLM_API_KEY",),
    }
    return _first_env(*aliases.get(provider, ()), default="")


def _database_url() -> str:
    supabase_ready = bool(
        _first_env("SUPABASE2_URL", "SUPABASE_URL")
        and _first_env("SUPABASE2_SERVICE_ROLE_KEY", "SUPABASE_SERVICE_ROLE_KEY")
    )
    raw = _first_env(
        "POC08_DATABASE_URL",
        "DATABASE_URL",
        default="sqlite:///./data/supabase-cache.db" if supabase_ready else "sqlite:///./data/app.db",
    )
    prefix = "sqlite:///./"
    if raw.startswith(prefix):
        return f"sqlite:///{(PROJECT_ROOT / raw[len(prefix):]).resolve()}"
    # Supabase가 제공하는 표준 URI를 psycopg 3 드라이버로 연결한다.
    if raw.startswith("postgres://"):
        return f"postgresql+psycopg://{raw[len('postgres://'):]}"
    if raw.startswith("postgresql://"):
        return f"postgresql+psycopg://{raw[len('postgresql://'):]}"
    return raw


def _data_dir() -> Path:
    raw = Path(os.getenv("DATA_DIR", "./data"))
    return (PROJECT_ROOT / raw).resolve() if not raw.is_absolute() else raw.resolve()


@dataclass(frozen=True)
class Settings:
    project_root: Path
    data_dir: Path
    raw_dir: Path
    parsed_dir: Path
    reports_dir: Path
    logs_dir: Path
    app_env: str
    app_timezone: str
    database_url: str
    supabase_url: str
    supabase_service_role_key: str
    supabase_timeout_seconds: int
    log_level: str
    g2b_mode: str
    g2b_service_key: str
    g2b_base_url_prenotice: str
    g2b_operation_prenotice: str
    g2b_operation_prenotice_opinion: str
    g2b_base_url_bid: str
    g2b_operation_bid: str
    g2b_operation_bid_attach: str
    g2b_page_size: int
    g2b_max_pages: int
    g2b_timeout_seconds: int
    stage2_provider: str
    stage2_base_url: str
    stage2_api_key: str
    stage2_model: str
    stage2_timeout_seconds: int
    stage2_max_input_chars: int
    stage2_min_interval_seconds: float
    stage2_fallback_provider: str
    stage2_fallback_base_url: str
    stage2_fallback_api_key: str
    stage2_fallback_model: str
    stage2_fallback_min_interval_seconds: float
    stage3_primary_provider: str
    stage3_primary_base_url: str
    stage3_primary_api_key: str
    stage3_primary_model: str
    stage3_primary_reasoning_effort: str
    stage3_fallback_provider: str
    stage3_fallback_base_url: str
    stage3_fallback_api_key: str
    stage3_fallback_model: str
    stage3_timeout_seconds: int
    stage3_max_input_chars: int
    stage3_daily_limit: int
    stage3_max_concurrency: int
    collect_lookback_days: int
    daily_report_hour: int
    max_files_per_notice: int
    max_file_size_mb: int
    hwp_cli_path: str
    hwp_parse_timeout_seconds: int
    hwp_parse_max_output_mb: int
    high_budget_review_won: int
    download_allowed_hosts: tuple[str, ...]
    admin_username: str
    admin_password: str
    admin_token: str
    proxy_token: str
    auto_seed_sample: bool

    @property
    def auth_enabled(self) -> bool:
        return bool(self.admin_token or (self.admin_username and self.admin_password))

    @property
    def llm_provider(self) -> str:
        """기존 화면/운영 스크립트용 요약값."""
        if self.stage2_provider == self.stage3_primary_provider:
            return self.stage2_provider
        return f"{self.stage2_provider}->{self.stage3_primary_provider}"

    @property
    def database_backend(self) -> str:
        return "sqlite" if self.database_url.startswith("sqlite") else "postgresql"

    @property
    def supabase_enabled(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_role_key)

    def ensure_directories(self) -> None:
        for path in (self.data_dir, self.raw_dir, self.parsed_dir, self.reports_dir, self.logs_dir):
            path.mkdir(parents=True, exist_ok=True)

    def validate_runtime(self) -> list[str]:
        problems: list[str] = []
        if self.g2b_mode == "live" and not self.g2b_service_key:
            problems.append("G2B_MODE=live에는 G2B_SERVICE_KEY가 필요합니다.")
        if bool(self.supabase_url) != bool(self.supabase_service_role_key):
            problems.append("Supabase REST 사용에는 URL과 SERVICE_ROLE_KEY가 모두 필요합니다.")
        supported = {
            "mock", "gemini", "openai", "nvidia", "kimi", "cohere",
            "mistral", "upstage", "openai_compatible",
        }
        endpoints = (
            ("STAGE2", self.stage2_provider, self.stage2_api_key),
            ("STAGE2_FALLBACK", self.stage2_fallback_provider, self.stage2_fallback_api_key),
            ("STAGE3_PRIMARY", self.stage3_primary_provider, self.stage3_primary_api_key),
            ("STAGE3_FALLBACK", self.stage3_fallback_provider, self.stage3_fallback_api_key),
        )
        for label, provider, api_key in endpoints:
            if provider not in supported:
                problems.append(f"{label}_PROVIDER={provider}는 지원하지 않습니다.")
            elif provider != "mock" and not api_key:
                problems.append(f"{label}_PROVIDER={provider}에는 API 키가 필요합니다.")
        if self.stage3_daily_limit < 0:
            problems.append("STAGE3_DAILY_LIMIT는 0 이상이어야 합니다. 0은 무제한입니다.")
        if self.stage3_max_concurrency < 1:
            problems.append("STAGE3_MAX_CONCURRENCY는 1 이상이어야 합니다.")
        if self.stage2_min_interval_seconds < 0:
            problems.append("STAGE2_MIN_INTERVAL_SECONDS는 0 이상이어야 합니다.")
        if self.stage2_fallback_min_interval_seconds < 0:
            problems.append("STAGE2_FALLBACK_MIN_INTERVAL_SECONDS는 0 이상이어야 합니다.")
        if self.hwp_parse_timeout_seconds < 1:
            problems.append("HWP_PARSE_TIMEOUT_SECONDS는 1 이상이어야 합니다.")
        if self.hwp_parse_max_output_mb < 1:
            problems.append("HWP_PARSE_MAX_OUTPUT_MB는 1 이상이어야 합니다.")
        if self.app_env == "production" and not self.auth_enabled:
            problems.append("production에는 ADMIN_TOKEN 또는 Basic Auth 계정이 필요합니다.")
        return problems


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    _load_local_env()
    data = _data_dir()
    legacy_provider = os.getenv("LLM_PROVIDER", "mock").lower()
    stage2_provider = os.getenv("STAGE2_PROVIDER", legacy_provider).lower()
    stage2_fallback_provider = os.getenv("STAGE2_FALLBACK_PROVIDER", "mock").lower()
    stage3_provider = os.getenv("STAGE3_PRIMARY_PROVIDER", legacy_provider).lower()
    fallback_provider = os.getenv("STAGE3_FALLBACK_PROVIDER", "mock").lower()
    supabase_url = _first_env("SUPABASE2_URL", "SUPABASE_URL").rstrip("/")
    supabase_key = _first_env("SUPABASE2_SERVICE_ROLE_KEY", "SUPABASE_SERVICE_ROLE_KEY")
    proxy_secret = _first_env("POC08_PROXY_TOKEN", default=supabase_key)
    proxy_token = (
        hmac.new(proxy_secret.encode("utf-8"), b"poc08-parent-proxy-v1", hashlib.sha256).hexdigest()
        if proxy_secret else ""
    )
    return Settings(
        project_root=PROJECT_ROOT,
        data_dir=data,
        raw_dir=data / "raw",
        parsed_dir=data / "parsed",
        reports_dir=data / "reports",
        logs_dir=data / "logs",
        app_env=os.getenv("APP_ENV", "local"),
        app_timezone=os.getenv("APP_TIMEZONE", "Asia/Seoul"),
        database_url=_database_url(),
        supabase_url=supabase_url,
        supabase_service_role_key=supabase_key,
        supabase_timeout_seconds=_int("SUPABASE_TIMEOUT_SECONDS", 15),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        g2b_mode=os.getenv("G2B_MODE", "mock").lower(),
        g2b_service_key=os.getenv("G2B_SERVICE_KEY", ""),
        g2b_base_url_prenotice=os.getenv("G2B_BASE_URL_PRENOTICE", "https://apis.data.go.kr/1230000/ao/HrcspSsstndrdInfoService").rstrip("/"),
        g2b_operation_prenotice=os.getenv("G2B_OPERATION_PRENOTICE", "getPublicPrcureThngInfoServc"),
        g2b_operation_prenotice_opinion=os.getenv(
            "G2B_OPERATION_PRENOTICE_OPINION", "getPublicPrcureThngOpinionInfoServc",
        ),
        g2b_base_url_bid=os.getenv("G2B_BASE_URL_BID", "https://apis.data.go.kr/1230000/ad/BidPublicInfoService").rstrip("/"),
        g2b_operation_bid=os.getenv("G2B_OPERATION_BID", "getBidPblancListInfoServc"),
        g2b_operation_bid_attach=os.getenv("G2B_OPERATION_BID_ATTACH", "getBidPblancListInfoEorderAtchFileInfo"),
        g2b_page_size=_int("G2B_PAGE_SIZE", 100),
        g2b_max_pages=_int("G2B_MAX_PAGES", 20),
        g2b_timeout_seconds=_int("G2B_TIMEOUT_SECONDS", 30),
        stage2_provider=stage2_provider,
        stage2_base_url=os.getenv(
            "STAGE2_BASE_URL",
            "https://generativelanguage.googleapis.com/v1beta/openai" if stage2_provider == "gemini" else "https://api.moonshot.ai/v1" if stage2_provider == "kimi" else "https://api.cohere.ai/compatibility/v1" if stage2_provider == "cohere" else "https://api.mistral.ai/v1" if stage2_provider == "mistral" else "https://api.upstage.ai/v1" if stage2_provider == "upstage" else os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
        ).rstrip("/"),
        stage2_api_key=_provider_api_key(stage2_provider, "STAGE2_API_KEY"),
        stage2_model=os.getenv("STAGE2_MODEL", "gemini-2.5-flash-lite" if stage2_provider == "gemini" else "kimi-k2.6" if stage2_provider == "kimi" else "command-a-plus-05-2026" if stage2_provider == "cohere" else "mistral-small-latest" if stage2_provider == "mistral" else "solar-pro4" if stage2_provider == "upstage" else os.getenv("LLM_MODEL", "mock-deterministic-v1")),
        stage2_timeout_seconds=_int("STAGE2_TIMEOUT_SECONDS", _int("LLM_TIMEOUT_SECONDS", 90)),
        stage2_max_input_chars=_int("STAGE2_MAX_INPUT_CHARS", 8_000),
        stage2_min_interval_seconds=_float("STAGE2_MIN_INTERVAL_SECONDS", 7.0 if stage2_provider == "gemini" else 0.0),
        stage2_fallback_provider=stage2_fallback_provider,
        stage2_fallback_base_url=os.getenv(
            "STAGE2_FALLBACK_BASE_URL",
            "https://generativelanguage.googleapis.com/v1beta/openai" if stage2_fallback_provider == "gemini" else "https://api.moonshot.ai/v1" if stage2_fallback_provider == "kimi" else "https://api.cohere.ai/compatibility/v1" if stage2_fallback_provider == "cohere" else "https://api.mistral.ai/v1" if stage2_fallback_provider == "mistral" else "https://api.upstage.ai/v1" if stage2_fallback_provider == "upstage" else "https://api.openai.com/v1",
        ).rstrip("/"),
        stage2_fallback_api_key=_provider_api_key(stage2_fallback_provider, "STAGE2_FALLBACK_API_KEY"),
        stage2_fallback_model=os.getenv("STAGE2_FALLBACK_MODEL", "gemini-2.5-flash-lite" if stage2_fallback_provider == "gemini" else "kimi-k2.6" if stage2_fallback_provider == "kimi" else "command-a-plus-05-2026" if stage2_fallback_provider == "cohere" else "mistral-small-latest" if stage2_fallback_provider == "mistral" else "solar-pro4" if stage2_fallback_provider == "upstage" else "mock-deterministic-v1"),
        stage2_fallback_min_interval_seconds=_float(
            "STAGE2_FALLBACK_MIN_INTERVAL_SECONDS",
            7.0 if stage2_fallback_provider == "gemini" else 0.0,
        ),
        stage3_primary_provider=stage3_provider,
        stage3_primary_base_url=os.getenv(
            "STAGE3_PRIMARY_BASE_URL",
            "https://api.moonshot.ai/v1" if stage3_provider == "kimi" else "https://api.cohere.ai/compatibility/v1" if stage3_provider == "cohere" else "https://integrate.api.nvidia.com/v1" if stage3_provider == "nvidia" else "https://api.openai.com/v1" if stage3_provider == "openai" else os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
        ).rstrip("/"),
        stage3_primary_api_key=_provider_api_key(stage3_provider, "STAGE3_PRIMARY_API_KEY"),
        stage3_primary_model=os.getenv("STAGE3_PRIMARY_MODEL", "kimi-k2.6" if stage3_provider == "kimi" else "command-a-plus-05-2026" if stage3_provider == "cohere" else "gpt-5.4-mini" if stage3_provider == "openai" else os.getenv("LLM_MODEL", "mock-deterministic-v1")),
        stage3_primary_reasoning_effort=os.getenv("STAGE3_PRIMARY_REASONING_EFFORT", "low").lower(),
        stage3_fallback_provider=fallback_provider,
        stage3_fallback_base_url=os.getenv(
            "STAGE3_FALLBACK_BASE_URL",
            "https://integrate.api.nvidia.com/v1" if fallback_provider == "nvidia" else "https://api.openai.com/v1",
        ).rstrip("/"),
        stage3_fallback_api_key=_provider_api_key(fallback_provider, "STAGE3_FALLBACK_API_KEY"),
        stage3_fallback_model=os.getenv("STAGE3_FALLBACK_MODEL", "nvidia/nemotron-3-super-120b-a12b" if fallback_provider == "nvidia" else "mock-deterministic-v1"),
        stage3_timeout_seconds=_int("STAGE3_TIMEOUT_SECONDS", _int("LLM_TIMEOUT_SECONDS", 180)),
        stage3_max_input_chars=_int("STAGE3_MAX_INPUT_CHARS", 100_000),
        stage3_daily_limit=_int("STAGE3_DAILY_LIMIT", 0),
        stage3_max_concurrency=_int("STAGE3_MAX_CONCURRENCY", 1),
        collect_lookback_days=_int("COLLECT_LOOKBACK_DAYS", 1),
        daily_report_hour=_int("DAILY_REPORT_HOUR", 7),
        max_files_per_notice=_int("MAX_FILES_PER_NOTICE", 20),
        max_file_size_mb=_int("MAX_FILE_SIZE_MB", 80),
        hwp_cli_path=os.getenv("HWP_CLI_PATH", "/usr/local/bin/hwp"),
        hwp_parse_timeout_seconds=_int("HWP_PARSE_TIMEOUT_SECONDS", 30),
        hwp_parse_max_output_mb=_int("HWP_PARSE_MAX_OUTPUT_MB", 10),
        high_budget_review_won=_int("HIGH_BUDGET_REVIEW_WON", 100_000_000),
        download_allowed_hosts=tuple(x.strip().lower() for x in os.getenv("DOWNLOAD_ALLOWED_HOSTS", "apis.data.go.kr,nopenapi.g2b.go.kr,g2b.go.kr,www.g2b.go.kr").split(",") if x.strip()),
        admin_username=os.getenv("ADMIN_USERNAME", ""),
        admin_password=os.getenv("ADMIN_PASSWORD", ""),
        admin_token=os.getenv("ADMIN_TOKEN", ""),
        proxy_token=proxy_token,
        auto_seed_sample=_bool("AUTO_SEED_SAMPLE", not bool(supabase_url and supabase_key)),
    )
