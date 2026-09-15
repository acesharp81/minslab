import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import AnalysisRun, Attachment, Notice
from app.routers.notices import _query, analysis_view
from app.services.collector import _needs_backlog_analysis


def _params(**overrides):
    values = {
        "stage": None, "agency": None, "grade": None, "action_status": None,
        "keyword": None, "date_from": None, "date_to": None,
        "analysis_status": None, "ai_relevance": None, "deadline_status": None,
        "recommended_action": None, "parse_status": None, "sort": None,
    }
    values.update(overrides)
    return values


def test_parse_issue_filter_combines_with_deadline_filter():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime.now(timezone.utc)
    with Session(engine) as db:
        open_failed = Notice(stage="bid", notice_no="1", agency_name="기관", title="열린 오류",
                             deadline_at=now + timedelta(days=2))
        open_failed.attachments.append(Attachment(
            original_filename="제안요청서.pdf", source_url="sample://1",
            download_status="downloaded", parse_status="failed",
        ))
        open_ok = Notice(stage="bid", notice_no="2", agency_name="기관", title="열린 정상",
                         deadline_at=now + timedelta(days=2))
        open_ok.attachments.append(Attachment(
            original_filename="제안요청서.pdf", source_url="sample://2",
            download_status="downloaded", parse_status="parsed",
        ))
        closed_failed = Notice(stage="bid", notice_no="3", agency_name="기관", title="닫힌 오류",
                               deadline_at=now - timedelta(days=2))
        closed_failed.attachments.append(Attachment(
            original_filename="과업지시서.hwp", source_url="sample://3",
            download_status="failed", parse_status="pending",
        ))
        db.add_all([open_failed, open_ok, closed_failed])
        db.commit()

        rows = db.scalars(_query(**_params(deadline_status="open", parse_status="issue"))).all()

    assert [row.title for row in rows] == ["열린 오류"]


def test_legacy_deep_result_is_marked_for_criteria_refresh():
    notice = Notice(stage="bid", notice_no="legacy", agency_name="기관", title="AI 사업")
    notice.analysis_runs.append(AnalysisRun(
        run_type="deep_ai", model_name="old-model", input_hash="o" * 64,
        status="success", result_json='{"final_grade":"A"}',
    ))
    assert analysis_view(notice)["key"] == "criteria_outdated"
    assert _needs_backlog_analysis(notice) is True

    notice.analysis_runs.append(AnalysisRun(
        run_type="deep_ai", model_name="new-model", input_hash="n" * 64,
        status="success",
        result_json='{"criteria_version":"common-platform-v3-six-categories","classification_code":"5","final_grade":"E"}',
    ))
    assert analysis_view(notice)["key"] == "deep_completed"
    assert _needs_backlog_analysis(notice) is False


def test_legacy_rule_gate_result_is_requeued_but_current_rule_gate_is_screened_out():
    notice = Notice(stage="bid", notice_no="legacy-gate", agency_name="기관", title="일반 사업")
    notice.analysis_runs.append(AnalysisRun(
        run_type="simple_ai", model_name="simple-model", input_hash="s" * 64,
        status="success", result_json='{"needs_deep_review":false}',
    ))
    notice.analysis_runs.append(AnalysisRun(
        run_type="deep_ai", model_name="rule-gate", input_hash="g" * 64,
        status="skipped", result_json='{"reason":"legacy rule gate"}',
    ))

    assert analysis_view(notice)["key"] == "criteria_outdated"
    assert _needs_backlog_analysis(notice) is True

    notice.analysis_runs.append(AnalysisRun(
        run_type="deep_ai", model_name="rule-gate", input_hash="c" * 64,
        status="skipped",
        result_json=(
            '{"criteria_version":"common-platform-v3-six-categories",'
            '"classification_code":"6","final_grade":"F"}'
        ),
    ))

    assert analysis_view(notice)["key"] == "screened_out"
    assert _needs_backlog_analysis(notice) is False


def test_classification_code_filter():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        for code in ("2", "5"):
            notice = Notice(stage="prenotice", notice_no=f"C-{code}", agency_name="기관", title=f"분류 {code}")
            notice.analysis_runs.append(AnalysisRun(
                run_type="deep_ai", model_name="model", input_hash=code * 64, status="success",
                result_json=json.dumps({
                    "criteria_version": "common-platform-v3-six-categories",
                    "classification_code": code,
                }),
            ))
            db.add(notice)
        db.commit()
        rows = db.scalars(_query(**_params(classification_code="2"))).all()
        assert [row.notice_no for row in rows] == ["C-2"]


def test_analysis_status_filters_distinguish_legacy_and_current_rule_gates():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        legacy = Notice(stage="bid", notice_no="legacy", agency_name="기관", title="구기준 제외")
        legacy.analysis_runs.append(AnalysisRun(
            run_type="deep_ai", model_name="rule-gate", input_hash="l" * 64, status="skipped",
            result_json=json.dumps({"reason": "legacy"}),
        ))
        current = Notice(stage="bid", notice_no="current", agency_name="기관", title="비AI 사업")
        current.analysis_runs.append(AnalysisRun(
            run_type="deep_ai", model_name="rule-gate", input_hash="c" * 64, status="skipped",
            result_json=json.dumps({
                "criteria_version": "common-platform-v3-six-categories",
                "classification_code": "6",
            }),
        ))
        db.add_all([legacy, current])
        db.commit()

        outdated = db.scalars(_query(**_params(analysis_status="criteria_outdated"))).all()
        screened = db.scalars(_query(**_params(analysis_status="screened_out"))).all()

        assert [row.notice_no for row in outdated] == ["legacy"]
        assert [row.notice_no for row in screened] == ["current"]
