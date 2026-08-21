"""Firefox E2E for PDF-backed Data MCP build, retrieval, install, and chat execution."""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.support.ui import WebDriverWait


URL = os.getenv("AIWORKS_BROWSER_URL", "http://127.0.0.1:8000/poc/aiworks/")
GECKODRIVER = os.getenv("AIWORKS_GECKODRIVER", "/snap/bin/geckodriver")
ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("AIWORKS_DB_PATH", str(ROOT.parent / "data" / "aiworks.sqlite3")))


def wait_for(driver, expression: str, timeout: int = 45):
    return WebDriverWait(driver, timeout).until(
        lambda current: current.execute_script(f"return Boolean({expression})")
    )


def set_value(driver, element_id: str, value: str):
    node = driver.find_element(By.ID, element_id)
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'}); arguments[0].focus()", node)
    try:
        node.clear()
        node.send_keys(value)
    except Exception as error:
        detail = driver.execute_script(
            """const n=arguments[0], r=n.getBoundingClientRect(), s=getComputedStyle(n);
            return {display:s.display,visibility:s.visibility,width:r.width,height:r.height,
              x:r.x,y:r.y,disabled:n.disabled,hidden:n.hidden,
              parentHidden:Boolean(n.closest('[hidden]')),view:document.querySelector('.module-view.active')?.id};""", node)
        raise AssertionError(f"{element_id} is not interactable: {detail}") from error


def approve(driver):
    wait_for(driver, "document.querySelector('#approvalDialog').open")
    driver.execute_script("document.querySelector('#approvalDialog').close('approve')")
    wait_for(driver, "!document.querySelector('#approvalDialog').open")


def searchable_budget_pdf() -> bytes:
    stream = b"BT /F1 12 Tf 72 720 Td (Budget policy total amount is 1,234 million won for 2027.) Tj 0 -24 Td (Digital government investment is 420 million won.) Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    content = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(content))
        content.extend(f"{index} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = len(content)
    content.extend(f"xref\n0 {len(objects) + 1}\n".encode() + b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        content.extend(f"{offset:010d} 00000 n \n".encode())
    content.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(content)


def cleanup_test_package(package_id: str) -> None:
    if not package_id.startswith("org.browser-budget-rag-") or not DB_PATH.is_file():
        return
    with sqlite3.connect(DB_PATH) as db:
        draft_ids = [
            row[0]
            for row in db.execute(
                "SELECT id FROM mcp_drafts WHERE json_extract(manifest_json, '$.id')=?",
                (package_id,),
            )
        ]
        db.execute("DELETE FROM mcp_installations WHERE package_id=?", (package_id,))
        for table in ("mcp_capabilities", "mcp_reference_chunks", "mcp_package_files"):
            db.execute(f"DELETE FROM {table} WHERE package_id=?", (package_id,))
        db.execute("DELETE FROM mcp_packages WHERE package_id=?", (package_id,))
        if draft_ids:
            placeholders = ",".join("?" for _ in draft_ids)
            db.execute(
                f"DELETE FROM mcp_draft_references WHERE draft_id IN ({placeholders})",
                draft_ids,
            )
            db.execute(f"DELETE FROM mcp_drafts WHERE id IN ({placeholders})", draft_ids)


def main():
    if not Path(GECKODRIVER).exists():
        raise SystemExit(f"geckodriver not found: {GECKODRIVER}")
    package_id = f"org.browser-budget-rag-{os.getpid()}"
    pdf_path = None
    options = Options()
    options.add_argument("-headless")
    driver = webdriver.Firefox(options=options, service=Service(GECKODRIVER))
    try:
        with tempfile.NamedTemporaryFile(dir=ROOT, suffix="-budget-policy.pdf", delete=False) as target:
            target.write(searchable_budget_pdf())
            pdf_path = Path(target.name)
        driver.set_window_size(1536, 1100)
        driver.get(URL)
        wait_for(driver, "document.querySelector('.local-badge').textContent.includes('v0.30.0')")
        wait_for(driver, "document.querySelector('[data-select-project=\"project-default\"]')")
        driver.execute_script("document.querySelector('[data-select-project=\"project-default\"]').click()")
        wait_for(driver, "!document.querySelector('#workbench').hidden || !document.querySelector('#welcomeTask').hidden")
        if driver.execute_script("return !document.querySelector('#welcomeTask').hidden"):
            driver.execute_script("document.querySelector('#enterDemo').click()")
        wait_for(driver, "document.querySelector('#workbench').hidden === false")
        driver.execute_script("document.querySelector(\"[data-view='builder']\").click()")
        wait_for(driver, "document.querySelector('#builderView').classList.contains('active')")
        wait_for(driver, "document.querySelector('.mcp-studio-page') !== null")
        driver.execute_script("document.querySelector(\"[data-builder-type='data']\").click()")
        wait_for(driver, "document.querySelector('#builderRagLab').hidden === false")
        if not driver.find_element(By.ID, "sourceIncluded").is_selected():
            raise AssertionError("Data MCP must include its indexed source by default")
        set_value(driver, "mcpPackageId", package_id)
        driver.find_element(By.ID, "generateManifest").click()
        wait_for(driver, "document.querySelector('#manifestPreview').textContent.includes('local-rag')")
        wait_for(driver, "document.querySelector('#builderView').classList.contains('active')")
        driver.find_element(By.ID, "referenceFile").send_keys(str(pdf_path))
        wait_for(driver, "document.querySelector('#referenceList').textContent.includes('RAG 준비')")
        wait_for(driver, "document.querySelector('#builderRagLab').hidden === false")
        wait_for(driver, "document.querySelector('#builderView').classList.contains('active')")
        wait_for(driver, "document.querySelector('#runDraftRag').disabled === false")
        set_value(driver, "draftRagQuery", "Budget policy total amount")
        driver.find_element(By.ID, "runDraftRag").click()
        wait_for(driver, "document.querySelector('#draftRagResult').textContent.includes('1,234 million won')")
        driver.find_element(By.ID, "runSandbox").click()
        wait_for(driver, "document.querySelector('#manifestStatus').textContent.includes('샌드박스 검증 통과')")
        driver.find_element(By.ID, "publishMcp").click()
        approve(driver)
        wait_for(driver, f"document.querySelector('#capabilityRegistryList').textContent.includes('{package_id}@0.1.0')")
        set_value(driver, "resolverIntent", "Budget policy total amount 조회해줘")
        driver.find_element(By.ID, "resolveIntent").click()
        wait_for(driver, f"document.querySelector('#resolverResult').textContent.includes('{package_id}@0.1.0')")
        driver.find_element(By.ID, "runResolvedIntent").click()
        approve(driver)
        wait_for(driver, "document.querySelector('#chat').textContent.includes('1,234 million won')")
        wait_for(driver, "document.querySelector('#chat').textContent.includes('1쪽')")
        driver.execute_script("document.querySelector('#runDraftRagReport').click()")
        wait_for(driver, "document.querySelector('#editorView').classList.contains('active')", timeout=45)
        wait_for(driver, "document.querySelector('#contextFile').textContent.includes('.hwpx')", timeout=45)
        print(
            json.dumps(
                {
                    "status": "passed",
                    "packageRef": package_id + "@0.1.0",
                    "pdfIndexed": True,
                    "draftRagPreview": True,
                    "resolvedFromPdfTopic": True,
                    "rhwpReportOpened": True,
                    "groundedChatAnswer": True,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    finally:
        driver.quit()
        if pdf_path:
            pdf_path.unlink(missing_ok=True)
        cleanup_test_package(package_id)


if __name__ == "__main__":
    main()
