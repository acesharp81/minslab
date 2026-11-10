from __future__ import annotations

import json
from dataclasses import replace

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import Base
from app.models import ActionItem, AnalysisRun, Attachment, Notice
from app.services.analyzer import CURRENT_CRITERIA_VERSION
from app.services.attachment_retention import purge_attachments_by_policy


def test_retention_purges_non_ai_and_ineligible_but_keeps_operational_records(tmp_path):
    raw_dir = tmp_path / "raw"
    parsed_dir = tmp_path / "parsed"
    raw_dir.mkdir()
    parsed_dir.mkdir()
    settings = replace(
        get_settings(), data_dir=tmp_path, raw_dir=raw_dir, parsed_dir=parsed_dir,
    )
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    shared_raw = raw_dir / "shared.pdf"
    shared_raw.write_bytes(b"shared")
    paths: dict[str, tuple] = {}

    def add_notice(db: Session, index: int, code: str, *, action_status: str = "") -> None:
        raw = shared_raw if index in {1, 6} else raw_dir / f"{index}.pdf"
        if raw != shared_raw:
            raw.write_bytes(str(index).encode())
        parsed = parsed_dir / f"{index}.txt"
        parsed.write_text(f"parsed {index}", encoding="utf-8")
        notice = Notice(
            stage="prenotice", notice_no=f"RET-{index}", title=f"보존정책 {index}",
        )
        notice.analysis_runs.append(AnalysisRun(
            run_type="deep_ai", model_name="test", input_hash=f"{index:064d}"[-64:],
            status="success", result_json=json.dumps({
                "criteria_version": CURRENT_CRITERIA_VERSION,
                "classification_code": code,
            }),
        ))
        notice.attachments.append(Attachment(
            original_filename=f"{index}.pdf", source_url=f"https://example.com/{index}",
            file_path=str(raw), text_path=str(parsed), text_excerpt=f"excerpt {index}",
            download_status="downloaded", parse_status="parsed",
        ))
        if action_status:
            notice.action = ActionItem(status=action_status)
        db.add(notice)
        paths[str(index)] = (raw, parsed)

    with Session(engine) as db:
        for code in ("1", "2", "3", "4", "5", "6"):
            add_notice(db, int(code), code)
        add_notice(db, 7, "5", action_status="completed_uses")
        db.commit()

        stats = purge_attachments_by_policy(db, settings=settings)
        attachments = {
            row.notice.notice_no: row
            for row in db.scalars(select(Attachment)).all()
        }

    assert stats["attachments_purged"] == 2
    assert stats["shared_files_preserved"] == 1
    assert shared_raw.is_file()
    assert not paths["5"][0].exists() and not paths["5"][1].exists()
    assert not paths["6"][1].exists()
    for index in (1, 2, 3, 4, 7):
        assert paths[str(index)][0].is_file()
        assert paths[str(index)][1].is_file()
        assert attachments[f"RET-{index}"].text_excerpt
    for index in (5, 6):
        attachment = attachments[f"RET-{index}"]
        assert attachment.file_path is None
        assert attachment.text_path is None
        assert attachment.text_excerpt is None
        assert attachment.parse_status == "purged"


def test_retention_dry_run_does_not_change_files_or_rows(tmp_path):
    raw_dir = tmp_path / "raw"
    parsed_dir = tmp_path / "parsed"
    raw_dir.mkdir()
    parsed_dir.mkdir()
    raw = raw_dir / "non-ai.pdf"
    parsed = parsed_dir / "non-ai.txt"
    raw.write_bytes(b"raw")
    parsed.write_text("text", encoding="utf-8")
    settings = replace(
        get_settings(), data_dir=tmp_path, raw_dir=raw_dir, parsed_dir=parsed_dir,
    )
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        notice = Notice(stage="prenotice", notice_no="DRY-6", title="비AI")
        notice.analysis_runs.append(AnalysisRun(
            run_type="deep_ai", model_name="test", input_hash="6" * 64,
            status="success", result_json=json.dumps({
                "criteria_version": CURRENT_CRITERIA_VERSION,
                "classification_code": "6",
            }),
        ))
        notice.attachments.append(Attachment(
            original_filename="non-ai.pdf", source_url="https://example.com/dry",
            file_path=str(raw), text_path=str(parsed), text_excerpt="text",
            download_status="downloaded", parse_status="parsed",
        ))
        db.add(notice)
        db.commit()

        stats = purge_attachments_by_policy(db, settings=settings, dry_run=True)
        attachment = db.scalar(select(Attachment))

    assert stats["attachments_purged"] == 1
    assert raw.is_file() and parsed.is_file()
    assert attachment.file_path == str(raw)
    assert attachment.text_excerpt == "text"
