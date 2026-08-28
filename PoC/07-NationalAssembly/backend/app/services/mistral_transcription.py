from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests


PROVIDER = "mistral"
DEFAULT_MODEL = "voxtral-mini-latest"
DEFAULT_BASE_URL = "https://api.mistral.ai/v1"


@dataclass(frozen=True, slots=True)
class TranscriptionResult:
    text: str
    segments: list[dict[str, Any]]
    response_payload: dict[str, Any]
    usage_metadata: dict[str, Any]


class MistralTranscriptionClient:
    def __init__(
        self, api_key: str, *, model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_BASE_URL, usd_per_minute: float = 0.003,
        timeout_seconds: float = 120.0,
    ):
        if not api_key:
            raise ValueError("MISTRAL_API_KEY is required")
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.usd_per_minute = float(usd_per_minute)
        self.timeout_seconds = timeout_seconds

    def transcribe(self, audio_path: Path, *, duration_seconds: float) -> TranscriptionResult:
        content_hash = hashlib.sha256(audio_path.read_bytes()).hexdigest()
        with audio_path.open("rb") as audio:
            response = requests.post(
                f"{self.base_url}/audio/transcriptions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                data={
                    "model": self.model,
                    "diarize": "true",
                    "timestamp_granularities": "segment",
                    "response_format": "verbose_json",
                },
                files={"file": (audio_path.name, audio, "audio/mpeg")},
                timeout=self.timeout_seconds,
            )
        response.raise_for_status()
        payload = response.json()
        raw_segments = payload.get("segments") or []
        segments: list[dict[str, Any]] = []
        for index, item in enumerate(raw_segments):
            if not isinstance(item, dict) or not str(item.get("text") or "").strip():
                continue
            start = item.get("start", item.get("start_time", 0))
            end = item.get("end", item.get("end_time", start))
            speaker = item.get("speaker_id", item.get("speaker", item.get("speaker_label")))
            segments.append({
                "index": index,
                "text": str(item["text"]).strip(),
                "start_seconds": float(start or 0),
                "end_seconds": float(end or start or 0),
                "speaker": str(speaker if speaker is not None else "speaker-unknown"),
            })
        text = str(payload.get("text") or "").strip()
        if not segments and text:
            segments = [{
                "index": 0, "text": text, "start_seconds": 0.0,
                "end_seconds": float(duration_seconds), "speaker": "speaker-unknown",
            }]
        request_id = str(
            response.headers.get("x-request-id")
            or payload.get("id")
            or f"audio-{content_hash}-{self.model}"
        )
        cost_usd = (float(duration_seconds) / 60.0) * self.usd_per_minute
        usage = {
            "request_id": request_id,
            "audio_seconds": float(duration_seconds),
            "cost_usd": round(cost_usd, 8),
            "model": self.model,
        }
        return TranscriptionResult(text, segments, payload, usage)
