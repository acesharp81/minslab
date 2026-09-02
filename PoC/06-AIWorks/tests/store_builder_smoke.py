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
        wait_for(driver, "document.querySelector('.local-badge').textContent.includes('v0.31.2')")
        wait_for(driver, "document.querySelector('[data-select-project]')")
        driver.find_element(By.CSS_SELECTOR, '[data-select-project]').click()
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
        usage_buttons = driver.find_elements(By.CSS_SELECTOR, "[data-template-usage]")
        report["templateUsageButtons"] = len(usage_buttons)
        report["templateUsageGuide"] = {"flow": None, "chatPrompt": None, "applyAction": None}
        if usage_buttons:
            usage_buttons[0].click()
            wait_for(driver, "document.querySelector('#templateUsageDialog').open")
            wait_for(driver, "document.querySelector('#templateUsageBody').textContent.includes('실제 변환 흐름')")
            report["templateUsageGuide"] = {
                "flow": "프로젝트 MD 원본" in driver.find_element(By.ID, "templateUsageBody").text,
                "chatPrompt": bool(driver.find_element(By.CSS_SELECTOR, ".template-usage-modes code").text),
                "applyAction": driver.find_element(By.ID, "templateUsageApply").text,
            }
            if not report["templateUsageGuide"]["flow"] or not report["templateUsageGuide"]["chatPrompt"]:
                raise AssertionError("양식 MCP 사용 안내에 실제 변환 흐름과 호출 문구가 표시되어야 합니다.")
            driver.find_element(By.CSS_SELECTOR, "#templateUsageDialog button[value='cancel']").click()
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
        driver.find_element(By.ID, "openBuilderManual").click()
        wait_for(driver, "document.querySelector('#builderManualDialog').open")
        report["builderManual"] = {
            "steps": len(driver.find_elements(By.CSS_SELECTOR, "[data-manual-step]")),
            "visualScene": bool(driver.find_elements(By.CSS_SELECTOR, ".manual-choice-scene")),
            "goAction": driver.find_element(By.ID, "builderManualGo").text,
        }
        if report["builderManual"]["steps"] != 5 or not report["builderManual"]["visualScene"]:
            raise AssertionError("Builder 초보자 매뉴얼은 5단계 조작 장면으로 표시되어야 합니다.")
        driver.find_element(By.CSS_SELECTOR, "#builderManualDialog button[value='cancel']").click()
        driver.find_element(By.CSS_SELECTOR, "[data-builder-type='template']").click()
        wait_for(driver, "!document.querySelector('#builderTemplateLab').hidden")
        report["templateEditUi"] = {
            "selector": driver.find_element(By.ID, "editableTemplateMcp").is_displayed(),
            "button": driver.find_element(By.ID, "openEditableTemplateMcp").text,
            "status": driver.find_element(By.ID, "editableTemplateMcpStatus").text,
            "usage": driver.find_element(By.ID, "templateUsageHelp").text,
        }
        if not report["templateEditUi"]["selector"]:
            raise AssertionError("Builder에서 등록된 양식 MCP 선택 콤보가 표시되어야 합니다.")
        if "수정 초안" not in report["templateEditUi"]["button"]:
            raise AssertionError("Builder에서 선택한 양식 MCP를 수정 초안으로 열 수 있어야 합니다.")
        if "사용법" not in report["templateEditUi"]["usage"]:
            raise AssertionError("Builder 양식 영역에서 실제 사용법을 열 수 있어야 합니다.")
        if os.getenv("AIWORKS_TEST_TEMPLATE_EDIT") == "1":
            wait_for(driver, "document.querySelector('#editableTemplateMcp').options.length>1")
            driver.execute_script("var s=document.querySelector('#editableTemplateMcp');s.selectedIndex=1;s.dispatchEvent(new Event('change',{bubbles:true}))")
            driver.find_element(By.ID, "openEditableTemplateMcp").click()
            wait_for(driver, "document.querySelector('#statusText').textContent.includes('수정 초안 열림')", timeout=30)
            wait_for(driver, "document.querySelector('#manifestPreview').textContent.includes('\\\"mcpType\\\": \\\"template\\\"')", timeout=30)
            wait_for(driver, "document.querySelector('#referenceList').textContent.includes('template-source')", timeout=30)
            wait_for(driver, "document.querySelector('#correctDraftTemplate').disabled===false", timeout=30)
            report["templateEditOpened"] = {
                "draftVersion": driver.find_element(By.ID, "mcpVersion").get_attribute("value"),
                "sourcePreserved": True,
                "mappingEnabled": True,
            }

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
        if report["externalPreset"]["transport"] != "streamable-http" or report["externalPreset"]["serverProfile"]:
            raise AssertionError("외부 MCP는 범용 Streamable HTTP 기본값이며 로컬 프로필을 강제하지 않아야 합니다.")
        if report["externalPreset"]["toolName"] != "query":
            raise AssertionError("범용 외부 MCP 기본 도구명이 설정되지 않았습니다.")
        if report["externalPreset"]["capability"] != "external.tool.invoke":
            raise AssertionError("범용 외부 MCP Capability가 설정되지 않았습니다.")
        driver.find_element(By.CSS_SELECTOR, "[data-view='settings']").click()
        wait_for(driver, "document.querySelector('#modelUsagePanel .store-grid')")
        report["modelUsagePanel"] = {
            "cards": len(driver.find_elements(By.CSS_SELECTOR, "#modelUsagePanel .store-card")),
            "hasCredential": "credentialIdentity" in driver.find_element(By.ID, "modelUsagePanel").text,
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
