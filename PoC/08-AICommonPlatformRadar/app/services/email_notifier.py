from __future__ import annotations

import smtplib
from email.message import EmailMessage
from zoneinfo import ZoneInfo

from ..models import ActionItem, Notice
from .runtime_settings import load_runtime_settings


def send_opinion_submitted_notification(notice: Notice, action: ActionItem, opinion_content: str) -> dict:
    # Defense in depth: even an internal caller must never send a notification
    # for a sample row or a bid notice. G2B opinion registration belongs only
    # to real prior-specification notices.
    if notice.stage != "prenotice":
        return {"sent": False, "reason": "not_prenotice"}
    if (notice.notice_no or "").upper().startswith("SAMPLE-"):
        return {"sent": False, "reason": "sample_notice"}
    config = load_runtime_settings()["notifications"]
    recipients = [str(item).strip() for item in config.get("recipients", []) if str(item).strip()]
    sender = config.get("from_email") or config.get("smtp_username")
    if not config.get("enabled") or not recipients:
        return {"sent": False, "reason": "disabled"}
    if not config.get("smtp_host") or not sender:
        return {"sent": False, "reason": "smtp_not_configured"}

    message = EmailMessage()
    submitted_at = action.contacted_at
    if submitted_at:
        if submitted_at.tzinfo is None:
            submitted_at = submitted_at.replace(tzinfo=ZoneInfo("UTC"))
        submitted_at = submitted_at.astimezone(ZoneInfo("Asia/Seoul"))
    submitted_label = submitted_at.strftime("%Y-%m-%d %H:%M KST") if submitted_at else "기록 없음"
    message["Subject"] = f"[조달췤!] 사전규격 의견 등록 · {notice.title}"
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    message.set_content(
        "\n".join([
            f"대상 사업: {notice.title}",
            f"기관: {notice.agency_name}",
            f"공고번호: {notice.notice_no}",
            f"단계: {'사전규격' if notice.stage == 'prenotice' else '본공고'}",
            "조치 상태: 조치중 · 의견 등록",
            f"의견 등록 확인 시각: {submitted_label}",
            f"공고 링크: {notice.url or '기록 없음'}",
            "",
            "사전규격 의견 등록 내용",
            opinion_content or "기록 없음",
        ])
    )
    with smtplib.SMTP(config["smtp_host"], int(config.get("smtp_port") or 587), timeout=15) as client:
        if config.get("use_tls", True):
            client.starttls()
        if config.get("smtp_username"):
            client.login(config["smtp_username"], config.get("smtp_password", ""))
        client.send_message(message)
    return {"sent": True, "recipients": len(recipients)}
