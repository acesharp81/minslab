import json

from app.models import ActionItem, AnalysisRun, Notice
from app.services.analyzer import CURRENT_CRITERIA_VERSION
from app.services.opinion_tracker import _tracking_result


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
