"""Firefox smoke: embedded derived HWPX must not open RHWP recovery choices."""

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
DB_PATH = Path(os.getenv("AIWORKS_DB_PATH", str(Path(__file__).resolve().parents[1] / "data" / "aiworks.sqlite3")))
DRAFT_ID = "aiworks-embedded-recovery-smoke"


def get_json(path: str) -> dict:
    return json.load(urllib.request.urlopen(API + path, timeout=30))


def find_derived_document() -> tuple[str, str]:
    requested = os.getenv("AIWORKS_TEST_PROJECT_ID", "").strip()
    projects = get_json("/projects").get("items") or []
    if requested:
        projects = [item for item in projects if item["id"] == requested]
    for project in projects:
        workspace = get_json(f"/projects/{project['id']}/workspace")
        for document in workspace.get("documents") or []:
            workbench = get_json(f"/projects/{project['id']}/documents/{document['id']}/workbench")
            if any(item.get("format") == "hwpx" for item in workbench.get("artifacts") or []):
                return project["id"], document["id"]
    raise SystemExit("파생 HWPX가 있는 활성 프로젝트가 없습니다.")


def wait_for(driver, expression: str, timeout: int = 60):
    return WebDriverWait(driver, timeout).until(
        lambda current: current.execute_script(f"return Boolean({expression})")
    )


def workspace_state(project_id: str):
    with sqlite3.connect(DB_PATH) as db:
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT * FROM project_workspace_states WHERE project_id=?", (project_id,)).fetchone()
        return dict(row) if row else None


def restore_workspace_state(project_id: str, previous: dict | None) -> None:
    with sqlite3.connect(DB_PATH) as db:
        if previous is None:
            db.execute("DELETE FROM project_workspace_states WHERE project_id=?", (project_id,))
            return
        db.execute(
            """
            INSERT INTO project_workspace_states(
                project_id,active_document_id,active_tab,active_view,chat_json,
                last_answer,updated_by,updated_at
            ) VALUES(?,?,?,?,?,?,?,?)
            ON CONFLICT(project_id) DO UPDATE SET
                active_document_id=excluded.active_document_id,
                active_tab=excluded.active_tab,active_view=excluded.active_view,
                chat_json=excluded.chat_json,last_answer=excluded.last_answer,
                updated_by=excluded.updated_by,updated_at=excluded.updated_at
            """,
            tuple(previous[key] for key in (
                "project_id", "active_document_id", "active_tab", "active_view",
                "chat_json", "last_answer", "updated_by", "updated_at",
            )),
        )


def main() -> None:
    project_id, document_id = find_derived_document()
    previous = workspace_state(project_id)
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
            restore_workspace_state(project_id, previous)


if __name__ == "__main__":
    main()
