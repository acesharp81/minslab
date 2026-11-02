#!/usr/bin/env python3
"""Create local-only reconstruction settings; never overwrite existing settings."""
from pathlib import Path
import os
import secrets


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    destination = root / ".env.standalone"
    values = {'POSTGRES_PASSWORD': 'random', 'AI_ENRICHMENT_ENABLED': 'false', 'WATCH_KAKAO_ENABLED': 'false', 'WATCH_LLM_ENABLED': 'false', 'NATIONAL_ASSEMBLY_PORT': '18070'}
    lines = [key + "=" + (secrets.token_hex(32) if value == "random" else value)
             for key, value in values.items()]
    fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as output:
        output.write("\n".join(lines) + "\n")
    print("Created .env.standalone (private settings; values are not printed).")


if __name__ == "__main__":
    main()
