"""Browser smoke test for the typed, guide-driven MCP Builder."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.support.ui import Select, WebDriverWait


ROOT = Path(__file__).resolve().parents[1]
URL = os.getenv("AIWORKS_BROWSER_URL", "http://127.0.0.1:8000/poc/aiworks/")
GECKODRIVER = os.getenv("AIWORKS_GECKODRIVER", "/snap/bin/geckodriver")
TEMPLATE = ROOT / "web" / "rhwp" / "samples" / "form-002.hwpx"
DB_PATH = Path(os.getenv("AIWORKS_DB_PATH", str(ROOT / "data" / "aiworks.sqlite3")))


def wait_for(driver, expression: str, timeout: int = 30):
    return WebDriverWait(driver, timeout).until(
        lambda current: current.execute_script(f"return Boolean({expression})")
    )


def set_value(driver, element_id: str, value: str):
    node = driver.find_element(By.ID, element_id)
    node.clear()
    node.send_keys(value)


def cleanup_test_draft(package_id: str) -> None:
    if not package_id.startswith("org.browser-mois-template-") or not DB_PATH.is_file():
        return
    with sqlite3.connect(DB_PATH) as db:
        draft_ids = [
            row[0]
            for row in db.execute(
                "SELECT id FROM mcp_drafts WHERE json_extract(manifest_json, '$.id')=?",
                (package_id,),
            )
        ]
        for draft_id in draft_ids:
            db.execute(
                "DELETE FROM native_document_sessions WHERE json_extract(intent_json, '$.builderDraftId')=?",
                (draft_id,),
            )
            db.execute("DELETE FROM mcp_draft_references WHERE draft_id=?", (draft_id,))
            db.execute("DELETE FROM audit_events WHERE detail_json LIKE ?", ("%" + draft_id + "%",))
            db.execute("DELETE FROM mcp_drafts WHERE id=?", (draft_id,))


def main():
    if not Path(GECKODRIVER).exists():
        raise SystemExit(f"geckodriver not found: {GECKODRIVER}")
    package_id = f"org.browser-mois-template-{os.getpid()}"
    options = Options()
    options.add_argument("-headless")
    driver = webdriver.Firefox(options=options, service=Service(GECKODRIVER))
    try:
        driver.set_window_size(1440, 1000)
        driver.get(URL)
        wait_for(driver, "document.querySelector('.local-badge').textContent.includes('v0.30.0')")
        wait_for(driver, "document.querySelector('[data-select-project=\"project-default\"]')")
        driver.find_element(By.CSS_SELECTOR, '[data-select-project="project-default"]').click()
        wait_for(driver, "!document.querySelector('#workbench').hidden || !document.querySelector('#welcomeTask').hidden")
        if driver.execute_script("return !document.querySelector('#welcomeTask').hidden"):
            driver.find_element(By.ID, "enterDemo").click()
        wait_for(driver, "document.querySelector('#workbench').hidden === false")
        top_menu = driver.execute_script(
            "return Array.from(document.querySelectorAll('.top-menu button')).map(node=>node.textContent.trim())"
        )
        if top_menu != ["MCP 만들기", "Store", "설정"]:
            raise AssertionError(f"unexpected initial top menu: {top_menu}")
        driver.execute_script("document.querySelector(\"[data-top-view='builder']\").click()")
        wait_for(driver, "document.querySelector('#workbench').hidden === false")
        wait_for(driver, "document.querySelector('#mcpType') !== null")
        wait_for(driver, "document.querySelector('#builderView').classList.contains('active')")

        type_select = Select(driver.find_element(By.ID, "mcpType"))
        type_values = [option.get_attribute("value") for option in type_select.options]
        if type_values != ["template", "process", "data", "tool", "external"]:
            raise AssertionError(f"unexpected MCP Builder types: {type_values}")
        type_select.select_by_value("template")

        set_value(driver, "mcpName", "행안부 실무보고 양식 MCP")
        set_value(driver, "mcpPackageId", package_id)
        set_value(driver, "mcpDescription", "업로드한 HWPX 양식을 기준으로 현재 보고서 내용을 행정 보고 형식에 맞춰 변환한다.")
        set_value(driver, "mcpInstructions", "원문의 제목과 내용을 유지하면서 양식의 입력 영역에 대응하고 검증 결과를 기록한다.")
        set_value(driver, "mcpCautions", "원문에 없는 수치를 추측하지 않는다.\n양식 버전을 결과에 기록한다.")
        set_value(driver, "mcpProcedure", "양식 구조를 확인한다.\n문서 내용을 입력 영역에 대응한다.\n검증 후 새 revision으로 저장한다.")
        set_value(driver, "mcpTriggers", "행안부 실무보고 양식으로 바꿔줘")
        source_included = driver.find_element(By.ID, "sourceIncluded")
        if not source_included.is_selected():
            source_included.click()
        driver.find_element(By.ID, "generateManifest").click()
        wait_for(driver, "document.querySelector('#manifestStatus').textContent.includes('서버 초안 저장됨')")
        wait_for(driver, "document.querySelector('#manifestPreview').textContent.includes('document.template.apply')")

        reference = driver.find_element(By.ID, "referenceFile")
        reference.send_keys(str(TEMPLATE))
        wait_for(driver, "document.querySelector('#referenceList').textContent.includes('template-source')", timeout=30)
        wait_for(driver, "document.querySelector('#convertDraftTemplate').disabled === false", timeout=30)
        driver.execute_script("document.querySelector('#convertDraftTemplate').click()")
        wait_for(driver, "document.querySelector('#templateConversionSummary').textContent.includes('실검증 통과')", timeout=45)
        wait_for(driver, "!document.querySelector('#builderTemplateLab').hidden && document.querySelector('#verifyDraftTemplate').disabled === false")
        driver.execute_script("document.querySelector('#verifyDraftTemplate').click()")
        wait_for(driver, "document.querySelector('#statusText').textContent.includes('양식 실렌더링 검증 통과')", timeout=45)
        driver.execute_script("document.querySelector('#runSandbox').click()")
        wait_for(driver, "document.querySelector('#manifestStatus').textContent.includes('샌드박스 검증 통과')", timeout=30)

        manifest_text = driver.execute_script(
            "return document.querySelector('#manifestPreview').textContent"
        )
        for expected in ("template", "builderGuide", "행안부 실무보고 양식으로 바꿔줘"):
            if expected not in manifest_text:
                raise AssertionError(f"Builder Manifest is missing {expected!r}")
        print(
            json.dumps(
                {
                    "status": "passed",
                    "types": type_values,
                    "templateAttached": True,
                    "guidePackaged": True,
                    "ordinaryHwpxConverted": True,
                    "renderQualityVerified": True,
                    "sandboxValidated": True,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    finally:
        driver.quit()
        cleanup_test_draft(package_id)


if __name__ == "__main__":
    main()
