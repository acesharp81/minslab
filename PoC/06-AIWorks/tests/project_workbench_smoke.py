"""Firefox acceptance smoke for the project document tab workbench."""

from __future__ import annotations

import base64
import importlib.util
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
PROJECT_ID = os.getenv("AIWORKS_TEST_PROJECT_ID", "project-default")
ROOT = Path(__file__).resolve().parents[1]


def wait_for(driver, expression: str, timeout: int = 60):
    return WebDriverWait(driver, timeout).until(lambda current: current.execute_script(f"return Boolean({expression})"))


def create_document() -> dict:
    body = json.dumps({
        "title": "워크벤치 브라우저 검증",
        "markdown": "# 워크벤치 브라우저 검증\n\n## 현황\n- 브라우저 동기화 대상입니다.",
        "actor": "browser-smoke",
    }, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        API + f"/projects/{PROJECT_ID}/documents", data=body,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    return json.load(urllib.request.urlopen(request, timeout=30))


def load_workspace() -> dict:
    return json.load(urllib.request.urlopen(API + f"/projects/{PROJECT_ID}/workspace", timeout=30))


def load_template_mcps() -> list[dict]:
    return json.load(urllib.request.urlopen(API + "/template-mcps", timeout=30)).get("items") or []


def ensure_template_mcp() -> tuple[list[dict], str | None]:
    existing = load_template_mcps()
    if existing:
        return existing, None
    package_id = f"org.workbench-template-{os.getpid()}"
    spec = importlib.util.spec_from_file_location("aiworks_workbench_fixture_backend", ROOT / "backend.py")
    backend = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(backend)
    draft = backend.create_mcp_draft({
        "name": "워크벤치 검증 양식 MCP",
        "package_id": package_id,
        "description": "빈 기준 DB에서 문서 양식 선택과 상태 보존을 검증하는 테스트 전용 MCP입니다.",
        "mcp_type": "template",
        "instructions": "프로젝트 Markdown의 제목과 본문을 HWPX 양식 슬롯에 적용합니다.",
        "procedure": "문서를 읽습니다.\n양식 슬롯을 적용합니다.\n결과를 검증합니다.",
        "source_included": True,
        "use_model": False,
        "actor": "browser-smoke",
    })
    starter = backend.builder_template_starter()
    source = base64.b64decode(starter["contentBase64"], validate=True)
    backend.add_mcp_draft_reference(draft["id"], {
        "filename": starter["filename"],
        "role": "template-source",
        "content_base64": base64.b64encode(source).decode("ascii"),
    })
    backend.validate_mcp_draft(draft["id"], {})
    published = backend.publish_mcp_draft(
        draft["id"], {"confirm_visibility": "private", "confirm_source_included": True, "actor": "browser-smoke"}
    )
    manifest = published["package"]["manifest"]
    backend.install_mcp_package({
        "package_id": manifest["id"],
        "version": manifest["version"],
        "approved_permissions": [item["scope"] for item in manifest["permissions"]],
        "acknowledge_signature": True,
        "actor": "browser-smoke",
    })
    installed = load_template_mcps()
    if not installed:
        raise AssertionError("test-owned Template MCP installation was not exposed")
    return installed, package_id


def cleanup_template_mcp(package_id: str | None) -> None:
    if not package_id or not package_id.startswith("org.workbench-template-") or not DB_PATH.is_file():
        return
    with sqlite3.connect(DB_PATH) as db:
        draft_ids = [
            row[0] for row in db.execute(
                "SELECT id FROM mcp_drafts WHERE json_extract(manifest_json, '$.id')=?", (package_id,)
            )
        ]
        db.execute("DELETE FROM mcp_installations WHERE package_id=?", (package_id,))
        for table in ("mcp_capabilities", "mcp_reference_chunks", "mcp_package_files"):
            db.execute(f"DELETE FROM {table} WHERE package_id=?", (package_id,))
        db.execute("DELETE FROM mcp_packages WHERE package_id=?", (package_id,))
        if draft_ids:
            placeholders = ",".join("?" for _ in draft_ids)
            db.execute(f"DELETE FROM mcp_template_originals WHERE draft_id IN ({placeholders})", draft_ids)
            db.execute(f"DELETE FROM mcp_draft_references WHERE draft_id IN ({placeholders})", draft_ids)
            db.execute(f"DELETE FROM mcp_drafts WHERE id IN ({placeholders})", draft_ids)


def load_document_workbench(document_id: str) -> dict:
    return json.load(urllib.request.urlopen(API + f"/projects/{PROJECT_ID}/documents/{document_id}/workbench", timeout=30))


def create_empty_project(name: str = "빈 프로젝트 브라우저 검증") -> dict:
    body = json.dumps({"name": name, "actor": "workspace-user"}, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(API + "/projects", data=body, headers={"Content-Type": "application/json"}, method="POST")
    return json.load(urllib.request.urlopen(request, timeout=30))


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
        API + f"/projects/{PROJECT_ID}/workspace-state", data=body,
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
        db.execute("DELETE FROM document_final_outputs WHERE document_id=?", (document_id,))
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
        if previous_state.get("updatedAt"):
            active_document_id = previous_state.get("activeDocumentId")
            if not active_document_id:
                row = db.execute(
                    "SELECT id FROM project_markdown_documents WHERE project_id=? AND status='active' ORDER BY updated_at DESC LIMIT 1",
                    (PROJECT_ID,),
                ).fetchone()
                active_document_id = row[0] if row else None
            db.execute(
                "UPDATE project_workspace_states SET active_document_id=?,active_tab=?,active_view=?,chat_json=?,last_answer=?,updated_by='browser-smoke-restore',updated_at=? WHERE project_id=?",
                (
                    active_document_id,
                    previous_state.get("activeTab") or "markdown",
                    previous_state.get("activeView") or "editor",
                    json.dumps(previous_state.get("chat") or [], ensure_ascii=False),
                    previous_state.get("lastAnswer") or "",
                    previous_state["updatedAt"],
                    PROJECT_ID,
                ),
            )
        else:
            db.execute("DELETE FROM project_workspace_states WHERE project_id=?", (PROJECT_ID,))


def cleanup_empty_project(project_id: str) -> None:
    with sqlite3.connect(DB_PATH) as db:
        conversation_ids = [
            row[0] for row in db.execute(
                "SELECT id FROM project_conversations WHERE project_id=?", (project_id,)
            )
        ]
        for conversation_id in conversation_ids:
            db.execute("DELETE FROM project_conversation_messages WHERE conversation_id=?", (conversation_id,))
        db.execute("DELETE FROM project_decisions WHERE project_id=?", (project_id,))
        db.execute("DELETE FROM project_conversations WHERE project_id=?", (project_id,))
        db.execute("DELETE FROM project_workspace_states WHERE project_id=?", (project_id,))
        db.execute("DELETE FROM project_members WHERE project_id=?", (project_id,))
        db.execute("DELETE FROM projects WHERE id=?", (project_id,))


def main() -> None:
    global PROJECT_ID
    if not Path(GECKODRIVER).exists():
        raise SystemExit(f"geckodriver not found: {GECKODRIVER}")
    active_fixture = create_empty_project("워크벤치 Phase 2 검증")
    PROJECT_ID = active_fixture["id"]
    previous_state = load_workspace().get("workspaceState") or {}
    template_mcps, created_template_package = ensure_template_mcp()
    document = create_document()
    empty_fixture = create_empty_project()
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
        wait_for(driver, f'document.querySelector("[data-select-project=\\"{empty_fixture["id"]}\\"]")')
        empty_project = driver.execute_script(
            """const button=document.querySelector('[data-select-project="%s"]');
            return {id:button.dataset.selectProject,name:button.querySelector('strong').textContent};
            """ % empty_fixture["id"]
        )
        driver.execute_script(
            """
            window.__aiworksSmokeFetch=window.fetch;
            window.fetch=function(input,options){
              if(String(input).includes('/workspace-state') && options && options.method==='POST'){
                return Promise.resolve(new Response(JSON.stringify({projectId:'smoke',chat:[]}),{status:200,headers:{'Content-Type':'application/json'}}));
              }
              return window.__aiworksSmokeFetch(input,options);
            };
            """
        )
        driver.find_element(By.CSS_SELECTOR, f'[data-select-project="{empty_project["id"]}"]').click()
        wait_for(driver, "!document.querySelector('#workbench').hidden && document.querySelector('.empty-project-tab')")
        wait_for(driver, "document.querySelector('#documentPaper').textContent.includes('아직 기본 문서가 없습니다')")
        if empty_project["name"] not in driver.find_element(By.ID, "documentPaper").text:
            raise AssertionError("empty project name was not rendered in the workspace")
        report["emptyProjectOpensImmediately"] = empty_project["name"]
        driver.execute_script("document.querySelector('#sidebarChangeProject').click()")
        wait_for(driver, "!document.querySelector('#projectGate').hidden")
        driver.execute_script("window.fetch=window.__aiworksSmokeFetch;delete window.__aiworksSmokeFetch;")
        wait_for(driver, f'document.querySelector("[data-select-project=\\"{PROJECT_ID}\\"]")')
        driver.find_element(By.CSS_SELECTOR, f'[data-select-project="{PROJECT_ID}"]').click()
        WebDriverWait(driver, 60).until(
            lambda current: current.find_element(By.CSS_SELECTOR, "#workbench:not([hidden]) [data-workbench-tab=metadata].active")
        )
        wait_for(driver, "document.querySelector('#chat').textContent.includes('마지막 작업을 이어서 검토해줘')")
        report["lastWorkspaceRestored"] = True
        report["restoredChatMessages"] = driver.execute_script("return document.querySelectorAll('#chat .message').length")
        wait_for(driver, "document.querySelector('#orchestrationResources').textContent.includes('문서')")
        driver.find_element(By.CSS_SELECTOR, '.activitybar [data-view="data"]').click()
        before_width = driver.execute_script("return document.querySelector('.assistant-panel').getBoundingClientRect().width")
        ActionChains(driver).move_to_element(driver.find_element(By.ID, "workspaceResizer")).click_and_hold().move_by_offset(70, 0).release().perform()
        wait_for(driver, f"Math.abs(document.querySelector('.assistant-panel').getBoundingClientRect().width-{before_width}) > 30")
        report["resizableSplit"] = round(driver.execute_script("return document.querySelector('.assistant-panel').getBoundingClientRect().width"))
        driver.find_element(By.CSS_SELECTOR, '[data-workbench-tab="markdown"]').click()
        wait_for(driver, "document.querySelector('[data-workbench-tab=\"markdown\"].active') && document.querySelector('#sourceEditor')")
        report["tabs"] = driver.execute_script("return Array.from(document.querySelectorAll('[data-workbench-tab]')).map(n=>n.dataset.workbenchTab)")
        if report["tabs"] != ["markdown", "artifact:hwpx", "outputs", "metadata", "history"]:
            raise AssertionError(f"unexpected workbench tabs: {report['tabs']}")
        derived_label = driver.find_element(By.CSS_SELECTOR, '[data-workbench-tab="artifact:hwpx"] span:nth-of-type(2)').text
        if derived_label != "완성 문서":
            raise AssertionError(f"derived document tab label is wrong: {derived_label}")
        report["derivedDocumentLabel"] = derived_label

        editor = driver.find_element(By.ID, "sourceEditor")
        updated_markdown = editor.get_attribute("value") + "\n- MD 자동 갱신 확인입니다."
        driver.execute_script("arguments[0].value=arguments[1];arguments[0].dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText'}));", editor, updated_markdown)
        wait_for(driver, "document.querySelector('[data-workbench-tab=\"markdown\"] small').textContent.includes('r2')", timeout=90)
        if driver.execute_script("return document.querySelector('[data-workbench-tab=\"artifact:hwpx\"] small').textContent.includes('최신')"):
            raise AssertionError("Markdown save must not automatically render HWPX")
        report["markdownSavedWithoutRender"] = True
        driver.find_element(By.ID, "syncMdToHwpx").click()
        wait_for(driver, "document.querySelector('[data-workbench-tab=\"artifact:hwpx\"] small').textContent.includes('최신')", timeout=90)
        driver.find_element(By.CSS_SELECTOR, '[data-workbench-tab="outputs"]').click()
        wait_for(driver, "document.querySelectorAll('[data-download-output]').length === 1", timeout=60)
        report["finalOutputRepository"] = True
        driver.find_element(By.CSS_SELECTOR, '.activitybar [data-view="settings"]').click()
        wait_for(driver, "document.querySelector('#projectGovernance .governance-summary')")
        wait_for(driver, "document.querySelector('#createSampleRecipe') && document.querySelector('#workflowRecipeLibrary')")
        report["projectGovernance"] = True
        report["recipeLibrary"] = True
        report["explicitMarkdownToHwpx"] = True

        driver.find_element(By.CSS_SELECTOR, '[data-workbench-tab="artifact:hwpx"]').click()
        wait_for(driver, "document.querySelector('[data-workbench-tab=\"artifact:hwpx\"].active') && document.querySelector('#aiSelectionMode')", timeout=60)
        wait_for(driver, "!document.querySelector('#templateMcpControl').hidden && !document.querySelector('#templateMcpSelect').disabled", timeout=60)
        target_template = template_mcps[0]
        selector_state = driver.execute_script(
            """const select=document.querySelector('#templateMcpSelect');return {value:select.value,options:Array.from(select.options).map(option=>({value:option.value,text:option.textContent}))};"""
        )
        if target_template["packageRef"] not in {item["value"] for item in selector_state["options"]}:
            raise AssertionError(f"installed template missing from selector: {selector_state}")
        if selector_state["value"] != target_template["packageRef"]:
            driver.execute_script(
                """window.confirm=()=>true;const select=document.querySelector('#templateMcpSelect');select.value=arguments[0];select.dispatchEvent(new Event('change',{bubbles:true}));""",
                target_template["packageRef"],
            )
            wait_for(
                driver,
                f"document.querySelector('#templateMcpSelect').value === {json.dumps(target_template['packageRef'])} && !document.querySelector('#templateMcpSelect').disabled",
                timeout=90,
            )
        persisted_artifact = next(item for item in load_document_workbench(document["id"])["artifacts"] if item["format"] == "hwpx")
        if persisted_artifact["templateId"] != target_template["packageRef"]:
            raise AssertionError(f"template selector did not persist current template: {persisted_artifact}")
        report["templateSelector"] = {
            "selected": target_template["packageRef"],
            "defaultRestored": driver.find_element(By.ID, "templateMcpSelect").get_attribute("value") == target_template["packageRef"],
        }
        wait_for(driver, "!document.querySelector('#templateMcpHelp').hidden")
        driver.find_element(By.ID, "templateMcpHelp").click()
        wait_for(driver, "document.querySelector('#templateUsageDialog').open")
        wait_for(driver, f"document.querySelector('#templateUsageDialog').dataset.packageRef === {json.dumps(target_template['packageRef'])}")
        usage_text = driver.find_element(By.ID, "templateUsageBody").text
        if "프로젝트 MD 원본" not in usage_text or "HWPX 완성 문서" not in usage_text:
            raise AssertionError("완성 문서 사용 안내에 실제 양식 변환 흐름이 없습니다.")
        report["templateUsageGuide"] = {
            "currentTemplate": driver.find_element(By.ID, "templateUsageDialog").get_attribute("data-package-ref"),
            "directApply": driver.find_element(By.ID, "templateUsageApply").is_enabled(),
        }
        driver.find_element(By.CSS_SELECTOR, "#templateUsageDialog button[value='cancel']").click()
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
        wait_for(
            driver,
            "document.querySelector('[data-workbench-tab=\"artifact:hwpx\"] small').textContent.includes('완성 문서에서 수정됨') && document.querySelector('#syncHwpxToMd').textContent.includes('수정 내용을')",
            timeout=60,
        )
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
        for _round in range(3):
            for tab in ["markdown", "outputs", "artifact:hwpx", "metadata", "history"]:
                driver.find_element(By.CSS_SELECTOR, f'[data-workbench-tab="{tab}"]').click()
                wait_for(driver, f'document.querySelector(\'[data-workbench-tab="{tab}"].active\')')
                try:
                    if tab == "markdown":
                        wait_for(driver, "document.querySelectorAll('#documentPaper #sourceEditor').length === 1", timeout=20)
                    elif tab == "artifact:hwpx":
                        wait_for(driver, "document.querySelector('#rhwpEditorHost') || document.querySelector('#documentPaper [data-native-target]')", timeout=20)
                    else:
                        wait_for(driver, "document.querySelectorAll('#documentPaper .workbench-info-head').length === 1", timeout=20)
                except Exception:
                    diagnostic = driver.execute_script(
                        """
                        const paper=document.querySelector('#documentPaper');
                        return {tab:document.querySelector('[data-workbench-tab].active')?.dataset.workbenchTab,
                          paperClass:paper.className,html:paper.innerHTML.slice(0,1200),status:document.querySelector('#statusText')?.textContent,
                          toast:document.querySelector('#toast')?.textContent};
                        """
                    )
                    raise AssertionError(f"tab render timeout round={_round} tab={tab}: {diagnostic}")
                mixed = driver.execute_script(
                    """
                    const paper=document.querySelector('#documentPaper');
                    const modes=[
                      Boolean(paper.querySelector('#sourceEditor')),
                      Boolean(paper.querySelector('.workbench-info-head')),
                      Boolean(paper.querySelector('#rhwpEditorHost') || paper.querySelector('[data-native-target]'))
                    ];
                    return modes.filter(Boolean).length;
                    """
                )
                if mixed != 1:
                    raise AssertionError(f"tab DOM accumulated for {tab}: modeCount={mixed}")
                panel_counts = driver.execute_script(
                    """
                    return {visible:document.querySelectorAll('.document-stage > article:not([hidden])').length,
                      cached:document.querySelectorAll('.document-stage > article[data-cached-workbench-tab]').length};
                    """
                )
                if panel_counts["visible"] != 1 or panel_counts["cached"] > 1:
                    raise AssertionError(f"workbench panel leak for {tab}: {panel_counts}")
        report["repeatedTabIsolation"] = True
        report["status"] = "passed"
        print(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        driver.quit()
        cleanup_document(document["id"], previous_state)
        cleanup_empty_project(empty_fixture["id"])
        cleanup_empty_project(active_fixture["id"])
        cleanup_template_mcp(created_template_package)


if __name__ == "__main__":
    main()
