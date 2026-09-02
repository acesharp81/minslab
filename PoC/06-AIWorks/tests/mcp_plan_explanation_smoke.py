"""Firefox acceptance smoke for human-readable MCP plan explanations."""

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
        plan_ids = [
            row[0] for row in db.execute(
                "SELECT id FROM plans WHERE document_context_json LIKE ?", (f"%{project_id}%",)
            )
        ]
        for plan_id in plan_ids:
            db.execute("DELETE FROM plans WHERE id=?", (plan_id,))
        db.execute("DELETE FROM project_workspace_states WHERE project_id=?", (project_id,))
        db.execute("DELETE FROM project_members WHERE project_id=?", (project_id,))
        db.execute("DELETE FROM projects WHERE id=?", (project_id,))


def main() -> None:
    project = post("/projects", {
        "name": "MCP 계획 설명 브라우저 검증",
        "classification": "internal",
        "actor": "workspace-user",
    })
    project_id = project["id"]
    options = Options()
    options.add_argument("-headless")
    driver = webdriver.Firefox(options=options, service=Service(GECKODRIVER))
    report = {"projectId": project_id}
    try:
        driver.set_window_size(1280, 900)
        driver.get(URL)
        wait_for(driver, f'document.querySelector("[data-select-project=\\"{project_id}\\"]")')
        driver.find_element(By.CSS_SELECTOR, f'[data-select-project="{project_id}"]').click()
        wait_for(driver, "!document.querySelector('#workbench').hidden")

        driver.find_element(By.ID, "chatInput").send_keys("우리부 예산 현황을 확인하고 싶어")
        driver.find_element(By.CSS_SELECTOR, "#chatForm .send-button").click()
        wait_for(driver, "document.querySelector('#approvalDialog[open]')")
        wait_for(driver, "document.querySelectorAll('#planSteps .explained-mcp').length >= 1")
        cards = driver.execute_script(
            """
            return Array.from(document.querySelectorAll('#planSteps .explained-mcp')).map(card=>({
              name:card.querySelector('strong').textContent,
              role:Array.from(card.querySelectorAll('p')).find(p=>p.textContent.includes('무엇을 하나요')).textContent,
              reason:Array.from(card.querySelectorAll('p')).find(p=>p.textContent.includes('왜 호출하나요')).textContent,
              reference:card.querySelector('code').textContent
            }));
            """
        )
        report["mcpCount"] = len(cards)
        report["names"] = [item["name"] for item in cards]
        report["allHaveRoleAndReason"] = all(
            len(item["role"]) > len("무엇을 하나요")
            and len(item["reason"]) > len("왜 호출하나요")
            for item in cards
        )
        if not report["allHaveRoleAndReason"]:
            raise AssertionError(f"missing MCP explanation: {cards}")
        driver.find_element(By.CSS_SELECTOR, "#approvalDialog button[value=cancel]").click()
        report["status"] = "passed"
        print(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        driver.quit()
        cleanup(project_id)


if __name__ == "__main__":
    main()
