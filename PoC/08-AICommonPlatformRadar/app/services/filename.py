from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path


SAFE_EXTENSIONS = {"pdf", "docx", "hwp", "hwpx", "txt", "zip"}


def slugify(value: str, max_length: int = 72) -> str:
    normalized = unicodedata.normalize("NFKC", value).lower().strip()
    normalized = re.sub(r"[^0-9a-z가-힣]+", "-", normalized)
    normalized = re.sub(r"-+", "-", normalized).strip("-")
    return (normalized[:max_length].rstrip("-") or "unknown")


def safe_original_name(value: str) -> str:
    name = Path(value.replace("\\", "/")).name
    name = unicodedata.normalize("NFKC", name).replace("\x00", "")
    name = re.sub(r"[\r\n\t]", "_", name).strip(" .")
    return name[:240] or "attachment"


def extension_from_name(value: str) -> str:
    suffix = Path(safe_original_name(value)).suffix.lower().lstrip(".")
    return suffix if suffix in SAFE_EXTENSIONS else ""


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def build_stored_filename(
    *, source: str, stage: str, notice_no: str, agency: str, posted_yyyymmdd: str,
    title: str, sequence: int, sha256: str, extension: str,
) -> str:
    ext = extension.lower().lstrip(".")
    if ext not in SAFE_EXTENSIONS:
        raise ValueError(f"허용되지 않은 확장자: {extension}")
    parts = [
        slugify(source, 12), slugify(stage, 18), slugify(notice_no, 40),
        slugify(agency, 36), re.sub(r"\D", "", posted_yyyymmdd)[:8] or "unknown",
        slugify(title, 72), f"{sequence:02d}", sha256[:8].lower(),
    ]
    return "_".join(parts) + f".{ext}"

