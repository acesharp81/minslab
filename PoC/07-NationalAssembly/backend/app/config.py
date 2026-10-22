from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    national_assembly_env: str = "development"
    national_assembly_log_level: str = "INFO"
    national_assembly_timezone: str = "Asia/Seoul"
    database_url: str = ""
    national_assembly_api_key: str = ""
    raw_data_dir: Path = PROJECT_DIR / "data" / "raw"
    processed_data_dir: Path = PROJECT_DIR / "data" / "processed"
    ai_enrichment_enabled: bool = False
    llm_provider: str = "disabled"
    llm_model: str = ""
    meeting_brief_provider: str = ""
    meeting_brief_model: str = "dots-studio/dots-3-note-preview:free"
    meeting_brief_mistral_model: str = "mistral-small-2603"
    meeting_brief_openai_model: str = "gpt-5.4-mini"
    meeting_brief_nvidia_enabled: bool = False
    meeting_brief_nvidia_model: str = "nvidia/nemotron-3-ultra-550b-a55b"
    meeting_brief_nvidia_min_interval_seconds: float = 6.0
    gemini_api_key: str = ""
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_daily_limit: int = 950
    openrouter_gateway_status_url: str = ""
    mistral_api_key: str = ""
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_daily_token_limit: int = 650_000
    nvidia_api_key: str = ""
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    mistral_base_url: str = "https://api.mistral.ai/v1"
    # Mistral Small 4 standard API pricing as of 2026-08-25.
    # The free monthly API credit is enforced by calculated USD cost.
    mistral_monthly_credit_usd: float = 10.0
    mistral_input_usd_per_million: float = 0.15
    mistral_output_usd_per_million: float = 0.60
    executive_transcription_model: str = "voxtral-mini-latest"
    executive_audio_chunk_seconds: int = 60
    executive_transcription_usd_per_minute: float = 0.003
    watch_alerts_enabled: bool = True
    watch_test_broadcasts_enabled: bool = True
    watch_kakao_enabled: bool = False
    watch_llm_enabled: bool = False
    watch_llm_provider: str = "openrouter"
    watch_llm_model: str = ""
    watch_kakao_redirect_uri: str = ""
    watch_public_base_url: str = ""
    watch_secondary_public_base_url: str = ""
    watch_session_cookie_name: str = "gukjeongbomi_session"
    watch_session_cookie_path: str = "/poc/national-assembly"
    topic_reports_enabled: bool = True
    topic_report_model: str = ""
    topic_report_daily_limit: int = 100
    topic_report_user_daily_limit: int = 10
    topic_report_max_period_days: int = 366
    official_change_reports_enabled: bool = True
    official_change_report_model: str = ""
    official_change_report_daily_limit: int = 100
    # PoC 7 owns these credentials and never falls back to another PoC.
    watch_kakao_rest_api_key: str = ""
    watch_kakao_client_secret: str = ""
    watch_kakao_token_encryption_key: str = ""
    watch_admin_token: str = ""
    watch_llm_monthly_budget_usd: float = 1.0
    watch_llm_debounce_seconds: int = 30
    watch_llm_min_new_matches: int = 3
    watch_llm_max_updates_per_session: int = 12


@lru_cache
def get_settings() -> Settings:
    return Settings()
