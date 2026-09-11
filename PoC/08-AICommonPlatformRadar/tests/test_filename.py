import pytest

from app.services.filename import build_stored_filename, extension_from_name, safe_original_name, sha256_bytes, slugify


@pytest.mark.parametrize(("source", "expected"), [
    ("생성형 AI 챗봇", "생성형-ai-챗봇"),
    ("  A (B) / C  ", "a-b-c"),
    ("../../evil.pdf", "evil-pdf"),
    ("***", "unknown"),
])
def test_slugify(source, expected):
    assert slugify(source) == expected


@pytest.mark.parametrize(("name", "expected"), [
    ("../제안요청서.PDF", "pdf"), ("a.docx", "docx"), ("x.exe", ""), ("script.py", ""),
])
def test_extension_allowlist(name, expected):
    assert extension_from_name(name) == expected


def test_safe_original_name_removes_path():
    assert safe_original_name("../../secret/제안서.pdf") == "제안서.pdf"


def test_sha256_is_stable():
    assert sha256_bytes(b"same") == sha256_bytes(b"same")
    assert len(sha256_bytes(b"same")) == 64


def test_standard_filename():
    result = build_stored_filename(
        source="g2b", stage="prenotice", notice_no="2026-001", agency="행정안전부",
        posted_yyyymmdd="20260911", title="AI 챗봇 플랫폼", sequence=1,
        sha256="a1b2c3d4" + "0" * 56, extension="pdf",
    )
    assert result == "g2b_prenotice_2026-001_행정안전부_20260911_ai-챗봇-플랫폼_01_a1b2c3d4.pdf"


def test_standard_filename_rejects_executable():
    with pytest.raises(ValueError):
        build_stored_filename(source="g2b", stage="bid", notice_no="1", agency="a", posted_yyyymmdd="20260101", title="t", sequence=1, sha256="a" * 64, extension="exe")

