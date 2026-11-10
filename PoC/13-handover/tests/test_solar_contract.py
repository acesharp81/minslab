import json
import httpx
import pytest
from app import engine

BLOCK = {"id": "immutable-id", "doc_id": "doc", "parse_id": "parse", "text": "문화기획팀은 사업계획을 준비하고 있다."}
DOCUMENT = {"id": "doc", "path": "합성.txt"}


def output(block_id="B1", quote="사업계획"):
    return {"items": [{"fields": {"title": {"block_id": block_id, "quote": quote}, "status": None, "owner": None, "due_date": None, "next_action": None, "notes": None}}]}


def fake_client(monkeypatch, responses):
    calls = []
    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, url, headers, json):
            calls.append(json)
            value = responses[min(len(calls) - 1, len(responses) - 1)]
            if isinstance(value, int):
                return httpx.Response(value, json={"error": "provider-secret-not-for-ui"})
            return httpx.Response(200, json={"model": "solar-pro4-test", "choices": [{"finish_reason": "stop", "message": {"content": __import__('json').dumps(value)}}], "usage": {"prompt_tokens": 50, "completion_tokens": 30, "total_tokens": 80}})
    monkeypatch.setattr(engine.httpx, "Client", Client)
    monkeypatch.setattr(engine.time, "sleep", lambda _: None)
    return calls


def test_quote_only_contract_preserves_original_and_nulls():
    value = output("immutable-id")
    candidate = engine.validate_model_result(value, DOCUMENT, [BLOCK])[0]
    assert candidate["fields"]["title"]["value"] == "사업계획"
    assert candidate["fields"]["status"]["value"] == ""
    with pytest.raises(ValueError):
        engine.validate_model_result(output("immutable-id", "사업계획 준비"), DOCUMENT, [BLOCK])


def test_validation_retry_keeps_evidence_checks_and_aggregates_usage(monkeypatch):
    calls = fake_client(monkeypatch, [output("B900"), output()])
    result = engine.llm_discover(DOCUMENT, [BLOCK], {"url": "https://model.invalid", "model": "solar-pro4", "key": "not-a-real-key"})
    assert len(calls) == 2
    assert calls[0]["response_format"]["type"] == "json_schema"
    assert calls[0]["response_format"]["json_schema"]["strict"]
    assert result["usage"]["total_tokens"] == 160
    assert result["calls"][0]["valid"] is False
    assert result["calls"][1]["valid"] is True
    ref = result["candidates"][0]["fields"]["title"]["evidence"][0]
    assert ref["block_id"] == BLOCK["id"]
    assert "not-a-real-key" not in json.dumps(result)


def test_failed_retry_retains_diagnostic_without_creating_candidates(monkeypatch):
    fake_client(monkeypatch, [output(quote="존재하지 않는 업무")])
    with pytest.raises(engine.ModelFailure) as exc:
        engine.llm_discover(DOCUMENT, [BLOCK], {"url": "https://model.invalid", "model": "solar-pro4", "key": "not-a-real-key"})
    assert len(exc.value.diagnostic["calls"]) == 2
    assert exc.value.diagnostic["usage"]["total_tokens"] == 160
    assert "not-a-real-key" not in str(exc.value)


def test_auth_failure_is_not_retried_or_reflected(monkeypatch):
    calls = fake_client(monkeypatch, [401])
    with pytest.raises(engine.ModelFailure) as exc:
        engine.llm_discover(DOCUMENT, [BLOCK], {"url": "https://model.invalid", "model": "solar-pro4", "key": "not-a-real-key"})
    assert len(calls) == 1
    assert "provider-secret" not in str(exc.value)
