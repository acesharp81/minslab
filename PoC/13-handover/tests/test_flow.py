import io
import json
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app.engine import validate_model_result
from app.main import create_app


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path)) as c:
        yield c


def new_case(c, title="합성 인수인계"):
    response = c.post("/api/cases", json={"title": title})
    assert response.status_code == 201, response.text
    return "/api/cases/" + response.json()["id"]


def generate(c, base, body=None):
    response = c.post(base + "/generate", json=body or {})
    assert response.status_code == 202, response.text
    job_id = response.json()["job_id"]
    for _ in range(300):
        details = c.get(base).json()
        job = next(j for j in details["jobs"] if j["id"] == job_id)
        if job["status"] not in {"RUNNING", "QUEUED"}:
            assert job["status"] == "SUCCEEDED", job
            return c.get(base + "/revisions/current").json()
        time.sleep(.03)
    pytest.fail("job timeout")


def seed(c):
    base = new_case(c)
    response = c.post(base + "/demo")
    assert response.status_code == 200, response.text
    return base, generate(c, base)


def test_complete_handover_and_immutable_history(client):
    c = client
    base, original = seed(c)
    payload = original["payload"]
    assert len(payload["items"]) == 5
    titles = {item["fields"]["title"]["value"] for item in payload["items"]}
    assert titles == {"2027년 생활문화 사업계획", "주민참여 워크숍 운영", "보조금 정산 검토", "월간 실적 보고", "시설 안전점검"}
    assert {d["format"] for d in c.get(base).json()["documents"]} == {".hwpx", ".docx", ".xlsx", ".pdf", ".txt"}
    assert all(d["block_count"] for d in c.get(base).json()["documents"])
    item = next(i for i in payload["items"] if "생활문화" in i["fields"]["title"]["value"])
    assert item["fields"]["due_date"]["review_status"] == "CONFLICT"
    assert "11월 말" == next(i for i in payload["items"] if "보조금" in i["fields"]["title"]["value"])["fields"]["due_date"]["value"]
    for work in payload["items"]:
        for field in work["fields"].values():
            for ref in field["evidence"]:
                source = c.get(base + "/blocks/" + ref["block_id"]).json()
                assert ref["quote"] in source["text"]
    edit_url = base + f"/revisions/{original['id']}/items/{item['id']}"
    body = {"expected_hash": original["hash"], "fields": {"due_date": "2026-11-27"}, "reason": "전임자가 변경 일정을 직접 확인"}
    assert c.patch(edit_url, json=body, headers={"X-Role": "successor"}).status_code == 403
    edited = c.patch(edit_url, json=body)
    assert edited.status_code == 200, edited.text
    edited = edited.json()
    assert edited["id"] != original["id"]
    assert c.patch(edit_url, json=body).status_code == 409
    field = next(i for i in edited["payload"]["items"] if i["id"] == item["id"])["fields"]["due_date"]
    assert field["provenance"] == "HUMAN_ENTERED" and not field["evidence"] and field["previous"]["evidence"]
    url = base + f"/revisions/{edited['id']}/confirm"
    assert c.post(url, json={"expected_hash": edited["hash"]}).status_code == 422
    assert c.post(url, json={"expected_hash": edited["hash"], "acknowledge_warnings": True}).status_code == 200
    successor = c.get(base + "/revisions/confirmed", headers={"X-Role": "successor"}).json()
    assert successor["id"] == edited["id"] and successor["hash"] == edited["hash"]
    assert c.get(base + "/revisions/" + original["id"]).json()["payload"] == payload
    for fmt in ["md", "html"]:
        result = c.get(base + f"/exports/{edited['id']}.{fmt}")
        assert result.status_code == 200 and "2026-11-27" in result.text and "2026-11-20" in result.text
    c.post(base + "/reindex")
    assert c.get(base + "/revisions/confirmed").json()["hash"] == edited["hash"]
    assert c.post(base + "/accept", headers={"X-Role": "successor"}, json={"expected_hash": edited["hash"]}).status_code == 200
    assert c.get(base).json()["accepted"]
    accepted = c.get(base).json()["accepted"]
    assert c.post(url, json={"expected_hash": edited["hash"], "acknowledge_warnings": True}).status_code == 200
    assert c.get(base).json()["accepted"] == accepted
    # A later generation must not replace what the successor reads.
    generate(c, base)
    assert c.get(base + "/revisions/confirmed").json()["id"] == edited["id"]


def test_scope_search_and_malformed_input(client):
    c = client
    base, rev = seed(c)
    other = new_case(c, "별도 사건")
    ref = rev["payload"]["items"][0]["fields"]["title"]["evidence"][0]
    assert c.get(other + "/blocks/" + ref["block_id"]).status_code == 404
    assert c.get(other + "/revisions/" + rev["id"]).status_code == 404
    assert c.get(other + "/search", params={"q": "주민"}).json()["results"] == []
    results = c.get(base + "/search", params={"q": "영수증"}).json()["results"]
    assert any("영수증" in b["text"] for b in results)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("../escape.txt", "bad")
    assert c.post(other + "/documents", files={"file": ("bad.zip", buf.getvalue())}).status_code == 422
    c.post(other + "/documents", files={"file": ("손상.pdf", b"invalid")})
    c.post(other + "/documents", files={"file": ("script.exe", b"MZ123")})
    generate(c, other)
    assert {d["status"] for d in c.get(other).json()["documents"]} == {"FAILED", "UNSUPPORTED"}


def test_new_source_requires_new_draft_and_duplicate_upload(client):
    c = client
    base, rev = seed(c)
    n = len(c.get(base).json()["documents"])
    doc = c.get(base).json()["documents"][0]
    raw = c.get(base + f"/documents/{doc['id']}/raw").content
    response = c.post(base + "/documents", files={"file": (doc["path"], raw)})
    assert response.json()["documents"][0]["duplicate"]
    assert len(c.get(base).json()["documents"]) == n
    c.post(base + "/documents", files={"file": ("추가.txt", "업무: 추가업무".encode())})
    assert c.post(base + f"/revisions/{rev['id']}/confirm", json={"expected_hash": rev["hash"], "acknowledge_warnings": True}).status_code == 409


def test_invalid_llm_fact_is_not_a_draft():
    block = {"id": "b", "text": "제출 예정", "doc_id": "doc", "parse_id": "p"}
    document = {"id": "doc"}
    with pytest.raises(ValueError):
        validate_model_result({"items": [{"fields": {"title": {"value": "완료", "quote": "제출 예정", "block_id": "b"}}}]}, document, [block])
    with pytest.raises(ValueError):
        validate_model_result({"items": [{"fields": {"title": {"value": "제출", "quote": "제출 예정", "block_id": "other"}}}]}, document, [block])
