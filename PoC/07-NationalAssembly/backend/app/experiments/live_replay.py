from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable


TOPIC_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("재난 대응", ("재난", "호우", "복구", "피해")),
    ("재정 집행", ("예산", "재정", "집행", "재원")),
    ("법률 지원", ("법률", "법무", "법률구조", "권리")),
)
MINISTRY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("행정안전부", ("재난", "호우", "복구", "행정안전")),
    ("기획재정부", ("예산", "재정", "재원")),
    ("법무부", ("법률", "법무", "법률구조")),
)
COMMITTEE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("행정안전위원회", ("재난", "호우", "행정안전")),
    ("예산결산특별위원회", ("예산", "재정", "재원")),
    ("법제사법위원회", ("법률", "법무", "권리")),
)


def _matches(text: str, rules: tuple[tuple[str, tuple[str, ...]], ...]) -> list[str]:
    return [name for name, keywords in rules if any(keyword in text for keyword in keywords)]


def _fixture_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def replay_live_fixture(
    payload: dict[str, Any],
    emit: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Replay synthetic caption revisions and return a deterministic saved-record shape."""
    if payload.get("simulation") is not True:
        raise ValueError("live replay accepts only fixtures explicitly marked simulation=true")

    events: list[dict[str, Any]] = []
    final_segments: list[dict[str, Any]] = []
    magazine: list[dict[str, Any]] = []

    for broadcast in payload.get("broadcasts", []):
        for segment in broadcast.get("segments", []):
            final_revision: dict[str, Any] | None = None
            for revision_number, revision in enumerate(segment.get("revisions", []), start=1):
                event = {
                    "event": "caption.final" if revision["is_final"] else "caption.partial",
                    "at_ms": revision["at_ms"],
                    "broadcast_id": broadcast["broadcast_id"],
                    "segment_id": segment["segment_id"],
                    "revision": revision_number,
                    "speaker_label": segment["speaker_label"],
                    "text": revision["text"],
                    "is_final": revision["is_final"],
                }
                events.append(event)
                if revision["is_final"]:
                    final_revision = revision
            if final_revision is None:
                raise ValueError(f"segment {segment['segment_id']} has no final revision")

            text = final_revision["text"]
            topics = _matches(text, TOPIC_RULES) or ["기타 정책"]
            ministries = _matches(text, MINISTRY_RULES)
            committees = _matches(text, COMMITTEE_RULES)
            normalized = {
                "broadcast_id": broadcast["broadcast_id"],
                "institution": broadcast["institution"],
                "segment_id": segment["segment_id"],
                "start_ms": segment["start_ms"],
                "end_ms": segment["end_ms"],
                "speaker_label": segment["speaker_label"],
                "text": text,
                "topics": topics,
                "ministries": ministries,
                "committees": committees,
                "revision_count": len(segment["revisions"]),
                "authority_status": "PROVISIONAL",
                "reconciliation_status": "UNRESOLVED",
                "simulation": True,
            }
            final_segments.append(normalized)
            magazine.append({
                "card_id": f"{broadcast['broadcast_id']}:{segment['segment_id']}",
                "institution": broadcast["institution"],
                "meeting_title": broadcast["meeting_title"],
                "meeting_date": broadcast["meeting_date"],
                "speaker_label": segment["speaker_label"],
                "major_quote": text,
                "topic": topics[0],
                "ministries": ministries,
                "committees": committees,
                "image_url": segment["image_url"],
                "image_alt": segment["image_alt"],
                "authority_status": "PROVISIONAL",
                "simulation": True,
            })

    events.sort(key=lambda item: (item["at_ms"], item["broadcast_id"], item["segment_id"]))
    if emit is not None:
        for event in events:
            emit(event)
    return {
        "schema_version": "live-replay-result.v1",
        "simulation": True,
        "simulation_id": payload["simulation_id"],
        "generated_at": payload["completed_at"],
        "source": {
            "type": "SYNTHETIC_FIXTURE",
            "fixture_name": payload["fixture_name"],
            "content_hash": _fixture_hash(payload),
        },
        "lifecycle_status": "ENDED",
        "authority_status": "PROVISIONAL",
        "reconciliation_status": "UNRESOLVED",
        "event_count": len(events),
        "segment_count": len(final_segments),
        "events": events,
        "segments": final_segments,
        "magazine": magazine,
    }


def load_and_replay(
    input_path: Path,
    output_path: Path,
    emit: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    result = replay_live_fixture(payload, emit=emit)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return result
