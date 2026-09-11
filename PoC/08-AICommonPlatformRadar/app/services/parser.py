from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree

from docx import Document
from pypdf import PdfReader

from .filename import SAFE_EXTENSIONS


@dataclass(frozen=True)
class ParseResult:
    status: str
    text: str = ""
    error: str | None = None


def is_safe_zip_member(name: str) -> bool:
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    return bool(normalized and not path.is_absolute() and ".." not in path.parts and not re.match(r"^[A-Za-z]:", normalized))


def _decode_text(content: bytes) -> str:
    for encoding in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def _parse_pdf(content: bytes) -> str:
    return "\n\n".join((page.extract_text() or "") for page in PdfReader(io.BytesIO(content)).pages)


def _parse_docx(content: bytes) -> str:
    document = Document(io.BytesIO(content))
    paragraphs = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
    for table in document.tables:
        for row in table.rows:
            paragraphs.append(" | ".join(cell.text.strip() for cell in row.cells))
    return "\n".join(paragraphs)


def _parse_hwpx(content: bytes) -> str:
    chunks: list[str] = []
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        for info in archive.infolist():
            if not is_safe_zip_member(info.filename):
                raise ValueError(f"안전하지 않은 HWPX 경로: {info.filename}")
            if not info.filename.startswith("Contents/") or not info.filename.endswith(".xml"):
                continue
            root = ElementTree.fromstring(archive.read(info))
            chunks.extend(element.text or "" for element in root.iter() if element.tag.endswith("}t"))
    return "\n".join(chunk for chunk in chunks if chunk.strip())


def _parse_zip(content: bytes, max_uncompressed_bytes: int = 100 * 1024 * 1024) -> str:
    chunks: list[str] = []
    total = 0
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        for info in archive.infolist():
            if not is_safe_zip_member(info.filename):
                raise ValueError(f"ZIP path traversal 차단: {info.filename}")
            total += info.file_size
            if total > max_uncompressed_bytes:
                raise ValueError("ZIP 압축 해제 크기 제한 초과")
            ext = Path(info.filename).suffix.lower().lstrip(".")
            if ext not in SAFE_EXTENSIONS or ext in {"zip", "hwp"} or info.is_dir():
                continue
            child = parse_bytes(archive.read(info), ext)
            if child.status == "parsed" and child.text.strip():
                chunks.append(f"\n--- {Path(info.filename).name} ---\n{child.text}")
    return "\n".join(chunks)


def parse_bytes(content: bytes, extension: str) -> ParseResult:
    ext = extension.lower().lstrip(".")
    if not content:
        return ParseResult("failed", error="0바이트 파일")
    if ext == "hwp":
        return ParseResult("unsupported", error="바이너리 HWP는 안전한 외부 변환기 구성 전까지 미지원")
    try:
        if ext == "txt":
            text = _decode_text(content)
        elif ext == "pdf":
            text = _parse_pdf(content)
        elif ext == "docx":
            text = _parse_docx(content)
        elif ext == "hwpx":
            text = _parse_hwpx(content)
        elif ext == "zip":
            text = _parse_zip(content)
        else:
            return ParseResult("unsupported", error=f"지원하지 않는 형식: {ext or 'unknown'}")
        cleaned = text.replace("\x00", "").strip()
        return ParseResult("parsed", cleaned) if cleaned else ParseResult("failed", error="추출된 본문이 없음")
    except Exception as exc:
        return ParseResult("failed", error=f"{type(exc).__name__}: {str(exc)[:500]}")


def parse_file(path: Path, extension: str | None = None) -> ParseResult:
    return parse_bytes(path.read_bytes(), extension or path.suffix)
