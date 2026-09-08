"""Firefox smoke: embedded derived HWPX must not open RHWP recovery choices."""

from __future__ import annotations

import json
import os
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
DRAFT_ID = "aiworks-embedded-recovery-smoke"
ACTOR = "rhwp-recovery-smoke"


def get_json(path: str) -> dict:
    return json.load(urllib.request.urlopen(API + path, timeout=30))


def post_json(path: str, payload: dict, method: str = "POST") -> dict:
    request = urllib.request.Request(
        API + path,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method=method,
    )
    return json.load(urllib.request.urlopen(request, timeout=30))


def create_fixture() -> tuple[dict, dict]:
    project = post_json("/projects", {"name": f"RHWP 복구 검증 {os.getpid()}", "actor": ACTOR})
    document = post_json(
        f"/projects/{project['id']}/documents",
        {"title": "RHWP 복구 검증", "markdown": "# RHWP 복구 검증\n\n- 내장 편집 복구 대화상자를 검사함.", "actor": ACTOR},
    )
    post_json(
        f"/projects/{project['id']}/documents/{document['id']}/render",
        {"format": "hwpx", "instruction": "중앙부처 개조식 보고서", "actor": ACTOR},
    )
    return project, document


def cleanup_fixture(project: dict) -> None:
    try:
        post_json(f"/projects/{project['id']}/status", {"action": "archive", "actor": ACTOR})
        post_json(
            f"/projects/{project['id']}",
            {"actor": ACTOR, "confirmation": project["name"], "acknowledge_irreversible": True},
            method="DELETE",
        )
    except Exception as error:
        print(f"warning: RHWP recovery fixture cleanup failed: {error}")


def wait_for(driver, expression: str, timeout: int = 60):
    return WebDriverWait(driver, timeout).until(
        lambda current: current.execute_script(f"return Boolean({expression})")
    )


def main() -> None:
    project, document = create_fixture()
    project_id, document_id = project["id"], document["id"]
    options = Options()
    options.add_argument("-headless")
    driver = webdriver.Firefox(options=options, service=Service(GECKODRIVER))
    report = {"projectId": project_id, "documentId": document_id}
    try:
        driver.set_window_size(1440, 900)
        driver.get(URL)
        wait_for(driver, "document.readyState === 'complete'")
        driver.execute_async_script(
            """
            const done=arguments[arguments.length-1];
            const request=indexedDB.open('rhwpStudioAutosave',1);
            request.onupgradeneeded=()=>request.result.createObjectStore('drafts',{keyPath:'id'});
            request.onerror=()=>done(String(request.error));
            request.onsuccess=()=>{
              const db=request.result,tx=db.transaction('drafts','readwrite');
              tx.objectStore('drafts').put({
                id:arguments[0],fileName:'복구_후보_검증.hwpx',sourceFormat:'hwpx',
                savedAt:Date.now(),byteLength:4,data:new Uint8Array([1,2,3,4]),dirtyReason:'smoke'
              });
              tx.oncomplete=()=>{db.close();done(null)};
              tx.onerror=()=>done(String(tx.error));
            };
            """,
            DRAFT_ID,
        )
        wait_for(driver, f"document.querySelector('[data-select-project=\"{project_id}\"]')")
        driver.find_element(By.CSS_SELECTOR, f'[data-select-project="{project_id}"]').click()
        wait_for(driver, "!document.querySelector('#workbench').hidden")
        wait_for(driver, 'document.querySelector("[data-workbench-tab=\\"artifact:hwpx\\"]")')
        driver.find_element(By.CSS_SELECTOR, '[data-workbench-tab="artifact:hwpx"]').click()
        wait_for(driver, "document.querySelector('#rhwpEditorHost iframe')")
        wait_for(driver, "document.querySelector('#rhwpEditorHost').dataset.ready === 'true'")
        driver.find_element(By.CSS_SELECTOR, '[data-workbench-tab="markdown"]').click()
        wait_for(driver, 'document.querySelector("[data-workbench-tab=\\"markdown\\"].active") && document.querySelector("#sourceEditor")')
        driver.find_element(By.CSS_SELECTOR, '[data-workbench-tab="artifact:hwpx"]').click()
        wait_for(driver, 'document.querySelector("[data-workbench-tab=\\"artifact:hwpx\\"].active")')
        wait_for(driver, "document.querySelector('#rhwpEditorHost iframe')")
        wait_for(driver, "document.querySelector('#rhwpEditorHost').dataset.ready === 'true'")
        iframe = driver.find_element(By.CSS_SELECTOR, "#rhwpEditorHost iframe")
        source = iframe.get_attribute("src")
        report["iframeUrl"] = source
        report["embeddedMode"] = "embedded=1" in source and "url=" in source
        if not report["embeddedMode"]:
            raise AssertionError(f"embedded recovery suppression is missing: {source}")
        driver.switch_to.frame(iframe)
        report["recoveryDialogVisible"] = driver.execute_script(
            "const node=document.querySelector('.recovery-dialog');return Boolean(node && getComputedStyle(node).display!=='none')"
        )
        report["recoveryChoiceTextVisible"] = "복구 후보를 모두 삭제" in driver.find_element(By.TAG_NAME, "body").text
        if report["recoveryDialogVisible"] or report["recoveryChoiceTextVisible"]:
            raise AssertionError("embedded RHWP displayed the standalone recovery dialog")
        driver.switch_to.default_content()
        report["status"] = "passed"
        print(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        try:
            driver.switch_to.default_content()
            driver.execute_async_script(
                """
                const done=arguments[arguments.length-1],request=indexedDB.open('rhwpStudioAutosave',1);
                request.onerror=()=>done();request.onsuccess=()=>{
                  const db=request.result,tx=db.transaction('drafts','readwrite');
                  tx.objectStore('drafts').delete(arguments[0]);
                  tx.oncomplete=()=>{db.close();done()};tx.onerror=()=>done();
                };
                """,
                DRAFT_ID,
            )
        finally:
            driver.quit()
            cleanup_fixture(project)


if __name__ == "__main__":
    main()
