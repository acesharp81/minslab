"""Browser smoke for the AIWorks RHWP default toolbox state."""

from __future__ import annotations

import json
import os
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.support.ui import WebDriverWait


ROOT = Path(__file__).resolve().parents[1]
URL = os.getenv("AIWORKS_BROWSER_URL", "http://127.0.0.1:8000/poc/aiworks/")
GECKODRIVER = os.getenv("AIWORKS_GECKODRIVER", "/snap/bin/geckodriver")
FIXTURE = ROOT / "web" / "rhwp" / "samples" / "form-002.hwpx"


def wait_for(driver, expression: str, timeout: int = 30):
    return WebDriverWait(driver, timeout).until(
        lambda current: current.execute_script(f"return Boolean({expression})")
    )


def main():
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
        wait_for(driver, "!document.querySelector('#workbench').hidden")
        driver.find_element(By.ID, "hwpxFile").send_keys(str(FIXTURE))
        wait_for(driver, "document.querySelector('#rhwpEditorHost[data-ready=true] iframe')")
        wait_for(
            driver,
            "(() => { const d=document.querySelector('#rhwpEditorHost iframe').contentDocument; "
            "const basic=d.querySelector('[data-cmd=\"view:toolbox-basic\"]'); "
            "const format=d.querySelector('[data-cmd=\"view:toolbox-format\"]'); "
            "return d.documentElement.dataset.aiworksDefaultToolbox==='format' "
            "&& basic && !basic.classList.contains('disabled') && !basic.classList.contains('active') "
            "&& basic.getAttribute('aria-checked')==='false' && getComputedStyle(d.querySelector('#icon-toolbar')).display==='none' "
            "&& format && !format.classList.contains('disabled') && format.classList.contains('active') "
            "&& format.getAttribute('aria-checked')==='true' && getComputedStyle(d.querySelector('#style-bar')).display!=='none'; })()",
        )
        result = driver.execute_script(
            "const d=document.querySelector('#rhwpEditorHost iframe').contentDocument; "
            "const basic=d.querySelector('[data-cmd=\"view:toolbox-basic\"]'); "
            "const format=d.querySelector('[data-cmd=\"view:toolbox-format\"]'); "
            "return {defaultToolbox:d.documentElement.dataset.aiworksDefaultToolbox, "
            "basic:{active:basic.classList.contains('active'),checked:basic.getAttribute('aria-checked'),display:getComputedStyle(d.querySelector('#icon-toolbar')).display}, "
            "format:{active:format.classList.contains('active'),checked:format.getAttribute('aria-checked'),display:getComputedStyle(d.querySelector('#style-bar')).display}};"
        )
        chat = driver.find_element(By.ID, "chatInput")
        chat.send_keys("전체 내용을 개조식으로 다듬어줘")
        driver.find_element(By.CSS_SELECTOR, "#chatForm .send-button").click()
        wait_for(driver, "document.querySelector('#approvalDialog').open")
        transfer = driver.find_element(By.ID, "externalTransfer")
        if not transfer.get_attribute("disabled"):
            raise AssertionError("로컬 전체 문서 변환이 외부 전송 승인을 요청했습니다.")
        driver.find_element(By.ID, "approveRun").click()
        wait_for(driver, "document.querySelector('#documentSaveState').textContent.includes('r2')")
        wait_for(driver, "document.querySelector('#chat').textContent.includes('새 revision으로 적용했습니다')")
        result["fullDocumentTransform"] = "revision-2"
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
