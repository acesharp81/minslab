import io
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
import pytest

from app.main import create_app
from app.store import digest, dump, now, uid
from test_flow import generate, new_case, seed


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path)) as c:
        yield c


def test_concurrent_edit_compare_and_swap(client):
    c = client
    base, rev = seed(c)
    item = rev["payload"]["items"][0]
    url = base + f"/revisions/{rev['id']}/items/{item['id']}"
    def change(value):
        return c.patch(url, json={"expected_hash": rev["hash"], "fields": {"due_date": value}, "reason": "동시 수정 시험"}).status_code
    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(change, ["2026-12-01", "2026-12-02"])) == [200, 409]
    assert len(c.get(base).json()["history"]) == 2


def test_request_idempotency_after_completion(client):
    base = new_case(client)
    client.post(base + "/demo")
    body = {"request_id": "one-explicit-generation"}
    rev = generate(client, base, body)
    response = client.post(base + "/generate", json=body)
    assert response.json()["reused"]
    assert client.get(base + "/revisions/current").json()["id"] == rev["id"]
    assert len(client.get(base).json()["jobs"]) == 1


def test_failed_stage_retry_preserves_completed_documents(client, monkeypatch):
    from app import jobs
    base = new_case(client)
    client.post(base + "/demo")
    original = jobs.rules_discover
    calls = []
    def fail_second(doc, blocks):
        calls.append(doc["path"])
        if len(calls) == 2:
            raise ValueError("의도적인 두 번째 문서 장애")
        return original(doc, blocks)
    monkeypatch.setattr(jobs, "rules_discover", fail_second)
    response = client.post(base + "/generate", json={})
    job_id = response.json()["job_id"]
    import time
    for _ in range(300):
        job = client.get(base).json()["jobs"][0]
        if job["status"] == "FAILED":
            break
        time.sleep(.01)
    assert job["status"] == "FAILED"
    assert client.get(base + "/revisions/current").json() is None
    first_calls = calls.count(calls[0])
    assert client.post(base + f"/jobs/{job_id}/retry").status_code == 200
    for _ in range(300):
        job = client.get(base).json()["jobs"][0]
        if job["status"] not in {"RUNNING", "QUEUED"}:
            break
        time.sleep(.01)
    assert job["status"] == "SUCCEEDED"
    assert calls.count(calls[0]) == first_calls
    assert job["attempts"] == 2


def test_restart_marks_interrupted_and_can_resume(tmp_path):
    with TestClient(create_app(tmp_path)) as c:
        base = new_case(c)
        c.post(base + "/documents", files={"file": ("인수.txt", "업무: 인수 시험\n담당: 가상팀".encode())})
        store = c.app.state.store
        doc = c.get(base).json()["documents"][0]
        job_id = uid()
        cfg = {"document_ids": [doc["id"]], "mode": "rules", "model": "label-rules-v1", "parent": None}
        with store.connect(write=True) as db:
            db.execute("INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (job_id, base.split('/')[-1], digest(cfg), "RUNNING", "DISCOVER", 10, 1, "", now(), now(), None, dump(cfg)))
    with TestClient(create_app(tmp_path)) as c:
        assert c.get(base).json()["jobs"][0]["status"] == "INTERRUPTED"
        assert c.post(base + f"/jobs/{job_id}/retry").status_code == 200
        import time
        for _ in range(300):
            row = c.get(base).json()["jobs"][0]
            if row["status"] not in {"RUNNING", "QUEUED"}:
                break
            time.sleep(.01)
        assert row["status"] == "SUCCEEDED"


def test_html_injection_and_bad_evidence_block_confirmation(client):
    c = client
    base, rev = seed(c)
    item = rev["payload"]["items"][0]
    body = {"expected_hash": rev["hash"], "fields": {"notes": '<img src=x onerror="alert(1)">'}, "reason": "이스케이프 시험"}
    edited = c.patch(base + f"/revisions/{rev['id']}/items/{item['id']}", json=body).json()
    assert c.post(base + f"/revisions/{edited['id']}/confirm", json={"expected_hash": edited["hash"], "acknowledge_warnings": True}).status_code == 200
    exported = c.get(base + f"/exports/{edited['id']}.html").text
    assert '<img src=x' not in exported
    assert c.post('/api/cases', json={"title": "외부 요청"}, headers={"Origin": "https://attacker.invalid"}).status_code == 403
    with c.app.state.store.connect(write=True) as db:
        payload = edited["payload"]
        payload["items"][0]["fields"]["title"]["evidence"][0]["block_id"] = "nonexistent"
        db.execute("UPDATE revisions SET payload=?,hash=? WHERE id=?", (dump(payload), digest(payload), edited["id"]))
    assert c.post(base + f"/revisions/{edited['id']}/confirm", json={"expected_hash": digest(payload), "acknowledge_warnings": True}).status_code == 422


def test_llm_http_contract_and_consent(tmp_path):
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["content-length"])))
            requests.append(body)
            document = json.loads(body["messages"][1]["content"])
            block = document["blocks"][0]
            fact = {"value": "가상 업무", "block_id": block["block_id"], "quote": "가상 업무"}
            result = {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps({"items": [{"fields": {"title": fact}}]})}}], "usage": {"total_tokens": 123}}
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
        def log_message(self, *_):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        config = {"url": f"http://127.0.0.1:{server.server_port}", "key": "synthetic-test-key", "model": "mock-contract"}
        with TestClient(create_app(tmp_path, config)) as c:
            base = new_case(c)
            c.post(base + "/documents", files={"file": ("문서.txt", "가상 업무 수행에 관한 자료".encode())})
            assert c.post(base + "/generate", json={"mode": "llm"}).status_code == 422
            assert not requests
            rev = generate(c, base, {"mode": "llm", "external_consent": True})
            assert rev["payload"]["mode"] == "llm"
            assert rev["payload"]["items"][0]["fields"]["title"]["value"] == "가상 업무"
            assert rev["payload"]["coverage"][0]["usage"]["total_tokens"] == 123
            assert "synthetic-test-key" not in json.dumps(rev)
    finally:
        server.shutdown()
        server.server_close()


def test_access_code_not_exposed_in_config(tmp_path, monkeypatch):
    monkeypatch.setenv("HANDOVER_ACCESS_TOKEN", "test-secret-code")
    with TestClient(create_app(tmp_path)) as c:
        assert c.get("/api/cases").status_code == 401
        assert c.post("/api/login", json={"token": "wrong"}).status_code == 401
        response = c.post("/api/login", json={"token": "test-secret-code"})
        assert response.status_code == 200
        assert "HttpOnly" in response.headers["set-cookie"]
        assert c.get("/api/cases").status_code == 200
        assert "test-secret-code" not in c.get("/api/config").text
