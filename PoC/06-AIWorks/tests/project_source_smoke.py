"""Firefox smoke for project source upload, plan explanation, search, and delete."""

from __future__ import annotations

import json
import os
import tempfile
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


def wait_for(driver, expression: str, timeout: int = 45):
    return WebDriverWait(driver, timeout).until(
        lambda current: current.execute_script(f"return Boolean({expression})")
    )


def delete_source(source_id: str) -> None:
    request = urllib.request.Request(
        API + "/projects/project-default/sources/" + source_id,
        data=json.dumps({"actor": "workspace-user"}).encode(),
        headers={"Content-Type": "application/json"},
        method="DELETE",
    )
    urllib.request.urlopen(request, timeout=20).read()


def main() -> None:
    options = Options()
    options.add_argument("-headless")
    driver = webdriver.Firefox(options=options, service=Service(GECKODRIVER))
    source_id = ""
    report = {}
    try:
        with tempfile.TemporaryDirectory(prefix=".aiworks-source-smoke-", dir=Path.cwd()) as temp_name:
            source_path = Path(temp_name) / "project-source-smoke.txt"
            source_path.write_text(
                "2026년 인공지능 공통기반 사업의 지적사항은 집행 지연이다. 향후 단계별 성과 점검이 필요하다.",
                encoding="utf-8",
            )
            driver.set_window_size(1440, 960)
            driver.get(URL)
            wait_for(driver, 'document.querySelector("[data-select-project=\\"project-default\\"]")')
            driver.find_element(By.CSS_SELECTOR, '[data-select-project="project-default"]').click()
            wait_for(driver, '!document.querySelector("#workbench").hidden')
            driver.find_element(By.CSS_SELECTOR, '[data-view="data"]').click()
            wait_for(driver, 'document.querySelector("#projectSourceInput")')
            driver.find_element(By.ID, "projectSourceInput").send_keys(str(source_path))
            wait_for(driver, 'document.querySelector(".project-source-card") && document.querySelector(".project-source-card").textContent.includes("project-source-smoke.txt")')
            source_id = driver.find_element(By.CSS_SELECTOR, "[data-source-select]").get_attribute("data-source-select")

            driver.find_element(By.ID, "chatInput").send_keys("자료에서 인공지능 공통기반 지적사항을 확인해줘")
            driver.find_element(By.CSS_SELECTOR, "#chatForm .send-button").click()
            wait_for(driver, 'document.querySelector("#approvalDialog").open')
            user_steps = driver.find_elements(By.CSS_SELECTOR, "#approvalUserSteps li")
            if not user_steps:
                raise AssertionError("user-facing execution steps are missing")
            details = driver.find_element(By.ID, "approvalTechnicalDetails")
            if details.get_attribute("open") is not None:
                raise AssertionError("technical MCP details should be collapsed by default")
            driver.execute_script("arguments[0].open=true", details)
            technical_text = details.text
            if "프로젝트 자료 검색 MCP" not in technical_text:
                raise AssertionError(f"project source MCP explanation missing: {technical_text}")
            driver.find_element(By.ID, "approveRun").click()
            wait_for(driver, 'document.querySelector("#chat").textContent.includes("집행 지연")', timeout=60)
            report = {
                "sourceId": source_id,
                "userSteps": len(user_steps),
                "technicalCollapsedByDefault": True,
                "groundedAnswer": True,
                "status": "passed",
            }
    finally:
        driver.quit()
        if source_id:
            delete_source(source_id)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
