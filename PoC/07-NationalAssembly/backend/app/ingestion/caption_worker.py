from __future__ import annotations

import argparse
import json
import os
import socket
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from ..adapters.live_sources import parse_assembly_caption_message
from ..adapters.national_assembly.base import AdapterError, SourcePayload
from ..db.live_repository import CaptionRevision
from ..db.schedule_repository import SourceVersionInput
from ..storage.raw_store import RawStore


CAPTION_PARSER_VERSION = "assembly-live-caption/1.0"


class CaptionRevisionSink(Protocol):
    def append_caption_revision(
        self, broadcast_id: uuid.UUID, revision: CaptionRevision
    ) -> tuple[uuid.UUID, bool]: ...


def persist_caption_message(
    *,
    broadcast_id: uuid.UUID,
    external_id: str,
    source_url: str,
    raw_message: str | bytes,
    received_at: datetime,
    raw_dir: Path,
    sink: CaptionRevisionSink,
) -> dict[str, Any]:
    content = raw_message if isinstance(raw_message, bytes) else raw_message.encode("utf-8")
    payload = SourcePayload(
        source_key="assembly_caption_message",
        content=content,
        content_type="application/json",
        retrieved_at=received_at,
        source_url=source_url,
        http_status=101,
    )
    artifact = RawStore(raw_dir).save(payload, parser_version=CAPTION_PARSER_VERSION)
    parsed = parse_assembly_caption_message(content.decode("utf-8"))
    speaker_segments = parsed["speaker_segments"]
    speaker_label = None
    if isinstance(speaker_segments, list) and speaker_segments:
        speaker_label = str(speaker_segments[0]["speaker"])
    source = SourceVersionInput(
        source_type="assembly_caption_message",
        source_url=source_url,
        content_hash=artifact.content_hash,
        raw_path=artifact.content_path,
        retrieved_at=received_at,
        parser_version=CAPTION_PARSER_VERSION,
        content_type="application/json",
        metadata={
            "broadcast_external_id": external_id,
            "source_segment_id": parsed["segment_id"],
            "speech_code": parsed["speech_code"],
        },
    )
    segment_id, inserted = sink.append_caption_revision(
        broadcast_id,
        CaptionRevision(
            source_segment_id=str(parsed["segment_id"]),
            text=str(parsed["transcript"]),
            speaker_label=speaker_label,
            is_final=bool(parsed["is_final"]),
            received_at=received_at,
            source_payload={
                "content_hash": artifact.content_hash,
                "raw_path": str(artifact.content_path),
                "parser_version": CAPTION_PARSER_VERSION,
                "speaker_segments": speaker_segments,
                "speech_code": parsed["speech_code"],
            },
            source=source,
        ),
    )
    return {
        "segment_id": str(segment_id),
        "source_segment_id": parsed["segment_id"],
        "is_final": parsed["is_final"],
        "revision_inserted": inserted,
        "raw_duplicate": artifact.duplicate,
        "content_hash": artifact.content_hash,
    }


def capture_broadcast(
    claim: dict[str, Any],
    *,
    database_url: str,
    raw_dir: Path,
    worker_id: str,
    lease_seconds: int,
) -> dict[str, Any]:
    from websockets.sync.client import connect as websocket_connect

    from ..db.connection import connect
    from ..db.live_repository import LiveRepository

    broadcast_id = claim["broadcast_id"]
    external_id = str(claim["external_id"])
    source_url = str(claim["caption_websocket_url"])
    stored = duplicates = malformed = 0
    retry = True
    try:
        with websocket_connect(
            source_url,
            subprotocols=["echo-protocol"],
            open_timeout=10,
            close_timeout=5,
            ping_interval=20,
            ping_timeout=20,
        ) as websocket:
            while True:
                try:
                    message = websocket.recv(timeout=15)
                except TimeoutError:
                    with connect(database_url) as connection:
                        if not LiveRepository(connection).heartbeat_capture(
                            broadcast_id, worker_id, lease_seconds
                        ):
                            retry = False
                            break
                    continue
                if message is None:
                    break
                received_at = datetime.now(timezone.utc)
                try:
                    with connect(database_url) as connection:
                        repository = LiveRepository(connection)
                        result = persist_caption_message(
                            broadcast_id=broadcast_id,
                            external_id=external_id,
                            source_url=source_url,
                            raw_message=message,
                            received_at=received_at,
                            raw_dir=raw_dir,
                            sink=repository,
                        )
                        alive = repository.heartbeat_capture(
                            broadcast_id, worker_id, lease_seconds
                        )
                    stored += int(result["revision_inserted"])
                    duplicates += int(not result["revision_inserted"])
                    if not alive:
                        retry = False
                        break
                except (AdapterError, UnicodeDecodeError):
                    malformed += 1
    finally:
        with connect(database_url) as connection:
            LiveRepository(connection).release_caption_capture(
                broadcast_id, worker_id, retry=retry
            )
    return {
        "broadcast_id": str(broadcast_id),
        "stored": stored,
        "duplicates": duplicates,
        "malformed": malformed,
        "retry": retry,
    }


def main() -> None:
    from ..config import get_settings
    from ..db.connection import connect
    from ..db.live_repository import LiveRepository
    from ..db.migrate import apply_migrations

    parser = argparse.ArgumentParser(description="Capture official Assembly LIVE captions")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument("--lease-seconds", type=int, default=45)
    args = parser.parse_args()
    if not 1 <= args.workers <= 3:
        parser.error("workers must be between 1 and 3")
    if not 1 <= args.poll_interval <= 30:
        parser.error("poll-interval must be between 1 and 30 seconds")
    if not 30 <= args.lease_seconds <= 300:
        parser.error("lease-seconds must be between 30 and 300")

    settings = get_settings()
    apply_migrations(settings.database_url)
    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    futures: set[Future[dict[str, Any]]] = set()
    with ThreadPoolExecutor(max_workers=args.workers, thread_name_prefix="caption") as executor:
        while True:
            completed = {future for future in futures if future.done()}
            for future in completed:
                futures.remove(future)
                try:
                    print(json.dumps(future.result(), ensure_ascii=False), flush=True)
                except Exception as exc:
                    print(json.dumps({"event": "capture.error", "error": type(exc).__name__}), flush=True)
            while len(futures) < args.workers:
                with connect(settings.database_url) as connection:
                    claim = LiveRepository(connection).claim_caption_capture(
                        worker_id, args.lease_seconds
                    )
                if claim is None:
                    break
                futures.add(executor.submit(
                    capture_broadcast,
                    claim,
                    database_url=settings.database_url,
                    raw_dir=settings.raw_data_dir,
                    worker_id=worker_id,
                    lease_seconds=args.lease_seconds,
                ))
            time.sleep(args.poll_interval)


if __name__ == "__main__":
    main()
