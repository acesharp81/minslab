"""Firefox acceptance smoke for deleting and restoring a project from the gate."""

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


def post(path: str, payload: dict) -> dict:
    request = urllib.request.Request(
        API + path,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    return json.load(urllib.request.urlopen(request, timeout=30))


def wait_for(driver, expression: str, timeout: int = 30):
    return WebDriverWait(driver, timeout).until(
        lambda current: current.execute_script(f"return Boolean({expression})")
    )


def cleanup(project_id: str) -> None:
    with sqlite3.connect(DB_PATH) as db:
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("DELETE FROM project_members WHERE project_id=?", (project_id,))
        db.execute("DELETE FROM projects WHERE id=?", (project_id,))


def main() -> None:
    project = post("/projects", {
        "name": "삭제 UI 브라우저 검증",
        "classification": "internal",
        "actor": "workspace-user",
    })
    project_id = project["id"]
    options = Options()
    options.add_argument("-headless")
    driver = webdriver.Firefox(options=options, service=Service(GECKODRIVER))
    report = {"projectId": project_id}
    try:
        driver.set_window_size(1280, 820)
        driver.get(URL)
        wait_for(driver, f'document.querySelector("[data-delete-project=\\"{project_id}\\"]")')
        driver.find_element(By.CSS_SELECTOR, f'[data-delete-project="{project_id}"]').click()
        alert = WebDriverWait(driver, 10).until(lambda current: current.switch_to.alert)
        report["confirmationMentionsRecovery"] = "복원" in alert.text
        alert.accept()

        wait_for(driver, f'!document.querySelector("[data-delete-project=\\"{project_id}\\"]")')
        wait_for(driver, f'document.querySelector("[data-restore-project=\\"{project_id}\\"]")')
        report["movedToDeletedList"] = "삭제된 프로젝트" in driver.find_element(By.ID, "projectList").text

        driver.find_element(By.CSS_SELECTOR, f'[data-restore-project="{project_id}"]').click()
        wait_for(driver, f'document.querySelector("[data-delete-project=\\"{project_id}\\"]")')
        wait_for(driver, f'!document.querySelector("[data-restore-project=\\"{project_id}\\"]")')
        report["restoredToActiveList"] = True
        report["status"] = "passed"
        print(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        driver.quit()
        cleanup(project_id)


if __name__ == "__main__":
    main()
