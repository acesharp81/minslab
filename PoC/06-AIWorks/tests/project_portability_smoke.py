"""Firefox smoke for AIWorks project portability and Recipe preview UI."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

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


def main() -> None:
    options = Options()
    options.add_argument("-headless")
    with tempfile.TemporaryDirectory(prefix=".aiworks-portability-", dir=Path.cwd()):
        driver = webdriver.Firefox(options=options, service=Service(GECKODRIVER))
        report = {}
        try:
            driver.set_window_size(1440, 900)
            driver.get(URL)
            wait_for(driver, "document.querySelector('.local-badge').textContent.includes('v0.30.0')")
            import_button = driver.find_element(By.ID, "importProjectBackup")
            if not import_button.is_displayed():
                raise AssertionError("project backup import button is not visible")
            report["projectImport"] = import_button.text

            wait_for(driver, "document.querySelector('[data-select-project=project-default]')")
            driver.find_element(By.CSS_SELECTOR, '[data-select-project="project-default"]').click()
            wait_for(driver, "!document.querySelector('#welcomeTask').hidden || !document.querySelector('#workbench').hidden")
            if not driver.execute_script("return document.querySelector('#welcomeTask').hidden"):
                driver.find_element(By.ID, "enterDemo").click()
                wait_for(driver, "!document.querySelector('#workbench').hidden")

            driver.find_element(By.CSS_SELECTOR, '[data-top-view="settings"]').click()
            wait_for(driver, "document.querySelector('#recipeSearchInput')")
            wait_for(driver, "document.querySelector('#downloadProjectBackup')")
            report["backupButton"] = driver.find_element(By.ID, "downloadProjectBackup").text
            search = driver.find_element(By.ID, "recipeSearchInput")
            search.send_keys("definitely-no-such-recipe")
            driver.find_element(By.ID, "searchWorkflowRecipes").click()
            wait_for(driver, "document.querySelector('#workflowRecipeLibrary').textContent.includes('검색 조건에 맞는 Recipe가 없습니다')")
            report["recipeSearch"] = "empty-result-rendered"

            backup = driver.execute_async_script(
                """
                const done=arguments[0];
                fetch('/api/poc/aiworks/projects/project-default/backup')
                  .then(r=>r.json()).then(done).catch(error=>done({error:String(error)}));
                """
            )
            if backup.get("format") != "aiworks-project-backup":
                raise AssertionError(f"unexpected backup response: {backup}")
            if len(backup.get("integrity", {}).get("sha256", "")) != 64:
                raise AssertionError("backup integrity SHA-256 missing")
            report["backup"] = {
                "schemaVersion": backup["schemaVersion"],
                "sha256": backup["integrity"]["sha256"][:12],
                "counts": backup["counts"],
            }
            report["status"] = "passed"
            print(json.dumps(report, ensure_ascii=False, indent=2))
        finally:
            driver.quit()


if __name__ == "__main__":
    main()
