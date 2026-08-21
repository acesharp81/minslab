"""Non-mutating browser smoke for MCP Store management and external Builder UI."""

from __future__ import annotations

import json
import os

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.support.ui import WebDriverWait


URL = os.getenv("AIWORKS_BROWSER_URL", "http://127.0.0.1:8000/poc/aiworks/")
GECKODRIVER = os.getenv("AIWORKS_GECKODRIVER", "/snap/bin/geckodriver")


def wait_for(driver, expression: str, timeout: int = 15):
    return WebDriverWait(driver, timeout).until(
        lambda current: current.execute_script(f"return Boolean({expression})")
    )


def main():
    options = Options()
    options.add_argument("-headless")
    driver = webdriver.Firefox(options=options, service=Service(GECKODRIVER))
    report = {}
    try:
        driver.set_window_size(1440, 900)
        driver.get(URL)
        wait_for(driver, "document.querySelector('.local-badge').textContent.includes('v0.30.0')")
        wait_for(driver, "document.querySelector('[data-select-project=\"project-default\"]')")
        driver.find_element(By.CSS_SELECTOR, '[data-select-project="project-default"]').click()
        wait_for(driver, "!document.querySelector('#workbench').hidden || !document.querySelector('#welcomeTask').hidden")
        if driver.execute_script("return !document.querySelector('#welcomeTask').hidden"):
            driver.find_element(By.ID, "enterDemo").click()
        wait_for(driver, "!document.querySelector('#workbench').hidden")
        driver.find_element(By.CSS_SELECTOR, "[data-view='store']").click()
        wait_for(driver, "document.querySelectorAll('.store-card').length>0")
        report["storeCards"] = len(driver.find_elements(By.CSS_SELECTOR, ".store-card"))
        report["editButtons"] = len(driver.find_elements(By.CSS_SELECTOR, "[data-edit]"))
        report["deleteButtons"] = len(driver.find_elements(By.CSS_SELECTOR, "[data-delete]"))
        if report["editButtons"] != report["storeCards"]:
            raise AssertionError("모든 Store 카드에 수정 버튼이 있어야 합니다.")
        configure = driver.find_element(By.CSS_SELECTOR, "[data-configure='core.intent-analysis']")
        configure.click()
        wait_for(driver, "document.querySelector('#mcpConfigurationDialog').open")
        report["intentConfiguration"] = driver.find_element(
            By.CSS_SELECTOR, "#mcpConfigurationDialog select[data-config-key='initialDocumentModel'] option:checked"
        ).text
        if "Solar Pro 4" not in report["intentConfiguration"]:
            raise AssertionError("최초 문서 생성 기본 모델은 Solar Pro 4여야 합니다.")
        driver.find_element(By.CSS_SELECTOR, "#mcpConfigurationDialog button[value='cancel']").click()
        driver.find_element(By.CSS_SELECTOR, "[data-view='builder']").click()
        wait_for(driver, "document.querySelectorAll('[data-builder-type]').length===5")
        driver.find_element(By.CSS_SELECTOR, "[data-builder-type='template']").click()
        wait_for(driver, "!document.querySelector('#builderTemplateLab').hidden")
        report["templateAuthoringMenu"] = {
            "quality": driver.find_element(By.ID, "verifyDraftTemplate").text,
            "sample": driver.find_element(By.ID, "downloadDraftTemplateSample").text,
            "edit": driver.find_element(By.ID, "openTemplateAuthoring").text,
        }
        if "RHWP" not in report["templateAuthoringMenu"]["edit"]:
            raise AssertionError("양식 MCP에 RHWP 양식 수정 메뉴가 표시되어야 합니다.")
        driver.find_element(By.CSS_SELECTOR, "[data-builder-type='external']").click()
        wait_for(driver, "!document.querySelector('#builderExternalFields').hidden")
        report["builderTypes"] = len(driver.find_elements(By.CSS_SELECTOR, "[data-builder-type]"))
        report["externalPreset"] = {
            "transport": driver.find_element(By.ID, "externalTransport").get_attribute("value"),
            "serverProfile": driver.find_element(By.ID, "externalServerProfile").get_attribute("value"),
            "toolName": driver.find_element(By.ID, "externalToolName").get_attribute("value"),
            "capability": driver.find_element(By.ID, "externalCapability").get_attribute("value"),
        }
        if report["externalPreset"]["transport"] != "stdio" or report["externalPreset"]["serverProfile"] != "kordoc@4.7.3":
            raise AssertionError("공식 KODAK 고정 버전 stdio 프로필이 설정되지 않았습니다.")
        if report["externalPreset"]["toolName"] != "generate_document":
            raise AssertionError("공식 KODAK generate_document 도구가 설정되지 않았습니다.")
        if report["externalPreset"]["capability"] != "document.hwpx.finalize":
            raise AssertionError("KODAK HWPX 자동 후처리 Capability가 설정되지 않았습니다.")
        print(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
