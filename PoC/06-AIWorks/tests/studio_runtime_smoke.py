"""Browser E2E for the visible MCP Studio build-install-resolve-run flow."""

from __future__ import annotations

import json
import os
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.support.ui import WebDriverWait


URL = os.getenv("AIWORKS_BROWSER_URL", "http://127.0.0.1:8000/poc/aiworks/")
GECKODRIVER = os.getenv("AIWORKS_GECKODRIVER", "/snap/bin/geckodriver")


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


def main():
    if not Path(GECKODRIVER).exists():
        raise SystemExit(f"geckodriver not found: {GECKODRIVER}")
    package_id = f"org.browser-process-runtime-{os.getpid()}"
    options = Options()
    options.add_argument("-headless")
    driver = webdriver.Firefox(options=options, service=Service(GECKODRIVER))
    try:
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
        wait_for(driver, f"document.querySelector('#chat').textContent.includes('{package_id}@0.1.0')")
        wait_for(
            driver,
            "document.querySelector('#rhwpEditorHost iframe') && document.querySelector('#rhwpEditorHost').dataset.ready === 'true'",
            timeout=45,
        )
        print(
            json.dumps(
                {
                    "status": "passed",
                    "studioVisible": True,
                    "packageRef": package_id + "@0.1.0",
                    "installedInRegistry": True,
                    "resolverMatched": True,
                    "chatExecuted": True,
                    "artifactOpenedInRhwp": True,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
