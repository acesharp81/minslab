#!/usr/bin/env python3
"""정의서.md · 번들-어댑터-정의서.md → HTML → PDF. 개발 전용: `markdown` 패키지와 Chrome이 필요하다.

  .venv/bin/python tools/build_docs_pdf.py
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC_DIR = ROOT / "docs" / "data-interface"
MD = DOC_DIR / "정의서.md"
PDF = DOC_DIR / "정의서.pdf"
DOCS = [(MD, PDF), (DOC_DIR / "번들-어댑터-정의서.md", DOC_DIR / "번들-어댑터-정의서.pdf")]   # 팀원에게 보내는 두 문서
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

CSS = """
@page { size: A4; margin: 18mm 16mm; }
body { font-family: 'Apple SD Gothic Neo','Noto Sans KR','Malgun Gothic',sans-serif; font-size: 10.5pt; line-height: 1.55; color: #1a1a1a; }
h1 { font-size: 20pt; border-bottom: 2px solid #333; padding-bottom: 6px; }
h2 { font-size: 14.5pt; margin-top: 22px; border-bottom: 1px solid #bbb; padding-bottom: 3px; page-break-after: avoid; }
h3, h4 { page-break-after: avoid; }
table { border-collapse: collapse; width: 100%; margin: 8px 0; font-size: 9pt; }
tr { page-break-inside: avoid; }
th, td { border: 1px solid #bbb; padding: 3px 6px; vertical-align: top; text-align: left; }
th { background: #f0f0f0; }
code { font-family: 'SF Mono', Menlo, Consolas, monospace; font-size: 0.92em; background: #f4f4f4; padding: 0 3px; border-radius: 2px; }
pre { background: #f4f4f4; padding: 8px 10px; font-size: 9pt; line-height: 1.4; page-break-inside: avoid; white-space: pre-wrap; }
pre code { background: none; padding: 0; }
"""


def render_html(md_text: str, title: str) -> str:
    import markdown  # 개발 전용 의존성이라 필요할 때만 불러온다

    body = markdown.markdown(md_text, extensions=["tables", "fenced_code"])
    return (f"<!doctype html><html lang=\"ko\"><head><meta charset=\"utf-8\"><title>{title}</title>"
            f"<style>{CSS}</style></head><body>{body}</body></html>")


def _pdf_is_complete(path: Path) -> bool:
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return False
    return data.startswith(b"%PDF") and b"%%EOF" in data[-1024:]


def print_html_to_pdf(html_path: Path | str, pdf_path: Path | str, chrome: str = CHROME, timeout: float = 120) -> None:
    """Chrome 헤드리스로 HTML을 PDF로 인쇄한다.

    Chrome 154는 PDF를 다 쓰고도 프로세스가 종료되지 않는다. 그래서 종료를 기다리지 않고
    PDF가 완성되면(끝에 %%EOF, 크기가 0.5초간 그대로) Chrome을 직접 종료한다.
    """
    pdf_path = Path(pdf_path)
    pdf_path.unlink(missing_ok=True)  # 예전 PDF를 새 것으로 착각하지 않게 먼저 지운다
    with tempfile.TemporaryDirectory() as profile:
        proc = subprocess.Popen(
            [chrome, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
             f"--user-data-dir={profile}", f"--print-to-pdf={pdf_path}", Path(html_path).resolve().as_uri()],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        try:
            deadline = time.monotonic() + timeout
            last_size, steady = -1, 0
            while time.monotonic() < deadline:
                if _pdf_is_complete(pdf_path):
                    size = pdf_path.stat().st_size
                    steady = steady + 1 if size == last_size else 0
                    last_size = size
                    if steady >= 2:
                        return
                elif proc.poll() is not None:
                    raise RuntimeError(f"Chrome이 PDF를 만들지 않고 종료함 (종료 코드 {proc.returncode})")
                time.sleep(0.25)
            raise TimeoutError(f"{timeout:g}초 안에 PDF가 완성되지 않음")
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()


def build_pdf(md_path: Path = MD, pdf_path: Path = PDF, chrome: str = CHROME) -> None:
    html = render_html(Path(md_path).read_text(encoding="utf-8"), Path(md_path).stem)
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "doc.html"
        page.write_text(html, encoding="utf-8")
        print_html_to_pdf(page, pdf_path, chrome=chrome)


def main() -> int:
    if not Path(CHROME).exists():
        print(f"오류: Chrome을 찾지 못함: {CHROME}")
        return 2
    for md, pdf in DOCS:
        build_pdf(md, pdf)
        print(f"생성: {pdf}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
