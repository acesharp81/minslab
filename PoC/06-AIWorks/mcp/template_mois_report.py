"""Local Ministry of the Interior and Safety report template transformer."""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree


MANIFEST = {
    "id": "template.mois-report",
    "name": "행안부 보고서 양식 MCP",
    "version": "0.1.0",
    "runtime": "local",
    "description": (
        "현재 HWPX의 문구를 보존하면서 AIWorks에 등록된 행안부 내부보고형 체험 양식으로 재구성합니다. "
        "공식 배포 서식 원본을 등록하기 전까지는 체험 양식으로 표시합니다."
    ),
    "inputs": {"sourceHwpx": {"type": "binary"}, "templateId": {"type": "string"}},
    "outputs": {"hwpx": {"type": "binary"}, "template": {"type": "object"}},
    "permissions": [
        {"scope": "document.read", "reason": "현재 HWPX 본문 읽기", "required": True},
        {"scope": "document.write", "reason": "양식이 적용된 HWPX revision 생성", "required": True},
    ],
}


TEMPLATE = {
    "id": "mois.internal-report.v1",
    "name": "행정안전부 내부보고형",
    "owner": "AIWorks 체험 등록",
    "officialSourceConnected": False,
    "outputFormat": "hwpx",
    "contentPolicy": "preserve-text",
    "notice": "공식 행정안전부 배포 서식 원본이 연결되면 해당 원본과 필드 계약으로 교체됩니다.",
}


HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"


def catalog() -> list[dict]:
    return [dict(TEMPLATE)]


def _paragraph_texts(source_hwpx: bytes) -> list[str]:
    if not source_hwpx.startswith(b"PK"):
        raise ValueError("양식 MCP는 유효한 HWPX ZIP 문서만 처리합니다.")
    texts: list[str] = []
    with zipfile.ZipFile(io.BytesIO(source_hwpx)) as archive:
        section_names = sorted(
            name
            for name in archive.namelist()
            if re.fullmatch(r"Contents/section\d+\.xml", name)
        )
        if not section_names:
            raise ValueError("HWPX 본문 section을 찾을 수 없습니다.")
        for section_name in section_names:
            root = ElementTree.fromstring(archive.read(section_name))
            for paragraph in root.findall(f"./{{{HP_NS}}}p"):
                value = "".join(
                    node.text or ""
                    for node in paragraph.iter(f"{{{HP_NS}}}t")
                ).strip()
                if value:
                    texts.append(value)
    return texts


def extract(source_hwpx: bytes, filename: str = "document.hwpx") -> dict:
    texts = _paragraph_texts(source_hwpx)
    filtered = [
        text
        for text in texts
        if not text.startswith("행정안전부 업무보고 |")
        and not text.startswith("작성일:")
        and not text.startswith("※ AIWorks 체험 양식")
    ]
    if not filtered:
        raise ValueError("양식을 적용할 HWPX 본문 문구가 없습니다.")
    title = filtered[0][:200]
    body_lines: list[str] = []
    for text in filtered[1:300]:
        if re.match(r"^(?:\d+[.)]|[ⅠⅡⅢⅣⅤ]+[.)])\s*", text) or text.startswith("□ "):
            body_lines.append("## " + text.removeprefix("□ ").strip())
        else:
            body_lines.append(text)
    return {
        "title": title,
        "content": "\n".join(body_lines),
        "sourceFilename": Path(filename).name,
        "paragraphCount": len(filtered),
        "template": dict(TEMPLATE),
    }


def apply(source_hwpx: bytes, filename: str, renderer) -> tuple[bytes, dict]:
    prepared = extract(source_hwpx, filename)
    artifact = renderer(
        prepared["title"],
        prepared["content"],
        profile="mois-internal",
    )
    metadata = {
        "template": prepared["template"],
        "sourceFilename": prepared["sourceFilename"],
        "sourceParagraphCount": prepared["paragraphCount"],
        "preservedTitle": prepared["title"],
    }
    return artifact, metadata
