from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Protocol

from ..adapters.live_sources import (
    ASSEMBLY_LIVE_LIST_URL,
    PARSER_VERSION,
    assembly_live_play_url,
    fetch_public_source,
    parse_assembly_live_list,
    parse_assembly_live_play,
)
from ..storage.raw_store import RawStore


class LiveLifecycleSink(Protocol):
    def observe_broadcast(self, observation: Any) -> Any: ...

    def finish_poll(self, active_external_ids: list[str], observed_at: Any) -> int: ...


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as temporary:
            json.dump(payload, temporary, ensure_ascii=False, indent=2)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def probe_assembly_live_once(
    raw_dir: Path,
    status_path: Path,
    lifecycle_sink: LiveLifecycleSink | None = None,
) -> dict[str, Any]:
    from ..db.live_repository import LiveBroadcastObservation
    from ..db.schedule_repository import SourceVersionInput

    store = RawStore(raw_dir)
    listing_payload = fetch_public_source("assembly_live_list", ASSEMBLY_LIVE_LIST_URL)
    listing_artifact = store.save(listing_payload, parser_version=PARSER_VERSION)
    assembly = parse_assembly_live_list(listing_payload.content)
    play_contracts: list[dict[str, Any]] = []
    for item in assembly["items"]:
        if not item["is_live"] or not item["meeting_external_id"]:
            continue
        url = assembly_live_play_url(str(item["channel_code"]), str(item["meeting_external_id"]))
        play_payload = fetch_public_source("assembly_live_play", url)
        artifact = store.save(play_payload, parser_version=PARSER_VERSION)
        contract = parse_assembly_live_play(play_payload.content)
        play_contracts.append({
            **contract,
            "content_hash": artifact.content_hash,
        })
        if lifecycle_sink is not None:
            lifecycle_sink.observe_broadcast(LiveBroadcastObservation(
                institution="LEGISLATURE",
                external_id=str(contract["meeting_external_id"]),
                committee_name=str(contract["committee_name"]) or None,
                title=str(contract["title"]) or None,
                caption_source_status=str(contract["caption_capture_status"]),
                caption_websocket_url=(
                    str(contract["caption_websocket_url"])
                    if contract["caption_websocket_url"] else None
                ),
                thumbnail_url=(str(item["thumbnail_url"]) if item["thumbnail_url"] else None),
                observed_at=play_payload.retrieved_at,
                source=SourceVersionInput(
                    source_type="assembly_live_play",
                    source_url=play_payload.source_url,
                    content_hash=artifact.content_hash,
                    raw_path=artifact.content_path,
                    retrieved_at=play_payload.retrieved_at,
                    parser_version=PARSER_VERSION,
                    content_type=play_payload.content_type,
                    metadata={
                        "channel_code": contract["channel_code"],
                        "committee_name": contract["committee_name"],
                        "caption_capture_status": contract["caption_capture_status"],
                    },
                ),
            ))
    if lifecycle_sink is not None:
        lifecycle_sink.finish_poll(
            [str(item["meeting_external_id"]) for item in assembly["items"] if item["is_live"]],
            listing_payload.retrieved_at,
        )
    previous: dict[str, Any] = {}
    try:
        previous = json.loads(status_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    snapshot = {
        "schema_version": "live-source-status.v1",
        "checked_at": listing_payload.retrieved_at.isoformat(),
        "assembly": {**assembly, "play_contracts": play_contracts},
        "executive": previous.get("executive", {
            "institution": "EXECUTIVE",
            "is_live": None,
            "source_status": "UNRESOLVED",
            "caption_contract_status": "UNVERIFIED",
        }),
        "contracts": {
            **previous.get("contracts", {}),
            "assembly_live_list": {
                "url": ASSEMBLY_LIVE_LIST_URL,
                "content_hash": listing_artifact.content_hash,
                "parser_version": PARSER_VERSION,
            },
        },
    }
    _atomic_json(status_path, snapshot)
    return snapshot


def main() -> None:
    # 설정 패키지는 실행 진입점에서만 필요하다. 수집 함수 자체는 경로를
    # 주입받아 독립적으로 테스트하고 다른 작업에서도 재사용할 수 있다.
    from ..config import get_settings
    from ..db.connection import connect
    from ..db.live_repository import LiveRepository
    from ..db.migrate import apply_migrations

    settings = get_settings()
    parser = argparse.ArgumentParser(description="Monitor official Assembly LIVE sources")
    parser.add_argument("--interval", type=int, default=30)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if not 15 <= args.interval <= 3600:
        parser.error("interval must be between 15 and 3600 seconds")
    status_path = settings.processed_data_dir / "live_status.json"
    apply_migrations(settings.database_url)
    while True:
        with connect(settings.database_url) as connection:
            snapshot = probe_assembly_live_once(
                settings.raw_data_dir,
                status_path,
                lifecycle_sink=LiveRepository(connection),
            )
        print(json.dumps({
            "checked_at": snapshot["checked_at"],
            "live_count": snapshot["assembly"]["live_count"],
            "caption_ready": len(snapshot["assembly"]["play_contracts"]),
        }, ensure_ascii=False), flush=True)
        if args.once:
            return
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
