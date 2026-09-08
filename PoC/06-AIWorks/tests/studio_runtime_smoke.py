"""Browser E2E for the visible MCP Studio build-install-resolve-run flow."""

from __future__ import annotations

import json
import os
import sqlite3
import urllib.request
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.support.ui import WebDriverWait


URL = os.getenv("AIWORKS_BROWSER_URL", "http://127.0.0.1:8000/poc/aiworks/")
API = os.getenv("AIWORKS_API_URL", "http://127.0.0.1:8000/api/poc/aiworks")
GECKODRIVER = os.getenv("AIWORKS_GECKODRIVER", "/snap/bin/geckodriver")
ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.getenv("AIWORKS_DB_PATH", str(ROOT / "data" / "aiworks.sqlite3")))
TEST_ACTOR = "studio-runtime-smoke"


def api(path: str, method: str = "GET", payload: dict | None = None) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        API + path, data=data, headers={"Content-Type": "application/json"}, method=method
    )
    return json.load(urllib.request.urlopen(request, timeout=30))


def create_project() -> dict:
    return api("/projects", "POST", {"name": f"Studio Runtime 검증 {os.getpid()}", "actor": TEST_ACTOR})


def cleanup_project(project: dict) -> None:
    try:
        api(f"/projects/{project['id']}/status", "POST", {"action": "archive", "actor": TEST_ACTOR})
        api(
            f"/projects/{project['id']}", "DELETE",
            {"actor": TEST_ACTOR, "confirmation": project["name"], "acknowledge_irreversible": True},
        )
    except Exception as error:
        print(f"warning: Studio Runtime project cleanup failed: {error}")


def wait_for(driver, expression: str, timeout: int = 45):
    return WebDriverWait(driver, timeout).until(
        lambda current: current.execute_script(f"return Boolean({expression})")
    )


def approve(driver):
    wait_for(driver, "document.querySelector('#approvalDialog').open")
    driver.execute_script(
        "const transfer=document.querySelector('#externalTransfer');"
        "if(!transfer.disabled)transfer.checked=true;"
        "document.querySelector('#approvalDialog').close('approve');"
    )
    wait_for(driver, "!document.querySelector('#approvalDialog').open")


def set_value(driver, element_id: str, value: str):
    node = driver.find_element(By.ID, element_id)
    node.clear()
    node.send_keys(value)


def cleanup_test_package(package_id: str) -> None:
    if not package_id.startswith("org.browser-process-runtime-") or not DB_PATH.is_file():
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
        for draft_id in draft_ids:
            db.execute("DELETE FROM mcp_draft_references WHERE draft_id=?", (draft_id,))
            db.execute("DELETE FROM mcp_drafts WHERE id=?", (draft_id,))


def main():
    if not Path(GECKODRIVER).exists():
        raise SystemExit(f"geckodriver not found: {GECKODRIVER}")
    package_id = f"org.browser-process-runtime-{os.getpid()}"
    project = create_project()
    options = Options()
    options.add_argument("-headless")
    driver = webdriver.Firefox(options=options, service=Service(GECKODRIVER))
    try:
        driver.set_window_size(1536, 1100)
        driver.get(URL)
        wait_for(driver, "document.querySelector('.local-badge').textContent.includes('v0.31.2')")
        wait_for(driver, f'document.querySelector("[data-select-project=\\"{project["id"]}\\"]")')
        driver.execute_script(
            "document.querySelector('[data-select-project=\"%s\"]').click()" % project["id"]
        )
        wait_for(driver, "!document.querySelector('#workbench').hidden || !document.querySelector('#welcomeTask').hidden")
        if driver.execute_script("return !document.querySelector('#welcomeTask').hidden"):
            driver.execute_script("document.querySelector('#enterDemo').click()")
        wait_for(driver, "document.querySelector('#workbench').hidden === false")
        driver.execute_script("document.querySelector(\"[data-view='builder']\").click()")
        wait_for(driver, "document.querySelector('.mcp-studio-page') !== null")
        if "필요한 MCP를 만들고 바로 불러보세요" not in driver.find_element(By.ID, "builderView").text:
            raise AssertionError("visible MCP Studio headline is missing")
        layout = driver.execute_script(
            "return {classes:document.querySelector('#workbench').className,"
            "assistant:getComputedStyle(document.querySelector('.assistant-panel')).display,"
            "columns:getComputedStyle(document.querySelector('#workbench')).gridTemplateColumns}"
        )
        if layout["assistant"] != "none":
            raise AssertionError(f"MCP Studio should use the full workspace width: {layout}")
        screenshot_path = os.getenv("AIWORKS_STUDIO_SCREENSHOT")
        if screenshot_path:
            driver.save_screenshot(screenshot_path)

        driver.execute_script("document.querySelector(\"[data-builder-type='process']\").click()")
        wait_for(driver, "document.querySelector(\"[data-builder-type='process']\").classList.contains('active')")
        set_value(driver, "mcpPackageId", package_id)
        driver.find_element(By.ID, "generateManifest").click()
        wait_for(driver, "document.querySelector('#manifestStatus').textContent.includes('서버 초안 저장됨')")
        driver.find_element(By.ID, "runSandbox").click()
        wait_for(driver, "document.querySelector('#manifestStatus').textContent.includes('샌드박스 검증 통과')")

        driver.execute_script("document.querySelector('#publishMcp').click()")
        approve(driver)
        wait_for(
            driver,
            f"document.querySelector('#capabilityRegistryList').textContent.includes('{package_id}@0.1.0')",
        )
        wait_for(driver, "document.querySelectorAll('#studioSteps .done').length === 5")
        if screenshot_path:
            driver.execute_script("document.querySelector('#builderView').scrollTop=0")
            driver.save_screenshot(screenshot_path)

        trigger = "이 자료를 결재 전 검토 보고서로 작성해줘"
        set_value(driver, "resolverIntent", trigger)
        driver.find_element(By.ID, "resolveIntent").click()
        wait_for(driver, f"document.querySelector('#resolverResult').textContent.includes('{package_id}@0.1.0')")
        wait_for(driver, "document.querySelector('#runResolvedIntent').disabled === false")
        driver.find_element(By.ID, "runResolvedIntent").click()
        approve(driver)
        wait_for(
            driver,
            "document.querySelector('#rhwpEditorHost iframe') && document.querySelector('#rhwpEditorHost').dataset.ready === 'true'",
            timeout=45,
        )
        package_ref = package_id + "@0.1.0"
        execution_event = next(
            (
                item for item in api("/audit?limit=200").get("items") or []
                if item.get("eventType") == "execution.completed"
                and (item.get("detail") or {}).get("dynamic") is True
                and (item.get("detail") or {}).get("package_ref") == package_ref
                and package_ref in ((item.get("detail") or {}).get("loaded_mcps") or [])
            ),
            None,
        )
        if not execution_event:
            raise AssertionError("동적 MCP 실행 packageRef와 loaded_mcps가 감사 이벤트에 기록되지 않았습니다.")
        print(
            json.dumps(
                {
                    "status": "passed",
                    "studioVisible": True,
                    "packageRef": package_ref,
                    "installedInRegistry": True,
                    "resolverMatched": True,
                    "chatExecuted": True,
                    "artifactOpenedInRhwp": True,
                    "auditExecutionId": execution_event.get("executionId"),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    finally:
        driver.quit()
        cleanup_test_package(package_id)
        cleanup_project(project)


if __name__ == "__main__":
    main()
