"""Bounded file adapters. Every retained text block has a physical source location."""
import io
import re
import stat
import zipfile
from datetime import date, datetime
from pathlib import Path, PurePosixPath

PARSER_VERSION = "source-v2-syhwp008-pdf-outline-docx12-xlsx315"
SUPPORTED = {".hwp", ".hwpx", ".pdf", ".docx", ".xlsx", ".txt", ".md"}
MAX_FILE = 20 * 1024 * 1024
MAX_TOTAL = 80 * 1024 * 1024
MAX_FILES = 100


class InputError(ValueError):
    pass


def safe_path(name):
    name = name.replace("\\", "/")
    p = PurePosixPath(name)
    if not name or p.is_absolute() or ".." in p.parts or ":" in name or any(ord(c) < 32 for c in name):
        raise InputError("안전하지 않은 파일 경로입니다.")
    if len(name) > 300:
        raise InputError("파일 경로는 300자 이내여야 합니다.")
    return str(p)


def check_zip(z, max_files=MAX_FILES):
    entries = z.infolist()
    if len(entries) > max_files:
        raise InputError(f"압축 항목 수가 제한({max_files})을 넘었습니다.")
    total = 0
    for info in entries:
        safe_path(info.filename)
        if stat.S_ISLNK(info.external_attr >> 16) or info.flag_bits & 1:
            raise InputError("심볼릭 링크·암호화 ZIP은 지원하지 않습니다.")
        total += info.file_size
        if info.file_size > MAX_FILE or total > MAX_TOTAL or info.file_size / max(info.compress_size, 1) > 250:
            raise InputError("압축 해제 용량 또는 압축률 제한을 초과했습니다.")
    return entries


def unpack_upload(name, data):
    if len(data) > MAX_TOTAL:
        raise InputError("업로드는 80MB 이하만 가능합니다.")
    if Path(name).suffix.lower() != ".zip":
        if len(data) > MAX_FILE:
            raise InputError("개별 파일은 20MB 이하만 가능합니다.")
        return [(safe_path(name), data)]
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            entries = check_zip(z)
            result = [(safe_path(i.filename), z.read(i)) for i in entries
                      if not i.is_dir() and not i.filename.startswith("__MACOSX/")]
            if len({p for p, _ in result}) != len(result):
                raise InputError("ZIP에 중복 경로가 있습니다.")
            if not result:
                raise InputError("ZIP에 처리할 파일이 없습니다.")
            return result
    except zipfile.BadZipFile as e:
        raise InputError("손상된 ZIP 파일입니다.") from e


def pdf_outline_blocks(text):
    """Keep a labelled outline paragraph together across visual line wraps.

    Original characters/newlines and page line ranges are retained. Only an
    explicit circle + parenthesized heading begins a continuation group.
    """
    pending=[];start=0
    for number,line in enumerate(text.splitlines(),1):
        labelled=bool(re.match(r'^\s*○\s*\([^)]+\)',line))
        boundary=bool(re.match(r'^\s*(?:[□○●•\-–]|\d+[.)]\s)',line))
        if pending and (boundary or not line.strip()):
            yield start,number-1,'\n'.join(pending);pending=[]
        if labelled:pending=[line];start=number
        elif pending:pending.append(line)
        elif line.strip():yield number,number,line
    if pending:yield start,number,'\n'.join(pending)


def parse(path, extension):
    warnings, blocks = [], []

    def add(text, location, kind="paragraph"):
        text = str(text).replace("\x00", "").strip()
        if text:
            for start in range(0, len(text), 6000):
                blocks.append({"text": text[start:start + 6000], "location": location + (f" · 구간 {start // 6000 + 1}" if len(text) > 6000 else ""), "kind": kind})
        if len(blocks) > 4000:
            raise InputError("문서당 4,000개 블록 제한을 초과했습니다.")

    if extension not in SUPPORTED:
        return "UNSUPPORTED", ["지원하지 않는 형식입니다. 실행·매크로 파일은 처리하지 않습니다."], []
    try:
        if extension in {".hwpx", ".docx", ".xlsx"}:
            with zipfile.ZipFile(path) as z:
                check_zip(z, 5000)
                names = z.namelist()
                expected = {".hwpx": "Contents/section", ".docx": "word/document.xml", ".xlsx": "xl/workbook.xml"}[extension]
                if not any(n.startswith(expected) for n in names):
                    raise InputError("확장자와 내부 파일 형식이 다릅니다.")
                if any("vbaproject" in n.lower() for n in names):
                    raise InputError("매크로가 포함된 문서는 지원하지 않습니다.")
        if extension in {".txt", ".md"}:
            raw = Path(path).read_bytes()
            try:
                content = raw.decode("utf-8-sig")
            except UnicodeDecodeError:
                content = raw.decode("cp949")
            for n, line in enumerate(content.splitlines(), 1):
                add(line, f"줄 {n}")
        elif extension in {".hwp", ".hwpx"}:
            import syhwp
            from syhwp.models import Image, Equation, Table
            if extension == ".hwp" and Path(path).read_bytes()[:8] != bytes.fromhex("d0cf11e0a1b11ae1"):
                raise InputError("HWP 5.x 파일 형식이 아닙니다.")
            doc = syhwp.open(path)
            for n, block in enumerate(doc.blocks, 1):
                if isinstance(block, (Image, Equation)):
                    warnings.append(f"블록 {n}: 그림·수식 내용은 의미 해석하지 않았습니다.")
                elif isinstance(block, Table):
                    for row in range(block.n_rows):
                        cells = sorted((c for c in block.cells if c.row == row), key=lambda c: c.col)
                        add(" | ".join(f"C{c.col + 1}: {c.text}" for c in cells), f"블록 {n} · 표 행 {row + 1}", "table_row")
                    if any(c.row_span > 1 or c.col_span > 1 for c in block.cells):
                        warnings.append(f"표 {n}: 병합 셀은 시작 셀에만 기록했습니다.")
                else:
                    add(block.text, f"블록 {n}")
            warnings.append("한글 문서 본문·표 추출입니다. 머리말·각주·도형 내 텍스트·시각적 배치는 완전성을 보장하지 않습니다.")
        elif extension == ".pdf":
            from pypdf import PdfReader
            if Path(path).read_bytes()[:5] != b"%PDF-":
                raise InputError("PDF 파일 형식이 아닙니다.")
            reader = PdfReader(path)
            if reader.is_encrypted:
                raise InputError("암호화 PDF는 지원하지 않습니다.")
            if len(reader.pages) > 200:
                raise InputError("PDF는 200페이지 이하만 지원합니다.")
            for n, page in enumerate(reader.pages, 1):
                text = page.extract_text() or ""
                if not text.strip():
                    warnings.append(f"{n}페이지: 추출 가능한 텍스트가 없습니다. OCR은 지원하지 않습니다.")
                for first,last,value in pdf_outline_blocks(text):
                    add(value, f"{n}페이지 · 줄 {first}"+(f"–{last}" if last!=first else ""))
                if page.images:
                    warnings.append(f"{n}페이지: 이미지의 내용은 해석하지 않았습니다.")
        elif extension == ".docx":
            from docx import Document
            from docx.table import Table
            doc = Document(path)
            for n, block in enumerate(doc.iter_inner_content(), 1):
                if isinstance(block, Table):
                    for row, cells in enumerate(block.rows, 1):
                        add(" | ".join(c.text for c in cells.cells), f"표 {n} · 행 {row}", "table_row")
                else:
                    add(block.text, f"문단 {n}")
            if doc.inline_shapes:
                warnings.append("삽입 이미지 내용은 해석하지 않았습니다.")
            warnings.append("본문·표를 추출했습니다. 머리말·꼬리말·주석·텍스트 상자는 검토 범위 밖입니다.")
        elif extension == ".xlsx":
            from openpyxl import load_workbook
            workbook_bytes = Path(path).read_bytes()
            wb = load_workbook(io.BytesIO(workbook_bytes), read_only=True, data_only=False)
            values = load_workbook(io.BytesIO(workbook_bytes), read_only=True, data_only=True)
            try:
                for sheet in wb:
                    if sheet.max_row > 10000 or sheet.max_column > 100:
                        raise InputError("시트는 10,000행·100열 이하만 지원합니다.")
                    for row_number, row in enumerate(sheet, 1):
                        cells = []
                        for cell in row:
                            value = cell.value
                            if value is None:
                                continue
                            if cell.data_type == "f":
                                cached = values[sheet.title][cell.coordinate].value
                                warnings.append(f"{sheet.title}!{cell.coordinate}: 수식은 실행하지 않으며 저장된 계산값만 참조합니다.")
                                value = f"수식 {value}; 저장값 {cached if cached is not None else '없음'}"
                            elif isinstance(value, (date, datetime)):
                                value = value.isoformat()
                            cells.append(f"{cell.coordinate}: {value}")
                        if cells:
                            from openpyxl.utils import get_column_letter
                            add(" | ".join(cells), f"{sheet.title}!A{row_number}:{get_column_letter(len(row))}{row_number}", "table_row")
            finally:
                wb.close()
                values.close()
        if not blocks:
            return "FAILED", warnings + ["추출 가능한 본문 텍스트가 없습니다."], []
        return "PARTIAL" if warnings else "SUCCESS", list(dict.fromkeys(warnings))[:100], blocks
    except Exception as exc:
        # Avoid leaking local paths or parser internals into UI.
        reason = str(exc) if isinstance(exc, InputError) else f"문서 해석 실패 ({type(exc).__name__}). 손상·암호화·지원 범위를 확인해 주세요."
        return ("PARTIAL" if blocks else "FAILED"), warnings + [reason], blocks
