from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..adapters.national_assembly.base import SourcePayload
from ..db.executive_audio_repository import ExecutiveAudioRepository
from ..db.live_repository import CaptionRevision
from ..db.schedule_repository import SourceVersionInput
from ..services.mistral_budget import mistral_usage_cost_usd
from ..storage.raw_store import RawStore


PARSER_VERSION = "ai-audio-transcription/1.1"


def capture_hls_audio(stream_url: str, target: Path, duration_seconds: int) -> None:
    completed = subprocess.run(
        [
            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
            "-i", stream_url, "-t", str(duration_seconds), "-vn", "-ac", "1",
            "-ar", "16000", "-b:a", "32k", "-f", "mp3", str(target),
        ],
        check=False,
        timeout=duration_seconds + 45,
        capture_output=True,
    )
    if completed.returncode != 0 or not target.exists() or target.stat().st_size < 512:
        raise RuntimeError("KTV audio capture failed")


def start_hls_segmenter(
    stream_url: str, directory: Path, *, chunk_seconds: int, start_number: int,
) -> subprocess.Popen[bytes]:
    pattern = directory / "chunk-%06d.mp3"
    return subprocess.Popen(
        [
            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
            "-i", stream_url, "-vn", "-ac", "1", "-ar", "16000",
            "-b:a", "32k", "-f", "segment", "-segment_time", str(chunk_seconds),
            "-segment_format", "mp3", "-reset_timestamps", "1",
            "-segment_start_number", str(start_number), str(pattern),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def completed_segment_paths(directory: Path, *, segmenter_running: bool) -> list[Path]:
    paths = sorted(directory.glob("chunk-*.mp3"))
    return paths[:-1] if segmenter_running and paths else paths


def segment_number(path: Path) -> int:
    return int(path.stem.rsplit("-", 1)[1])


def segment_directory_signature(directory: Path) -> tuple[tuple[str, int, int], ...]:
    signature: list[tuple[str, int, int]] = []
    for path in sorted(directory.glob("chunk-*.mp3")):
        try:
            stat = path.stat()
        except FileNotFoundError:
            continue
        signature.append((path.name, stat.st_size, stat.st_mtime_ns))
    return tuple(signature)


def audio_duration_ms(audio_path: Path, *, fallback_seconds: int) -> int:
    completed = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path),
        ],
        check=False, timeout=15, capture_output=True, text=True,
    )
    try:
        duration_ms = int(round(float(completed.stdout.strip()) * 1000))
    except (TypeError, ValueError):
        duration_ms = 0
    return duration_ms if completed.returncode == 0 and duration_ms > 0 else fallback_seconds * 1000


def store_audio_chunk(
    *, broadcast_id: uuid.UUID, chunk_number: int, stream_url: str,
    audio_path: Path, captured_at: datetime, duration_ms: int,
    raw_dir: Path, repository: ExecutiveAudioRepository,
) -> dict[str, Any]:
    content = audio_path.read_bytes()
    payload = SourcePayload(
        source_key="ai_audio_chunk", content=content, content_type="audio/mpeg",
        retrieved_at=captured_at, source_url=stream_url, http_status=200,
    )
    artifact = RawStore(raw_dir).save(payload, parser_version=PARSER_VERSION)
    chunk_id = repository.save_captured(
        broadcast_id, chunk_number, content_hash=artifact.content_hash,
        raw_path=artifact.content_path, captured_at=captured_at,
        duration_ms=duration_ms,
    )
    return {"chunk_id": chunk_id, "content_hash": artifact.content_hash,
            "raw_path": artifact.content_path, "duplicate": artifact.duplicate}


def persist_transcription(
    *, chunk: dict[str, Any], result: Any, stream_url: str,
    live_repository: Any, audio_repository: ExecutiveAudioRepository,
    model: str,
    continuation_speaker: str | None = None,
) -> int:
    broadcast_id = chunk["broadcast_id"]
    chunk_number = int(chunk["chunk_number"])
    base_offset = int(
        chunk.get("start_offset_ms", chunk_number * int(chunk["duration_ms"]))
    )
    received_at = datetime.now(timezone.utc)
    inserted = 0
    source = SourceVersionInput(
        source_type="ai_audio_transcription", source_url=stream_url,
        content_hash=hashlib.sha256(
            json.dumps(result.response_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest(),
        raw_path=Path(chunk["raw_path"]), retrieved_at=received_at,
        parser_version=PARSER_VERSION, content_type="application/json",
        metadata={"chunk_number": chunk_number, "audio_content_hash": chunk["content_hash"]},
    )
    first_source_speaker = str(result.segments[0]["speaker"]) if result.segments else ""
    speaker_map = ({first_source_speaker: continuation_speaker}
                   if continuation_speaker and first_source_speaker else {})
    for index, segment in enumerate(result.segments):
        source_speaker = str(segment["speaker"])
        speaker = speaker_map.get(source_speaker) or f"chunk-{chunk_number}:{source_speaker}"
        _, created = live_repository.append_caption_revision(
            broadcast_id,
            CaptionRevision(
                source_segment_id=f"stt-{chunk_number:06d}-{index:04d}",
                text=segment["text"], speaker_label=speaker, is_final=True,
                received_at=received_at,
                start_offset_ms=base_offset + int(segment["start_seconds"] * 1000),
                end_offset_ms=base_offset + int(segment["end_seconds"] * 1000),
                source_payload={
                    "audio_content_hash": chunk["content_hash"],
                    "chunk_number": chunk_number,
                    "transcription_provider": "mistral",
                    "transcription_model": model,
                    "speaker_segments": [{
                        "speaker": speaker, "text": segment["text"],
                    }],
                },
                source=source,
            ),
        )
        inserted += int(created)
    audio_repository.complete(
        chunk["chunk_id"], provider="mistral", model=model,
        transcript_payload=result.response_payload,
        usage_metadata=result.usage_metadata,
    )
    audio_repository.record_usage(
        provider="mistral", request_id=result.usage_metadata["request_id"],
        model=model, audio_seconds=result.usage_metadata["audio_seconds"],
        cost_usd=result.usage_metadata["cost_usd"],
    )
    return inserted


def capture_broadcast(claim: dict[str, Any], *, settings: Any, worker_id: str) -> dict[str, Any]:
    from ..db.connection import connect
    from ..db.live_repository import LiveRepository
    from ..db.summary_repository import SummaryRepository
    from ..services.mistral_transcription import MistralTranscriptionClient

    broadcast_id = claim["broadcast_id"]
    stream_url = str(claim["media_stream_url"])
    chunk_seconds = max(20, min(int(settings.executive_audio_chunk_seconds), 180))
    client = MistralTranscriptionClient(
        settings.mistral_api_key, model=settings.executive_transcription_model,
        base_url=settings.mistral_base_url,
        usd_per_minute=settings.executive_transcription_usd_per_minute,
    )
    captured = transcribed = failures = 0
    retry = True
    terminal_failure = False
    segmenter: subprocess.Popen[bytes] | None = None
    try:
        with connect(settings.database_url) as connection:
            start_number = ExecutiveAudioRepository(connection).next_chunk_number(broadcast_id)
        with tempfile.TemporaryDirectory(prefix="ktv-audio-") as temporary:
            segment_dir = Path(temporary)
            resume_post_processing = claim.get("lifecycle_status") == "ENDED"
            if not resume_post_processing:
                segmenter = start_hls_segmenter(
                    stream_url, segment_dir, chunk_seconds=chunk_seconds,
                    start_number=start_number,
                )
            stored_paths: set[Path] = set()
            live_ended = resume_post_processing
            segmenter_stalled = False
            stalled_after_seconds = max(chunk_seconds * 2 + 30, 150)
            last_segment_signature = segment_directory_signature(segment_dir)
            last_segment_progress_at = time.monotonic()
            if resume_post_processing:
                retry = False
            while True:
                running = segmenter is not None and segmenter.poll() is None
                segmenter_stalled = False
                if running:
                    signature = segment_directory_signature(segment_dir)
                    if signature != last_segment_signature:
                        last_segment_signature = signature
                        last_segment_progress_at = time.monotonic()
                    elif time.monotonic() - last_segment_progress_at >= stalled_after_seconds:
                        idle_seconds = int(time.monotonic() - last_segment_progress_at)
                        segmenter.terminate()
                        try:
                            segmenter.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            segmenter.kill()
                            segmenter.wait(timeout=5)
                        running = False
                        segmenter_stalled = True
                        print(json.dumps({
                            "event": "executive.audio.segmenter_stalled",
                            "broadcast_id": str(broadcast_id),
                            "idle_seconds": idle_seconds,
                        }), flush=True)
                if not live_ended:
                    with connect(settings.database_url) as connection:
                        alive = LiveRepository(connection).heartbeat_audio_fallback(
                            broadcast_id, worker_id, chunk_seconds + 120,
                        )
                    if not alive:
                        live_ended = True
                        retry = False
                        if running:
                            segmenter.terminate()
                            try:
                                segmenter.wait(timeout=15)
                            except subprocess.TimeoutExpired:
                                segmenter.kill()
                                segmenter.wait(timeout=5)
                        running = False

                for local_path in completed_segment_paths(
                    segment_dir, segmenter_running=running,
                ):
                    if local_path in stored_paths or local_path.stat().st_size < 512:
                        continue
                    with connect(settings.database_url) as connection:
                        store_audio_chunk(
                            broadcast_id=broadcast_id,
                            chunk_number=segment_number(local_path),
                            stream_url=stream_url, audio_path=local_path,
                            captured_at=datetime.now(timezone.utc),
                            duration_ms=audio_duration_ms(
                                local_path, fallback_seconds=chunk_seconds,
                            ),
                            raw_dir=settings.raw_data_dir,
                            repository=ExecutiveAudioRepository(connection),
                        )
                    stored_paths.add(local_path)
                    captured += 1

                if segmenter_stalled:
                    raise RuntimeError("KTV continuous audio segmenter stalled")

                with connect(settings.database_url) as connection:
                    audio = ExecutiveAudioRepository(connection)
                    chunk = audio.claim_pending(broadcast_id)
                    usage_snapshot = (
                        SummaryRepository(connection).monthly_token_usage(
                            "mistral", settings.llm_model,
                        ) if chunk else None
                    )
                result = None
                if chunk:
                    current_cost = mistral_usage_cost_usd(
                        usage_snapshot or {},
                        input_usd_per_million=settings.mistral_input_usd_per_million,
                        output_usd_per_million=settings.mistral_output_usd_per_million,
                    )
                    next_cost = (float(chunk["duration_ms"]) / 60000.0) * float(
                        settings.executive_transcription_usd_per_minute
                    )
                    if current_cost + next_cost > float(settings.mistral_monthly_credit_usd):
                        with connect(settings.database_url) as connection:
                            ExecutiveAudioRepository(connection).fail(
                                chunk["chunk_id"], "MONTHLY_CREDIT_LIMIT",
                            )
                        failures += 1
                        chunk = None

                if chunk:
                    try:
                        result = client.transcribe(
                            Path(chunk["raw_path"]),
                            duration_seconds=float(chunk["duration_ms"]) / 1000.0,
                        )
                    except Exception as exc:
                        with connect(settings.database_url) as connection:
                            ExecutiveAudioRepository(connection).fail(
                                chunk["chunk_id"], type(exc).__name__,
                            )
                        failures += 1

                if chunk and result is not None:
                    with connect(settings.database_url) as connection:
                        boundary_ms = int(chunk.get(
                            "start_offset_ms",
                            int(chunk["chunk_number"]) * int(chunk["duration_ms"]),
                        ))
                        previous = connection.execute(
                            """
                            SELECT speaker_label, end_offset_ms
                            FROM transcript_segments
                            WHERE broadcast_id = %s AND is_final = true
                            ORDER BY end_offset_ms DESC NULLS LAST, last_received_at DESC
                            LIMIT 1
                            """,
                            (broadcast_id,),
                        ).fetchone()
                        first_start_ms = (
                            int(result.segments[0]["start_seconds"] * 1000)
                            if result.segments else 999999
                        )
                        continuation_speaker = (
                            str(previous[0])
                            if previous and previous[0] and previous[1] is not None
                            and int(previous[1]) >= boundary_ms - 1500
                            and first_start_ms <= 1500
                            else None
                        )
                        transcribed += persist_transcription(
                            chunk=chunk, result=result, stream_url=stream_url,
                            live_repository=LiveRepository(connection),
                            audio_repository=ExecutiveAudioRepository(connection),
                            model=settings.executive_transcription_model,
                            continuation_speaker=continuation_speaker,
                        )
                    print(json.dumps({
                        "event": "executive.audio.progress",
                        "broadcast_id": str(broadcast_id),
                        "captured_chunks": captured,
                        "transcript_segments": transcribed,
                        "failures": failures,
                    }), flush=True)

                if live_ended:
                    with connect(settings.database_url) as connection:
                        pending_status = connection.execute(
                            """
                            SELECT
                              COUNT(*) FILTER (
                                WHERE transcription_status IN ('CAPTURED', 'PROCESSING', 'FAILED')
                                  AND attempts < 4
                              ),
                              COUNT(*) FILTER (WHERE transcription_status <> 'TRANSCRIBED')
                            FROM executive_audio_chunks
                            WHERE broadcast_id = %s
                            """,
                            (broadcast_id,),
                        ).fetchone()
                    if int(pending_status[0]) == 0:
                        terminal_failure = int(pending_status[1]) > 0
                        break
                elif not running:
                    raise RuntimeError("KTV continuous audio segmenter stopped")

                if not chunk:
                    time.sleep(0.5)
    finally:
        if segmenter is not None and segmenter.poll() is None:
            segmenter.terminate()
            try:
                segmenter.wait(timeout=10)
            except subprocess.TimeoutExpired:
                segmenter.kill()
        with connect(settings.database_url) as connection:
            lifecycle_row = connection.execute(
                "SELECT lifecycle_status FROM live_broadcasts WHERE id = %s",
                (broadcast_id,),
            ).fetchone()
            if lifecycle_row and lifecycle_row[0] == "ENDED":
                unresolved = connection.execute(
                    """
                    SELECT
                      COUNT(*) FILTER (WHERE transcription_status <> 'TRANSCRIBED'),
                      COUNT(*) FILTER (
                        WHERE transcription_status IN ('CAPTURED', 'PROCESSING', 'FAILED')
                          AND attempts < 4
                      )
                    FROM executive_audio_chunks WHERE broadcast_id = %s
                    """,
                    (broadcast_id,),
                ).fetchone()
                if int(unresolved[0]) > 0:
                    retry = int(unresolved[1]) > 0
                    terminal_failure = not retry
                else:
                    retry = False
            LiveRepository(connection).release_audio_fallback(
                broadcast_id, worker_id, retry=retry, failed=terminal_failure,
            )
    return {
        "broadcast_id": str(broadcast_id), "captured": captured,
        "transcript_segments": transcribed, "failures": failures,
        "retry": retry, "terminal_failure": terminal_failure,
    }


def main() -> None:
    from ..config import get_settings
    from ..db.connection import connect
    from ..db.live_repository import LiveRepository
    from ..db.migrate import apply_migrations

    parser = argparse.ArgumentParser(description="Capture and transcribe audio only while official captions are unavailable")
    parser.add_argument("--interval", type=float, default=5.0)
    parser.add_argument("--lease-seconds", type=int, default=180)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    if not settings.mistral_api_key:
        raise RuntimeError("MISTRAL_API_KEY is required")
    apply_migrations(settings.database_url)
    worker_id = f"{socket.gethostname()}:{os.getpid()}:executive-audio"
    while True:
        with connect(settings.database_url) as connection:
            claim = LiveRepository(connection).claim_audio_fallback_capture(
                worker_id, args.lease_seconds,
            )
        if claim:
            print(json.dumps({
                "event": "executive.audio.started",
                "broadcast_id": str(claim["broadcast_id"]),
                "lifecycle_status": claim["lifecycle_status"],
            }), flush=True)
            try:
                result = capture_broadcast(claim, settings=settings, worker_id=worker_id)
                print(json.dumps({"event": "executive.audio.completed", **result}), flush=True)
            except Exception as exc:
                print(json.dumps({"event": "executive.audio.error", "error": type(exc).__name__}), flush=True)
        if args.once:
            return
        time.sleep(max(2.0, min(args.interval, 60.0)))


if __name__ == "__main__":
    main()
