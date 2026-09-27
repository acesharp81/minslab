import asyncio
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from app.config import get_settings
from app.db import Base
from app.models import ActionItem, AnalysisRun, AuditLog, Notice
from app.services.analyzer import CURRENT_CRITERIA_VERSION
from app.services.g2b_client import G2BClient
from app.services.opinion_tracker import _failure_tracking, _tracking_result, refresh_notice_opinions, refresh_tracked_opinions_cached
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def _notice() -> Notice:
    notice = Notice(
        stage="prenotice", notice_no="R26BD001", agency_name="기관", title="AI 사업",
        raw_payload_json=json.dumps({"bfSpecRgstNo": "R26BD001"}),
    )
    notice.action = ActionItem(status="contacted")
    notice.analysis_runs.append(AnalysisRun(
        id=1, run_type="deep_ai", model_name="model", input_hash="a" * 64, status="success",
        result_json=json.dumps({
            "criteria_version": CURRENT_CRITERIA_VERSION,
            "classification_code": "2",
            "guidance_message": "인공지능데이터행정법 제27조제2항에 따라 공통기반 활용을 검토하고 회신해 주시기 바랍니다.",
        }, ensure_ascii=False),
    ))
    return notice


def test_registered_opinion_without_reply_is_waiting():
    result = _tracking_result(_notice(), [{
        "opninNo": "3", "rplyNo": "0", "opninTitl": "공통기반 활용 검토",
        "opninCntnts": "인공지능데이터행정법 제27조제2항에 따라 공통기반 활용을 검토하고 회신해 주시기 바랍니다.",
        "inptDt": "20260915100000",
    }])

    assert result["status"] == "submitted_waiting"
    assert result["matched_reply_count"] == 0
    assert result["submitted_content"].startswith("인공지능데이터행정법")


def test_in_progress_action_is_tracked_after_extension_confirms_submission():
    notice = _notice()
    notice.action.status = "in_progress"

    result = _tracking_result(notice, [{
        "opninNo": "3", "rplyNo": "0", "opninTitl": "공통기반 활용 검토",
        "opninCntnts": "인공지능데이터행정법 제27조제2항에 따라 공통기반 활용을 검토하고 회신해 주시기 바랍니다.",
        "inptDt": "20260915100000",
    }])

    assert result["status"] == "submitted_waiting"


def test_reply_to_registered_opinion_is_exposed():
    root = {
        "opninNo": "3", "rplyNo": "0", "opninTitl": "공통기반 활용 검토",
        "opninCntnts": "인공지능데이터행정법 제27조제2항에 따라 공통기반 활용을 검토하고 회신해 주시기 바랍니다.",
        "inptDt": "20260915100000",
    }
    reply = {
        "opninNo": "3", "rplyNo": "1", "opninCntnts": "본공고에 반영하겠습니다.",
        "inptDt": "20260916130000",
    }

    result = _tracking_result(_notice(), [root, reply])

    assert result["status"] == "replied"
    assert result["matched_reply_count"] == 1
    assert result["latest_reply_content"] == "본공고에 반영하겠습니다."


def test_empty_opinion_list_is_not_a_matching_failure():
    notice = _notice()
    assert _tracking_result(notice, [])["status"] == "not_submitted"
    confirmed = _tracking_result(notice, [], submission={
        "recorded": True, "submitted_at": "2026-09-15T10:00:00+00:00",
        "submitted_content": "등록 당시 문안",
    })
    assert confirmed["status"] == "submitted_unverified"
    assert confirmed["status_label"] == "등록 기록 있음 · 나라장터 미확인"
    assert confirmed["opinion_count"] == 0
    assert confirmed["submitted_content"] == "등록 당시 문안"


def test_mock_mode_cannot_be_mistaken_for_an_empty_public_opinion_list():
    client = G2BClient(settings=replace(get_settings(), g2b_mode="mock"))
    with pytest.raises(RuntimeError, match="G2B_MODE=live"):
        asyncio.run(client.prenotice_opinions("R26BD001"))


def test_unrelated_public_opinion_is_not_our_unmatched_submission():
    notice = _notice()
    rows = [{"opninNo": "9", "rplyNo": "0", "opninCntnts": "납품 장소를 확인해 주세요."}]
    unrelated = _tracking_result(notice, rows)
    recorded = _tracking_result(notice, rows, submission={"recorded": True})

    assert unrelated["status"] == "not_submitted"
    assert unrelated["status_label"] == "다른 공개 의견만 확인"
    assert recorded["status"] == "unmatched"


def test_refresh_uses_submission_audit_and_keeps_local_content():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    class Client:
        async def prenotice_opinions(self, _registration_no):
            return []

    with Session(engine) as db:
        notice = _notice()
        db.add(notice)
        db.flush()
        db.add(AuditLog(
            event_type="opinion_submitted", entity_type="action_item",
            entity_id=str(notice.action.id),
            detail_json=json.dumps({"opinion_content": "등록 당시 문안"}),
        ))
        db.commit()
        asyncio.run(refresh_tracked_opinions_cached(db, client=Client()))
        first = json.loads(notice.raw_payload_json)["_poc08_opinion_tracking"]
        asyncio.run(refresh_tracked_opinions_cached(db, client=Client()))
        second = json.loads(notice.raw_payload_json)["_poc08_opinion_tracking"]

    assert first["status"] == "submitted_unverified"
    assert second["submitted_content"] == "등록 당시 문안"
    assert second["submitted_at"]


def test_dashboard_refresh_detects_reply_and_reuses_recent_check():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    root = {
        "opninNo": "3", "rplyNo": "0", "opninTitl": "공통기반 활용 검토",
        "opninCntnts": "인공지능데이터행정법 제27조제2항에 따라 공통기반 활용을 검토하고 회신해 주시기 바랍니다.",
        "inptDt": "20260915100000",
    }
    reply = {
        "opninNo": "3", "rplyNo": "1", "opninCntnts": "본공고에 반영하겠습니다.",
        "inptDt": "20260916130000",
    }

    class Client:
        def __init__(self):
            self.calls = 0

        async def prenotice_opinions(self, _registration_no):
            self.calls += 1
            return [root, reply]

    client = Client()
    with Session(engine) as db:
        notice = _notice()
        notice.action.status = "in_progress"
        db.add(notice)
        db.flush()
        db.add(AuditLog(
            event_type="opinion_submitted", entity_type="action_item",
            entity_id=str(notice.action.id),
            detail_json=json.dumps({"opinion_content": root["opninCntnts"]}),
        ))
        db.commit()

        first = asyncio.run(refresh_tracked_opinions_cached(
            db, min_interval=timedelta(minutes=5), client=client,
        ))
        second = asyncio.run(refresh_tracked_opinions_cached(
            db, min_interval=timedelta(minutes=5), client=client,
        ))

        tracking = json.loads(notice.raw_payload_json)["_poc08_opinion_tracking"]

    assert first["changed"] == 1
    assert first["replied"] == 1
    assert second["skipped"] == 1
    assert client.calls == 1
    assert tracking["status"] == "replied"


def test_unregistered_action_does_not_call_g2b_or_show_reply_failure():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    class Client:
        calls = 0

        async def prenotice_opinions(self, _registration_no):
            self.calls += 1
            raise AssertionError("등록 의견이 없는 공고는 조회하면 안 됩니다")

    client = Client()
    with Session(engine) as db:
        notice = Notice(
            stage="prenotice", notice_no="R26BD100", agency_name="기관", title="AI 사업",
            raw_payload_json=json.dumps({"_poc08_opinion_tracking": {
                "status": "error", "status_label": "답변 확인 실패",
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "detail": "RuntimeError: G2B 호출 실패: HTTP 429",
            }}),
        )
        notice.action = ActionItem(status="completed_ineligible")
        db.add(notice)
        db.commit()

        stats = asyncio.run(refresh_tracked_opinions_cached(db, client=client))
        tracking = json.loads(notice.raw_payload_json)["_poc08_opinion_tracking"]

    assert client.calls == 0
    assert stats["skipped"] == 1
    assert tracking["status"] == "not_submitted"
    assert tracking["status_label"] == "의견 등록 기록 없음"


def test_rate_limit_stops_batch_and_cools_down_registered_opinions():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    class Client:
        calls = 0

        async def prenotice_opinions(self, _registration_no):
            self.calls += 1
            raise RuntimeError("G2B 호출 실패: HTTP 429")

    client = Client()
    with Session(engine) as db:
        notices = []
        for suffix in ("1", "2"):
            notice = Notice(
                stage="prenotice", notice_no=f"R26BD20{suffix}",
                agency_name="기관", title="AI 사업",
            )
            notice.action = ActionItem(status="in_progress")
            db.add(notice)
            db.flush()
            db.add(AuditLog(
                event_type="opinion_submitted", entity_type="action_item",
                entity_id=str(notice.action.id),
                detail_json=json.dumps({"opinion_content": "공통기반 활용 검토 바랍니다."}),
            ))
            notices.append(notice)
        db.commit()

        first = asyncio.run(refresh_tracked_opinions_cached(db, client=client))
        second = asyncio.run(refresh_tracked_opinions_cached(db, client=client))
        tracking = [json.loads(notice.raw_payload_json)["_poc08_opinion_tracking"] for notice in notices]

    assert client.calls == 1
    assert first["failed"] == 1
    assert first["skipped"] == 1
    assert second["skipped"] == 2
    assert all(item["status"] == "rate_limited" for item in tracking)
    assert all(item["submitted_at"] and "답변이 없다는 뜻이 아니" in item["detail"] for item in tracking)


def test_old_429_error_is_relabelled_without_immediate_retry():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    class Client:
        calls = 0

        async def prenotice_opinions(self, _registration_no):
            self.calls += 1
            raise AssertionError("429 직후에는 재시도하면 안 됩니다")

    client = Client()
    with Session(engine) as db:
        notice = Notice(
            stage="prenotice", notice_no="R26BD300", agency_name="기관", title="AI 사업",
            raw_payload_json=json.dumps({"_poc08_opinion_tracking": {
                "status": "error", "status_label": "답변 확인 실패",
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "detail": "RuntimeError: G2B 호출 실패: HTTP 429",
            }}),
        )
        notice.action = ActionItem(status="in_progress")
        db.add(notice)
        db.flush()
        db.add(AuditLog(
            event_type="opinion_submitted", entity_type="action_item",
            entity_id=str(notice.action.id), detail_json="{}",
        ))
        db.commit()

        stats = asyncio.run(refresh_tracked_opinions_cached(db, client=client))
        tracking = json.loads(notice.raw_payload_json)["_poc08_opinion_tracking"]

    assert client.calls == 0
    assert stats["skipped"] == 1
    assert tracking["status"] == "rate_limited"
    assert tracking["submitted_at"]


def test_verified_reply_is_preserved_during_rate_limit():
    previous = {
        "status": "replied", "status_label": "답변 등록 1건",
        "checked_at": "2026-09-24T01:00:00+00:00",
        "matched_reply_count": 1, "latest_reply_content": "반영하겠습니다.",
    }
    tracking = _failure_tracking(previous, {}, RuntimeError("G2B 호출 실패: HTTP 429"))

    assert tracking["status"] == "replied"
    assert tracking["latest_reply_content"] == "반영하겠습니다."
    assert tracking["last_check_error"] == "rate_limited"


def test_manual_refresh_returns_rate_limit_state_instead_of_502():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    class Client:
        async def prenotice_opinions(self, _registration_no):
            raise RuntimeError("G2B 호출 실패: HTTP 429")

    with Session(engine) as db:
        notice = Notice(stage="prenotice", notice_no="R26BD400", agency_name="기관", title="AI 사업")
        notice.action = ActionItem(status="in_progress")
        db.add(notice)
        db.flush()
        db.add(AuditLog(
            event_type="opinion_submitted", entity_type="action_item",
            entity_id=str(notice.action.id), detail_json="{}",
        ))
        db.commit()

        tracking = asyncio.run(refresh_notice_opinions(db, notice, client=Client()))

    assert tracking["status"] == "rate_limited"
    assert tracking["submitted_at"]
