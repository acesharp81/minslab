import json
from datetime import datetime, timedelta, timezone

from app.db import Base, get_db
from app.main import app
from app.models import AnalysisRun, Attachment, Notice
from app.routers.notices import _query, analysis_source_evidence, analysis_view
from app.services.collector import _needs_backlog_analysis
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool


def _params(**overrides):
    values = {
        "stage": None, "agency": None, "grade": None, "action_status": None,
        "keyword": None, "date_from": None, "date_to": None,
        "analysis_status": None, "ai_relevance": None, "deadline_status": None,
        "recommended_action": None, "parse_status": None, "sort": None,
    }
    values.update(overrides)
    return values


def test_source_evidence_combines_ai_basis_gate_quotes_and_missing_gate_questions():
    notice = Notice(
        stage="prenotice", notice_no="EVIDENCE-1", agency_name="행정안전부",
        title="생성형 AI 민원상담 구축",
    )
    notice.analysis_runs.append(AnalysisRun(
        run_type="simple_ai", model_name="test", input_hash="s" * 64, status="success",
        result_json=json.dumps({
            "ai_relevance": "high", "needs_deep_review": True, "reason": "AI 사업",
            "evidence": [{
                "quote": "생성형 AI 민원상담 구축", "section": "사업명",
                "interpretation": "AI 서비스를 구축하는 사업",
            }], "confidence": 0.9,
        }),
    ))
    result = {
        "classification_code": "3", "ai_relevance": "high",
        "network_scope": "unclear", "task_scope": "government", "model_fit": "unclear",
        "platform_usage": "not_mentioned",
        "task_scope_evidence": [{
            "quote": "행정안전부 소관 국가사무", "section": "과업지시서",
            "interpretation": "국가사무 근거",
        }],
        "check_questions": [],
    }

    view = analysis_source_evidence(notice, result)

    assert view["ai_evidence"][0]["quote"] == "생성형 AI 민원상담 구축"
    assert view["gate_evidence"][0]["gate"] == "국가사무"
    assert any("행정망" in question for question in view["questions"])
    assert any("LLM·RAG" in question for question in view["questions"])
    assert any("공통기반" in question for question in view["questions"])


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
        result_json='{"criteria_version":"common-platform-v8-national-task-evidence","classification_code":"5","final_grade":"E"}',
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
            '{"criteria_version":"common-platform-v8-national-task-evidence",'
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
                    "criteria_version": "common-platform-v8-national-task-evidence",
                    "classification_code": code,
                }),
            ))
            db.add(notice)
        db.commit()
        rows = db.scalars(_query(**_params(classification_code="2"))).all()
        assert [row.notice_no for row in rows] == ["C-2"]

        action_rows = db.scalars(_query(**_params(action_required=True))).all()
        assert [row.notice_no for row in action_rows] == ["C-2"]


def test_scope_out_legacy_result_is_presented_and_filtered_as_non_ai_service():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        notice = Notice(stage="bid_notice", notice_no="LEGACY-SCOPE", title="AI 감리 용역")
        notice.analysis_runs.append(AnalysisRun(
            run_type="deep_ai", model_name="model", input_hash="z" * 64, status="success",
            result_json=json.dumps({
                "criteria_version": "common-platform-v8-national-task-evidence",
                "classification_code": "5", "service_scope": "non_target",
            }),
        ))
        db.add(notice)
        db.commit()

        assert analysis_view(notice)["classification_code"] == "6"
        code_five = db.scalars(_query(**_params(classification_code="5"))).all()
        code_six = db.scalars(_query(**_params(classification_code="6"))).all()

    assert code_five == []
    assert [row.notice_no for row in code_six] == ["LEGACY-SCOPE"]


def test_classification_filter_uses_latest_result_and_rejects_later_simple_run():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        latest_wins = Notice(
            stage="prenotice", notice_no="LATEST", agency_name="기관", title="최신 분류",
        )
        latest_wins.analysis_runs.extend([
            AnalysisRun(
                run_type="deep_ai", model_name="model", input_hash="a" * 64,
                status="success", result_json=json.dumps({
                    "criteria_version": "common-platform-v8-national-task-evidence",
                    "classification_code": "2",
                }),
            ),
            AnalysisRun(
                run_type="deep_ai", model_name="model", input_hash="b" * 64,
                status="success", result_json=json.dumps({
                    "criteria_version": "common-platform-v8-national-task-evidence",
                    "classification_code": "5",
                }),
            ),
        ])
        invalidated = Notice(
            stage="prenotice", notice_no="INVALIDATED", agency_name="기관", title="재분석 대기",
        )
        invalidated.analysis_runs.extend([
            AnalysisRun(
                run_type="deep_ai", model_name="model", input_hash="c" * 64,
                status="success", result_json=json.dumps({
                    "criteria_version": "common-platform-v8-national-task-evidence",
                    "classification_code": "2",
                }),
            ),
            AnalysisRun(
                run_type="simple_ai", model_name="model", input_hash="d" * 64,
                status="success", result_json='{"needs_deep_review":true}',
            ),
        ])
        db.add_all([latest_wins, invalidated])
        db.commit()

        code_two = db.scalars(_query(**_params(classification_code="2"))).all()
        code_five = db.scalars(_query(**_params(classification_code="5"))).all()

    assert code_two == []
    assert [row.notice_no for row in code_five] == ["LATEST"]


def test_notice_page_applies_filters_before_ten_item_pagination():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        now = datetime.now(timezone.utc)
        db.add_all([
            Notice(
                stage="bid_notice", notice_no=f"PAGE-{index:02d}",
                agency_name="대상기관" if index < 12 else "제외기관",
                title=f"페이지 사업 {index:02d}",
                posted_at=now + timedelta(minutes=index),
            )
            for index in range(14)
        ])
        db.commit()

    def override_db():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            first = client.get("/notices?agency=대상기관&sort=newest")
            second = client.get("/notices?agency=대상기관&sort=newest&page=2")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert first.status_code == 200
    assert "검색 결과 <strong>12</strong>건" in first.text
    assert first.text.count("공고번호 PAGE-") == 10
    assert "페이지 사업 11" in first.text
    assert "페이지 사업 01" not in first.text
    assert second.text.count("공고번호 PAGE-") == 2
    assert "페이지 사업 01" in second.text
    assert "agency=%EB%8C%80%EC%83%81%EA%B8%B0%EA%B4%80" in second.text


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
                "criteria_version": "common-platform-v8-national-task-evidence",
                "classification_code": "6",
            }),
        ))
        db.add_all([legacy, current])
        db.commit()

        outdated = db.scalars(_query(**_params(analysis_status="criteria_outdated"))).all()
        screened = db.scalars(_query(**_params(analysis_status="screened_out"))).all()

        assert [row.notice_no for row in outdated] == ["legacy"]
        assert [row.notice_no for row in screened] == ["current"]
