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
    gemini_api_key: str = ""
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_daily_limit: int = 500
    mistral_api_key: str = ""
    mistral_base_url: str = "https://api.mistral.ai/v1"
    # Mistral Small 4 standard API pricing as of 2026-08-25.
    # The free monthly API credit is enforced by calculated USD cost.
    mistral_monthly_credit_usd: float = 10.0
    mistral_input_usd_per_million: float = 0.15
    mistral_output_usd_per_million: float = 0.60
    executive_transcription_model: str = "voxtral-mini-latest"
    executive_audio_chunk_seconds: int = 60
    executive_transcription_usd_per_minute: float = 0.003


@lru_cache
def get_settings() -> Settings:
    return Settings()
