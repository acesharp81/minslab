"""Opt-in live Solar evaluation against synthetic data only. Never reads uploaded documents."""
import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import dotenv_values
from fastapi.testclient import TestClient
from app.demo import expanded_archive
from app.main import create_app

EXPECTED = ["2027년 생활문화 사업계획", "주민참여 워크숍 운영", "보조금 정산 검토", "월간 실적 보고", "시설 안전점검", "분기별 문화시설 이용통계", "작은도서관 프로그램 개편", "2027년 문화행사 예산안", "지역예술인 간담회", "주민 공모사업 모집", "동네 기록전시 준비"]
root = Path(__file__).resolve().parents[1]
settings = dotenv_values(root / ".env")
assert settings.get("HANDOVER_LLM_KEY"), "프로젝트 모델 키가 필요합니다."
config = {"url": settings["HANDOVER_LLM_URL"], "model": "solar-pro4", "key": settings["HANDOVER_LLM_KEY"]}
out = root / "test-results" / "solar4-v040"
out.mkdir(parents=True, exist_ok=True)
start = time.monotonic()
with tempfile.TemporaryDirectory(prefix="handover-solar-eval-") as temp, TestClient(create_app(temp, config)) as c:
    case_id = c.post("/api/cases", json={"title": "Solar Pro 4 · 12개 합성 문서 검증"}).json()["id"]
    base = "/api/cases/" + case_id
    archive = expanded_archive()
    (out / "synthetic-fixtures.zip").write_bytes(archive)
    assert c.post(base + "/documents", files={"file": ("synthetic.zip", archive)}).status_code == 200
    job_id = c.post(base + "/generate", json={"mode": "llm", "external_consent": True, "request_id": "live-eval-1"}).json()["job_id"]
    last = None
    for _ in range(900):
        details = c.get(base).json()
        job = next(j for j in details["jobs"] if j["id"] == job_id)
        progress = (job["stage"], job["progress"])
        if progress != last:
            print("progress", progress, flush=True); last = progress
        if job["status"] not in {"QUEUED", "RUNNING"}:
            break
        time.sleep(1)
    if job["status"] != "SUCCEEDED":
        (out / "failure.json").write_text(json.dumps({"job": job, "audit": c.app.state.store.rows("SELECT action,detail FROM audit WHERE case_id=?", (case_id,))}, ensure_ascii=False, indent=2))
        raise RuntimeError(job["error"])
    rev = c.get(base + "/revisions/current").json()
    (out / "revision.json").write_text(json.dumps(rev, ensure_ascii=False, indent=2))
    items = rev["payload"]["items"]
    titles = [i["fields"]["title"]["value"] for i in items]
    checks = {"core_coverage": all(any(t in title for title in titles) for t in EXPECTED), "no_extra_work": len(items) == len(EXPECTED), "scan_failed": any(d["path"].startswith("12_") and d["status"] == "FAILED" for d in details["documents"])}
    target = next(i for i in items if "2027년 생활문화 사업계획" in i["fields"]["title"]["value"])
    checks["due_conflict"] = target["fields"]["due_date"]["review_status"] == "CONFLICT"
    policy = next(i for i in items if "작은도서관" in i["fields"]["title"]["value"])
    checks["consulted_is_not_owner"] = "독서정책팀" not in policy["fields"]["owner"]["value"]
    checks["no_fake_completion"] = all(i["business_status"] != "COMPLETED" for i in items if "점검" in i["fields"]["title"]["value"] or "모집" in i["fields"]["title"]["value"])
    checks["report_progress_fields"] = all(i["fields"][k]["value"] for i in items[:5] for k in ["completed_work", "remaining_work", "issues"])
    citations = 0
    for item in items:
        for field in item["fields"].values():
            for ref in field["evidence"]:
                block = c.get(base + "/blocks/" + ref["block_id"]).json()
                assert ref["quote"] in block["text"]
                citations += 1
    edited = c.patch(base + f"/revisions/{rev['id']}/items/{target['id']}", json={"expected_hash": rev["hash"], "fields": {"due_date": "2026-11-27"}, "reason": "전임자 확인 · 실제 Solar 초안 검증"}).json()
    confirmed = c.post(base + f"/revisions/{edited['id']}/confirm", json={"expected_hash": edited["hash"], "acknowledge_warnings": True})
    checks["confirm"] = confirmed.status_code == 200
    successor = c.get(base + "/revisions/confirmed", headers={"X-Role": "successor"}).json()
    checks["successor_same_revision"] = successor["id"] == edited["id"]
    questions = [
        ("생활문화 사업계획의 최종 기한은 언제인가요?", "due_date", "2026-11-27"),
        ("보조금 정산 검토에서 막힌 문제는 무엇인가요?", "issues", "영수증"),
        ("생활문화 사업계획 협의 부서와 연락처를 알려주세요", "contacts", "culture@example.invalid"),
        ("문화기획팀 담당자의 생일은 언제인가요?", None, None),
    ]
    answers = []
    for question, field, expected in questions:
        response = c.post(base + "/questions", json={"question": question, "expected_revision": edited["id"], "mode": "llm", "external_consent": True})
        assert response.status_code == 200, response.text
        answer = response.json()
        if field:
            assert any(f["field"] == field and expected in f["value"] for f in answer["facts"]), answer
        else:
            assert not answer["facts"] and answer["status"] == "NOT_IN_CONFIRMED", answer
        answers.append(answer)
    checks["live_questions"] = True
    (out / "questions.json").write_text(json.dumps(answers, ensure_ascii=False, indent=2))
    final_report = c.get(base + "/reports/confirmed")
    checks["report_both_parties_equal"] = final_report.status_code == 200 and final_report.text == c.get(base + "/reports/confirmed", headers={"X-Role": "successor"}).text
    for fmt in ["md", "html"]:
        export = c.get(base + f"/exports/{edited['id']}.{fmt}")
        checks["export_" + fmt] = export.status_code == 200 and "2026-11-27" in export.text
        (out / ("handover-confirmed." + fmt)).write_text(export.text)
    coverage = rev["payload"]["coverage"]
    report = {"model": config["model"], "resolved_models": sorted({r["resolved_model"] for r in coverage if r.get("resolved_model")}), "seconds": round(time.monotonic() - start, 2), "documents": len(details["documents"]), "items": len(items), "expected_items": len(EXPECTED), "titles": titles, "quotes_verified": citations, "checks": checks, "model_calls": sum(len(r.get("calls", [])) for r in coverage), "usage": {key: sum(r.get("usage", {}).get(key, 0) for r in coverage) for key in ["prompt_tokens", "completion_tokens", "total_tokens"]}, "question_calls": len(answers), "question_usage": {key: sum(a["usage"].get(key, 0) for a in answers) for key in ["prompt_tokens", "completion_tokens", "total_tokens"]}}
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    assert all(checks.values()), "실제 모델 평가의 실패 항목을 확인하세요."
