from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin

from ..adapters.live_sources import fetch_public_source
from ..adapters.national_assembly.base import SourcePayload
from ..db.executive_audio_repository import ExecutiveAudioRepository
from ..db.live_repository import CaptionRevision
from ..db.schedule_repository import SourceVersionInput
from ..services.mistral_budget import mistral_usage_cost_usd
from ..storage.raw_store import RawStore


PARSER_VERSION = "assembly-quick-vod-backfill/1.0"


@dataclass(frozen=True, slots=True)
class PlaylistSegment:
    index: int
    duration_seconds: float
    url: str


def parse_event_playlist(content: bytes, playlist_url: str) -> list[PlaylistSegment]:
    lines = content.decode("utf-8-sig").splitlines()
    if not lines or lines[0].strip() != "#EXTM3U":
        raise ValueError("Quick VOD playlist marker is missing")
    if "#EXT-X-PLAYLIST-TYPE:EVENT" not in {line.strip() for line in lines}:
        raise ValueError("Quick VOD playlist is not an EVENT playlist")
    segments: list[PlaylistSegment] = []
    pending_duration: float | None = None
    for raw_line in lines[1:]:
        line = raw_line.strip()
        if line.startswith("#EXTINF:"):
            pending_duration = float(line.removeprefix("#EXTINF:").split(",", 1)[0])
            continue
        if not line or line.startswith("#") or pending_duration is None:
            continue
        segments.append(PlaylistSegment(
            index=len(segments),
            duration_seconds=pending_duration,
            url=urljoin(playlist_url, line),
        ))
        pending_duration = None
    if not segments:
        raise ValueError("Quick VOD playlist has no media segments")
    return segments


def recoverable_duration(
    segments: list[PlaylistSegment], cutoff_seconds: float,
) -> tuple[int, float]:
    count = 0
    duration = 0.0
    for segment in segments:
        next_duration = duration + segment.duration_seconds
        if next_duration > cutoff_seconds:
            break
        count += 1
        duration = next_duration
    return count, duration


def download_playlist_segments(
    segments: list[PlaylistSegment], target_dir: Path, *, workers: int = 8,
) -> list[Path]:
    if not segments:
        raise ValueError("Quick VOD segment download requires at least one segment")
    target_dir.mkdir(parents=True, exist_ok=True)

    def download(segment: PlaylistSegment) -> Path:
        payload = fetch_public_source(
            f"assembly_quick_vod_segment_{segment.index}",
            segment.url,
            timeout_seconds=90,
        )
        if len(payload.content) < 512:
            raise RuntimeError(f"Quick VOD segment {segment.index} is empty")
        path = target_dir / f"{segment.index:06d}.ts"
        path.write_bytes(payload.content)
        return path

    bounded_workers = max(1, min(workers, len(segments)))
    with ThreadPoolExecutor(max_workers=bounded_workers) as executor:
        return list(executor.map(download, segments))


def concatenate_transport_streams(segment_paths: list[Path], target: Path) -> None:
    if not segment_paths:
        raise ValueError("Quick VOD concatenation requires at least one segment")
    with target.open("wb") as output:
        for segment_path in segment_paths:
            with segment_path.open("rb") as segment:
                shutil.copyfileobj(segment, output)


def capture_quick_vod_audio(
    segments: list[PlaylistSegment], target: Path, duration_seconds: float,
    *, download_workers: int = 8,
) -> None:
    print(json.dumps({
        "event": "quick_vod_backfill.download_started",
        "segment_count": len(segments),
        "download_workers": download_workers,
    }), flush=True)
    segment_paths = download_playlist_segments(
        segments, target.parent / "segments", workers=download_workers,
    )
    transport_stream = target.parent / "quick-vod-backfill.ts"
    concatenate_transport_streams(segment_paths, transport_stream)
    print(json.dumps({
        "event": "quick_vod_backfill.download_completed",
        "segment_count": len(segment_paths),
        "source_bytes": transport_stream.stat().st_size,
    }), flush=True)
    completed = subprocess.run(
        [
            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(transport_stream), "-t", f"{duration_seconds:.3f}", "-vn",
            "-ac", "1", "-ar", "16000", "-b:a", "32k", "-f", "mp3",
            str(target),
        ],
        check=False,
        timeout=300,
        capture_output=True,
    )
    if completed.returncode != 0 or not target.exists() or target.stat().st_size < 512:
        raise RuntimeError("Quick VOD audio capture failed")


def persist_backfill_transcription(
    *, broadcast_id: uuid.UUID, playlist_url: str, playlist_start_at: datetime,
    duration_seconds: float, audio_artifact: object, response_artifact: object,
    result: object, model: str, live_repository: object,
) -> int:
    source = SourceVersionInput(
        source_type="assembly_quick_vod_transcription",
        source_url=playlist_url,
        content_hash=getattr(response_artifact, "content_hash"),
        raw_path=getattr(response_artifact, "content_path"),
        retrieved_at=datetime.now(timezone.utc),
        parser_version=PARSER_VERSION,
        content_type="application/json",
        metadata={
            "audio_content_hash": getattr(audio_artifact, "content_hash"),
            "audio_raw_path": str(getattr(audio_artifact, "content_path")),
            "playlist_start_at": playlist_start_at.isoformat(),
            "duration_seconds": duration_seconds,
            "transcription_model": model,
        },
    )
    source_key = hashlib.sha256(playlist_url.encode("utf-8")).hexdigest()[:12]
    inserted = 0
    for index, segment in enumerate(getattr(result, "segments")):
        start_seconds = max(0.0, float(segment["start_seconds"]))
        end_seconds = min(duration_seconds, max(start_seconds, float(segment["end_seconds"])))
        if start_seconds >= duration_seconds:
            continue
        _, created = live_repository.append_caption_revision(
            broadcast_id,
            CaptionRevision(
                source_segment_id=f"qvod-backfill-{source_key}-{index:05d}",
                text=str(segment["text"]),
                speaker_label=f"qvod:{segment['speaker']}",
                is_final=True,
                received_at=playlist_start_at + timedelta(seconds=end_seconds),
                start_offset_ms=int(start_seconds * 1000),
                end_offset_ms=int(end_seconds * 1000),
                source_payload={
                    "audio_content_hash": getattr(audio_artifact, "content_hash"),
                    "transcription_provider": "mistral",
                    "transcription_model": model,
                    "transcription_source": "QUICK_VOD_BACKFILL",
                    "playlist_start_at": playlist_start_at.isoformat(),
                    "speaker_segments": [{
                        "speaker": f"qvod:{segment['speaker']}",
                        "text": str(segment["text"]),
                    }],
                },
                source=source,
            ),
        )
        inserted += int(created)
    return inserted


def write_manifest(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def main() -> None:
    from ..config import get_settings
    from ..db.connection import connect
    from ..db.live_repository import LiveRepository
    from ..db.migrate import apply_migrations
    from ..db.summary_repository import SummaryRepository
    from ..services.mistral_transcription import MistralTranscriptionClient

    parser = argparse.ArgumentParser(description="Backfill a missed Assembly LIVE interval from official Quick VOD")
    parser.add_argument("--broadcast-id", required=True)
    parser.add_argument("--playlist-url", required=True)
    parser.add_argument("--playlist-start-at", required=True)
    parser.add_argument("--overlap-guard-seconds", type=float, default=5.0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    if not settings.mistral_api_key and not args.dry_run:
        raise RuntimeError("MISTRAL_API_KEY is required")
    broadcast_id = uuid.UUID(args.broadcast_id)
    playlist_start_at = datetime.fromisoformat(args.playlist_start_at)
    if playlist_start_at.tzinfo is None:
        raise ValueError("playlist-start-at must include a timezone")
    apply_migrations(settings.database_url)

    with connect(settings.database_url) as connection:
        row = connection.execute(
            """
            SELECT institution, stt_fallback_started_at,
                   (SELECT COUNT(*) FROM transcript_segments segment
                    WHERE segment.broadcast_id = broadcast.id
                      AND segment.source_segment_id LIKE 'qvod-backfill-%%')
            FROM live_broadcasts broadcast WHERE broadcast.id = %s
            """,
            (broadcast_id,),
        ).fetchone()
    if not row or row[0] != "LEGISLATURE":
        raise ValueError("broadcast is not a stored legislature broadcast")
    if int(row[2]) > 0:
        print(json.dumps({"event": "quick_vod_backfill.skipped", "reason": "ALREADY_STORED"}))
        return
    if row[1] is None:
        raise ValueError("broadcast has no STT fallback boundary")

    playlist_payload = fetch_public_source(
        "assembly_quick_vod_playlist", args.playlist_url, timeout_seconds=30,
    )
    playlist_artifact = RawStore(settings.raw_data_dir).save(
        playlist_payload, parser_version=PARSER_VERSION,
    )
    segments = parse_event_playlist(playlist_payload.content, args.playlist_url)
    cutoff_seconds = (
        row[1].astimezone(timezone.utc) - playlist_start_at.astimezone(timezone.utc)
    ).total_seconds() - max(0.0, args.overlap_guard_seconds)
    segment_count, duration_seconds = recoverable_duration(segments, cutoff_seconds)
    if segment_count == 0:
        raise ValueError("Quick VOD has no complete segment before the STT boundary")
    estimate = round(duration_seconds / 60 * settings.executive_transcription_usd_per_minute, 8)
    plan = {
        "event": "quick_vod_backfill.plan",
        "broadcast_id": str(broadcast_id),
        "playlist_segments": segment_count,
        "duration_seconds": round(duration_seconds, 3),
        "estimated_cost_usd": estimate,
        "playlist_content_hash": playlist_artifact.content_hash,
    }
    print(json.dumps(plan), flush=True)
    if args.dry_run:
        return

    with connect(settings.database_url) as connection:
        provider_usage = SummaryRepository(connection).monthly_provider_usage("mistral")
    current_cost = mistral_usage_cost_usd(
        provider_usage,
        input_usd_per_million=settings.mistral_input_usd_per_million,
        output_usd_per_million=settings.mistral_output_usd_per_million,
    )
    if current_cost + estimate > settings.mistral_monthly_credit_usd:
        raise RuntimeError("Mistral monthly credit limit would be exceeded")

    with tempfile.TemporaryDirectory(prefix="assembly-qvod-backfill-") as temporary:
        audio_path = Path(temporary) / "quick-vod-backfill.mp3"
        capture_quick_vod_audio(segments[:segment_count], audio_path, duration_seconds)
        audio_payload = SourcePayload(
            source_key="assembly_quick_vod_audio",
            content=audio_path.read_bytes(),
            content_type="audio/mpeg",
            retrieved_at=datetime.now(timezone.utc),
            source_url=args.playlist_url,
            http_status=200,
        )
        audio_artifact = RawStore(settings.raw_data_dir).save(
            audio_payload, parser_version=PARSER_VERSION,
        )
        client = MistralTranscriptionClient(
            settings.mistral_api_key,
            model=settings.executive_transcription_model,
            base_url=settings.mistral_base_url,
            usd_per_minute=settings.executive_transcription_usd_per_minute,
            timeout_seconds=900,
        )
        result = client.transcribe(audio_artifact.content_path, duration_seconds=duration_seconds)
        response_payload = SourcePayload(
            source_key="assembly_quick_vod_transcription",
            content=json.dumps(result.response_payload, ensure_ascii=False, sort_keys=True).encode("utf-8"),
            content_type="application/json",
            retrieved_at=datetime.now(timezone.utc),
            source_url=args.playlist_url,
            http_status=200,
        )
        response_artifact = RawStore(settings.raw_data_dir).save(
            response_payload, parser_version=PARSER_VERSION,
        )

    with connect(settings.database_url) as connection:
        ExecutiveAudioRepository(connection).record_usage(
            provider="mistral",
            request_id=result.usage_metadata["request_id"],
            model=settings.executive_transcription_model,
            audio_seconds=result.usage_metadata["audio_seconds"],
            cost_usd=result.usage_metadata["cost_usd"],
        )
    with connect(settings.database_url) as connection:
        inserted = persist_backfill_transcription(
            broadcast_id=broadcast_id,
            playlist_url=args.playlist_url,
            playlist_start_at=playlist_start_at,
            duration_seconds=duration_seconds,
            audio_artifact=audio_artifact,
            response_artifact=response_artifact,
            result=result,
            model=settings.executive_transcription_model,
            live_repository=LiveRepository(connection),
        )
    completed = {
        **plan,
        "event": "quick_vod_backfill.completed",
        "inserted_segments": inserted,
        "request_count": 1,
        "actual_cost_usd": result.usage_metadata["cost_usd"],
    }
    write_manifest(
        settings.processed_data_dir / "quick_vod_backfills" / f"{broadcast_id}.json",
        completed,
    )
    print(json.dumps(completed), flush=True)


if __name__ == "__main__":
    main()
