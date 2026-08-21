"""Build editable HWPX report artifacts for the self-hosted RHWP editor."""

from __future__ import annotations

import html
import io
import re
import zipfile
from datetime import date
from pathlib import Path


MANIFEST = {
    "id": "document.report-hwpx",
    "name": "보고서 HWPX 산출 MCP",
    "version": "0.1.0",
    "runtime": "local",
    "description": "보고서 MCP의 Markdown 결과를 RHWP에서 편집 가능한 HWPX 산출물로 패키징합니다.",
    "inputs": {"title": {"type": "string"}, "content": {"type": "string"}},
    "outputs": {"hwpx": {"type": "binary"}},
    "permissions": [{"scope": "document.write", "reason": "새 HWPX 산출물 생성", "required": True}],
}


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = ROOT / "web" / "rhwp" / "samples" / "form-002.hwpx"


def _safe_text(value: str) -> str:
    value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(value or ""))
    return html.escape(value, quote=False)


def _report_lines(title: str, content: str) -> list[tuple[str, str]]:
    lines: list[tuple[str, str]] = [("title", title.strip() or "AIWorks 파생 보고서")]
    for raw in str(content or "").replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        if not line or line.startswith("# "):
            continue
        if line.startswith("## "):
            lines.append(("heading", line[3:].strip()))
        elif line.startswith("### "):
            lines.append(("heading", line[4:].strip()))
        elif re.match(r"^[-*]\s+", line):
            # The paragraph style owns the visual marker. Keeping a marker in
            # text produces duplicates such as "- · 100임." after templates.
            lines.append(("bullet", re.sub(r"^(?:(?:[-*+•·○ㅇ□▪◦])\s*)+", "", line).strip()))
        else:
            lines.append(("body", re.sub(r"\*\*(.*?)\*\*", r"\1", line)))
    return [(kind, text[:20_000]) for kind, text in lines[:300] if text]


def _inject_title_style(header: str) -> str:
    if '<hh:charPr id="89"' in header:
        return header
    source = re.search(r'<hh:charPr id="10".*?</hh:charPr>', header, re.DOTALL)
    count = re.search(r'(<hh:charProperties itemCnt=")(\d+)(">)', header)
    if not source or not count:
        raise ValueError("RHWP HWPX 기반 템플릿의 글자 스타일 정의가 올바르지 않습니다.")
    title_style = source.group(0).replace('id="10"', 'id="89"', 1).replace('height="1200"', 'height="2200"', 1)
    header = header.replace("</hh:charProperties>", title_style + "</hh:charProperties>", 1)
    item_count = int(count.group(2)) + 1
    return header[: count.start()] + count.group(1) + str(item_count) + count.group(3) + header[count.end() :]


def _profile_lines(title: str, content: str, profile: str) -> list[tuple[str, str]]:
    source_lines = _report_lines(title, content)
    if profile != "mois-internal":
        return source_lines
    today = date.today()
    body = source_lines[1:] if source_lines and source_lines[0][0] == "title" else source_lines
    normalized: list[tuple[str, str]] = []
    for kind, text in body:
        if kind == "body" and not text.startswith(("○", "ㅇ", "-", "※")):
            normalized.append(("body", "○ " + text))
        elif kind == "bullet":
            normalized.append(("bullet", text))
        else:
            normalized.append((kind, text))
    return [
        ("label", "행정안전부 업무보고 | 내부검토"),
        ("blank", ""),
        ("title", title.strip() or "업무 검토보고"),
        ("meta", f"작성일: {today.year}. {today.month}. {today.day}.  |  담당부서: 확인 필요"),
        ("blank", ""),
        *normalized,
        ("blank", ""),
        ("note", "※ AIWorks 체험 양식 적용본이며, 공식 배포 서식 원본 연결 시 해당 필드·스타일 계약으로 교체됩니다."),
    ]


def build(title: str, content: str, profile: str = "standard") -> bytes:
    if not TEMPLATE_PATH.is_file():
        raise FileNotFoundError("RHWP HWPX 기반 템플릿을 찾을 수 없습니다.")
    with zipfile.ZipFile(TEMPLATE_PATH) as source:
        section = source.read("Contents/section0.xml").decode("utf-8")
        root_open = section[: section.index("<hp:p")]
        sec_pr = re.search(r"<hp:secPr\b.*?</hp:secPr>", section, re.DOTALL)
        col_pr = re.search(r"<hp:ctrl><hp:colPr\b.*?</hp:ctrl>", section, re.DOTALL)
        page_num = re.search(r"<hp:ctrl><hp:pageNum\b.*?</hp:ctrl>", section, re.DOTALL)
        if not sec_pr or not col_pr:
            raise ValueError("RHWP HWPX 기반 템플릿의 구역 설정이 올바르지 않습니다.")

        header = source.read("Contents/header.xml").decode("utf-8")
        if profile == "mois-internal":
            header = _inject_title_style(header)

        paragraphs = [
            '<hp:p id="4100000000" paraPrIDRef="21" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
            '<hp:run charPrIDRef="9">'
            + sec_pr.group(0)
            + col_pr.group(0)
            + "</hp:run>"
            + ('<hp:run charPrIDRef="9">' + page_num.group(0) + "</hp:run>" if page_num else "")
            + "</hp:p>"
        ]
        profile_lines = _profile_lines(title, content, profile)
        for index, (kind, text) in enumerate(profile_lines, start=1):
            char_pr = {
                "label": "10",
                "title": "89" if profile == "mois-internal" else "10",
                "meta": "9",
                "heading": "10",
                "body": "28" if profile == "mois-internal" else "9",
                "bullet": "36" if profile == "mois-internal" else "9",
                "note": "36",
                "blank": "9",
            }.get(kind, "9")
            para_pr = {
                "label": "23",
                "title": "23" if profile == "mois-internal" else "21",
                "meta": "23",
                "heading": "64",
                "body": "21",
                "bullet": "59",
                "note": "21",
                "blank": "21",
            }.get(kind, "21")
            text_node = f"<hp:t>{_safe_text(text)}</hp:t>" if text else ""
            paragraphs.append(
                f'<hp:p id="{4100000000 + index}" paraPrIDRef="{para_pr}" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
                f'<hp:run charPrIDRef="{char_pr}">{text_node}</hp:run></hp:p>'
            )
        report_section = (root_open + "".join(paragraphs) + "</hs:sec>").encode("utf-8")
        preview = "\n".join(text for _, text in profile_lines if text).encode("utf-8")

        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as target:
            for info in source.infolist():
                data = source.read(info.filename)
                if info.filename == "Contents/section0.xml":
                    data = report_section
                elif info.filename == "Contents/header.xml":
                    data = header.encode("utf-8")
                elif info.filename == "Preview/PrvText.txt":
                    data = preview
                target.writestr(info, data)
        return output.getvalue()
