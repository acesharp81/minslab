from __future__ import annotations

import hashlib
import json
from typing import Any


def openrouter_headers(
    api_key: str, body: dict[str, Any], *, workload: str, priority: int,
) -> dict[str, str]:
    encoded = json.dumps(body, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "HTTP-Referer": "https://www.minslab.kr",
        "X-Title": "POC-07 National Assembly",
        "X-Minslab-Project": "poc7",
        "X-Minslab-Workload": workload[:60],
        "X-Minslab-Priority": str(max(1, min(int(priority), 100))),
        "X-Minslab-Data-Class": "public_official",
        "X-Idempotency-Key": "poc7:" + hashlib.sha256(encoded).hexdigest(),
    }
