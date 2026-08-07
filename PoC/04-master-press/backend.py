"""Homepage-mounted backend for PoC 04 Master Press.

All news-domain behavior lives in this folder. The root homepage only mounts static
assets, forwards API calls, supplies the shared administrator session result, and
runs worker_tick() from its existing ASGI lifespan.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import threading
import time
from pathlib import Path
from urllib.parse import quote


PROJECT_DIR = Path(__file__).resolve().parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))


from master_press.magazine import MagazinePublisher
from master_press.kakao import KakaoError
from master_press.service import case_worker_tick, common_worker_tick, embedding_worker_tick, shadow_worker_tick, get_service, worker_tick
from master_press.storage import RECIPIENT_UNSUBSCRIBE_INVITE_LABEL, now_iso
from master_press.supabase_seed import SupabaseSeed
from master_press.supabase_daily_metrics import SupabaseDailyMetrics
from master_press.supabase_reconcile import SupabaseReconciler


class MasterPressError(RuntimeError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _require_admin(admin_authenticated: bool) -> None:
    if not admin_authenticated:
        raise MasterPressError("홈페이지 관리자 로그인이 필요합니다.", 401)


_ADMIN_BOOTSTRAP_CACHE: dict | None = None


def _invalidate_admin_bootstrap_cache() -> None:
    global _ADMIN_BOOTSTRAP_CACHE
    _ADMIN_BOOTSTRAP_CACHE = None


def _is_db_locked_error(error: Exception) -> bool:
    return "locked" in str(error).lower()


def _clone_payload(payload: dict) -> dict:
    # Keep cache mutations isolated between requests.
    return json.loads(json.dumps(payload, ensure_ascii=False))


def _db_quick_lock_probe(database_path: str) -> bool:
    connection = None
    try:
        connection = sqlite3.connect(str(database_path), timeout=0.05)
        connection.execute("SELECT 1")
        return False
    except sqlite3.OperationalError as error:
        return _is_db_locked_error(error)
    finally:
        if connection is not None:
            connection.close()


def _cached_admin_bootstrap(reason: str = "") -> dict | None:
    if not _ADMIN_BOOTSTRAP_CACHE:
        return None
    cached = _clone_payload(_ADMIN_BOOTSTRAP_CACHE)
    cached["degraded"] = {
        "reason": reason or "database_locked",
        "generated_at": now_iso(),
    }
    return cached


def _build_public_dashboard(
    case_id: str = "",
    organization_id: str = "",
    tags: list[str] | None = None,
    search: str = "",
    include_groups: bool = True,
    limit: int = 100,
    offset: int = 0,
    include_press_stats: bool = True,
    delivery_filter: str = "all",
    days: int = 7,
) -> dict:
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
    dashboard = service.store.pipeline_dashboard(
        case_id or None,
        organization_id or None,
        tags=tags or [],
        limit=max(1, min(100, int(limit))),
        offset=max(0, int(offset)),
        search=search,
        delivery_filter=delivery_filter,
        days=max(1, min(30, int(days))),
        include_groups=include_groups,
        include_press_stats=include_press_stats,
    )
    dashboard.setdefault("pipeline", {})["providers"] = service.pipeline_provider_status()
    monitor = service.store.pipeline_monitor_status()
    seconds_since_success = monitor.get("seconds_since_last_success")
    collection_healthy = seconds_since_success is not None and float(seconds_since_success) <= 300
    dashboard["collection_health"] = {
        "healthy": collection_healthy,
        "label": "수집 정상" if collection_healthy else "수집 중단",
        "seconds_since_last_success": seconds_since_success,
        "last_success_at": (monitor.get("last_success") or {}).get("finished_at", ""),
    }
    return {
        "project": {"id": "master-press", "title": "AI 언론동향 비서", "display_no": "04"},
        "organizations": organizations,
        "cases": cases,
        "dashboard": dashboard,
    }


_PUBLIC_DASHBOARD_CACHE: dict[tuple, tuple[float, dict]] = {}
_PUBLIC_DASHBOARD_LOCKS: dict[tuple, threading.Lock] = {}
_PUBLIC_DASHBOARD_CACHE_GUARD = threading.Lock()
_PUBLIC_DASHBOARD_CACHE_SECONDS = 15.0


def public_dashboard(
    case_id: str = "", organization_id: str = "", tags: list[str] | None = None,
    search: str = "", include_groups: bool = True, limit: int = 100, offset: int = 0,
    include_press_stats: bool = True, delivery_filter: str = "all", days: int = 7,
) -> dict:
    """Short shared cache prevents a same-filter request stampede."""
    key = (
        str(case_id), str(organization_id), tuple(sorted(str(value) for value in (tags or []))),
        str(search), bool(include_groups), int(limit), int(offset), bool(include_press_stats),
        str(delivery_filter), int(days),
    )
    now = time.monotonic()
    with _PUBLIC_DASHBOARD_CACHE_GUARD:
        cached = _PUBLIC_DASHBOARD_CACHE.get(key)
        if cached and now - cached[0] <= _PUBLIC_DASHBOARD_CACHE_SECONDS:
            return _clone_payload(cached[1])
        key_lock = _PUBLIC_DASHBOARD_LOCKS.setdefault(key, threading.Lock())
    with key_lock:
        now = time.monotonic()
        with _PUBLIC_DASHBOARD_CACHE_GUARD:
            cached = _PUBLIC_DASHBOARD_CACHE.get(key)
            if cached and now - cached[0] <= _PUBLIC_DASHBOARD_CACHE_SECONDS:
                return _clone_payload(cached[1])
        result = _build_public_dashboard(
            case_id, organization_id, tags, search, include_groups, limit, offset,
            include_press_stats, delivery_filter, days,
        )
        with _PUBLIC_DASHBOARD_CACHE_GUARD:
            _PUBLIC_DASHBOARD_CACHE[key] = (time.monotonic(), result)
            if len(_PUBLIC_DASHBOARD_CACHE) > 64:
                oldest = min(_PUBLIC_DASHBOARD_CACHE, key=lambda item: _PUBLIC_DASHBOARD_CACHE[item][0])
                _PUBLIC_DASHBOARD_CACHE.pop(oldest, None)
                _PUBLIC_DASHBOARD_LOCKS.pop(oldest, None)
        return _clone_payload(result)


def signup_bootstrap(admin: bool = False) -> dict:
    service = get_service()
    with service.store.connect() as connection:
        rows = connection.execute(
            """SELECT case_id,COUNT(DISTINCT recipient_id) total FROM (
                   SELECT case_id,recipient_id FROM case_recipients
                   UNION ALL
                   SELECT src.case_id,sr.recipient_id
                   FROM signup_request_cases src
                   JOIN signup_requests sr ON sr.id=src.request_id
                   WHERE src.status='approved' AND sr.recipient_id IS NOT NULL
               ) GROUP BY case_id"""
        ).fetchall()
    subscriber_counts = {str(row["case_id"]): int(row["total"] or 0) for row in rows}
    organizations = []
    for organization in service.store.list_organizations(active_only=True):
        cases = service.store.list_cases_for_organization(organization["id"], active_only=True)
        organizations.append({
            "id": organization["id"],
            "name": organization["name"],
            "cases": [
                {
                    "id": case["id"],
                    "name": case["name"],
                    "topic_search_prompt": case.get("topic_search_prompt") or case.get("topic_description") or "",
                    "semantic_weight": case.get("semantic_weight", 0.25),
                    "llm_weight": case.get("llm_weight", 0.75),
                    "subscriber_count": subscriber_counts.get(str(case["id"]), 0),
                }
                for case in cases
            ],
        })
    return {"organizations": organizations, "requests": service.store.list_signup_requests(include_private=False), "case_proposals": service.store.list_case_proposals(admin=admin)}



def fast_recipient_statuses(service) -> list[dict]:
    recipients = service.store.list_recipients()
    for recipient in recipients:
        ok = recipient.get("status") == "active" and not recipient.get("last_error")
        recipient["connection_status"] = "connected" if ok else "failed"
        recipient["connection_label"] = "저장된 상태 정상" if ok else (recipient.get("last_error") or "재확인 필요")
        recipient["connection_error"] = recipient.get("last_error") or ""
    return recipients


def admin_bootstrap() -> dict:
    global _ADMIN_BOOTSTRAP_CACHE
    service = get_service()
    if _ADMIN_BOOTSTRAP_CACHE and _db_quick_lock_probe(str(service.settings.database_path)):
        cached = _cached_admin_bootstrap("database_locked_probe")
        if cached:
            return cached

    try:
        cases = service.store.list_cases()
        organizations = service.store.list_organizations()
        for case in cases:
            case["recipient_ids"] = service.store.case_recipient_ids(case["id"])
        common_model = service.selected_common_llm_model()
        case_model = service.selected_case_model1()
        payload = {
            "readiness": service.settings.readiness(),
            "settings": {
                "common_llm_model": common_model,
                "common_llm_models": service.configured_common_reserve_models(common_model),
                "llm_model": common_model,
                "llm_models": service.configured_common_reserve_models(common_model),
                "common_provider": service.model_role_status(service.selected_common_llm_model(), "common", probe=False),
                "groq": service.groq_status(probe=False),
                "case_llm_model": case_model,
                "case_llm_models": [case_model] if case_model else [],
                "openrouter": service.model_role_status(case_model, "case", probe=False),
                "case_model1": service.selected_case_model1(),
                "case_model1_provider": service.model_role_status(service.selected_case_model1(), "case", probe=False),
                "case_model2": service.selected_case_model2(),
                "case_model2_provider": service.model_role_status(service.selected_case_model2(), "case", probe=False),
                "case_single_model": service.selected_case_single_model(),
                "case_single_provider": service.model_role_status(service.selected_case_single_model(), "case", probe=False),
                "nvidia": service.nvidia_status(probe=False),
                "openai_shadow": service.shadow_status(),
                "common_fallback_llm_model": service.selected_common_fallback_model(),
                "common_fallback_llm_models": service.available_common_fallback_models(),
                "common_fallback_provider": service.model_role_status(service.selected_common_fallback_model(), "common", probe=False),
                "case_fallback_llm_model": service.selected_case_model2(),
                "case_fallback_llm_models": [service.selected_case_model2()],
                "case_fallback_provider": {**service.model_role_status(service.selected_case_model2(), "case", probe=False), "enabled": True},
                "case_fallback_enabled": True,
                "burst_llm_model": service.selected_common_turbo_model(),
                "burst_llm_models": service.available_burst_models(),
                "burst_provider": service.model_role_status(service.selected_common_turbo_model(), "common", probe=False),
                "burst_threshold": service.selected_burst_threshold(),
                "reserve1_llm_model": service.selected_reserve1_model(),
                "reserve1_llm_models": service.configured_common_reserve_models(service.selected_reserve1_model()),
                "reserve1_provider": service._status_for_switchable_llm_model(service.selected_reserve1_model(), probe=False),
                "cloudflare": service.cloudflare_status(probe=False),
                "reserve2_llm_model": service.selected_reserve2_model(),
                "reserve2_llm_models": service.available_reserve2_models(),
                "reserve2_provider": service._status_for_switchable_llm_model(service.selected_reserve2_model(), probe=False),
                "gemini": service.gemini_status(probe=False),
                "announcements": service.store.list_announcements(include_inactive=True),
                "embedding_model": service.selected_embedding_model(),
                "embedding_models": [service.selected_embedding_model()] if service.selected_embedding_model() else [],
                "ollama_embedding": service.ollama_embedding_status(probe=False),
                "case_batch_size": service.selected_case_batch_size(),
                "signup_auto_approve": service.store.signup_auto_approve_enabled(),
                "semantic_candidate_threshold": float(service.store.get_setting("semantic_candidate_threshold", "65")),
                "press_release_match_threshold": float(service.store.get_setting("press_release_match_threshold", str(service.settings.press_release_match_threshold))),
                "similar_article_threshold": float(service.store.get_setting("similar_article_threshold", "65")),
                "magazine_similarity_threshold": float(service.store.get_setting("magazine_similarity_threshold", "90")),
                "openai_shadow_enabled": service.shadow_enabled(),
                "openai_shadow_daily_limit": service.shadow_daily_limit(),
                "raw_retention_days": service.settings.raw_retention_days,
                "metadata_retention_days": service.settings.metadata_retention_days,
                "per_run_article_limit": service.settings.per_run_article_limit,
                "body_backfill": service.body_backfill_status(),
                "supabase_outbox": service.store.supabase_outbox_status(),
                "processing_summary": service.store.processing_summary(14),
                "supabase_seed": SupabaseSeed(service.store, service.mirror).status(),
                "supabase_daily_metrics": SupabaseDailyMetrics(service.store, service.mirror).status(),
                "press_rag": service.press_releases.status(),
                "supabase_reconcile": SupabaseReconciler(service.settings, service.store).status(),
            },
            "organizations": organizations,
            "cases": cases,
            "recipients": fast_recipient_statuses(service),
            "signup_requests": service.store.list_signup_requests(include_private=True),
        }
        _ADMIN_BOOTSTRAP_CACHE = _clone_payload(payload)
        return payload
    except sqlite3.OperationalError as error:
        if _is_db_locked_error(error):
            cached = _cached_admin_bootstrap("database_locked")
            if cached:
                return cached
        raise


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
        # Keep every page lightweight; the client asks for the next page only
        # after the article list itself is scrolled near its bottom.
        try:
            requested_limit = int(query.get("limit") or 15)
        except (TypeError, ValueError):
            requested_limit = 15
        try:
            requested_offset = int(query.get("offset") or 0)
        except (TypeError, ValueError):
            requested_offset = 0
        return public_dashboard(
            str(query.get("case_id") or ""),
            str(query.get("organization_id") or ""),
            [value for value in str(query.get("tags") or "").split(",") if value],
            str(query.get("q") or ""),
            include_groups=True,
            limit=max(5, min(30, requested_limit)),
            offset=max(0, requested_offset),
            delivery_filter=str(query.get("delivery_filter") or "all"),
            days=max(1, min(30, int(query.get("days") or 7))),
            include_press_stats=True,
        )

    if path == "/catalog" and method == "GET":
        organizations = [
            {"id": item["id"], "name": item["name"]}
            for item in service.store.list_organizations(active_only=True)
        ]
        cases = [
            {
                "id": item["id"],
                "name": item["name"],
                "organization_id": item.get("organization_id"),
                "sort_order": item.get("sort_order", 0),
            }
            for item in service.store.list_cases(active_only=True)
        ]
        return {"organizations": organizations, "cases": cases}

    if path == "/magazines" and method == "GET":
        publisher = MagazinePublisher(service.store)
        organization_id = str(query.get("organization_id") or "").strip()
        return {
            "organizations": [{"id": item["id"], "name": item["name"]} for item in service.store.list_organizations(active_only=True)],
            "items": publisher.editions(organization_id, int(query.get("limit") or 365)),
        }

    if path.startswith("/magazines/") and method == "GET":
        edition_id = path[len("/magazines/"):].strip("/")
        edition = MagazinePublisher(service.store).edition(edition_id)
        if not edition:
            raise MasterPressError("매거진 에디션을 찾지 못했습니다.", 404)
        return {"edition": edition}

    if path == "/signup/bootstrap" and method == "GET":
        return signup_bootstrap(admin_authenticated)

    if path == "/announcements/current" and method == "GET":
        return {"items": service.store.current_announcements()}

    if path == "/case-proposals" and method == "GET":
        return {"items": service.store.list_case_proposals(admin=admin_authenticated)}

    if path == "/case-proposals" and method == "POST":
        try:
            item = service.store.save_case_proposal(payload)
            return {"item": service.store.get_case_proposal(item["id"], admin=admin_authenticated), "items": service.store.list_case_proposals(admin=admin_authenticated)}
        except ValueError as error:
            raise MasterPressError(str(error)) from error

    if path.startswith("/case-proposals/"):
        proposal_id = path[len("/case-proposals/"):].strip("/")
        if method == "PUT":
            try:
                item = service.store.save_case_proposal(payload, proposal_id, password_required=not admin_authenticated)
                return {"item": service.store.get_case_proposal(item["id"], admin=admin_authenticated), "items": service.store.list_case_proposals(admin=admin_authenticated)}
            except ValueError as error:
                raise MasterPressError(str(error)) from error
        if method == "DELETE":
            try:
                if admin_authenticated:
                    # Admin hard-delete without knowing the user password.
                    with service.store.connect() as connection:
                        deleted = connection.execute("DELETE FROM case_proposals WHERE id=?", (proposal_id,)).rowcount > 0
                else:
                    deleted = service.store.delete_case_proposal(proposal_id, str(payload.get("password") or ""))
                if not deleted:
                    raise MasterPressError("케이스 신청 글을 찾지 못했습니다.", 404)
                return {"deleted": True, "items": service.store.list_case_proposals(admin=admin_authenticated)}
            except ValueError as error:
                raise MasterPressError(str(error)) from error

    if path == "/signup/kakao-registration" and method == "POST":
        invite, token = service.store.create_invite("구독 신청자", 1440)
        base = request_base.rstrip("/")
        invite["registration_url"] = f"{base}/poc/master-press/connect?invite={quote(token)}"
        return {"registration": invite}

    if path == "/signup/kakao-unsubscribe" and method == "POST":
        invite, token = service.store.create_invite(RECIPIENT_UNSUBSCRIBE_INVITE_LABEL, 15)
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
        magazine_slots = payload.get("magazine_slots", [])
        if not isinstance(magazine_slots, list): raise MasterPressError("매거진 에디션 선택값이 올바르지 않습니다.")
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
            magazine_slots,
        )
        _invalidate_admin_bootstrap_cache()
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
            article_limit=max(1, min(5000, int(query.get("article_limit") or 60))),
            include_detail=str(query.get("detail") or "") in {"1", "true", "yes"},
        )

    if path == "/delivery-trends" and method == "GET":
        organization_id = str(query.get("organization_id") or "").strip()
        return service.store.case_delivery_trends(organization_id or None, int(query.get("days") or 14))

    if path == "/press-releases" and method == "GET":
        limit = max(1, min(50, int(query.get("limit") or 20)))
        offset = max(0, int(query.get("offset") or 0))
        items = service.press_releases.list_releases(
            str(query.get("organization_id") or ""), limit + 1,
            str(query.get("q") or ""), offset,
        )
        return {
            "items": items[:limit], "offset": offset, "limit": limit,
            "has_more": len(items) > limit,
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

    if path == "/admin/shadow/disagreements" and method == "GET":
        _require_admin(admin_authenticated)
        return service.store.shadow_disagreements(int(query.get("limit") or 50))

    if path == "/admin/shadow/feedback" and method == "GET":
        _require_admin(admin_authenticated)
        return service.store.shadow_feedback_history(int(query.get("limit") or 100))

    if path.startswith("/admin/shadow/disagreements/") and method == "POST":
        _require_admin(admin_authenticated)
        suffix = path[len("/admin/shadow/disagreements/"):].strip("/").split("/")
        if len(suffix) == 2 and suffix[1] == "feedback":
            try:
                return {"feedback": service.store.save_shadow_feedback(suffix[0], payload.get("verdict"), payload.get("reason"), payload.get("comment"))}
            except ValueError as error:
                raise MasterPressError(str(error), 400)
        raise MasterPressError("그림자 판정 피드백 경로가 올바르지 않습니다.", 404)

    if path == "/admin/bootstrap" and method == "GET":
        _require_admin(admin_authenticated)
        return admin_bootstrap()

    if path.startswith("/admin/case-proposals/"):
        _require_admin(admin_authenticated)
        suffix = path[len("/admin/case-proposals/"):].strip("/").split("/")
        proposal_id = suffix[0]
        if len(suffix) == 1 and method == "GET":
            item = service.store.get_case_proposal(proposal_id, admin=True)
            if not item:
                raise MasterPressError("케이스 신청 글을 찾지 못했습니다.", 404)
            return {"item": item}
        if len(suffix) >= 2 and suffix[1] == "allow" and method == "POST":
            item = service.store.allow_case_proposal(proposal_id)
            if not item:
                raise MasterPressError("케이스 신청 글을 찾지 못했습니다.", 404)
            return {"item": item, "items": service.store.list_case_proposals(admin=True)}

    if path == "/admin/model-status" and method == "GET":
        _require_admin(admin_authenticated)
        target = str(query.get("target") or "").strip().lower()
        if target == "common":
            model = service.selected_common_llm_model()
            models = service.configured_common_reserve_models(model)
            return {"target": target, "common_llm_model": model, "common_llm_models": models, "llm_models": models, "common_provider": service.model_role_status(model, "common", probe=True)}
        if target == "case":
            model = service.selected_case_model1()
            return {"target": target, "case_llm_model": model, "case_llm_models": [model], "case_provider": service.model_role_status(model, "case", probe=True), "openrouter": service.model_role_status(model, "case", probe=False)}
        if target == "common_fallback":
            model = service.selected_common_fallback_model()
            return {"target": target, "common_fallback_llm_model": model, "common_fallback_llm_models": service.available_common_fallback_models(), "common_fallback_provider": service.model_role_status(model, "common", probe=True)}
        if target == "case_fallback":
            model = service.selected_case_model2()
            return {"target": target, "case_fallback_llm_model": model, "case_fallback_llm_models": [model], "case_fallback_provider": {**service.model_role_status(model, "case", probe=True), "enabled": True}}
        if target == "case_single":
            model = service.selected_case_single_model()
            return {"target": target, "case_single_model": model, "case_single_models": [model], "case_single_provider": service.model_role_status(model, "case", probe=True)}
        if target == "burst":
            model = service.selected_common_turbo_model()
            return {"target": target, "burst_llm_model": model, "burst_llm_models": [model], "burst_provider": service.model_role_status(model, "common", probe=True), "burst_threshold": service.selected_burst_threshold()}
        if target == "reserve1":
            model = service.selected_reserve1_model()
            return {"target": target, "reserve1_llm_model": model, "reserve1_llm_models": service.configured_common_reserve_models(model), "reserve1_provider": service._status_for_switchable_llm_model(model, probe=False)}
        if target == "reserve2":
            model = service.selected_reserve2_model()
            return {"target": target, "reserve2_llm_model": model, "reserve2_llm_models": service.available_reserve2_models(), "reserve2_provider": service._status_for_switchable_llm_model(model, probe=True), "gemini": service.gemini_status(probe=False)}
        if target == "embedding":
            model = service.selected_embedding_model()
            return {"target": target, "embedding_model": model, "embedding_models": service.available_embedding_models(), "ollama_embedding": service.ollama_embedding_status(probe=True)}
        raise MasterPressError("확인할 모델 영역을 찾지 못했습니다.", 404)

    if path == "/admin/case-keyword-suggestions" and method == "GET":
        _require_admin(admin_authenticated)
        raw_case_ids = [value.strip() for value in str(query.get("case_ids") or "").split(",") if value.strip()]
        if raw_case_ids:
            selected = {item["id"] for item in service.store.list_cases()}
            case_ids = [value for value in raw_case_ids if value in selected]
        else:
            case_ids = [item["id"] for item in service.store.list_cases()]
        days = int(query.get("days") or 30)
        limit = int(query.get("limit") or 5)
        items = [
            {
                "case_id": case_id,
                "sent_keyword_suggestions": service.store.case_sent_keyword_suggestions(case_id, days=days, limit=limit),
            }
            for case_id in case_ids
        ]
        return {"items": items}

    if path == "/admin/signup-requests/approve-pending" and method == "POST":
        _require_admin(admin_authenticated)
        result = service.store.approve_all_pending_signup_requests("관리자 일괄 승인")
        _invalidate_admin_bootstrap_cache()
        return result

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
            magazine_slots = payload.get("magazine_slots", [])
            if not isinstance(magazine_slots, list):
                raise MasterPressError("매거진 알림 선택값이 올바르지 않습니다.")
            try:
                request = service.store.set_signup_request_subscriptions(
                    request_id, case_ids, str(payload.get("admin_note") or "관리자 구독 조정"),
                    magazine_slots=magazine_slots,
                )
                _invalidate_admin_bootstrap_cache()
                return {"request": request}
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

    if path == "/admin/settings/signup-auto-approve" and method == "PUT":
        _require_admin(admin_authenticated)
        enabled = payload.get("enabled") is True
        service.store.set_setting("signup_auto_approve", "1" if enabled else "0")
        _invalidate_admin_bootstrap_cache()
        return {"signup_auto_approve": enabled}

    if path in {"/admin/settings/common-llm-model", "/admin/settings/llm-model"} and method == "PUT":
        _require_admin(admin_authenticated)
        model = str(payload.get("model") or "").strip()[:120]
        if not model:
            raise MasterPressError("공통분석 모델을 선택하세요.")
        models = service.available_common_llm_models()
        if models and model not in models:
            raise MasterPressError("현재 공통분석/예비1에서 지원하는 모델만 선택할 수 있습니다.")
        service.store.set_setting("common_llm_model", model)
        return {"common_llm_model": model, "common_llm_models": models, "common_provider": service._status_for_switchable_llm_model(model, probe=True), "cloudflare": service.cloudflare_status(probe=False), "groq": service.groq_status(probe=False), "openrouter": service.openrouter_status(probe=False)}

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

    if path == "/admin/settings/activate-primary-model" and method == "PUT":
        _require_admin(admin_authenticated)
        target = str(payload.get("target") or "").strip().lower()
        model = str(payload.get("model") or "").strip()[:160]
        if target == "common":
            models = service.available_common_llm_models()
            if not model or (models and model not in models):
                raise MasterPressError("공통분석 기본 모델을 선택하세요.")
            service.store.set_setting("common_llm_model", model)
            if bool(payload.get("force")):
                provider = service._provider_for_switchable_llm_model(model)
                service._clear_provider_quota_lock(provider)
                service.store.set_setting(f"llm_provider_temporary_until:{provider}", "")
                service.store.set_setting(f"llm_provider_temporary_reason:{provider}", "")
                service.store.set_setting(f"llm_provider_transient_failures:{provider}", "0")
                released = service.store.release_article_analysis_retries()
            else:
                released = {"pending_released": 0, "failed_requeued": 0}
            status = service._status_for_switchable_llm_model(model, probe=False)
        elif target == "case":
            models = service.available_case_llm_models()
            if not model or not model.endswith(":free") or (models and model not in models):
                raise MasterPressError("OpenRouter 무료 케이스 판정 모델을 선택하세요.")
            service.store.set_setting("case_llm_model", model)
            if bool(payload.get("force")):
                service._clear_provider_quota_lock("openrouter")
            status = service.openrouter_status(probe=False)
        else:
            raise MasterPressError("전환할 기본 모델 영역을 찾지 못했습니다.")
        waiting_until = str(status.get("disabled_until") or status.get("reset_at") or "") if status.get("exhausted") else ""
        return {"target": target, "model": model, "activated": not bool(waiting_until), "waiting_until": waiting_until, "provider": status, "released_jobs": released if target == "common" else {"pending_released": 0, "failed_requeued": 0}}

    if path == "/admin/settings/promote-reserve-model" and method == "PUT":
        _require_admin(admin_authenticated)
        reserve = str(payload.get("reserve") or "").strip()
        if reserve not in {"1", "2"}:
            raise MasterPressError("예비1 또는 예비2 모델만 기본 모델로 전환할 수 있습니다.")
        openrouter = service.openrouter_status(probe=False)
        if not openrouter.get("exhausted"):
            raise MasterPressError("예비 모델이 사용 중일 때만 기본 모델로 전환할 수 있습니다.")
        model = service.selected_reserve1_model() if reserve == "1" else service.selected_reserve2_model()
        if not model:
            raise MasterPressError("전환할 예비 모델을 찾지 못했습니다.")
        service.store.set_setting("common_llm_model", model)
        return {"common_llm_model": model, "reserve": reserve, "common_provider": service._status_for_switchable_llm_model(model, probe=True)}

    if path == "/admin/settings/reserve-llm-models" and method == "PUT":
        _require_admin(admin_authenticated)
        reserve1 = str(payload.get("reserve1_model") or "").strip()[:180]
        reserve2 = str(payload.get("reserve2_model") or "").strip()[:180]
        if not reserve1:
            raise MasterPressError("예비1 모델을 입력하세요.")
        if not reserve2:
            raise MasterPressError("예비2 모델을 입력하세요.")
        service.store.set_setting("reserve1_llm_model", reserve1)
        service.store.set_setting("reserve2_llm_model", reserve2)
        return {
            "reserve1_llm_model": reserve1, "reserve1_llm_models": service.available_reserve1_models(), "reserve1_provider": service._status_for_switchable_llm_model(reserve1, probe=True), "groq": service.groq_status(probe=False), "cloudflare": service.cloudflare_status(probe=False),
            "reserve2_llm_model": reserve2, "reserve2_llm_models": service.available_reserve2_models(), "reserve2_provider": service._status_for_switchable_llm_model(reserve2, probe=True), "gemini": service.gemini_status(probe=False),
        }

    if path == "/admin/settings/pipeline-models" and method == "PUT":
        _require_admin(admin_authenticated)
        common_fallback = str(payload.get("common_fallback_model") or "").strip()[:180]
        case_fallback = str(payload.get("case_fallback_model") or "").strip()[:180]
        burst = str(payload.get("burst_model") or "").strip()[:180]
        try:
            burst_threshold = int(payload.get("burst_threshold", 5))
        except (TypeError, ValueError):
            raise MasterPressError("업무집중 지원 대기 임계값을 확인하세요.")
        if common_fallback not in service.available_common_fallback_models():
            raise MasterPressError("공통분석 예비 모델은 확정된 Cloudflare 모델만 사용할 수 있습니다.")
        if case_fallback != service.selected_case_model2():
            raise MasterPressError("케이스 모델2는 NVIDIA gpt-oss-120b로 고정됩니다.")
        if burst != service.selected_common_turbo_model():
            raise MasterPressError("공통 Turbo는 OpenRouter 단건 모델로 고정됩니다.")
        if burst_threshold < 5 or burst_threshold > 100:
            raise MasterPressError("업무집중 지원 대기 임계값은 5~100건으로 설정하세요.")
        service.store.set_setting("common_fallback_llm_model", common_fallback)
        service.store.set_setting("case_fallback_llm_model", case_fallback)
        service.store.set_setting("burst_llm_model", burst)
        service.store.set_setting("burst_threshold", str(burst_threshold))
        return {
            "common_fallback_llm_model": common_fallback,
            "case_fallback_llm_model": case_fallback,
            "burst_llm_model": burst,
            "burst_threshold": burst_threshold,
            "common_fallback_provider": service._status_for_switchable_llm_model(common_fallback, probe=False),
            "case_fallback_provider": service._status_for_switchable_llm_model(case_fallback, probe=False),
            "burst_provider": service._status_for_switchable_llm_model(burst, probe=False),
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
        hard_delete = str(query.get("hard") or "").lower() in {"1", "true", "yes"}
        if not service.store.delete_announcement(item_id, hard=hard_delete):
            raise MasterPressError("공지사항을 찾지 못했습니다.", 404)
        return {"deleted": True, "hard_deleted": hard_delete, "items": service.store.list_announcements(include_inactive=True)}

    if path == "/admin/supabase-history" and method == "GET":
        _require_admin(admin_authenticated)
        try:
            limit = max(1, min(100, int(query.get("limit") or 20)))
        except (TypeError, ValueError):
            limit = 20
        case_id = str(query.get("case_id") or "").strip()
        remote_items = service.mirror.recent_score_history(limit, case_id)
        remote_status = service.mirror.history_read_status()
        if remote_items is not None:
            return {"source": "supabase", "read_source": remote_status["source"], "read_status": remote_status,
                    "items": remote_items, "latency_ms": service.mirror.last_duration_ms}
        with service.store.connect() as connection:
            where, params = ("WHERE s.case_id=?", [case_id]) if case_id else ("", [])
            rows = connection.execute(
                f"""SELECT s.id,s.article_id,s.case_id,s.final_score,s.summary,s.organization_tag,s.article_type,s.decision,s.created_at,
                           a.title,a.publisher,a.published_at,a.original_url
                    FROM article_scores s JOIN articles a ON a.id=s.article_id
                    {where} ORDER BY s.created_at DESC LIMIT ?""", (*params, limit)
            ).fetchall()
        return {"source": "sqlite_fallback", "read_source": remote_status["source"], "read_status": remote_status,
                "items": [dict(row) for row in rows], "latency_ms": service.mirror.last_duration_ms, "error": service.mirror.last_error}

    if path == "/admin/supabase-seed/control" and method == "POST":
        _require_admin(admin_authenticated)
        seed = SupabaseSeed(service.store, service.mirror)
        action = str(payload.get("action") or "").strip().lower()
        if action == "pause":
            return {"supabase_seed": seed.pause(), "supabase_outbox": service.store.supabase_outbox_status()}
        if action == "continue":
            return {"supabase_seed": seed.continue_next_stage(), "supabase_outbox": service.store.supabase_outbox_status()}
        raise MasterPressError("동기화 제어 동작을 찾지 못했습니다.", 400)

    if path == "/admin/supabase-daily-metrics/control" and method == "POST":
        _require_admin(admin_authenticated)
        metrics = SupabaseDailyMetrics(service.store, service.mirror)
        action = str(payload.get("action") or "").strip().lower()
        if action == "enable":
            if payload.get("schema_applied") is not True:
                raise MasterPressError("Supabase 스키마 적용을 확인한 뒤 활성화할 수 있습니다.")
            service.store.set_setting(metrics.ENABLED_KEY, "1")
            return {"supabase_daily_metrics": metrics.status(), "result": metrics.run_once(),
                    "supabase_outbox": service.store.supabase_outbox_status()}
        if action == "disable":
            service.store.set_setting(metrics.ENABLED_KEY, "0")
            return {"supabase_daily_metrics": metrics.status(), "supabase_outbox": service.store.supabase_outbox_status()}
        if action == "run":
            return {"supabase_daily_metrics": metrics.status(), "result": metrics.run_once(),
                    "supabase_outbox": service.store.supabase_outbox_status()}
        raise MasterPressError("분석 이력 동기화 제어 동작을 찾지 못했습니다.", 400)

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

    if path == "/admin/settings/analysis-thresholds" and method == "PUT":
        _require_admin(admin_authenticated)
        try:
            batch_size = max(1, min(10, int(payload.get("batch_size", 10))))
            semantic_threshold = max(0.0, min(100.0, float(payload.get("semantic_candidate_threshold", 65))))
            press_threshold = max(0.0, min(100.0, float(payload.get("press_release_match_threshold", 65))))
            similar_threshold = max(0.0, min(100.0, float(payload.get("similar_article_threshold", 65))))
            shadow_enabled = bool(payload.get("openai_shadow_enabled", True))
            shadow_daily_limit = max(1, min(1000, int(payload.get("openai_shadow_daily_limit", service.shadow_daily_limit()))))
            magazine_threshold = max(70.0, min(99.0, float(payload.get("magazine_similarity_threshold", 90))))
        except (TypeError, ValueError):
            raise MasterPressError("분석 기준 값이 올바르지 않습니다.")
        for key, value in (
            ("case_batch_size", batch_size), ("semantic_candidate_threshold", semantic_threshold),
            ("press_release_match_threshold", press_threshold), ("similar_article_threshold", similar_threshold),
            ("magazine_similarity_threshold", magazine_threshold),
            ("openai_shadow_enabled", "1" if shadow_enabled else "0"),
            ("openai_shadow_daily_limit", shadow_daily_limit),
        ):
            service.store.set_setting(key, str(value))
        _invalidate_admin_bootstrap_cache()
        return {
            "case_batch_size": batch_size, "semantic_candidate_threshold": semantic_threshold,
            "press_release_match_threshold": press_threshold, "similar_article_threshold": similar_threshold,
            "magazine_similarity_threshold": magazine_threshold, "openai_shadow_enabled": shadow_enabled,
            "openai_shadow_daily_limit": shadow_daily_limit, "openai_shadow": service.shadow_status(),
        }

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

    if path.startswith("/analysis/"):
        suffix = path[len("/analysis/"):].split("/")
        if len(suffix) >= 3 and suffix[2] == "report" and method == "GET":
            return {
                **service.analysis_report(suffix[0], suffix[1]),
                "llm_models": service.available_case_llm_models(),
                "selected_llm_model": service.selected_case_llm_model(),
            }
        if len(suffix) >= 3 and suffix[2] == "feedback" and method == "POST":
            article_id, case_id = suffix[0], suffix[1]
            reasons = payload.get("reasons")
            comment = str(payload.get("comment") or "").strip()[:1000]
            if not isinstance(reasons, list) or not reasons:
                raise MasterPressError("피드백 사유를 하나 이상 선택하세요.", 400)
            saved = []
            for reason in dict.fromkeys(str(item or "").strip() for item in reasons):
                if not reason:
                    continue
                saved.append(service.store.save_analysis_feedback(article_id, case_id, reason, comment))
            return {"saved": len(saved), "feedback": service.store.analysis_feedback_summary(article_id, case_id)}

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
        if len(suffix) >= 3 and suffix[2] == "feedback" and method == "POST":
            article_id, case_id = suffix[0], suffix[1]
            reasons = payload.get("reasons")
            comment = str(payload.get("comment") or "").strip()[:1000]
            if not isinstance(reasons, list) or not reasons:
                raise MasterPressError("피드백 사유를 하나 이상 선택하세요.", 400)
            saved = []
            for reason in dict.fromkeys(str(item or "").strip() for item in reasons):
                if not reason:
                    continue
                saved.append(service.store.save_analysis_feedback(article_id, case_id, reason, comment))
            return {"saved": len(saved), "feedback": service.store.analysis_feedback_summary(article_id, case_id)}
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

    if path == "/admin/operation-logs" and method == "GET":
        _require_admin(admin_authenticated)
        return service.store.operation_logs(int(query.get("days") or 7), int(query.get("limit") or 1000))

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
        if action == "feedback-analysis" and method == "GET":
            try:
                case = service.store.get_case(case_id)
                if not case:
                    raise MasterPressError("케이스를 찾지 못했습니다.", 404)
                feedback_summary = service.store.analysis_feedback_summary(None, case_id)
                # Generate feedback-based guidance
                if feedback_summary.get("total", 0) > 0:
                    guidance = _generate_feedback_guidance(case, feedback_summary)
                    if guidance:
                        feedback_summary["guidance"] = guidance
                return {"feedback": feedback_summary, "case": case}
            except Exception as error:
                raise MasterPressError(str(error), 500)

    if path == "/admin/invites" and method == "POST":
        _require_admin(admin_authenticated)
        invite, token = service.store.create_invite(payload.get("label", ""), int(payload.get("ttl_minutes", 60)))
        base = request_base.rstrip("/")
        invite["url"] = f"{base}/poc/master-press/connect?invite={quote(token)}"
        return {"invite": invite}

    if path.startswith("/admin/magazines/") and method == "POST":
        _require_admin(admin_authenticated)
        suffix = path[len("/admin/magazines/"):].strip("/").split("/")
        edition_id = suffix[0] if suffix else ""
        action = suffix[1] if len(suffix) > 1 else ""
        try:
            if action == "republish":
                return service.republish_magazine(edition_id)
            if action == "resend":
                return service.resend_magazine(edition_id)
        except ValueError as error:
            raise MasterPressError(str(error)) from error

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
        if action == "magazine-test" and method == "POST":
            try:
                return service.resend_recent_magazines(recipient_id, 3)
            except ValueError as error:
                raise MasterPressError(str(error)) from error

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
    service = get_service()
    invite = service.store.valid_invite(state)
    if invite and invite.get("label") == RECIPIENT_UNSUBSCRIBE_INVITE_LABEL:
        result = service.kakao.complete_unsubscribe_authorization(code, state)
        result["_oauth_action"] = "unsubscribe"
        _invalidate_admin_bootstrap_cache()
        return result
    return service.kakao.complete_authorization(code, state)


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


def _generate_feedback_analysis_prompt(case: dict, feedback_summary: dict) -> str:
    """Generate a prompt for feedback-based case analysis."""
    case_name = case.get("name", "케이스")
    total_feedback = feedback_summary.get("total", 0)
    breakdown = feedback_summary.get("breakdown", [])
    
    feedback_reasons = "\n".join([
        f"- {reason.get('reason', 'unknown')}: {reason.get('count', 0)}건"
        for reason in breakdown[:10]
    ]) if breakdown else "피드백 없음"
    
    recent_comments = "\n".join([
        f"- {comment.get('comment', '')}"
        for comment in feedback_summary.get("recent_comments", [])[:3]
    ]) if feedback_summary.get("recent_comments") else "최근 코멘트 없음"
    
    prompt = f"""
다음 케이스의 판정 결과에 대해 사용자들로부터 받은 피드백을 분석하고, 개선 방안을 제시해주세요.

케이스: {case_name}
전체 피드백: {total_feedback}건

주요 피드백 사유:
{feedback_reasons}

최근 코멘트:
{recent_comments}

위 피드백을 분석하여 이 케이스의 판정 기준 개선에 도움이 될 만한 조언을 3-5개 항목으로 정리해 주세요.
각 항목은 "- "로 시작하고, 구체적이고 실행 가능한 개선 사항이어야 합니다.
"""
    return prompt.strip()


def _generate_feedback_guidance(case: dict, feedback_summary: dict) -> list:
    """Generate actionable guidance based on feedback patterns."""
    guidance = []
    breakdown = feedback_summary.get("breakdown", [])
    total = feedback_summary.get("total", 0)
    
    # Analyze feedback patterns and generate guidance
    if breakdown:
        top_reasons = breakdown[:3]
        
        # Reason-specific guidance
        reason_guidance_map = {
            "expected_send": "실제로 포함해야 한다는 평가가 누적되었습니다. 누락된 기사의 공통 조건을 분석하세요.",
            "expected_exclude": "실제로 제외해야 한다는 평가가 누적되었습니다. 과대 매칭 패턴을 제외 기준에 반영하세요.",
            "topic_or_target_error": "케이스의 주제와 대상 정의를 더 명확하게 구분해보세요.",
            "condition_or_keyword_error": "필수 조건과 키워드·동의어 범위를 재검토하세요.",
            "context_or_subject_error": "단순 언급과 핵심 주체를 구분하는 맥락 판정을 보강하세요.",
            "stance_error": "어조·긍부정 판단 근거와 예외를 프롬프트에 추가하세요.",
            "evidence_or_body_error": "본문 수집 상태와 근거 문장 판정 과정을 점검하세요.",
            "required_terms_missing": "필수 키워드 검사 기준을 재검토하세요. 본문에서 핵심 키워드가 명시적으로 나타나는지 확인하는 로직을 강화할 수 있습니다.",
            "include_terms_missing": "포함 키워드 기준을 더 정교하게 설정하세요. 주제 관련 동의어나 표현을 추가로 인식하도록 조정할 수 있습니다.",
            "topic_target_not_verified": "대상 기관이나 인물이 기사의 중심인지 판단하는 기준을 강화해보세요. 단순 언급이 아닌 주요 행위자인지 확인하는 로직이 필요할 수 있습니다.",
            "llm_insufficient_relevance": "LLM 판정 임계값을 조정하거나, 추가 컨텍스트 정보를 제공하면 판정 정확도를 높일 수 있습니다.",
            "body_unavailable": "기사 본문 수집 과정을 점검하세요. 페이로드나 API 오류로 본문을 완전히 확보하지 못하는 경우가 있는지 확인하세요.",
        }
        
        for reason_item in top_reasons:
            reason = reason_item.get("reason", "")
            count = reason_item.get("count", 0)
            if reason in reason_guidance_map:
                guidance.append(reason_guidance_map[reason])
        
        # Pattern-based guidance
        if total >= 10:
            guidance.append(f"피드백이 {total}건 이상으로 많습니다. 이 케이스의 판정 기준을 전반적으로 재검토하는 것을 권장합니다.")
    
    # Default guidance if no breakdown
    if not guidance:
        guidance = [
            "사용자 피드백을 정기적으로 검토하여 판정 기준 개선에 반영하세요.",
            "케이스의 핵심 조건(필수 키워드, 대상, 어조)이 명확히 정의되어 있는지 확인하세요.",
            "새로운 판정 규칙을 적용할 때는 과거 피드백 데이터를 함께 검토하면 좋습니다.",
        ]
    
    return guidance[:5]  # Return top 5 guidance items
