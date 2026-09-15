import io
import zipfile

from app.services.parser import is_safe_zip_member, parse_bytes


def test_zip_path_traversal_is_rejected():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("../../evil.txt", "no")
    result = parse_bytes(buffer.getvalue(), "zip")
    assert result.status == "failed"
    assert "traversal" in (result.error or "")


def test_safe_zip_member_rules():
    assert is_safe_zip_member("docs/rfp.txt")
    assert not is_safe_zip_member("../rfp.txt")
    assert not is_safe_zip_member("/etc/passwd")
    assert not is_safe_zip_member("C:/evil.txt")


def test_txt_encodings():
    assert parse_bytes("생성형 AI".encode("cp949"), "txt").text == "생성형 AI"


def test_invalid_hwp_signature_fails_safely():
    result = parse_bytes(b"fake hwp", "hwp")
    assert result.status == "failed"
    assert "시그니처" in (result.error or "")


def test_binary_hwp_uses_cli(monkeypatch):
    class Completed:
        returncode = 0
        stdout = "생성형 AI 사업".encode()
        stderr = b""

    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return Completed()

    monkeypatch.setattr("app.services.parser.subprocess.run", fake_run)
    result = parse_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1payload", "hwp")
    assert result.status == "parsed"
    assert result.text == "생성형 AI 사업"
    assert captured["command"][1:4] == ["cat", "--format", "markdown"]


def test_mislabeled_hwpx_uses_hwp_cli(monkeypatch):
    class Completed:
        returncode = 0
        stdout = "실제 OLE HWP".encode()
        stderr = b""

    monkeypatch.setattr("app.services.parser.subprocess.run", lambda *_args, **_kwargs: Completed())
    result = parse_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1payload", "hwpx")
    assert result.status == "parsed"
    assert "OLE HWP" in result.text


def test_zero_byte_isolated_failure():
    assert parse_bytes(b"", "pdf").status == "failed"


def test_zip_parses_allowed_children_and_ignores_script():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("rfp.txt", "AI 챗봇 구축")
        archive.writestr("run.sh", "danger")
    result = parse_bytes(buffer.getvalue(), "zip")
    assert result.status == "parsed"
    assert "AI 챗봇" in result.text
    assert "danger" not in result.text


def test_xlsx_extracts_shared_inline_and_numeric_cells():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "xl/sharedStrings.xml",
            '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<si><t>생성형 AI</t></si></sst>',
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
            '<row><c t="s"><v>0</v></c><c t="inlineStr"><is><t>업무망</t></is></c><c><v>42</v></c></row>'
            '</sheetData></worksheet>',
        )

    result = parse_bytes(buffer.getvalue(), "xlsx")

    assert result.status == "parsed"
    assert result.text == "생성형 AI | 업무망 | 42"
