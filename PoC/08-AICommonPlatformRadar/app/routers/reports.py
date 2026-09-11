from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..schemas import ReportRequest
from ..services.report_builder import build_daily_report


router = APIRouter()


@router.get("/reports/daily", response_class=HTMLResponse)
def report_page(request: Request, report_date: date | None = None, db: Session = Depends(get_db)):
    artifact = build_daily_report(db, report_date)
    markdown = Path(artifact.markdown_path).read_text(encoding="utf-8")
    return request.app.state.templates.TemplateResponse(request, "daily_report.html", {"artifact": artifact, "markdown": markdown})


@router.get("/api/reports/daily")
def report_api(report_date: date | None = None, db: Session = Depends(get_db)):
    artifact = build_daily_report(db, report_date)
    return {"date": artifact.report_date, "summary": artifact.summary, "markdown": Path(artifact.markdown_path).read_text(encoding="utf-8")}


@router.post("/api/reports/daily/generate")
def generate_report(payload: ReportRequest, db: Session = Depends(get_db)):
    artifact = build_daily_report(db, payload.report_date)
    return {"date": artifact.report_date, "summary": artifact.summary, "markdown_path": artifact.markdown_path, "html_path": artifact.html_path}


@router.get("/api/reports/daily/download/{report_date}/{format_name}")
def download_report(report_date: date, format_name: str, db: Session = Depends(get_db)):
    if format_name not in {"md", "html"}:
        raise HTTPException(400, "md 또는 html만 지원합니다.")
    artifact = build_daily_report(db, report_date)
    path = artifact.markdown_path if format_name == "md" else artifact.html_path
    media = "text/markdown" if format_name == "md" else "text/html"
    return FileResponse(path, media_type=media, filename=Path(path).name)
