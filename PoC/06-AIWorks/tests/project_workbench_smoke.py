"""Firefox acceptance smoke for the project document tab workbench."""

from __future__ import annotations

import json
import os
import sqlite3
import urllib.request
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.support.ui import WebDriverWait


URL = os.getenv("AIWORKS_BROWSER_URL", "http://127.0.0.1:8000/poc/aiworks/")
API = os.getenv("AIWORKS_API_URL", "http://127.0.0.1:8000/api/poc/aiworks")
GECKODRIVER = os.getenv("AIWORKS_GECKODRIVER", "/snap/bin/geckodriver")
DB_PATH = Path(os.getenv("AIWORKS_DB_PATH", str(Path(__file__).resolve().parents[1] / "data" / "aiworks.sqlite3")))


def wait_for(driver, expression: str, timeout: int = 60):
    return WebDriverWait(driver, timeout).until(lambda current: current.execute_script(f"return Boolean({expression})"))


def create_document() -> dict:
    body = json.dumps({
        "title": "워크벤치 브라우저 검증",
        "markdown": "# 워크벤치 브라우저 검증\n\n## 현황\n- 브라우저 동기화 대상입니다.",
        "actor": "browser-smoke",
    }, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        API + "/projects/project-default/documents", data=body,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    return json.load(urllib.request.urlopen(request, timeout=30))


def load_workspace() -> dict:
    return json.load(urllib.request.urlopen(API + "/projects/project-default/workspace", timeout=30))


def save_workspace_state(document_id: str) -> dict:
    body = json.dumps({
        "active_document_id": document_id,
        "active_tab": "metadata",
        "active_view": "editor",
        "chat": [
            {"role": "user", "text": "마지막 작업을 이어서 검토해줘", "kind": "message"},
            {"role": "assistant", "text": "프로젝트 문맥과 마지막 편집 화면을 저장했습니다.", "kind": "message"},
        ],
        "last_answer": "프로젝트 문맥과 마지막 편집 화면을 저장했습니다.",
        "actor": "browser-smoke",
    }, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        API + "/projects/project-default/workspace-state", data=body,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    return json.load(urllib.request.urlopen(request, timeout=30))


def cleanup_document(document_id: str, previous_state: dict) -> None:
    with sqlite3.connect(DB_PATH) as db:
        db.execute("PRAGMA foreign_keys=ON")
        legacy_version_ids = [
            row[0]
            for row in db.execute(
                "SELECT id FROM document_versions WHERE filename LIKE '워크벤치_브라우저_검증%'"
            )
        ]
        fact_ids = [
            row[0]
            for row in db.execute(
                "SELECT DISTINCT fact_id FROM project_fact_values WHERE source_document_id=?",
                (document_id,),
            )
        ]
        db.execute("DELETE FROM native_document_sessions WHERE markdown_document_id=?", (document_id,))
        db.execute("DELETE FROM project_document_sync_events WHERE document_id=?", (document_id,))
        db.execute("DELETE FROM project_document_artifacts WHERE document_id=?", (document_id,))
        db.execute("DELETE FROM project_fact_values WHERE source_document_id=?", (document_id,))
        db.execute("DELETE FROM project_markdown_versions WHERE document_id=?", (document_id,))
        db.execute("DELETE FROM project_markdown_documents WHERE id=?", (document_id,))
        for fact_id in fact_ids:
            db.execute(
                "DELETE FROM project_facts WHERE id=? AND status='candidate' AND NOT EXISTS (SELECT 1 FROM project_fact_values WHERE fact_id=?)",
                (fact_id, fact_id),
            )
        db.execute("DELETE FROM document_versions WHERE filename LIKE '워크벤치_브라우저_검증%'")
        db.execute("DELETE FROM audit_events WHERE detail_json LIKE ?", ("%" + document_id + "%",))
        for version_id in legacy_version_ids:
            db.execute("DELETE FROM audit_events WHERE detail_json LIKE ?", ("%" + version_id + "%",))
        if previous_state.get("updatedAt"):
            active_document_id = previous_state.get("activeDocumentId")
            if not active_document_id:
                row = db.execute(
                    "SELECT id FROM project_markdown_documents WHERE project_id='project-default' AND status='active' ORDER BY updated_at DESC LIMIT 1"
                ).fetchone()
                active_document_id = row[0] if row else None
            db.execute(
                "UPDATE project_workspace_states SET active_document_id=?,active_tab=?,active_view=?,chat_json=?,last_answer=?,updated_by='browser-smoke-restore',updated_at=? WHERE project_id='project-default'",
                (
                    active_document_id,
                    previous_state.get("activeTab") or "markdown",
                    previous_state.get("activeView") or "editor",
                    json.dumps(previous_state.get("chat") or [], ensure_ascii=False),
                    previous_state.get("lastAnswer") or "",
                    previous_state["updatedAt"],
                ),
            )
        else:
            db.execute("DELETE FROM project_workspace_states WHERE project_id='project-default'")


def main() -> None:
    if not Path(GECKODRIVER).exists():
        raise SystemExit(f"geckodriver not found: {GECKODRIVER}")
    previous_state = load_workspace().get("workspaceState") or {}
    document = create_document()
    save_workspace_state(document["id"])
    options = Options()
    options.add_argument("-headless")
    driver = webdriver.Firefox(options=options, service=Service(GECKODRIVER))
    report = {"documentId": document["id"]}
    try:
        driver.set_window_size(1440, 900)
        driver.get(URL)
        wait_for(driver, "document.readyState === 'complete'")
        report["projectGateRequired"] = driver.execute_script(
            "return !document.querySelector('#projectGate').hidden && document.querySelector('#welcomeTask').hidden && document.querySelector('#workbench').hidden"
        )
        if not report["projectGateRequired"]:
            raise AssertionError("project selection must be required before entering the workspace")
        wait_for(driver, "document.querySelector('[data-select-project=\"project-default\"]')")
        driver.find_element(By.CSS_SELECTOR, '[data-select-project="project-default"]').click()
        WebDriverWait(driver, 60).until(
            lambda current: current.find_element(By.CSS_SELECTOR, "#workbench:not([hidden]) [data-workbench-tab=metadata].active")
        )
        wait_for(driver, "document.querySelector('#chat').textContent.includes('마지막 작업을 이어서 검토해줘')")
        report["lastWorkspaceRestored"] = True
        report["restoredChatMessages"] = driver.execute_script("return document.querySelectorAll('#chat .message').length")
        wait_for(driver, "document.querySelector('#orchestrationResources').textContent.includes('MD')")
        driver.find_element(By.CSS_SELECTOR, '.activitybar [data-view="data"]').click()
        before_width = driver.execute_script("return document.querySelector('.assistant-panel').getBoundingClientRect().width")
        ActionChains(driver).move_to_element(driver.find_element(By.ID, "workspaceResizer")).click_and_hold().move_by_offset(70, 0).release().perform()
        wait_for(driver, f"Math.abs(document.querySelector('.assistant-panel').getBoundingClientRect().width-{before_width}) > 30")
        report["resizableSplit"] = round(driver.execute_script("return document.querySelector('.assistant-panel').getBoundingClientRect().width"))
        driver.find_element(By.CSS_SELECTOR, '[data-workbench-tab="markdown"]').click()
        wait_for(driver, "document.querySelector('[data-workbench-tab=\"markdown\"].active') && document.querySelector('#sourceEditor')")
        report["tabs"] = driver.execute_script("return Array.from(document.querySelectorAll('[data-workbench-tab]')).map(n=>n.dataset.workbenchTab)")
        if report["tabs"] != ["markdown", "artifact:hwpx", "metadata", "history"]:
            raise AssertionError(f"unexpected workbench tabs: {report['tabs']}")

        editor = driver.find_element(By.ID, "sourceEditor")
        updated_markdown = editor.get_attribute("value") + "\n- MD 자동 갱신 확인입니다."
        driver.execute_script("arguments[0].value=arguments[1];arguments[0].dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText'}));", editor, updated_markdown)
        wait_for(driver, "document.querySelector('[data-workbench-tab=\"markdown\"] small').textContent.includes('r2')", timeout=90)
        if driver.execute_script("return document.querySelector('[data-workbench-tab=\"artifact:hwpx\"] small').textContent.includes('동기화됨')"):
            raise AssertionError("Markdown save must not automatically render HWPX")
        report["markdownSavedWithoutRender"] = True
        driver.find_element(By.ID, "syncMdToHwpx").click()
        wait_for(driver, "document.querySelector('[data-workbench-tab=\"artifact:hwpx\"] small').textContent.includes('동기화됨')", timeout=90)
        driver.find_element(By.CSS_SELECTOR, '.activitybar [data-view="settings"]').click()
        wait_for(driver, "document.querySelector('#projectGovernance .governance-summary')")
        wait_for(driver, "document.querySelector('#createSampleRecipe') && document.querySelector('#workflowRecipeLibrary')")
        report["projectGovernance"] = True
        report["recipeLibrary"] = True
        report["explicitMarkdownToHwpx"] = True

        driver.find_element(By.CSS_SELECTOR, '[data-workbench-tab="artifact:hwpx"]').click()
        wait_for(driver, "document.querySelector('[data-workbench-tab=\"artifact:hwpx\"].active') && document.querySelector('#aiSelectionMode')", timeout=60)
        driver.find_element(By.ID, "aiSelectionMode").click()
        wait_for(driver, "document.querySelector('#nativeMcpPanel') && document.querySelectorAll('[data-native-target]').length > 0")
        target = driver.execute_script("return Array.from(document.querySelectorAll('[data-native-target]')).find(n=>n.textContent.includes('MD 자동 갱신 확인'))")
        if target is None:
            raise AssertionError("rendered HWPX does not contain the MD edit")
        before = target.text
        target.click()
        before_input = driver.find_element(By.ID, "nativeBefore")
        after_input = driver.find_element(By.ID, "nativeAfter")
        before_input.send_keys(before)
        after_input.send_keys("□ HWPX에서 변경한 내용임.")
        driver.find_element(By.ID, "nativeApply").click()
        wait_for(driver, "document.querySelector('[data-workbench-tab=\"artifact:hwpx\"] small').textContent.includes('MD 반영 필요') || document.querySelector('#syncHwpxToMd').textContent.includes('반영 필요')", timeout=60)
        if driver.execute_script("return document.querySelector('[data-workbench-tab=\"markdown\"] small').textContent.includes('r3')"):
            raise AssertionError("HWPX save must not automatically promote Markdown")
        report["hwpxSavedPending"] = True
        driver.find_element(By.ID, "syncHwpxToMd").click()
        wait_for(driver, "document.querySelector('[data-workbench-tab=\"markdown\"] small').textContent.includes('r3')", timeout=60)
        report["explicitHwpxToMarkdown"] = True

        driver.find_element(By.CSS_SELECTOR, '[data-workbench-tab="markdown"]').click()
        wait_for(driver, "document.querySelector('#sourceEditor') && document.querySelector('#sourceEditor').value.includes('HWPX에서 변경한 내용임.')")
        report["markdownPromoted"] = True
        driver.find_element(By.CSS_SELECTOR, '[data-workbench-tab="metadata"]').click()
        wait_for(driver, "document.querySelector('.workbench-fact-grid')")
        report["metadataTab"] = True
        driver.find_element(By.CSS_SELECTOR, '[data-workbench-tab="history"]').click()
        wait_for(driver, "document.querySelectorAll('.workbench-history article').length > 0")
        report["historyEvents"] = driver.execute_script("return document.querySelectorAll('.workbench-history article').length")
        report["status"] = "passed"
        print(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        driver.quit()
        cleanup_document(document["id"], previous_state)


if __name__ == "__main__":
    main()
