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


def test_hwp_is_safe_unsupported():
    result = parse_bytes(b"fake hwp", "hwp")
    assert result.status == "unsupported"


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

