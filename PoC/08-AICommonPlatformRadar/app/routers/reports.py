from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..schemas import ReportRequest
from ..services.report_builder import build_daily_report, get_daily_report
from ..services.statistics_builder import build_statistics


router = APIRouter()


@router.get("/reports/daily", response_class=HTMLResponse)
def report_page(
    request: Request, report_date: date | None = None, period: str = "30d",
    db: Session = Depends(get_db),
):
    return request.app.state.templates.TemplateResponse(
        request, "daily_report.html", {"stats": build_statistics(db, period=period)},
    )


@router.get("/api/statistics")
def statistics_api(period: str = "30d", db: Session = Depends(get_db)):
    return build_statistics(db, period=period)


@router.get("/api/reports/daily")
def report_api(report_date: date | None = None, db: Session = Depends(get_db)):
    artifact = get_daily_report(db, report_date)
    return artifact.as_dict(include_markdown=True)


@router.post("/api/reports/daily/generate")
def generate_report(payload: ReportRequest, db: Session = Depends(get_db)):
    artifact = build_daily_report(db, payload.report_date, finalized=True)
    return artifact.as_dict()


@router.get("/api/reports/daily/download/{report_date}/{format_name}")
def download_report(report_date: date, format_name: str, db: Session = Depends(get_db)):
    if format_name not in {"md", "html", "json"}:
        raise HTTPException(400, "md, html 또는 json만 지원합니다.")
    artifact = get_daily_report(db, report_date)
    paths = {"md": artifact.markdown_path, "html": artifact.html_path, "json": artifact.json_path}
    media_types = {"md": "text/markdown", "html": "text/html", "json": "application/json"}
    path = paths[format_name]
    media = media_types[format_name]
    return FileResponse(path, media_type=media, filename=Path(path).name)
