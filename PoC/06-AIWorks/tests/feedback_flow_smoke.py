"""Focused browser smoke test for the optional-file AIWorks 0.18 flow."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.support.ui import WebDriverWait


URL = os.getenv("AIWORKS_BROWSER_URL", "http://127.0.0.1:8000/poc/aiworks/")
GECKODRIVER = os.getenv("AIWORKS_GECKODRIVER", "/snap/bin/geckodriver")


def wait_for(driver, expression: str, timeout: int = 60):
    return WebDriverWait(driver, timeout).until(
        lambda current: current.execute_script(f"return Boolean({expression})")
    )


def approve(driver):
    wait_for(driver, "document.querySelector('#approvalDialog').open")
    transfer = driver.find_element(By.ID, "externalTransfer")
    driver.execute_script(
        "if(!arguments[0].disabled)arguments[0].checked=true;"
        "const dialog=document.querySelector('#approvalDialog');dialog.close('approve');",
        transfer,
    )
    wait_for(driver, "!document.querySelector('#approvalDialog').open")


def send_chat(driver, text: str):
    input_node = driver.find_element(By.ID, "chatInput")
    input_node.send_keys(text)
    driver.find_element(By.CSS_SELECTOR, "#chatForm .send-button").click()
    approve(driver)


def current_filename(driver) -> str:
    active = driver.execute_script("return document.querySelector('#activeFileName').textContent.trim()")
    context = driver.execute_script("return document.querySelector('#contextFile').textContent.trim()")
    context = context.removeprefix("⌁").strip()
    return context if context.endswith(".hwpx") else active


def main():
    if not Path(GECKODRIVER).exists():
        raise SystemExit(f"geckodriver not found: {GECKODRIVER}")
    options = Options()
    options.add_argument("-headless")
    driver = webdriver.Firefox(options=options, service=Service(GECKODRIVER))
    try:
        driver.set_window_size(1440, 900)
        driver.get(URL)
        wait_for(driver, "document.querySelector('.local-badge').textContent.includes('v0.30.0')")
        wait_for(driver, "document.querySelector('[data-select-project=\"project-default\"]')")
        driver.find_element(By.CSS_SELECTOR, '[data-select-project="project-default"]').click()
        wait_for(driver, "!document.querySelector('#workbench').hidden || !document.querySelector('#welcomeTask').hidden")
        live_enabled = driver.execute_async_script(
            "const done=arguments[0];fetch('/api/poc/aiworks/bootstrap')"
            ".then(response=>response.json()).then(data=>done(Boolean(data.openrouter.liveExecutionEnabled)))"
            ".catch(error=>done('error:'+error.message));"
        )
        if live_enabled is not False:
            raise RuntimeError("feedback_flow_smoke는 AIWORKS_OPENROUTER_LIVE=0인 로컬 서비스에서만 실행할 수 있습니다.")
        initial_prompt = "우리부 예산 현황을 확인하고 싶어"
        if driver.execute_script("return !document.querySelector('#welcomeTask').hidden"):
            welcome = driver.find_element(By.ID, "welcomePrompt")
            welcome.send_keys(initial_prompt)
            driver.find_element(By.CSS_SELECTOR, "#welcomeForm .welcome-send").click()
            approve(driver)
        else:
            wait_for(driver, "!document.querySelector('#workbench').hidden")
            send_chat(driver, initial_prompt)
        wait_for(driver, "document.querySelector('#chat').textContent.includes('data.budget@0.1.0')")
        wait_for(driver, "document.querySelector('#chat').textContent.includes('1,284')")

        wait_for(driver, "document.querySelector('.rhwp-edit-answer') !== null")
        send_chat(driver, "이를 바탕으로 문서를 편집하자")
        wait_for(driver, "document.querySelector('#rhwpEditorHost iframe') && document.querySelector('#rhwpEditorHost').dataset.ready === 'true'", timeout=30)
        report_filename = current_filename(driver)
        if "보고서" not in report_filename or not report_filename.endswith(".hwpx"):
            raise AssertionError(f"RHWP HWPX report was not opened: {report_filename}")
        if driver.find_elements(By.CSS_SELECTOR, "#documentPaper [data-report-editable]"):
            raise AssertionError("generated report fell back to the HTML editor")

        editor_frame = driver.find_element(By.CSS_SELECTOR, "#rhwpEditorHost iframe")
        driver.switch_to.frame(editor_frame)
        wait_for(driver, "document.querySelector('textarea[aria-label=\"문서 편집 입력\"]') !== null", timeout=20)
        driver.execute_script("window.__aiworksReportMarker='rhwp-report-v1';document.querySelector('textarea[aria-label=\"문서 편집 입력\"]').focus()")
        ActionChains(driver).key_down(Keys.CONTROL).send_keys("a").key_up(Keys.CONTROL).perform()
        driver.switch_to.default_content()
        driver.find_element(By.ID, "chatInput").click()
        wait_for(driver, "document.querySelector('#contextSelection').classList.contains('has-selection')")
        driver.execute_script("const p=document.querySelector('#proposal');p.hidden=true;p.dataset.before='';p.dataset.executionId=''")
        send_chat(driver, "이 문구에 대해서 당위성을 강조하는 문구로 바꿔")
        wait_for(driver, "!document.querySelector('#proposal').hidden && document.querySelector('#proposal').dataset.executionId")
        proposal = driver.execute_script(
            "return {before:document.querySelector('#proposal').dataset.before,after:document.querySelector('#proposal').dataset.after}"
        )
        if not proposal["before"].strip() or proposal["after"].strip() == proposal["before"].strip():
            raise AssertionError(f"RHWP selection rewrite is invalid: {proposal}")
        driver.find_element(By.ID, "applyProposal").click()
        try:
            wait_for(driver, "/\\br([2-9]|[1-9][0-9]+)\\b/.test(document.querySelector('#documentSaveState').textContent) || document.querySelector('#documentSaveState').textContent.includes('저장 실패')", timeout=30)
        except Exception as error:
            detail = driver.execute_script(
                "return {status:document.querySelector('#statusText').textContent,"
                "save:document.querySelector('#documentSaveState').textContent,"
                "proposalHidden:document.querySelector('#proposal').hidden};"
            )
            raise AssertionError(f"RHWP suggestion save did not finish: {detail}") from error
        save_state = driver.find_element(By.ID, "documentSaveState").text
        revision = re.search(r"\br(\d+)\b", save_state)
        if not revision or int(revision.group(1)) < 2:
            raise AssertionError(f"RHWP suggestion was not persisted as a new revision: {save_state}")
        retained_frame = driver.find_element(By.CSS_SELECTOR, "#rhwpEditorHost iframe")
        driver.switch_to.frame(retained_frame)
        marker = driver.execute_script("return window.__aiworksReportMarker")
        driver.switch_to.default_content()
        if marker != "rhwp-report-v1":
            raise AssertionError("RHWP report iframe was reloaded after applying the suggestion")
        active_filename = current_filename(driver)
        expected_version_name = report_filename.removesuffix(".hwpx") + "_AIWorks.hwpx"
        if active_filename not in {report_filename, expected_version_name}:
            raise AssertionError(
                f"applying a suggestion navigated away from the generated report: {report_filename!r} -> {active_filename!r}"
            )

        send_chat(driver, "행안부 보고서 양식으로 바꿔줘")
        wait_for(driver, "document.querySelector('#chat').textContent.includes('template.mois-report@0.1.0')")
        wait_for(driver, "document.querySelector('#documentSaveState').textContent.includes('r3')", timeout=30)
        wait_for(driver, "document.querySelector('#rhwpEditorHost iframe') && document.querySelector('#rhwpEditorHost').dataset.ready === 'true'", timeout=30)
        formatted_filename = current_filename(driver)
        if "행안부보고" not in formatted_filename or not formatted_filename.endswith(".hwpx"):
            raise AssertionError(f"MOIS template was not applied to the RHWP document: {formatted_filename}")
        if driver.find_elements(By.CSS_SELECTOR, "#documentPaper [data-report-editable]"):
            raise AssertionError("MOIS template transformation fell back to the HTML editor")
        print(json.dumps({"status": "passed", "budgetMcp": True, "derivedReport": report_filename, "formattedReport": formatted_filename, "templateMcp": "template.mois-report@0.1.0", "editor": "RHWP", "selectionRetained": True}, ensure_ascii=False, indent=2))
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
