#!/usr/bin/env python3
"""Create a self-contained PoC 7 .env without printing secret values.

An optional source env is only a one-time migration input. Runtime and deploy
scripts always read PoC/07-NationalAssembly/.env exclusively.
"""
from __future__ import annotations

import argparse
import base64
import os
import secrets
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_TARGET = PROJECT_DIR / ".env"
KAKAO_REDIRECT = (
    "https://www.minslab.kr/poc/national-assembly/api/watch/kakao/callback"
)
PUBLIC_BASE = "https://www.minslab.kr/poc/national-assembly/"


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip():
            values[key.strip()] = value
    return values


def fernet_key() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii")


def source_value(source: dict[str, str], *names: str) -> str:
    for name in names:
        value = source.get(name, "").strip()
        if value:
            return value
    return ""


def replace_values(path: Path, updates: dict[str, str]) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    seen: set[str] = set()
    output: list[str] = []
    for line in lines:
        if "=" not in line or line.lstrip().startswith("#"):
            output.append(line)
            continue
        key = line.split("=", 1)[0].strip()
        if key in updates:
            output.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            output.append(line)
    missing_items = [(key, value) for key, value in updates.items() if key not in seen]
    if missing_items:
        if output and output[-1]:
            output.append("")
        output.append("# PoC 7 independent alert delivery")
        for key, value in missing_items:
            output.append(f"{key}={value}")
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(6)}.tmp")
    temporary.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bootstrap an independent PoC 7 environment",
    )
    parser.add_argument("--source", type=Path, help="optional existing env to import once")
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    args = parser.parse_args()
    current = parse_env(args.target)
    source = {**parse_env(args.source)} if args.source else {}
    source = {**source, **{key: value for key, value in current.items() if value}}
    openrouter_key = source_value(source, "OPENROUTER_API_KEY")
    updates = {
        "WATCH_ALERTS_ENABLED": "true",
        "WATCH_LLM_ENABLED": "true" if openrouter_key else "false",
        "WATCH_LLM_PROVIDER": "openrouter",
        "WATCH_LLM_MODEL": source.get(
            "WATCH_LLM_MODEL", "dots-studio/dots-3-note-preview:free",
        ),
        "OPENROUTER_DAILY_LIMIT": source.get("OPENROUTER_DAILY_LIMIT", "500"),
        "WATCH_TEST_BROADCASTS_ENABLED": source.get("WATCH_TEST_BROADCASTS_ENABLED", "true"),
        "WATCH_DIGEST_ENABLED": source.get("WATCH_DIGEST_ENABLED", "true"),
        "WATCH_KAKAO_ENABLED": "true",
        "WATCH_KAKAO_REDIRECT_URI": KAKAO_REDIRECT,
        "WATCH_PUBLIC_BASE_URL": PUBLIC_BASE,
        "WATCH_KAKAO_REST_API_KEY": source_value(
            source, "WATCH_KAKAO_REST_API_KEY",
        ),
        "WATCH_KAKAO_CLIENT_SECRET": source_value(
            source, "WATCH_KAKAO_CLIENT_SECRET",
        ),
        "WATCH_KAKAO_TOKEN_ENCRYPTION_KEY": source_value(
            source, "WATCH_KAKAO_TOKEN_ENCRYPTION_KEY",
        ) or fernet_key(),
        "WATCH_ADMIN_TOKEN": source_value(source, "WATCH_ADMIN_TOKEN")
        or secrets.token_urlsafe(32),
    }
    if openrouter_key:
        updates["OPENROUTER_API_KEY"] = openrouter_key
        updates["OPENROUTER_BASE_URL"] = source.get(
            "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1",
        )
    mistral_key = source_value(source, "MISTRAL_API_KEY")
    if mistral_key:
        updates["MISTRAL_API_KEY"] = mistral_key
    replace_values(args.target, updates)
    missing = [
        key for key in ("WATCH_KAKAO_REST_API_KEY",)
        if not updates.get(key)
    ]
    print("PoC 7 .env updated; secret values were not displayed.")
    print("Kakao configuration: " + ("INCOMPLETE" if missing else "READY"))
    if missing:
        print("Missing keys: " + ", ".join(missing))
        raise SystemExit(2)


if __name__ == "__main__":
    main()
