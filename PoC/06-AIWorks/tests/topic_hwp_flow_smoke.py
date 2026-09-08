"""Firefox E2E for grounded topic search followed by an HWP report request."""

from __future__ import annotations

import base64
import json
import os
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
ACTOR = "topic-hwp-smoke"


def api(path: str, method: str = "GET", payload: dict | None = None) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        API + path, data=data, headers={"Content-Type": "application/json"}, method=method
    )
    return json.load(urllib.request.urlopen(request, timeout=30))


def wait_for(driver, expression: str, timeout: int = 60):
    return WebDriverWait(driver, timeout).until(
        lambda current: current.execute_script(f"return Boolean({expression})")
    )


def approve(driver):
    wait_for(driver, "document.querySelector('#approvalDialog').open")
    driver.execute_script("document.querySelector('#approvalDialog').close('approve')")
    wait_for(driver, "!document.querySelector('#approvalDialog').open")


def send_chat(driver, text: str):
    node = driver.find_element(By.ID, "chatInput")
    node.clear()
    node.send_keys(text)
    driver.find_element(By.CSS_SELECTOR, "#chatForm .send-button").click()
    approve(driver)


def cleanup(project: dict):
    try:
        api(f"/projects/{project['id']}/status", "POST", {"action": "archive", "actor": ACTOR})
        api(
            f"/projects/{project['id']}", "DELETE",
            {"actor": ACTOR, "confirmation": project["name"], "acknowledge_irreversible": True},
        )
    except Exception as error:
        print(f"warning: topic HWP fixture cleanup failed: {error}")


def register_source(project_id: str, filename: str, content: str) -> dict:
    return api(
        f"/projects/{project_id}/sources",
        "POST",
        {
            "filename": filename,
            "content_base64": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "classification": "internal",
            "actor": ACTOR,
        },
    )


def main():
    if not Path(GECKODRIVER).exists():
        raise SystemExit(f"geckodriver not found: {GECKODRIVER}")
    project = api(
        "/projects", "POST",
        {"name": f"범정부 AI HWP 검증 {os.getpid()}", "actor": ACTOR},
    )
    register_source(
        project["id"],
        "2026년_범정부_AI_공통기반_지적사항.txt",
        (
            "76쪽 범정부 인공지능 공통기반 사업은 사전계획 수립 지연이 지적되었다. "
            "77쪽 개별 AI 사업의 선행 착수로 중복투자 우려가 있다. "
            "78쪽 공통기반 활용계획을 의무화해야 한다. "
            "79쪽 단계별 성과지표와 집행 점검이 필요하다. "
            "80쪽 향후 기관별 이행 현황을 정기 점검해야 한다."
        ),
    )
    register_source(
        project["id"],
        "A-WEB_무관자료.txt",
        "A-WEB은 해외 선거기관 대상 전자선거 제도 협력 및 연수 사업을 수행한다.",
    )
    options = Options()
    options.add_argument("-headless")
    driver = webdriver.Firefox(options=options, service=Service(GECKODRIVER))
    try:
        driver.set_window_size(1440, 950)
        driver.get(URL)
        wait_for(driver, f'document.querySelector("[data-select-project=\\"{project["id"]}\\"]")')
        driver.find_element(By.CSS_SELECTOR, f'[data-select-project="{project["id"]}"]').click()
        wait_for(driver, "document.querySelector('#workbench').hidden === false")

        send_chat(driver, "범정부AI 공통기반에 관련된 지적 사항을 찾아줘")
        wait_for(driver, "document.querySelector('.result-sources') && !document.querySelector('.message.streaming')")
        wait_for(driver, "document.querySelector('.rhwp-edit-answer')")
        chat_text = driver.find_element(By.ID, "chat").text
        if "범정부" not in chat_text or "공통기반" not in chat_text:
            raise AssertionError("grounded answer did not contain the requested topic")
        if "A-WEB" in chat_text:
            raise AssertionError("unrelated A-WEB evidence leaked into the requested topic answer")
        if not any(page in chat_text for page in ("76쪽", "77쪽", "78쪽", "79쪽", "80쪽")):
            raise AssertionError("grounded answer did not cite the expected common AI platform pages")

        send_chat(driver, "보고서를 HWP로 만들어줘")
        wait_for(
            driver,
            "document.querySelector('#rhwpEditorHost iframe') && document.querySelector('#rhwpEditorHost').dataset.ready === 'true'",
        )
        documents = api(f"/projects/{project['id']}/documents").get("items") or []
        if not documents:
            raise AssertionError("HWP request did not persist a Markdown source document")
        report = api(f"/projects/{project['id']}/documents/{documents[0]['id']}")
        markdown = str(report.get("markdown") or "")
        if "범정부" not in markdown or "공통기반" not in markdown:
            raise AssertionError("HWP report did not retain the grounded topic")
        forbidden = [term for term in ("HWP 사용 방법", "RHWP 편집 링크", "다운로드하여 한글에서") if term in markdown]
        if forbidden:
            raise AssertionError("HWP usage guidance leaked into report content: " + ", ".join(forbidden))
        filename = driver.find_element(By.ID, "contextFile").text
        if not filename.endswith(".hwpx"):
            raise AssertionError(f"HWP request did not open an editable HWPX: {filename}")
        print(json.dumps({
            "status": "passed", "topic": "범정부 AI 공통기반", "unrelatedEvidenceExcluded": True,
            "reportFilename": filename, "usageGuideExcluded": True,
        }, ensure_ascii=False, indent=2))
    finally:
        driver.quit()
        cleanup(project)


if __name__ == "__main__":
    main()
