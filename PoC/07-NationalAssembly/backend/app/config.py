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


@lru_cache
def get_settings() -> Settings:
    return Settings()
