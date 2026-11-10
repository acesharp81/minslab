import io
import zipfile
from pathlib import Path

from openpyxl import Workbook
from pypdf import PdfWriter
import pytest

from app.engine import annotate_items, empty_field, rules_discover
from app.parsers import InputError, parse, unpack_upload


def test_scan_only_pdf_is_not_success(tmp_path):
    pdf = PdfWriter()
    pdf.add_blank_page(width=200, height=200)
    target = tmp_path / "hash-name"
    with target.open("wb") as f:
        pdf.write(f)
    status, warnings, blocks = parse(target, ".pdf")
    assert status == "FAILED" and not blocks
    assert any("OCR" in w for w in warnings)


def test_xlsx_formula_empty_cells_and_date_coordinates(tmp_path):
    from datetime import datetime
    wb = Workbook()
    ws = wb.active
    ws.title = "업무표"
    ws.append(["업무: 검토 업무", None, "담당: 담당팀"])
    ws.append([datetime(2026, 12, 4), "=1+1"])
    target = tmp_path / "hash-name"
    wb.save(target)
    status, warnings, blocks = parse(target, ".xlsx")
    assert status == "PARTIAL" and any("수식" in w for w in warnings)
    assert any("A2: 2026-12-04" in b["text"] and "업무표!A2:C2" in b["location"] for b in blocks)
    assert any("저장값 없음" in b["text"] for b in blocks)


def test_archive_compression_bomb_and_duplicate_path():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("bomb.txt", b"0" * 1000000)
    with pytest.raises(InputError):
        unpack_upload("data.zip", buf.getvalue())


def test_status_and_date_are_not_overpromoted():
    fields = {key: empty_field() for key in ["title", "due_date", "status"]}
    fields["title"]["value"] = "안전 점검"
    fields["due_date"]["value"] = "11월 말"
    fields["status"]["value"] = "사전 점검 완료"
    item = annotate_items([{"fields": fields}])[0]
    assert item["business_status"] == "UNKNOWN"
    assert item["fields"]["due_date"]["precision"] == "MONTH"
    assert item["fields"]["due_date"]["normalized_date"] is None
    blocks = [{"id": "b", "doc_id": "d", "parse_id": "p", "text": "업무: 점검\n협의: 예산팀\n기한: 11월 말"}]
    result = rules_discover({"id": "d"}, blocks)
    assert result["candidates"][0]["fields"]["owner"]["value"] == ""


def test_pdf_outline_preserves_wrapped_field_and_line_locations():
    from app.parsers import pdf_outline_blocks
    text='보고서 제목\n□ 예산\n○ (예산 현황) 편성액: 100원 | 잔액:\n60원\n○ (추후 계획) 보완 요청 후\n승인\n- 상세 사항\n일반 본문'
    result=list(pdf_outline_blocks(text))
    assert result[2]==(3,4,'○ (예산 현황) 편성액: 100원 | 잔액:\n60원')
    assert result[3]==(5,6,'○ (추후 계획) 보완 요청 후\n승인')
    assert result[4]==(7,7,'- 상세 사항')
    assert list(pdf_outline_blocks(''))==[]
