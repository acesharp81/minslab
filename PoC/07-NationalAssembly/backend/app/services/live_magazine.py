from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROTATION_MS = 5_000
ALLOWED_INSTITUTIONS = {"EXECUTIVE", "LEGISLATURE"}


def filter_magazine_payload(
    payload: dict[str, Any],
    institution: str | None = None,
    scope: str | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    if payload.get("simulation") is not True:
        raise ValueError("simulation magazine payload must be explicitly marked")
    if payload.get("authority_status") != "PROVISIONAL":
        raise ValueError("simulation magazine must remain PROVISIONAL")
    if institution and institution not in ALLOWED_INSTITUTIONS:
        raise ValueError("unsupported institution")
    if not 1 <= limit <= 20:
        raise ValueError("limit must be between 1 and 20")

    cards = payload.get("magazine", [])
    if institution:
        cards = [card for card in cards if card.get("institution") == institution]
    if scope:
        cards = [
            card for card in cards
            if scope in card.get("ministries", []) or scope in card.get("committees", [])
        ]
    cards = sorted(cards, key=lambda card: (card.get("meeting_date", ""), card.get("card_id", "")), reverse=True)
    return {
        "items": cards[:limit],
        "count": min(len(cards), limit),
        "available_count": len(cards),
        "rotation_ms": ROTATION_MS,
        "simulation": True,
        "authority_status": "PROVISIONAL",
        "generated_at": payload.get("generated_at"),
        "source": payload.get("source"),
    }


def load_live_magazine(
    path: Path,
    institution: str | None = None,
    scope: str | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return filter_magazine_payload(payload, institution=institution, scope=scope, limit=limit)
