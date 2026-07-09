"""Small environment helpers for local and hosted runs."""

from __future__ import annotations

import os
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent


def load_project_env(env_path: Path | None = None) -> None:
    """Load .env values without overriding process-provided environment."""
    path = env_path or PROJECT_DIR / ".env"
    try:
        with path.open(encoding="utf-8") as env_file:
            for raw_line in env_file:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip(chr(34)).strip(chr(39))
                if not key or not value or value.startswith("YOUR_"):
                    continue
                if not os.environ.get(key):
                    os.environ[key] = value
    except OSError:
        pass


def env_first(*names: str, default: str | None = None) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return default
