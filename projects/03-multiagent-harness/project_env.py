"""홈페이지 저장소 루트 .env를 비밀값 출력 없이 읽는 환경 로더."""

from __future__ import annotations

import os
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPOSITORY_ROOT = HERE.parents[1]


def load_project_env(path: Path | None = None) -> Path:
    target = path or REPOSITORY_ROOT / ".env"
    if not target.is_file():
        return target
    for raw_line in target.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and value and not value.startswith("YOUR_"):
            os.environ.setdefault(key, value)
    return target
