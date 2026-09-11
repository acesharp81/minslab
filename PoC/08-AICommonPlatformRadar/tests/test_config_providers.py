from dataclasses import replace

from app.config import _database_url, get_settings


def test_supabase_standard_url_uses_psycopg3(monkeypatch):
    monkeypatch.delenv("POC08_DATABASE_URL", raising=False)
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://postgres.project:password@pooler.example.com:5432/postgres?sslmode=require",
    )
    assert _database_url().startswith("postgresql+psycopg://")


def test_poc08_database_url_has_precedence(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///generic.db")
    monkeypatch.setenv("POC08_DATABASE_URL", "postgresql://postgres:pw@poc08.example.com/postgres")
    assert "poc08.example.com" in _database_url()


def test_existing_root_key_aliases_are_supported(monkeypatch):
    monkeypatch.setenv("STAGE2_PROVIDER", "gemini")
    monkeypatch.setenv("STAGE3_PRIMARY_PROVIDER", "openai")
    monkeypatch.setenv("STAGE3_FALLBACK_PROVIDER", "nvidia")
    monkeypatch.setenv("Google_AI_STUDIO_API_KEY", "gemini-test")
    monkeypatch.setenv("OpenAI_API_KEY", "openai-test")
    monkeypatch.setenv("NVIDIA_API_KEY", "nvidia-test")
    for name in ("STAGE2_API_KEY", "STAGE3_PRIMARY_API_KEY", "STAGE3_FALLBACK_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.stage2_api_key == "gemini-test"
    assert settings.stage3_primary_api_key == "openai-test"
    assert settings.stage3_fallback_api_key == "nvidia-test"
    assert not replace(settings, app_env="local").validate_runtime()
    get_settings.cache_clear()
