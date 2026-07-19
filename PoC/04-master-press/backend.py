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
from master_press.service import case_worker_tick, common_worker_tick, get_service, worker_tick
from master_press.storage import now_iso


class MasterPressError(RuntimeError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _require_admin(admin_authenticated: bool) -> None:
    if not admin_authenticated:
        raise MasterPressError("홈페이지 관리자 로그인이 필요합니다.", 401)


def public_dashboard(case_id: str = "", organization_id: str = "", tags: list[str] | None = None) -> dict:
    service = get_service()
    cases = []
    for case in service.store.list_cases(active_only=True):
        cases.append({
            "id": case["id"],
            "name": case["name"],
            "organization_id": case.get("organization_id"),
            "topic_search_prompt": case.get("topic_search_prompt", case["topic_description"]),
            "include_terms": case["include_terms"],
            "required_terms": case["required_terms"],
            "collection_mode": case["collection_mode"],
            "collection_interval_minutes": case["collection_interval_minutes"],
            "collection_times": case["collection_times"],
            "delivery_mode": case["delivery_mode"],
            "delivery_times": case["delivery_times"],
            "send_relevant_immediately": case["send_relevant_immediately"],
            "relevance_threshold": case["relevance_threshold"],
            "next_collect_at": case["next_collect_at"],
            "last_collected_at": case["last_collected_at"],
        })
    organizations = [
        {
            "id": item["id"],
            "name": item["name"],
            "is_active": item["is_active"],
            "next_collect_at": item.get("next_collect_at"),
            "last_collected_at": item.get("last_collected_at"),
        }
        for item in service.store.list_organizations(active_only=True)
    ]
    dashboard = service.store.pipeline_dashboard(case_id or None, organization_id or None, tags=tags or [], limit=100)
    dashboard.setdefault("pipeline", {})["providers"] = service.pipeline_provider_status()
    return {
        "project": {"id": "master-press", "title": "AI 언론동향 비서", "display_no": "04"},
        "organizations": organizations,
        "cases": cases,
        "dashboard": dashboard,
    }


def admin_bootstrap() -> dict:
    service = get_service()
    cases = service.store.list_cases()
    organizations = service.store.list_organizations()
    for case in cases:
        case["recipient_ids"] = service.store.case_recipient_ids(case["id"])
    return {
        "readiness": service.settings.readiness(),
        "settings": {
            "llm_model": service.selected_llm_model(),
            "llm_models": service.available_llm_models(),
            "case_llm_model": service.selected_case_llm_model(),
            "case_llm_models": service.available_case_llm_models(),
            "openrouter": service.openrouter_status(probe=True),
            "embedding_model": service.settings.embedding_model,
            "raw_retention_days": service.settings.raw_retention_days,
            "metadata_retention_days": service.settings.metadata_retention_days,
            "per_run_article_limit": service.settings.per_run_article_limit,
        },
        "organizations": organizations,
        "cases": cases,
        "recipients": service.recipients_with_connection_status(),
        "dashboard": {**service.store.pipeline_dashboard(limit=100), "provider_status": service.pipeline_provider_status()},
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
        return public_dashboard(
            str(query.get("case_id") or ""),
            str(query.get("organization_id") or ""),
            [value for value in str(query.get("tags") or "").split(",") if value],
        )

    if path == "/analysis/insights" and method == "GET":
        case_id = str(query.get("case_id") or "").strip()
        organization_id = str(query.get("organization_id") or "").strip()
        organization_scope = str(query.get("scope") or "") == "organization"
        sent_only = str(query.get("sent_only") or "") in {"1", "true", "yes"}
        delivery_only = str(query.get("delivery_only") or "") in {"1", "true", "yes"}
        if not case_id and not (organization_scope and organization_id):
            raise MasterPressError("신경망 분석은 케이스를 선택한 뒤 실행할 수 있습니다.")
        if sent_only and not case_id:
            raise MasterPressError("발송 완료 기사 분석은 케이스를 선택한 뒤 실행할 수 있습니다.")
        return service.store.analysis_insights(
            case_id or None, organization_id or None, int(query.get("days") or 7), sent_only=sent_only, delivery_only=delivery_only,
        )

    if path == "/press-releases" and method == "GET":
        return {
            "items": service.press_releases.list_releases(
                str(query.get("organization_id") or ""), int(query.get("limit") or 50)
            ),
            "status": service.press_releases.status(),
        }

    if path.startswith("/press-releases/") and method == "GET":
        release_id = path[len("/press-releases/"):]
        item = service.press_releases.get_release(release_id, include_markdown=True)
        if not item:
            raise MasterPressError("보도자료를 찾지 못했습니다.", 404)
        return {"item": item}

    if path.startswith("/articles/") and path.endswith("/press-releases") and method == "GET":
        article_id = path[len("/articles/"):-len("/press-releases")].strip("/")
        if not service.store.get_article(article_id):
            raise MasterPressError("기사를 찾지 못했습니다.", 404)
        return {"items": service.press_releases.releases_for_article(article_id)}

    if path == "/admin/bootstrap" and method == "GET":
        _require_admin(admin_authenticated)
        return admin_bootstrap()

    if path == "/admin/settings/llm-model" and method == "PUT":
        _require_admin(admin_authenticated)
        model = str(payload.get("model") or "").strip()[:120]
        if not model:
            raise MasterPressError("Ollama 모델을 선택하세요.")
        models = service.available_llm_models()
        if models and model not in models:
            raise MasterPressError("현재 Ollama에 설치된 모델만 선택할 수 있습니다.")
        service.store.set_setting("llm_model", model)
        return {"llm_model": model, "llm_models": models}

    if path == "/admin/settings/case-llm-model" and method == "PUT":
        _require_admin(admin_authenticated)
        model = str(payload.get("model") or "").strip()[:160]
        if not model or not model.endswith(":free"):
            raise MasterPressError("OpenRouter 무료 모델을 선택하세요.")
        models = service.available_case_llm_models()
        if models and model not in models:
            raise MasterPressError("현재 OpenRouter에서 JSON 판정을 지원하는 무료 모델만 선택할 수 있습니다.")
        service.store.set_setting("case_llm_model", model)
        return {"case_llm_model": model, "case_llm_models": models, "openrouter": service.openrouter_status(probe=True)}

    if path.startswith("/admin/analysis/"):
        _require_admin(admin_authenticated)
        suffix = path[len("/admin/analysis/"):].split("/")
        if len(suffix) >= 3 and suffix[2] == "report" and method == "GET":
            return {
                **service.analysis_report(suffix[0], suffix[1]),
                "llm_models": service.available_llm_models(),
                "selected_llm_model": service.selected_llm_model(),
            }
        if len(suffix) >= 3 and suffix[2] == "reanalyze" and method == "POST":
            article, case = service.store.get_article(suffix[0]), service.store.get_case(suffix[1])
            if not article or not case:
                raise MasterPressError("기사 또는 케이스를 찾지 못했습니다.", 404)
            model = str(payload.get("model") or service.selected_llm_model()).strip()
            models = service.available_llm_models()
            if models and model not in models:
                raise MasterPressError("현재 Ollama에 설치된 모델만 선택할 수 있습니다.")
            return {"job": service.store.queue_reanalysis(article["id"], case["id"], model)}
        if len(suffix) >= 2 and suffix[1] == "apply" and method == "POST":
            job = service.store.get_reanalysis(suffix[0])
            if not job or job.get("status") != "completed":
                raise MasterPressError("완료된 재분석 결과가 없습니다.", 409)
            result, case, article = job.get("result") or {}, service.store.get_case(job["case_id"]), service.store.get_article(job["article_id"])
            if not case or not article:
                raise MasterPressError("기사 또는 케이스를 찾지 못했습니다.", 404)
            saved = service.store.save_score(article["id"], case["id"], int(case.get("version", 1)), result)
            service.mirror.article_score(article, saved)
            return {"score": saved, "send_eligible": result.get("decision") == "send", "job_id": job["id"]}
        if len(suffix) >= 2 and suffix[1] == "send" and method == "POST":
            job = service.store.get_reanalysis(suffix[0])
            if not job or job.get("status") != "completed":
                raise MasterPressError("완료된 재분석 결과가 없습니다.", 409)
            result, case = job.get("result") or {}, service.store.get_case(job["case_id"])
            if not case or result.get("decision") != "send":
                raise MasterPressError("발송 조건을 충족한 재분석 결과가 아닙니다.", 409)
            for recipient_id in service.store.case_recipient_ids(case["id"]):
                service.store.queue_delivery(job["article_id"], case["id"], recipient_id, now_iso())
            return service.send_due(20)

    if path == "/admin/organizations" and method == "POST":
        _require_admin(admin_authenticated)
        return {"organization": service.store.save_organization(payload)}

    if path.startswith("/admin/organizations/"):
        _require_admin(admin_authenticated)
        suffix = path[len("/admin/organizations/"):].split("/")
        organization_id = suffix[0]
        action = suffix[1] if len(suffix) > 1 else ""
        if not action and method in {"PUT", "PATCH"}:
            organization = service.store.save_organization(payload, organization_id)
            service.mirror.organization(organization)
            return {"organization": organization}
        if not action and method == "DELETE":
            archived = service.store.archive_organization(organization_id)
            organization = service.store.get_organization(organization_id)
            if organization:
                service.mirror.organization(organization)
            return {"archived": archived}
        if action == "run" and method == "POST":
            return service.run_organization(organization_id)


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
                "[AI 언론동향 비서] 수신자 연결 테스트\n\n카카오톡 나와의 채팅 연결이 정상입니다.",
                f"{base}/poc/master-press/",
            )
            return {"sent": True, "status": status, "response": response}

    if path == "/admin/tick" and method == "POST":
        _require_admin(admin_authenticated)
        return worker_tick()

    if path == "/admin/press-releases/sync" and method == "POST":
        _require_admin(admin_authenticated)
        return service.press_releases.sync(force=True)

    if path == "/admin/deliveries/send" and method == "POST":
        _require_admin(admin_authenticated)
        return service.send_due(int(payload.get("limit", 20)))

    raise MasterPressError("AI 언론동향 비서 API 경로를 찾지 못했습니다.", 404)


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
        "organization_count": len(service.store.list_organizations()),
        "case_count": len(service.store.list_cases()),
        "recipient_count": len(service.store.list_recipients()),
    }
