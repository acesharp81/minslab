from __future__ import annotations

import json
import secrets
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import AuditLog
from ..schemas import AdminPasswordChange, NotificationSettingsPatch, OpinionSenderProfile
from ..services.opinion_guidance import load_opinion_sender_profile, save_opinion_sender_profile
from ..services.runtime_settings import (
    change_admin_password,
    create_admin_session,
    public_notification_settings,
    update_notification_settings,
    verify_admin_password,
    verify_admin_session,
)


router = APIRouter()
COOKIE_NAME = "poc08_admin_session"


def settings_authorized(request: Request) -> bool:
    if verify_admin_session(request.cookies.get(COOKIE_NAME, "")):
        return True
    expected = get_settings().proxy_token
    supplied = request.headers.get("x-poc08-proxy-token", "")
    return bool(expected and supplied and secrets.compare_digest(expected, supplied))


@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, db: Session = Depends(get_db)):
    if not settings_authorized(request):
        return request.app.state.templates.TemplateResponse(
            request, "settings_login.html", {"admin_username": get_settings().admin_username or "admin"},
        )
    rows = db.scalars(
        select(AuditLog).where(AuditLog.event_type == "classification_error_report")
        .order_by(AuditLog.created_at.desc()).limit(200)
    ).all()
    reports = []
    for row in rows:
        try:
            detail = json.loads(row.detail_json or "{}")
        except json.JSONDecodeError:
            detail = {}
        reports.append({"row": row, "detail": detail})
    return request.app.state.templates.TemplateResponse(request, "settings.html", {
        "profile": load_opinion_sender_profile(),
        "notifications": public_notification_settings(),
        "error_reports": reports,
        "admin_username": get_settings().admin_username or "admin",
    })


@router.post("/settings/login")
async def settings_login(request: Request):
    values = parse_qs((await request.body()).decode("utf-8", errors="replace"))
    username = (values.get("username") or [""])[0]
    password = (values.get("password") or [""])[0]
    if not verify_admin_password(username, password):
        return request.app.state.templates.TemplateResponse(
            request, "settings_login.html",
            {"admin_username": get_settings().admin_username or "admin", "login_error": "아이디 또는 암호가 올바르지 않습니다."},
            status_code=401,
        )
    response = RedirectResponse(request.url_for("settings_page"), status_code=303)
    response.set_cookie(
        COOKIE_NAME, create_admin_session(username), max_age=12 * 60 * 60,
        httponly=True, secure=request.url.scheme == "https", samesite="lax",
    )
    return response


@router.post("/settings/logout")
def settings_logout(request: Request):
    response = RedirectResponse(request.url_for("settings_page"), status_code=303)
    response.delete_cookie(COOKIE_NAME)
    return response


@router.get("/settings/opinion-sender")
def legacy_opinion_sender_settings(request: Request):
    return RedirectResponse(request.url_for("settings_page"), status_code=307)


@router.get("/api/settings/opinion-sender")
def opinion_sender_settings_api(request: Request):
    if not settings_authorized(request):
        raise HTTPException(401, "설정 로그인이 필요합니다.")
    return load_opinion_sender_profile()


@router.put("/api/settings/opinion-sender")
def update_opinion_sender_settings(profile: OpinionSenderProfile, request: Request):
    if not settings_authorized(request):
        raise HTTPException(401, "설정 로그인이 필요합니다.")
    return save_opinion_sender_profile(profile)


@router.get("/api/settings/notifications")
def notification_settings_api(request: Request):
    if not settings_authorized(request):
        raise HTTPException(401, "설정 로그인이 필요합니다.")
    return public_notification_settings()


@router.put("/api/settings/notifications")
def update_notification_settings_api(patch: NotificationSettingsPatch, request: Request):
    if not settings_authorized(request):
        raise HTTPException(401, "설정 로그인이 필요합니다.")
    values = patch.model_dump()
    values["recipients"] = list(dict.fromkeys(item.strip() for item in values["recipients"] if item.strip()))
    return update_notification_settings(values)


@router.put("/api/settings/admin-password")
def update_admin_password(patch: AdminPasswordChange):
    username = get_settings().admin_username or "admin"
    if not verify_admin_password(username, patch.current_password):
        raise HTTPException(400, "현재 암호가 올바르지 않습니다.")
    change_admin_password(patch.new_password)
    return {"updated": True}
