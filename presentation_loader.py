"""File-backed presentation catalog and administrator upload helper."""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path


BASE_DIR = Path(__file__).parent
PRESENTATIONS_DIR = BASE_DIR / "presentations"
MAX_PRESENTATION_BYTES = 10 * 1024 * 1024


def _safe_slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_value).strip("-")[:64]
    return slug or "presentation"


def _unique_slug(title: str) -> str:
    base = _safe_slug(title)
    candidate = base
    suffix = 2
    while (PRESENTATIONS_DIR / candidate).exists():
        candidate = f"{base[:56]}-{suffix}"
        suffix += 1
    return candidate


def _metadata_for(folder: Path) -> dict | None:
    html_path = folder / "index.html"
    metadata_path = folder / "presentation.json"
    if not html_path.is_file() or not metadata_path.is_file():
        return None
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(metadata, dict):
        return None
    slug = folder.name
    title = str(metadata.get("title") or slug).strip()[:120]
    created_at = str(metadata.get("created_at") or "")
    return {
        "id": slug,
        "title": title,
        "date": created_at[:10] or datetime.fromtimestamp(
            html_path.stat().st_mtime, tz=timezone.utc
        ).date().isoformat(),
        "summary": "업로드한 HTML 설명자료",
        "description": "관리자 화면에서 등록한 프레젠테이션 자료입니다.",
        "tags": ["HTML", "PRESENTATION"],
        "url": f"/presentations/view/{slug}/",
        "created_at": created_at,
        "size_bytes": html_path.stat().st_size,
    }


def load_presentations() -> list[dict]:
    """Return valid presentation folders, newest first."""
    if not PRESENTATIONS_DIR.exists():
        return []
    items = []
    for folder in PRESENTATIONS_DIR.iterdir():
        if folder.is_dir() and not folder.name.startswith("."):
            item = _metadata_for(folder)
            if item:
                items.append(item)
    items.sort(key=lambda item: (item.get("created_at", ""), item["title"]), reverse=True)
    for index, item in enumerate(items, start=1):
        item["no"] = f"{index:02d}"
    return items


def presentations_as_json() -> str:
    value = json.dumps(load_presentations(), ensure_ascii=False)
    return value.replace("</", "<\\/")


def save_presentation(title: str, html: str, filename: str = "") -> dict:
    """Validate and atomically add one standalone HTML presentation."""
    clean_title = str(title or "").strip()
    if not clean_title:
        raise ValueError("왼쪽 목록에 표시할 제목을 입력하세요.")
    if len(clean_title) > 120:
        raise ValueError("제목은 120자 이하여야 합니다.")
    if filename and not str(filename).lower().endswith(('.html', '.htm')):
        raise ValueError("HTML 파일만 업로드할 수 있습니다.")
    if not isinstance(html, str) or not html.strip():
        raise ValueError("업로드할 HTML 파일이 비어 있습니다.")
    encoded = html.encode("utf-8")
    if len(encoded) > MAX_PRESENTATION_BYTES:
        raise ValueError("HTML 파일은 10MB를 넘을 수 없습니다.")
    lowered = html[:100_000].lower()
    if "<html" not in lowered and "<!doctype html" not in lowered:
        raise ValueError("완전한 HTML 문서 파일을 선택하세요.")

    PRESENTATIONS_DIR.mkdir(parents=True, exist_ok=True)
    slug = _unique_slug(clean_title)
    target_dir = PRESENTATIONS_DIR / slug
    target_dir.mkdir()
    created_at = datetime.now(timezone.utc).isoformat()
    metadata = {
        "title": clean_title,
        "original_filename": Path(str(filename or "presentation.html")).name[:255],
        "created_at": created_at,
    }
    try:
        html_temp = target_dir / ".index.html.tmp"
        metadata_temp = target_dir / ".presentation.json.tmp"
        html_temp.write_bytes(encoded)
        metadata_temp.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        html_temp.replace(target_dir / "index.html")
        metadata_temp.replace(target_dir / "presentation.json")
    except OSError:
        for path in target_dir.iterdir():
            path.unlink(missing_ok=True)
        target_dir.rmdir()
        raise
    return _metadata_for(target_dir) or {}


def update_presentation(slug: str, title: str, html: str | None = None, filename: str = "") -> dict:
    """Update a presentation title and optionally replace its HTML while preserving its URL."""
    target_html = presentation_file(slug)
    if target_html is None:
        raise ValueError("수정할 설명자료를 찾을 수 없습니다.")
    clean_title = str(title or "").strip()
    if not clean_title:
        raise ValueError("왼쪽 목록에 표시할 제목을 입력하세요.")
    if len(clean_title) > 120:
        raise ValueError("제목은 120자 이하여야 합니다.")

    replacement = None
    if html is not None:
        if filename and not str(filename).lower().endswith((".html", ".htm")):
            raise ValueError("HTML 파일만 업로드할 수 있습니다.")
        if not isinstance(html, str) or not html.strip():
            raise ValueError("교체할 HTML 파일이 비어 있습니다.")
        replacement = html.encode("utf-8")
        if len(replacement) > MAX_PRESENTATION_BYTES:
            raise ValueError("HTML 파일은 10MB를 넘을 수 없습니다.")
        lowered = html[:100_000].lower()
        if "<html" not in lowered and "<!doctype html" not in lowered:
            raise ValueError("완전한 HTML 문서 파일을 선택하세요.")

    target_dir = target_html.parent
    metadata_path = target_dir / "presentation.json"
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        metadata = {}
    metadata["title"] = clean_title
    metadata["updated_at"] = datetime.now(timezone.utc).isoformat()
    if replacement is not None:
        metadata["original_filename"] = Path(str(filename or "presentation.html")).name[:255]
        html_temp = target_dir / ".index.html.tmp"
        html_temp.write_bytes(replacement)
        html_temp.replace(target_html)
    metadata_temp = target_dir / ".presentation.json.tmp"
    metadata_temp.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    metadata_temp.replace(metadata_path)
    return _metadata_for(target_dir) or {}


def presentation_file(slug: str) -> Path | None:
    """Resolve one catalogued HTML file without allowing path traversal."""
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,70}", str(slug or "")):
        return None
    target = (PRESENTATIONS_DIR / slug / "index.html").resolve()
    try:
        target.relative_to(PRESENTATIONS_DIR.resolve())
    except ValueError:
        return None
    return target if target.is_file() else None
