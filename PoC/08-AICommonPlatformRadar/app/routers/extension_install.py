from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse

from ..config import get_settings


router = APIRouter()


@router.get("/extension/install", response_class=HTMLResponse)
def extension_install_page(request: Request):
    return request.app.state.templates.TemplateResponse(request, "extension_install.html", {})


@router.get("/extension/download")
def extension_download():
    archive = get_settings().project_root / "dist" / "jodalcheck-g2b-helper.zip"
    if not archive.is_file():
        raise HTTPException(503, "확장프로그램 설치 파일이 아직 준비되지 않았습니다.")
    return FileResponse(
        archive, media_type="application/zip", filename="jodalcheck-g2b-helper.zip",
    )
