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
    "description": "ReportDocument 의미 블록을 표와 목록 구조를 보존한 RHWP 편집용 HWPX로 렌더링합니다.",
    "mcpType": "tool",
    "capabilities": ["document.hwpx.render"],
    "inputs": {"reportDocument": {"type": "object"}, "rendererProfile": {"type": "string"}},
    "outputs": {"hwpx": {"type": "binary"}, "renderMetadata": {"type": "object"}},
    "permissions": [{"scope": "document.write", "reason": "새 HWPX 산출물 생성", "required": True}],
    "supports": [".md", ".hwpx", "ReportDocument@1.0"],
    "dependencies": ["document.report-structure@0.1.0"],
    "visibility": "organization",
    "sourceIncluded": True,
    "executionAdapter": {"kind": "code", "version": "1.0", "entrypoint": "mcp.report_hwpx.build_document", "arbitraryCode": False},
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


def _profile_blocks(document: dict, profile: str) -> list[dict]:
    """Preserve ReportDocument semantics until the HWPX renderer boundary."""
    title = str(document.get("title") or "AIWorks 파생 보고서").strip()
    blocks = [dict(block) for block in (document.get("blocks") or []) if isinstance(block, dict)]
    if profile != "mois-internal":
        return [{"type": "title", "text": title}, *blocks]
    today = date.today()
    normalized_blocks = []
    for block in blocks:
        if block.get("type") == "paragraph" and not str(block.get("text") or "").startswith(("○", "ㅇ", "-", "※")):
            block["text"] = "○ " + str(block.get("text") or "")
        normalized_blocks.append(block)
    return [
        {"type": "label", "text": "행정안전부 업무보고 | 내부검토"},
        {"type": "blank", "text": ""},
        {"type": "title", "text": title},
        {"type": "meta", "text": f"작성일: {today.year}. {today.month}. {today.day}.  |  담당부서: 확인 필요"},
        {"type": "blank", "text": ""},
        *normalized_blocks,
        {"type": "blank", "text": ""},
        {"type": "note", "text": "AIWorks 체험 양식 적용본이며, 공식 배포 서식 원본 연결 시 해당 필드·스타일 계약으로 교체됩니다."},
    ]


def _paragraph_xml(paragraph_id: int, kind: str, text: str, profile: str, level: int = 1) -> str:
    char_pr = {
        "label": "10", "title": "89" if profile == "mois-internal" else "10", "meta": "9",
        "heading": "10", "paragraph": "28" if profile == "mois-internal" else "9",
        "list_item": "36" if profile == "mois-internal" else "9", "note": "36", "blank": "9",
    }.get(kind, "9")
    list_para = {1: "59", 2: "60", 3: "61", 4: "62"}.get(max(1, min(4, int(level or 1))), "59")
    para_pr = {
        "label": "23", "title": "23" if profile == "mois-internal" else "21", "meta": "23",
        "heading": "64", "paragraph": "21", "list_item": list_para, "note": "21", "blank": "21",
    }.get(kind, "21")
    text_node = f"<hp:t>{_safe_text(text)}</hp:t>" if text else ""
    return (f'<hp:p id="{paragraph_id}" paraPrIDRef="{para_pr}" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
            f'<hp:run charPrIDRef="{char_pr}">{text_node}</hp:run></hp:p>')


def _table_xml(paragraph_id: int, table_id: int, rows: list[list[str]]) -> str:
    normalized = [[str(cell or "")[:20_000] for cell in row] for row in rows if isinstance(row, list)]
    if not normalized:
        return ""
    column_count = max(len(row) for row in normalized)
    normalized = [row + [""] * (column_count - len(row)) for row in normalized]
    table_width, row_height = 47_673, 2_800
    cell_width = max(1, table_width // column_count)
    table_rows = []
    for row_index, row in enumerate(normalized):
        cells = []
        for column_index, value in enumerate(row):
            border, char_pr = ("6", "10") if row_index == 0 else ("4", "9")
            cells.append(
                f'<hp:tc name="" header="{1 if row_index == 0 else 0}" hasMargin="0" protect="0" editable="1" dirty="0" borderFillIDRef="{border}">'
                '<hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="CENTER" linkListIDRef="0" linkListNextIDRef="0" textWidth="0" textHeight="0" hasTextRef="0" hasNumRef="0">'
                f'<hp:p id="{paragraph_id + row_index * column_count + column_index + 1}" paraPrIDRef="23" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
                f'<hp:run charPrIDRef="{char_pr}"><hp:t>{_safe_text(value)}</hp:t></hp:run></hp:p></hp:subList>'
                f'<hp:cellAddr colAddr="{column_index}" rowAddr="{row_index}"/><hp:cellSpan colSpan="1" rowSpan="1"/>'
                f'<hp:cellSz width="{cell_width}" height="{row_height}"/><hp:cellMargin left="141" right="141" top="141" bottom="141"/></hp:tc>')
        table_rows.append("<hp:tr>" + "".join(cells) + "</hp:tr>")
    table = (f'<hp:tbl id="{table_id}" zOrder="0" numberingType="TABLE" textWrap="TOP_AND_BOTTOM" textFlow="BOTH_SIDES" lock="0" '
             f'dropcapstyle="None" pageBreak="CELL" repeatHeader="1" rowCnt="{len(normalized)}" colCnt="{column_count}" cellSpacing="0" borderFillIDRef="4" noAdjust="1">'
             f'<hp:sz width="{table_width}" widthRelTo="ABSOLUTE" height="{row_height * len(normalized)}" heightRelTo="ABSOLUTE" protect="0"/>'
             '<hp:pos treatAsChar="1" affectLSpacing="0" flowWithText="1" allowOverlap="0" holdAnchorAndSO="0" vertRelTo="PARA" horzRelTo="PARA" vertAlign="TOP" horzAlign="LEFT" vertOffset="0" horzOffset="0"/>'
             '<hp:outMargin left="0" right="0" top="283" bottom="283"/><hp:inMargin left="141" right="141" top="141" bottom="141"/>'
             + "".join(table_rows) + "</hp:tbl>")
    return (f'<hp:p id="{paragraph_id}" paraPrIDRef="21" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
            f'<hp:run charPrIDRef="9">{table}</hp:run></hp:p>')


def build(title: str, content: str, profile: str = "standard") -> bytes:
    # Compatibility entrypoint for existing callers and builder previews.
    kind_map = {"body": "paragraph", "bullet": "list_item"}
    lines = _report_lines(title, content)
    blocks = [
        {"type": kind_map.get(kind, kind), "text": text, **({"level": 1} if kind == "bullet" else {})}
        for kind, text in lines
        if kind != "title"
    ]
    return build_document({"contractVersion": "1.0", "title": title, "blocks": blocks}, profile)


def build_document(document: dict, profile: str = "standard") -> bytes:
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
        profile_blocks = _profile_blocks(document, profile)
        paragraph_id, table_id = 4_100_000_001, 2_120_000_000
        for block in profile_blocks:
            kind = str(block.get("type") or "paragraph")
            if kind == "table":
                paragraphs.append(_table_xml(paragraph_id, table_id, block.get("rows") or []))
                table_id += 1
                paragraph_id += 1 + sum(len(row) for row in (block.get("rows") or []) if isinstance(row, list))
                continue
            paragraphs.append(_paragraph_xml(paragraph_id, kind, str(block.get("text") or "")[:20_000], profile, int(block.get("level") or 1)))
            paragraph_id += 1
        report_section = (root_open + "".join(paragraphs) + "</hs:sec>").encode("utf-8")
        preview_lines = []
        for block in profile_blocks:
            if block.get("type") == "table":
                preview_lines.extend(" | ".join(str(cell or "") for cell in row) for row in (block.get("rows") or []))
            elif block.get("text"):
                preview_lines.append(str(block["text"]))
        preview = "\n".join(preview_lines).encode("utf-8")

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
