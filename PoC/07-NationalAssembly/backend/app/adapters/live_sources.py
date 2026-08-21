from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from html import unescape
from urllib import error as url_error
from urllib import parse as url_parse
from urllib import request as url_request

from .national_assembly.base import AdapterError, SourcePayload


ASSEMBLY_LIVE_LIST_URL = "https://assembly.webcast.go.kr/main/service/live_list.asp"
KTV_REFERENCE_URL = "https://www.ktv.go.kr/content/player?content_id=758125"
ASSEMBLY_LIVE_PLAY_URL = "https://assembly.webcast.go.kr/main/service/live_play.asp"
PARSER_VERSION = "live-source-probe/1.0"
TARGET_NAMES = {
    "예결위": "예산결산특별위원회",
    "법사위": "법제사법위원회",
    "행안위": "행정안전위원회",
}


def fetch_public_source(source_key: str, url: str, timeout_seconds: float = 15.0) -> SourcePayload:
    request = url_request.Request(url, headers={"User-Agent": "POC-07-NationalAssembly/0.1"})
    try:
        with url_request.urlopen(request, timeout=timeout_seconds) as response:
            content = response.read()
            status = int(response.status)
            content_type = response.headers.get_content_type()
    except url_error.HTTPError as error:
        raise AdapterError(f"HTTP {error.code} from {source_key}") from error
    except (url_error.URLError, TimeoutError) as error:
        raise AdapterError(f"request failed for {source_key}: {type(error).__name__}") from error
    return SourcePayload(
        source_key=source_key,
        content=content,
        content_type=content_type,
        retrieved_at=datetime.now(timezone.utc),
        source_url=url,
        http_status=status,
    )


def parse_assembly_live_list(content: bytes) -> dict[str, object]:
    try:
        payload = json.loads(content.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AdapterError("invalid assembly live list JSON") from exc
    rows = payload.get("xlist")
    if not isinstance(rows, list):
        raise AdapterError("assembly live list has no xlist")

    items: list[dict[str, object]] = []
    for row in rows:
        short_name = str(row.get("xname", "")).strip()
        if short_name not in TARGET_NAMES:
            continue
        status = str(row.get("xstat", "")).strip()
        items.append({
            "institution": "LEGISLATURE",
            "committee_name": TARGET_NAMES[short_name],
            "short_name": short_name,
            "channel_code": str(row.get("xcode", "")).strip(),
            "meeting_external_id": str(row.get("xcgcd", "")).strip() or None,
            "title": str(row.get("xsubj", "")).strip() or None,
            "status_text": str(row.get("xdesc", "")).strip() or "상태 미상",
            "is_live": status == "1",
            "has_caption_service": str(row.get("xsami", "")).strip() == "1",
            "quick_vod_available": str(row.get("xqvod", "")).strip() == "1",
            "quick_vod_url": str(row.get("qlink", "")).strip() or None,
            "thumbnail_url": str(row.get("xthmb", "")).strip() or None,
        })
    if len(items) != len(TARGET_NAMES):
        raise AdapterError("target committee rows are incomplete")
    return {
        "items": items,
        "count": len(items),
        "live_count": sum(bool(item["is_live"]) for item in items),
        "source_time": payload.get("qtime"),
        "source_status": "OFFICIAL",
    }


def parse_ktv_player_contract(content: bytes) -> dict[str, object]:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AdapterError("invalid KTV player HTML") from exc
    content_id = re.search(r'playerContentId\s*=\s*"([0-9]+)"', text)
    title = re.search(r'<meta\s+name="title"\s+content="([^"]*)"', text, re.IGNORECASE)
    if not content_id or not title:
        raise AdapterError("KTV player contract markers are missing")
    machine_caption_markers = (
        '<track kind="captions"',
        '<track kind="subtitles"',
        ".vtt",
        "captionUrl",
        "subtitleUrl",
    )
    return {
        "institution": "EXECUTIVE",
        "content_id": content_id.group(1),
        "title": unescape(title.group(1)),
        "player_detected": "WeNMediaPlayer" in text,
        "hls_library_detected": "/vodplayer/lib/hls.js" in text,
        "machine_caption_track_detected": any(marker.lower() in text.lower() for marker in machine_caption_markers),
        "caption_contract_status": "UNVERIFIED",
        "live_detection_status": "PAGE_DISCOVERY_ONLY",
    }


def assembly_live_play_url(channel_code: str, meeting_external_id: str) -> str:
    query = url_parse.urlencode({"xcode": channel_code, "xcgcd": meeting_external_id})
    return f"{ASSEMBLY_LIVE_PLAY_URL}?{query}"


def parse_assembly_live_play(content: bytes) -> dict[str, object]:
    try:
        payload = json.loads(content.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AdapterError("invalid assembly live play JSON") from exc
    if payload.get("xcode") == "invalid-request":
        raise AdapterError("assembly live play request is invalid")
    required = ("xcode", "xcgcd", "xsubj", "xstat", "xsami", "xhls")
    if any(name not in payload for name in required):
        raise AdapterError("assembly live play contract markers are missing")
    caption_server = str(payload.get("xsami", "")).strip()
    hls_profiles = payload.get("xhls", [])
    stream_url = None
    if isinstance(hls_profiles, list):
        for profile in hls_profiles:
            if not isinstance(profile, dict):
                continue
            candidates = [profile.get("default"), *profile.values()]
            stream_url = next((
                str(value).strip() for value in candidates
                if isinstance(value, str)
                and value.strip().startswith("https://")
                and ".m3u8" in value
            ), None)
            if stream_url:
                break
    return {
        "channel_code": str(payload["xcode"]),
        "meeting_external_id": str(payload["xcgcd"]),
        "committee_name": str(payload.get("xfull", "")).strip() or str(payload.get("xname", "")).strip(),
        "title": str(payload["xsubj"]).strip(),
        "status_text": str(payload.get("xdesc", "")).strip(),
        "is_live": str(payload["xstat"]) == "1",
        "caption_websocket_url": f"{caption_server}/hls" if caption_server else None,
        "caption_capture_status": "READY_TO_CAPTURE" if caption_server else "UNAVAILABLE",
        "hls_profiles": hls_profiles,
        "stream_url": stream_url,
        "quick_vod_available": str(payload.get("xqvod", "")) == "1",
        "quick_vod_url": str(payload.get("qlink", "")).strip() or None,
        "source_time": payload.get("qtime"),
    }


def parse_assembly_caption_message(content: str) -> dict[str, object]:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise AdapterError("invalid assembly caption JSON") from exc
    if "segment" not in payload or "transcript" not in payload:
        raise AdapterError("assembly caption message markers are missing")
    speakers = []
    for item in payload.get("transcripts") or []:
        if isinstance(item, list) and len(item) >= 2:
            speakers.append({"speaker": str(item[0]), "text": str(item[1]).lstrip("-").strip()})
    final_value = payload.get("final", False)
    is_final = final_value is True or str(final_value).lower() in {"1", "true", "final"}
    return {
        "segment_id": str(payload["segment"]),
        "transcript": str(payload["transcript"]).strip(),
        "speaker_segments": speakers,
        "is_final": is_final,
        "speech_code": payload.get("scd"),
    }
