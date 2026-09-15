from __future__ import annotations

import io
import zipfile
from dataclasses import replace
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import Base
from app.models import Attachment
from app.services import collector
from app.services.attachment_policy import (
    business_document_key,
    is_business_document,
    select_preferred_documents,
)
from app.services.collector import _store_attachment, _upsert_notice, parse_preferred_attachments
from app.services.downloader import DownloadResult
from app.services.filename import sha256_bytes
from app.services.g2b_client import G2BAttachment, G2BNotice


@pytest.fixture
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session


@pytest.mark.parametrize("filename", [
    "제안요청서.pdf",
    "과업지시서.hwpx",
    "사업 설명서.docx",
    "과업내용서.hwp",
    "요구사항명세서.pdf",
    "RFP_digital_platform.docx",
    "Terms of Reference.pdf",
])
def test_business_document_allowlist(filename):
    assert is_business_document(filename)


@pytest.mark.parametrize("filename", [
    "입찰공고서.pdf",
    "설계내역서.xlsx",
    "긴급입찰 공고 사유서.hwpx",
    "계약정보요약서.pdf",
    "가격제안서.hwp",
    "제품사용설명서.pdf",
    "Announcement.docx",
    "제안요청서 첨부_증명표장출원 지정상품목록.xlsx",
])
def test_non_business_documents_are_excluded(filename):
    assert not is_business_document(filename)


def test_same_title_uses_best_supported_parser_format():
    rows = [
        G2BAttachment("1. 제안요청서.hwp", "https://example.com/rfp.hwp"),
        G2BAttachment("2. 제안요청서.pdf;", "https://example.com/rfp.pdf"),
        G2BAttachment("3. 제안요청서.hwpx", "https://example.com/rfp.hwpx"),
        G2BAttachment("입찰공고서.pdf", "https://example.com/notice.pdf"),
        G2BAttachment("과업지시서.pdf", "https://example.com/task.pdf"),
    ]

    selected = select_preferred_documents(rows, name=lambda row: row.name)

    assert [row.name for row in selected] == ["3. 제안요청서.hwpx", "과업지시서.pdf"]
    assert business_document_key("1. 제안요청서.hwp") == business_document_key("3. 제안요청서.hwpx")


def test_opaque_g2b_names_are_kept_until_response_reveals_filename():
    rows = [
        G2BAttachment("downloadFile.do", "https://example.com/1"),
        G2BAttachment("attachment", "https://example.com/2"),
    ]
    assert select_preferred_documents(rows, name=lambda row: row.name) == rows


def _notice() -> G2BNotice:
    return G2BNotice(
        stage="prenotice",
        notice_no="POLICY-1",
        bid_no=None,
        agency_name="테스트기관",
        agency_code=None,
        title="AI 사업",
        budget_amount=100_000_000,
        posted_at=datetime.now(timezone.utc),
        deadline_at=None,
        url=None,
        raw={},
    )


def _hwpx(text: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "Contents/section0.xml",
            f'<hp:p xmlns:hp="urn:test"><hp:t>{text}</hp:t></hp:p>',
        )
    return buffer.getvalue()


def test_only_preferred_duplicate_is_sent_to_parser(tmp_path, db, monkeypatch):
    settings = replace(
        get_settings(), project_root=tmp_path, data_dir=tmp_path / "data", raw_dir=tmp_path / "data/raw",
        parsed_dir=tmp_path / "data/parsed", reports_dir=tmp_path / "data/reports", logs_dir=tmp_path / "data/logs",
    )
    settings.ensure_directories()
    monkeypatch.setattr(collector, "get_settings", lambda: settings)
    notice_data = _notice()
    notice, _ = _upsert_notice(db, notice_data)
    contents = {
        "hwp": b"binary-hwp",
        "pdf": b"not-a-real-pdf",
        "hwpx": _hwpx("생성형 AI 공통기반 활용"),
    }

    def fake_download(url):
        ext = url.rsplit(".", 1)[-1]
        content = contents[ext]
        return DownloadResult(
            "downloaded", content, f"제안요청서.{ext}", ext, sha256_bytes(content)
        )

    monkeypatch.setattr(collector, "download_attachment", fake_download)
    parser_calls = []
    original_parse = collector.parse_bytes

    def tracked_parse(content, extension):
        parser_calls.append(extension)
        return original_parse(content, extension)

    monkeypatch.setattr(collector, "parse_bytes", tracked_parse)
    for sequence, ext in enumerate(("hwp", "pdf", "hwpx"), start=1):
        _store_attachment(
            db, notice, notice_data, sequence, f"https://example.com/rfp.{ext}", f"제안요청서.{ext}"
        )
    db.flush()

    parse_preferred_attachments(db, notice)
    rows = db.scalars(select(Attachment).order_by(Attachment.id)).all()

    assert parser_calls == ["hwpx"]
    assert [row.parse_status for row in rows] == ["skipped_duplicate", "skipped_duplicate", "parsed"]
    assert rows[-1].text_excerpt == "생성형 AI 공통기반 활용"


def test_hidden_irrelevant_filename_is_not_stored_or_parsed(tmp_path, db, monkeypatch):
    settings = replace(
        get_settings(), project_root=tmp_path, data_dir=tmp_path / "data", raw_dir=tmp_path / "data/raw",
        parsed_dir=tmp_path / "data/parsed", reports_dir=tmp_path / "data/reports", logs_dir=tmp_path / "data/logs",
    )
    settings.ensure_directories()
    monkeypatch.setattr(collector, "get_settings", lambda: settings)
    monkeypatch.setattr(
        collector,
        "download_attachment",
        lambda _url: DownloadResult(
            "downloaded", b"notice", "입찰공고서.pdf", "pdf", sha256_bytes(b"notice")
        ),
    )
    notice_data = _notice()
    notice, _ = _upsert_notice(db, notice_data)

    result = _store_attachment(
        db, notice, notice_data, 1, "https://example.com/downloadFile.do", "downloadFile.do"
    )
    db.flush()
    attachment = db.scalar(select(Attachment))

    assert result == "skipped"
    assert attachment.parse_status == "skipped"
    assert attachment.file_path is None
    assert list(settings.raw_dir.iterdir()) == []


def test_known_irrelevant_unsupported_format_is_reclassified_as_skipped(db):
    notice, _ = _upsert_notice(db, _notice())
    db.add(Attachment(
        notice_id=notice.id,
        source_url="https://example.com/cost.xlsx",
        original_filename="설계내역서.xlsx",
        download_status="unsupported",
        parse_status="unsupported",
    ))
    db.flush()

    statuses = parse_preferred_attachments(db, notice)

    assert statuses["https://example.com/cost.xlsx"] == "skipped"
