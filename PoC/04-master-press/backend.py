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
from master_press.service import case_worker_tick, common_worker_tick, embedding_worker_tick, get_service, worker_tick
from master_press.storage import now_iso


class MasterPressError(RuntimeError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _require_admin(admin_authenticated: bool) -> None:
    if not admin_authenticated:
        raise MasterPressError("홈페이지 관리자 로그인이 필요합니다.", 401)


def public_dashboard(case_id: str = "", organization_id: str = "", tags: list[str] | None = None, search: str = "") -> dict:
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
            "sort_order": case.get("sort_order", 0),
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
    dashboard = service.store.pipeline_dashboard(case_id or None, organization_id or None, tags=tags or [], limit=100, search=search)
    dashboard.setdefault("pipeline", {})["providers"] = service.pipeline_provider_status()
    return {
        "project": {"id": "master-press", "title": "AI 언론동향 비서", "display_no": "04"},
        "organizations": organizations,
        "cases": cases,
        "dashboard": dashboard,
    }


def signup_bootstrap() -> dict:
    service = get_service()
    organizations = []
    for organization in service.store.list_organizations(active_only=True):
        cases = service.store.list_cases_for_organization(organization["id"], active_only=True)
        organizations.append({
            "id": organization["id"],
            "name": organization["name"],
            "cases": [{"id": case["id"], "name": case["name"]} for case in cases],
        })
    return {"organizations": organizations, "requests": service.store.list_signup_requests(include_private=False)}


def admin_bootstrap() -> dict:
    service = get_service()
    cases = service.store.list_cases()
    organizations = service.store.list_organizations()
    for case in cases:
        case["recipient_ids"] = service.store.case_recipient_ids(case["id"])
        case["sent_keyword_suggestions"] = service.store.case_sent_keyword_suggestions(case["id"], days=30, limit=5)
    common_model = service.selected_common_llm_model()
    case_model = service.selected_case_llm_model()
    return {
        "readiness": service.settings.readiness(),
        "settings": {
            "common_llm_model": common_model,
            "common_llm_models": [common_model] if common_model else [],
            "llm_model": common_model,
            "llm_models": [common_model] if common_model else [],
            "groq": service.groq_status(probe=False),
            "case_llm_model": case_model,
            "case_llm_models": [case_model] if case_model else [],
            "openrouter": service.openrouter_status(probe=False),
            "reserve1_llm_model": service.selected_reserve1_model(),
            "reserve1_llm_models": service.available_reserve1_models(),
            "cloudflare": service.cloudflare_status(probe=False),
            "reserve2_llm_model": service.selected_reserve2_model(),
            "reserve2_llm_models": service.available_reserve2_models(),
            "gemini": service.gemini_status(probe=False),
            "announcements": service.store.list_announcements(include_inactive=True),
            "embedding_model": service.selected_embedding_model(),
            "embedding_models": service.available_embedding_models(),
            "ollama_embedding": service.ollama_embedding_status(probe=True),
            "case_batch_size": service.selected_case_batch_size(),
            "semantic_candidate_threshold": float(service.store.get_setting("semantic_candidate_threshold", "65")),
            "press_release_match_threshold": float(service.store.get_setting("press_release_match_threshold", str(service.settings.press_release_match_threshold))),
            "similar_article_threshold": float(service.store.get_setting("similar_article_threshold", "65")),
            "raw_retention_days": service.settings.raw_retention_days,
            "metadata_retention_days": service.settings.metadata_retention_days,
            "per_run_article_limit": service.settings.per_run_article_limit,
        },
        "organizations": organizations,
        "cases": cases,
        "recipients": service.recipients_with_connection_status(),
        "signup_requests": service.store.list_signup_requests(include_private=True),
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
            str(query.get("q") or ""),
        )

    if path == "/signup/bootstrap" and method == "GET":
        return signup_bootstrap()

    if path == "/announcements/current" and method == "GET":
        return {"items": service.store.current_announcements()}

    if path == "/signup/kakao-registration" and method == "POST":
        invite, token = service.store.create_invite("구독 신청자", 1440)
        base = request_base.rstrip("/")
        invite["registration_url"] = f"{base}/poc/master-press/connect?invite={quote(token)}"
        return {"registration": invite}

    if path == "/signup/kakao-status" and method == "GET":
        recipient_id = str(query.get("recipient_id") or "").strip()
        recipient = service.store.get_recipient(recipient_id) if recipient_id else None
        scopes = recipient and recipient.get("scopes") or "[]"
        try:
            granted_scopes = json.loads(scopes) if isinstance(scopes, str) else scopes
        except Exception:
            granted_scopes = []
        kakao_registered = bool(recipient and recipient.get("status") != "deleted" and "talk_message" in set(granted_scopes or []))
        return {"kakao_registered": kakao_registered, "recipient_id": recipient_id if kakao_registered else ""}

    if path == "/signup/requests" and method == "POST":
        case_ids = payload.get("case_ids", [])
        if not isinstance(case_ids, list):
            raise MasterPressError("케이스 선택값이 올바르지 않습니다.")
        recipient_id = str(payload.get("recipient_id") or "").strip()
        if recipient_id:
            recipient = service.store.get_recipient(recipient_id)
            raw_scopes = recipient and recipient.get("scopes") or "[]"
            try:
                granted_scopes = json.loads(raw_scopes) if isinstance(raw_scopes, str) else raw_scopes
            except Exception:
                granted_scopes = []
            if not (recipient and recipient.get("status") != "deleted" and "talk_message" in set(granted_scopes or [])):
                raise MasterPressError("카카오 메시지 전송 동의가 확인된 뒤 구독 요청할 수 있습니다.")
        request, token = service.store.create_signup_request(
            str(payload.get("applicant_name") or ""),
            str(payload.get("organization_id") or ""),
            case_ids,
            1440,
            recipient_id,
        )
        if not recipient_id:
            base = request_base.rstrip("/")
            request["registration_url"] = f"{base}/poc/master-press/connect?invite={quote(token)}"
        return {"request": request}

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
                str(query.get("organization_id") or ""),
                int(query.get("limit") or 50),
                str(query.get("q") or ""),
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

    if path.startswith("/admin/signup-requests/"):
        _require_admin(admin_authenticated)
        suffix = path[len("/admin/signup-requests/"):].split("/")
        request_id = suffix[0]
        if len(suffix) == 1 and method == "DELETE":
            deleted = service.store.delete_signup_request(request_id)
            if not deleted:
                raise MasterPressError("구독 요청을 찾지 못했습니다.", 404)
            return {"deleted": True}
        if len(suffix) >= 2 and suffix[1] == "subscriptions" and method in {"PUT", "POST"}:
            case_ids = payload.get("case_ids", [])
            if not isinstance(case_ids, list):
                raise MasterPressError("구독 케이스 선택값이 올바르지 않습니다.")
            try:
                return {"request": service.store.set_signup_request_subscriptions(
                    request_id, case_ids, str(payload.get("admin_note") or "관리자 구독 조정")
                )}
            except ValueError as error:
                raise MasterPressError(str(error)) from error
        if len(suffix) >= 3 and suffix[1] == "cases" and method in {"PUT", "POST"}:
            case_id = suffix[2]
            action = suffix[3] if len(suffix) > 3 else ""
            try:
                if action == "revoke":
                    context = service.store.signup_case_context(request_id, case_id)
                    recipient_id = str(context.get("recipient_id") or "")
                    if not recipient_id:
                        raise ValueError("카카오 수신 등록 정보가 없어 해제 안내를 보낼 수 없습니다.")
                    base = request_base.rstrip("/")
                    service.kakao.send_to_me(
                        recipient_id,
                        "[AI 언론동향 비서] 케이스 수신이 해제되었습니다\n\n"
                        f"해제 케이스: {context.get('case_name') or '케이스'}\n"
                        "이후 해당 케이스의 알림은 발송되지 않습니다.",
                        f"{base}/poc/master-press/signup",
                    )
                    return {"request": service.store.revoke_signup_case(
                        request_id, case_id, str(payload.get("admin_note") or "수신 해제")
                    )}
                return {"request": service.store.decide_signup_case(
                    request_id, case_id, str(payload.get("decision") or ""), str(payload.get("admin_note") or "")
                )}
            except ValueError as error:
                raise MasterPressError(str(error)) from error

    if path in {"/admin/settings/common-llm-model", "/admin/settings/llm-model"} and method == "PUT":
        _require_admin(admin_authenticated)
        model = str(payload.get("model") or "").strip()[:120]
        if not model:
            raise MasterPressError("Groq 공통분석 모델을 선택하세요.")
        models = service.available_common_llm_models()
        if models and model not in models:
            raise MasterPressError("현재 Groq에서 사용할 수 있는 공통분석 모델만 선택할 수 있습니다.")
        service.store.set_setting("common_llm_model", model)
        return {"common_llm_model": model, "common_llm_models": models, "groq": service.groq_status(probe=True)}

    if path == "/admin/settings/embedding-model" and method == "PUT":
        _require_admin(admin_authenticated)
        model = str(payload.get("model") or "").strip()[:120]
        if not model:
            raise MasterPressError("Ollama 임베딩 모델을 선택하세요.")
        models = service.available_embedding_models()
        if models and model not in models:
            raise MasterPressError("현재 Ollama에 설치된 임베딩 모델만 선택할 수 있습니다.")
        previous = service.selected_embedding_model()
        rebuilt = {}
        if previous and previous != model:
            rebuilt = service.store.reset_embedding_indexes()
        service.store.set_setting("embedding_model", model)
        service.scoring.ollama.embedding_model = model
        return {
            "embedding_model": model, "embedding_models": models,
            "rebuilt": rebuilt, "ollama_embedding": service.ollama_embedding_status(probe=True),
        }

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

    if path == "/admin/settings/reserve-llm-models" and method == "PUT":
        _require_admin(admin_authenticated)
        reserve1 = str(payload.get("reserve1_model") or "").strip()[:180]
        reserve2 = str(payload.get("reserve2_model") or "").strip()[:180]
        if not reserve1:
            raise MasterPressError("예비1 Cloudflare 모델을 입력하세요.")
        if not reserve2:
            raise MasterPressError("예비2 Gemini 모델을 입력하세요.")
        service.store.set_setting("reserve1_llm_model", reserve1)
        service.store.set_setting("reserve2_llm_model", reserve2)
        return {
            "reserve1_llm_model": reserve1, "reserve1_llm_models": service.available_reserve1_models(), "cloudflare": service.cloudflare_status(probe=True),
            "reserve2_llm_model": reserve2, "reserve2_llm_models": service.available_reserve2_models(), "gemini": service.gemini_status(probe=True),
        }

    if path == "/admin/announcements" and method == "POST":
        _require_admin(admin_authenticated)
        try:
            item = service.store.save_announcement(payload)
        except ValueError as error:
            raise MasterPressError(str(error)) from error
        return {"item": item, "items": service.store.list_announcements(include_inactive=True)}

    if path.startswith("/admin/announcements/") and method == "DELETE":
        _require_admin(admin_authenticated)
        item_id = path[len("/admin/announcements/"):].strip("/")
        if not service.store.delete_announcement(item_id):
            raise MasterPressError("공지사항을 찾지 못했습니다.", 404)
        return {"deleted": True, "items": service.store.list_announcements(include_inactive=True)}

    if path == "/admin/settings/case-batch" and method == "PUT":
        _require_admin(admin_authenticated)
        try:
            batch_size = max(1, min(10, int(payload.get("batch_size", 10))))
            semantic_threshold = max(0.0, min(100.0, float(payload.get("semantic_candidate_threshold", 65))))
        except (TypeError, ValueError):
            raise MasterPressError("배치 크기 또는 벡터 후보 기준이 올바르지 않습니다.")
        service.store.set_setting("case_batch_size", str(batch_size))
        service.store.set_setting("semantic_candidate_threshold", str(semantic_threshold))
        return {"case_batch_size": batch_size, "semantic_candidate_threshold": semantic_threshold}

    if path == "/admin/settings/press-release-match" and method == "PUT":
        _require_admin(admin_authenticated)
        try:
            threshold = max(0.0, min(100.0, float(payload.get("threshold", 65))))
        except (TypeError, ValueError):
            raise MasterPressError("관련 보도자료 유사도 기준이 올바르지 않습니다.")
        service.store.set_setting("press_release_match_threshold", str(threshold))
        return {"press_release_match_threshold": threshold}


    if path == "/admin/settings/similar-articles" and method == "PUT":
        _require_admin(admin_authenticated)
        try:
            threshold = max(0.0, min(100.0, float(payload.get("threshold", 65))))
        except (TypeError, ValueError):
            raise MasterPressError("유사 기사 묶음 기준이 올바르지 않습니다.")
        service.store.set_setting("similar_article_threshold", str(threshold))
        return {"similar_article_threshold": threshold}

    if path.startswith("/admin/analysis/"):
        _require_admin(admin_authenticated)
        suffix = path[len("/admin/analysis/"):].split("/")
        if len(suffix) >= 2 and suffix[1] == "reanalyze" and method == "POST":
            article = service.store.get_article(suffix[0])
            if not article:
                raise MasterPressError("기사를 찾지 못했습니다.", 404)
            try:
                return service.requeue_article_case_evaluations(article["id"])
            except ValueError as error:
                raise MasterPressError(str(error), 409)
        if len(suffix) >= 3 and suffix[2] == "report" and method == "GET":
            return {
                **service.analysis_report(suffix[0], suffix[1]),
                "llm_models": service.available_case_llm_models(),
                "selected_llm_model": service.selected_case_llm_model(),
            }
        if len(suffix) >= 3 and suffix[2] == "reanalyze" and method == "POST":
            article, case = service.store.get_article(suffix[0]), service.store.get_case(suffix[1])
            if not article or not case:
                raise MasterPressError("기사 또는 케이스를 찾지 못했습니다.", 404)
            model = str(payload.get("model") or service.selected_case_llm_model()).strip()
            models = service.available_case_llm_models()
            if models and model not in models:
                raise MasterPressError("현재 OpenRouter 케이스 판정 모델만 선택할 수 있습니다.")
            return {"job": service.store.queue_reanalysis(article["id"], case["id"], model)}
        if len(suffix) >= 2 and suffix[1] == "apply" and method == "POST":
            job = service.store.get_reanalysis(suffix[0])
            if not job or job.get("status") != "completed":
                raise MasterPressError("완료된 재분석 결과가 없습니다.", 409)
            result, case, article = job.get("result") or {}, service.store.get_case(job["case_id"]), service.store.get_article(job["article_id"])
            if not case or not article:
                raise MasterPressError("기사 또는 케이스를 찾지 못했습니다.", 404)
            current_evaluation = service.store.get_current_case_evaluation(article["id"], case["id"])
            updated_evaluation = None
            if current_evaluation:
                updated_evaluation = service.store.save_case_evaluation(current_evaluation["id"], result, str(job.get("model") or result.get("analysis_report", {}).get("model") or ""))
            saved = service.store.save_score(article["id"], case["id"], int(case.get("version", 1)), result)
            service.mirror.article_score(article, saved)
            return {"score": saved, "evaluation": updated_evaluation, "send_eligible": result.get("decision") == "send", "job_id": job["id"]}
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
        if len(suffix) >= 3 and suffix[1] == "cases" and suffix[2] == "order" and method in {"PUT", "PATCH"}:
            ordered = service.store.reorder_cases(organization_id, payload.get("case_ids", []))
            for case in ordered:
                service.mirror.case(case)
            return {"organization_id": organization_id, "cases": ordered}
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
            base = request_base.rstrip("/")
            status, response = service.kakao.send_to_me(
                recipient_id,
                "[AI 언론동향 비서] 구독 해지 안내\n\n관리자 권한으로 구독이 해지되었습니다. 이후 해당 카카오 계정으로 알림이 발송되지 않습니다.",
                f"{base}/poc/master-press/",
            )
            service.kakao.disconnect(recipient_id)
            return {"deleted": True, "notice_sent": True, "notice_status": status, "notice_response": response}
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
