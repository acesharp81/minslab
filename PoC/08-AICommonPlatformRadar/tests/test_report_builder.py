import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import Base
from app.models import AnalysisRun, Attachment, Notice, NoticeDecision, PipelineRun
from app.services import report_builder
from app.services.report_builder import build_daily_report, get_daily_report


KST = timezone(timedelta(hours=9))


@pytest.fixture
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session


@pytest.fixture
def report_settings(tmp_path: Path, monkeypatch):
    settings = replace(
        get_settings(), project_root=tmp_path, data_dir=tmp_path / "data",
        raw_dir=tmp_path / "data/raw", parsed_dir=tmp_path / "data/parsed",
        reports_dir=tmp_path / "data/reports", logs_dir=tmp_path / "data/logs",
    )
    settings.ensure_directories()
    templates = tmp_path / "app/templates"
    templates.mkdir(parents=True)
    source = get_settings().project_root / "app/templates/daily_report_export.html"
    (templates / source.name).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(report_builder, "get_settings", lambda: settings)
    return settings


def _seed(db: Session, *, failed: int = 0):
    now = datetime.now(timezone.utc)
    run = PipelineRun(run_kind="collect", mode="mock", status="success", started_at=now,
                      finished_at=now, stats_json=json.dumps({"received": 1, "analysis_failed": failed}))
    notice = Notice(stage="prenotice", notice_no="R-1", agency_name="테스트기관", title="AI 상담 사업",
                    budget_amount=100_000_000, created_at=now, updated_at=now)
    notice.decision = NoticeDecision(final_grade="B", priority_score=88, recommended_action="contact",
                                     summary="공통기반 확인 필요", possible_functions_json='["RAG"]',
                                     key_evidence_json='[{"quote":"AI 상담"}]')
    notice.attachments.append(Attachment(original_filename="제안요청서.pdf", source_url="sample://rfp",
                                         download_status="downloaded", parse_status="parsed"))
    notice.analysis_runs.extend([
        AnalysisRun(run_type="simple_ai", model_name="test-small", input_hash="s" * 64,
                    status="success", result_json='{"needs_deep_review":true}', created_at=now),
        AnalysisRun(run_type="deep_ai", model_name="test-large", input_hash="d" * 64,
                    status="success",
                    result_json='{"criteria_version":"common-platform-v7-service-construction-scope","classification_code":"2","final_grade":"B","guidance_message":"본공고에 공통기반 활용 범위를 반영해 주시기 바랍니다."}',
                    created_at=now),
    ])
    db.add_all([run, notice])
    db.commit()


def test_rich_report_writes_html_json_and_markdown(db, report_settings):
    _seed(db)
    day = datetime.now(KST).date()
    artifact = build_daily_report(db, day, finalized=True, require_successful_batch=True)
    html = Path(artifact.html_path).read_text(encoding="utf-8")
    payload = json.loads(Path(artifact.json_path).read_text(encoding="utf-8"))
    assert artifact.status == "ready"
    assert artifact.finalized is True
    assert "우선 조치 대상" in html and "AI 상담 사업" in html
    assert "적합·미반영" in html
    assert "시스템 구성, 적용 기능 및 제안요청서 반영 방향 검토" in html
    assert "<pre>" not in html
    assert payload["batch"]["state"] == "ready"
    assert payload["summary"]["simple_review"] == 1
    assert payload["summary"]["deep_candidates"] == 1
    assert payload["summary"]["deep_review"] == 1
    assert payload["summary"]["classification_distribution"]["2"] == 1
    assert payload["processing"]["priority_contact"] == 1
    assert len(payload["recent"]) == 7
    assert payload["monthly"]["deep_verified"] == 1
    assert Path(artifact.markdown_path).name == f"{day.isoformat()}_daily_report.md"


def test_report_marks_partial_batch(db, report_settings):
    _seed(db, failed=1)
    artifact = build_daily_report(db, datetime.now(KST).date())
    assert artifact.status == "partial"
    assert artifact.data["batch"]["label"] == "일부 실패 포함"


def test_report_uses_successful_batch_when_later_attempt_failed(db, report_settings):
    _seed(db)
    now = datetime.now(timezone.utc)
    db.add(PipelineRun(run_kind="collect", mode="mock", status="failed", started_at=now,
                       finished_at=now, error_message="interrupted"))
    db.commit()
    artifact = build_daily_report(db, datetime.now(KST).date(), finalized=True, require_successful_batch=True)
    assert artifact.status == "ready"
    assert artifact.data["batch"]["stats"]["received"] == 1


def test_final_report_requires_completed_batch(db, report_settings):
    with pytest.raises(RuntimeError, match="수집 배치가 완료되지 않아"):
        build_daily_report(db, datetime.now(KST).date(), finalized=True, require_successful_batch=True)


def test_finalized_snapshot_is_not_overwritten_by_page_read(db, report_settings):
    _seed(db)
    day = datetime.now(KST).date()
    finalized = build_daily_report(db, day, finalized=True, require_successful_batch=True)
    generated_at = finalized.generated_at
    db.query(PipelineRun).delete()
    db.commit()
    loaded = get_daily_report(db, day)
    assert loaded.finalized is True
    assert loaded.generated_at == generated_at
    assert loaded.status == "ready"
