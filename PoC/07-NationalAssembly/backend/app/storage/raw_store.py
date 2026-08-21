from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from ..adapters.national_assembly.base import SourcePayload


@dataclass(frozen=True, slots=True)
class RawArtifact:
    content_hash: str
    content_path: Path
    manifest_path: Path
    duplicate: bool


class RawStore:
    def __init__(self, root: Path):
        self.root = Path(root)

    def save(self, payload: SourcePayload, *, parser_version: str) -> RawArtifact:
        content_hash = hashlib.sha256(payload.content).hexdigest()
        day = payload.retrieved_at.strftime("%Y/%m/%d")
        directory = self.root / payload.source_key / day
        directory.mkdir(parents=True, exist_ok=True)

        detected_format = self._detect_format(payload.content, payload.content_type)
        extension = f".{detected_format}"
        content_path = directory / f"{content_hash}{extension}"
        manifest_path = directory / f"{content_hash}.manifest.json"
        duplicate = content_path.exists()

        if not duplicate:
            self._atomic_write_bytes(content_path, payload.content)

        manifest = {
            "source_type": payload.source_key,
            "source_url": payload.source_url,
            "retrieved_at": payload.retrieved_at.isoformat(),
            "content_hash": content_hash,
            "content_type": payload.content_type,
            "detected_format": detected_format,
            "http_status": payload.http_status,
            "parser_version": parser_version,
            "duplicate_content": duplicate,
        }
        self._atomic_write_bytes(
            manifest_path,
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8"),
        )
        return RawArtifact(content_hash, content_path, manifest_path, duplicate)

    @staticmethod
    def _detect_format(content: bytes, content_type: str) -> str:
        if content.startswith(b"%PDF-"):
            return "pdf"
        prefix = content.lstrip()[:1]
        if prefix in {b"{", b"["}:
            return "json"
        lowered = content_type.lower()
        if prefix == b"<" and "html" in lowered:
            return "html"
        if prefix == b"<":
            return "xml"
        if "json" in lowered:
            return "json"
        if "html" in lowered:
            return "html"
        if "pdf" in lowered:
            return "pdf"
        return "xml"

    @staticmethod
    def _atomic_write_bytes(path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(descriptor, "wb") as temporary:
                temporary.write(content)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_name, path)
        except Exception:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
            raise
