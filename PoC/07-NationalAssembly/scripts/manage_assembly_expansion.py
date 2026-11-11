#!/usr/bin/env python3
"""Register one official scheduled meeting using its committee identifier.

Configuration only: does not start capture, call models, or modify reports.
Keep disabled entries so provenance and pending report work remain available.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.domain.assembly_expansion import SCHEMA, validate_config

CALENDAR_URL = "https://assembly.webcast.go.kr/main/service/calendar.asp?qdate="
LIST_URL = "https://assembly.webcast.go.kr/main/service/live_list.asp"


def read_source(url: str, raw_dir: Path | None = None) -> tuple[dict, str]:
    with urlopen(url, timeout=20) as response:
        content = response.read()
    digest = hashlib.sha256(content).hexdigest()
    if raw_dir is not None:
        raw_dir.mkdir(parents=True, exist_ok=True)
        path = raw_dir / (digest + ".json")
        if not path.exists():
            with path.open("xb") as target:
                target.write(content)
    return json.loads(content.decode("utf-8-sig")), digest


def resolve_meeting(committee_id: str, day: str, calendar: dict, listing: dict,
                    meeting_id: str | None = None) -> dict:
    channels = [row for row in listing["xlist"] if str(row.get("xbill")) == committee_id]
    if len(channels) != 1:
        raise ValueError("official committee identifier must resolve to exactly one channel")
    channel = channels[0]
    meetings = [row for block in calendar["xdays"] if block.get("xdate") == day.replace("-", "")
                for row in block["xlist"] if str(row.get("xcode")) == str(channel["xcode"])
                and (not meeting_id or row.get("xcgcd") == meeting_id)]
    if len(meetings) != 1:
        raise ValueError("expected exactly one scheduled broadcast; specify --meeting-id if ambiguous")
    meeting = meetings[0]
    name = re.sub(r"^제\s*\d+\s*차\s*", "", meeting["xconf"]).strip()
    if not name.endswith("위원회"):
        raise ValueError("official schedule does not identify a committee meeting")
    return {"committee_id": committee_id, "committee_name": name,
            "channel_code": str(channel["xcode"]), "meeting_external_id": meeting["xcgcd"],
            "scheduled_date": day, "scheduled_time": meeting.get("xdesc"),
            "meeting_title": meeting["xsubj"], "enabled": True,
            "capture_from": day + "T08:00:00+09:00",
            "capture_until": (date.fromisoformat(day) + timedelta(days=1)).isoformat() + "T09:00:00+09:00"}


def save_config(path: Path, payload: dict, action: str) -> None:
    validate_config(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    previous = path.read_bytes() if path.exists() else b""
    content = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode()
    fd, temp = tempfile.mkstemp(prefix=".assembly-expansion-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as target:
            target.write(content); target.flush(); os.fsync(target.fileno())
        os.chmod(temp, 0o644)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp): os.unlink(temp)
    audit = {"at": datetime.now(timezone.utc).isoformat(), "action": action,
             "before_sha256": hashlib.sha256(previous).hexdigest(),
             "after_sha256": hashlib.sha256(content).hexdigest(), "config": payload}
    with path.with_suffix(".audit.jsonl").open("a", encoding="utf-8") as target:
        target.write(json.dumps(audit, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["register", "disable", "show"])
    parser.add_argument("--config", type=Path, default=ROOT / "data/config/assembly_expansion.json")
    parser.add_argument("--committee-id")
    parser.add_argument("--date", type=date.fromisoformat)
    parser.add_argument("--meeting-id")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    payload = json.loads(args.config.read_text()) if args.config.exists() else {"schema_version": SCHEMA, "entries": []}
    validate_config(payload)
    if args.action == "register":
        if not args.committee_id or not args.date: parser.error("register requires --committee-id and --date")
        calendar_url = CALENDAR_URL + args.date.strftime("%Y%m")
        raw_dir = None if args.dry_run else args.config.parent.parent / "raw/assembly-expansion-registration"
        calendar, chash = read_source(calendar_url, raw_dir); listing, lhash = read_source(LIST_URL, raw_dir)
        entry = resolve_meeting(args.committee_id, args.date.isoformat(), calendar, listing, args.meeting_id)
        entry["evidence"] = {"calendar_url": calendar_url, "calendar_sha256": chash,
                             "live_list_url": LIST_URL, "live_list_sha256": lhash,
                             "raw_directory": "raw/assembly-expansion-registration" if raw_dir else None,
                             "verified_at": datetime.now(timezone.utc).isoformat()}
        # Existing grants are never silently re-enabled or replaced.
        if any(e["meeting_external_id"] == entry["meeting_external_id"] for e in payload["entries"]):
            raise ValueError("meeting already registered; existing grant preserved")
        payload["entries"].append(entry)
    elif args.action == "disable":
        if not args.meeting_id: parser.error("disable requires --meeting-id")
        matches = [e for e in payload["entries"] if e["meeting_external_id"] == args.meeting_id]
        if len(matches) != 1: raise ValueError("meeting not registered")
        matches[0]["enabled"] = False
    validate_config(payload)
    if args.action != "show" and not args.dry_run: save_config(args.config, payload, args.action)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
