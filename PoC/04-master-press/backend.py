"""Homepage-mounted backend for PoC 04 Master Press.

All news-domain behavior lives in this folder. The root homepage only mounts static
assets, forwards API calls, supplies the shared administrator session result, and
runs worker_tick() from its existing ASGI lifespan.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import quote


PROJECT_DIR = Path(__file__).resolve().parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from master_press.kakao import KakaoError
from master_press.service import get_service, worker_tick


class MasterPressError(RuntimeError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _require_admin(admin_authenticated: bool) -> None:
    if not admin_authenticated:
        raise MasterPressError("홈페이지 관리자 로그인이 필요합니다.", 401)


def public_dashboard(case_id: str = "") -> dict:
    service = get_service()
    cases = []
    for case in service.store.list_cases(active_only=True):
        cases.append({
            "id": case["id"],
            "name": case["name"],
            "topic_description": case["topic_description"],
            "include_terms": case["include_terms"],
            "required_terms": case["required_terms"],
            "collection_mode": case["collection_mode"],
            "collection_interval_minutes": case["collection_interval_minutes"],
            "collection_times": case["collection_times"],
            "delivery_mode": case["delivery_mode"],
            "delivery_times": case["delivery_times"],
            "relevance_threshold": case["relevance_threshold"],
            "next_collect_at": case["next_collect_at"],
            "last_collected_at": case["last_collected_at"],
        })
    return {
        "project": {"id": "master-press", "title": "마스터언론", "display_no": "04"},
        "cases": cases,
        "dashboard": service.store.dashboard(case_id or None),
    }


def admin_bootstrap() -> dict:
    service = get_service()
    cases = service.store.list_cases()
    for case in cases:
        case["recipient_ids"] = service.store.case_recipient_ids(case["id"])
    return {
        "readiness": service.settings.readiness(),
        "settings": {
            "llm_model": service.settings.llm_model,
            "embedding_model": service.settings.embedding_model,
            "raw_retention_days": service.settings.raw_retention_days,
            "metadata_retention_days": service.settings.metadata_retention_days,
            "per_run_article_limit": service.settings.per_run_article_limit,
        },
        "cases": cases,
        "recipients": service.store.list_recipients(),
        "dashboard": service.store.dashboard(),
    }


def dispatch(
    subpath: str,
    method: str,
    payload: dict | None = None,
    query: dict | None = None,
    admin_authenticated: bool = False,
    request_base: str = "",
) -> dict:
    service = get_service()
    payload = payload or {}
    query = query or {}
    path = "/" + str(subpath or "").strip("/")
    method = method.upper()

    if path in {"/", "/dashboard"} and method == "GET":
        return public_dashboard(str(query.get("case_id") or ""))

    if path == "/admin/bootstrap" and method == "GET":
        _require_admin(admin_authenticated)
        return admin_bootstrap()

    if path == "/admin/cases" and method == "POST":
        _require_admin(admin_authenticated)
        case = service.store.save_case(payload)
        service.mirror.case(service.store.get_case(case["id"]) or case)
        service.store.set_case_recipients(case["id"], payload.get("recipient_ids", []))
        return {"case": service.store.get_case(case["id"]), "recipient_ids": service.store.case_recipient_ids(case["id"])}

    if path.startswith("/admin/cases/"):
        _require_admin(admin_authenticated)
        suffix = path[len("/admin/cases/"):].split("/")
        case_id = suffix[0]
        action = suffix[1] if len(suffix) > 1 else ""
        if not action and method in {"PUT", "PATCH"}:
            case = service.store.save_case(payload, case_id)
            service.mirror.case(service.store.get_case(case_id) or case)
            service.store.set_case_recipients(case_id, payload.get("recipient_ids", service.store.case_recipient_ids(case_id)))
            return {"case": service.store.get_case(case_id), "recipient_ids": service.store.case_recipient_ids(case_id)}
        if not action and method == "DELETE":
            return {"deleted": service.store.delete_case(case_id)}
        if action == "run" and method == "POST":
            return service.run_case(case_id)
        if action == "recipients" and method == "POST":
            service.store.set_case_recipients(case_id, payload.get("recipient_ids", []))
            return {"case_id": case_id, "recipient_ids": service.store.case_recipient_ids(case_id)}
        if action == "improvements" and method == "GET":
            return service.store.low_score_analysis(case_id, int(query.get("days") or 7))

    if path == "/admin/invites" and method == "POST":
        _require_admin(admin_authenticated)
        invite, token = service.store.create_invite(payload.get("label", ""), int(payload.get("ttl_minutes", 60)))
        base = request_base.rstrip("/")
        invite["url"] = f"{base}/poc/master-press/connect?invite={quote(token)}"
        return {"invite": invite}

    if path.startswith("/admin/recipients/"):
        _require_admin(admin_authenticated)
        suffix = path[len("/admin/recipients/"):].split("/")
        recipient_id = suffix[0]
        action = suffix[1] if len(suffix) > 1 else ""
        if not action and method == "DELETE":
            service.kakao.disconnect(recipient_id)
            return {"deleted": True}
        if action == "test" and method == "POST":
            base = request_base.rstrip("/")
            status, response = service.kakao.send_to_me(
                recipient_id,
                "[마스터언론] 수신자 연결 테스트\n\n카카오톡 나와의 채팅 연결이 정상입니다.",
                f"{base}/poc/master-press/",
            )
            return {"sent": True, "status": status, "response": response}

    if path == "/admin/tick" and method == "POST":
        _require_admin(admin_authenticated)
        return worker_tick()

    if path == "/admin/deliveries/send" and method == "POST":
        _require_admin(admin_authenticated)
        return service.send_due(int(payload.get("limit", 20)))

    raise MasterPressError("마스터언론 API 경로를 찾지 못했습니다.", 404)


def kakao_authorization_url(invite_token: str) -> str:
    return get_service().kakao.authorization_url(invite_token)


def complete_kakao_authorization(code: str, state: str) -> dict:
    return get_service().kakao.complete_authorization(code, state)


def article_redirect_url(article_id: str) -> str:
    article = get_service().store.get_article(str(article_id))
    if not article:
        raise MasterPressError("원문 기사를 찾지 못했습니다.", 404)
    return quote(str(article["original_url"]), safe=":/?&=%#@+;,")


def status() -> dict:
    service = get_service()
    return {
        "ready": service.settings.readiness(),
        "case_count": len(service.store.list_cases()),
        "recipient_count": len(service.store.list_recipients()),
    }
