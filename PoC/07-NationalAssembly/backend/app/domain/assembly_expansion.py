"""Hot-reloaded, exact-meeting opt-ins; retain entries for report provenance.

Capture permission expires independently of processing and read permission.
No new committee names or source identifiers belong in application code.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LABEL = "확장성 테스트용"
SCHEMA = "assembly-expansion/1"


def validate_config(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA:
        raise ValueError("invalid assembly expansion schema")
    entries = payload.get("entries")
    if not isinstance(entries, list) or len(entries) > 20:
        raise ValueError("invalid expansion entries")
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("invalid expansion entry")
        for key in ("committee_id", "committee_name", "channel_code", "meeting_external_id"):
            if not isinstance(entry.get(key), str) or not entry[key].strip():
                raise ValueError("missing expansion identity")
        if type(entry.get("enabled")) is not bool:
            raise ValueError("enabled must be boolean")
        start = datetime.fromisoformat(entry["capture_from"])
        end = datetime.fromisoformat(entry["capture_until"])
        if start.tzinfo is None or end.tzinfo is None or not 0 < (end-start).total_seconds() <= 48*3600:
            raise ValueError("capture window must be timezone-aware and at most 48 hours")
        if entry["meeting_external_id"] in seen:
            raise ValueError("duplicate expansion meeting")
        seen.add(entry["meeting_external_id"])
    return entries


def config_path() -> Path:
    from ..config import get_settings
    return get_settings().processed_data_dir.parent / "config" / "assembly_expansion.json"


def configured_entries() -> list[dict[str, Any]]:
    try:
        return validate_config(json.loads(config_path().read_text(encoding="utf-8")))
    except FileNotFoundError:
        return []
    except (OSError, ValueError, TypeError, KeyError):
        logging.getLogger(__name__).error("Invalid assembly expansion configuration; extra capture denied")
        return []


def capture_allowed(entry: dict[str, Any], now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    return bool(entry["enabled"] and datetime.fromisoformat(entry["capture_from"]) <= now
                < datetime.fromisoformat(entry["capture_until"]))


def meeting_ids(*, capture: bool = False) -> list[str]:
    return [entry["meeting_external_id"] for entry in configured_entries()
            if not capture or capture_allowed(entry)]


def meeting_metadata(external_id: str | None) -> dict[str, Any]:
    entry = next((entry for entry in configured_entries()
                  if entry["meeting_external_id"] == external_id), None)
    return ({"is_expansion_test": True, "expansion_label": LABEL,
             "expansion_committee_id": entry["committee_id"]} if entry else {})


def match_source(row: dict[str, Any]) -> dict[str, Any] | None:
    return next((entry for entry in configured_entries()
                 if entry["committee_id"] == str(row.get("xbill", ""))
                 and entry["channel_code"] == str(row.get("xcode", ""))
                 and entry["meeting_external_id"] == str(row.get("xcgcd", ""))), None)
