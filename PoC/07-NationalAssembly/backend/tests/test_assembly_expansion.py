import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock

import pytest

from app.domain import assembly_expansion as scope
from app.adapters.live_sources import parse_assembly_live_list
from app.db.live_repository import LiveRepository


def entry():
    return dict(committee_id="TEST-COMMITTEE", committee_name="새위원회",
                channel_code="TEST-CHANNEL", meeting_external_id="TEST-MEETING",
                capture_from="2026-11-11T08:00:00+09:00",
                capture_until="2026-11-12T09:00:00+09:00", enabled=True)


@pytest.fixture
def config(tmp_path, monkeypatch):
    path = tmp_path / "scope.json"
    monkeypatch.setattr(scope, "config_path", lambda: path)
    return path


def write(path, entries):
    path.write_text(json.dumps({"schema_version": scope.SCHEMA, "entries": entries}))


def test_hot_reload_add_disable_and_retain_provenance(config):
    assert scope.meeting_ids() == []
    e = entry(); write(config, [e])
    assert scope.meeting_ids() == ["TEST-MEETING"]
    assert scope.meeting_metadata("TEST-MEETING")["expansion_label"] == "확장성 테스트용"
    e["enabled"] = False; write(config, [e])
    assert scope.meeting_ids(capture=True) == []
    assert scope.meeting_ids() == ["TEST-MEETING"]
    config.write_text("broken")
    assert scope.meeting_ids(capture=True) == []


@pytest.mark.parametrize("time,expected", [
    ("2026-11-11T07:59:59+09:00", False), ("2026-11-11T08:00:00+09:00", True),
    ("2026-11-12T00:05:00+09:00", True), ("2026-11-12T09:00:00+09:00", False),
])
def test_capture_window(time, expected):
    assert scope.capture_allowed(entry(), datetime.fromisoformat(time)) is expected


def test_invalid_window_and_duplicate_rejected():
    e = entry(); e["capture_until"] = "2026-12-01T09:00:00+09:00"
    with pytest.raises(ValueError): scope.validate_config(dict(schema_version=scope.SCHEMA, entries=[e]))
    with pytest.raises(ValueError): scope.validate_config(dict(schema_version=scope.SCHEMA, entries=[entry(), entry()]))


def test_exact_official_identifiers_only_and_existing_committees_unchanged(config):
    payload = json.loads((Path(__file__).parent / "fixtures/synthetic_assembly_live_list.json").read_text())
    before = parse_assembly_live_list(json.dumps(payload).encode())
    e = entry(); write(config, [e])
    row = dict(xname="새위", xbill=e["committee_id"], xcode=e["channel_code"],
               xcgcd=e["meeting_external_id"], xstat="1", xdesc="속개")
    payload["xlist"].append(row)
    after = parse_assembly_live_list(json.dumps(payload).encode())
    assert after["items"][:-1] == before["items"]
    assert after["items"][-1]["is_expansion_test"]
    for field in ["xbill", "xcode", "xcgcd"]:
        wrong = deepcopy(payload); wrong["xlist"][-1][field] = "OTHER"
        assert parse_assembly_live_list(json.dumps(wrong).encode())["items"] == before["items"]
    # Disabled entries still convey actual live/recess status; never invent ENDED.
    e["enabled"] = False; write(config, [e])
    result = parse_assembly_live_list(json.dumps(payload).encode())["items"][-1]
    assert result["is_live"] and not result["capture_allowed"]


@pytest.mark.parametrize("method,args", [
    ("claim_caption_capture", ("worker",)), ("claim_audio_fallback_capture", ("worker",)),
    ("heartbeat_capture", ("broadcast", "worker")),
    ("heartbeat_audio_fallback", ("broadcast", "worker")),
])
def test_capture_sql_parameters_and_expiry_guard(config, method, args):
    write(config, [entry()])
    conn = Mock(); conn.execute.return_value.fetchone.return_value = None
    getattr(LiveRepository(conn), method)(*args)
    sql, params = conn.execute.call_args.args
    assert sql.count("%s") == len(params)
    assert "external_id = ANY(%s)" in sql
    assert "행정안전위원회" in next(p for p in params if isinstance(p, list) and "행정안전위원회" in p)


def test_report_collection_api_and_markdown(config, monkeypatch):
    from fastapi.testclient import TestClient
    from contextlib import nullcontext
    from app import main
    write(config, [entry()])
    repo = Mock(); repo.list_ended_broadcasts.return_value = []
    monkeypatch.setattr(main, "connect", lambda _: nullcontext(Mock()))
    monkeypatch.setattr(main, "LiveRepository", lambda _: repo)
    client = TestClient(main.app)
    for collection in ["regular", "expansion_test"]:
        result = client.get("/api/live/broadcasts", params={"collection": collection})
        assert result.status_code == 200
        assert repo.list_ended_broadcasts.call_args.kwargs["collection"] == collection
    assert client.get("/api/live/broadcasts?collection=bad").status_code == 422
    assert client.get("/api/live/expansion-tests").json()["items"][0]["committee_id"] == "TEST-COMMITTEE"
    assert "확장성 테스트용" in main._meeting_brief_markdown({"brief": {}, "is_expansion_test": True})
    assert "확장성 테스트용" not in main._meeting_brief_markdown({"brief": {}})


def test_identifier_registration_resolves_one_meeting_and_rejects_ambiguity():
    import importlib.util
    spec = importlib.util.spec_from_file_location("expansion_cli", Path(__file__).parents[2] / "scripts/manage_assembly_expansion.py")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    listing = {"xlist": [{"xbill": "NEW", "xcode": "99"}]}
    row = {"xcode": "99", "xcgcd": "MEETING-1", "xconf": "제1차 새로운위원회", "xsubj": "회의", "xdesc": "10:00"}
    calendar = {"xdays": [{"xdate": "20261111", "xlist": [row]}]}
    selected = module.resolve_meeting("NEW", "2026-11-11", calendar, listing)
    assert selected["committee_name"] == "새로운위원회"
    assert selected["meeting_external_id"] == "MEETING-1"
    calendar["xdays"][0]["xlist"].append({**row, "xcgcd": "MEETING-2"})
    with pytest.raises(ValueError): module.resolve_meeting("NEW", "2026-11-11", calendar, listing)
    assert module.resolve_meeting("NEW", "2026-11-11", calendar, listing, "MEETING-1") == selected


@pytest.mark.parametrize("allowed,recess,mismatch,observed", [
    (True, False, False, 1), (False, False, False, 0),
    (True, True, False, 0), (True, False, True, 0),
])
def test_monitor_capture_and_real_lifecycle_are_independent(config, tmp_path, monkeypatch, allowed, recess, mismatch, observed):
    from datetime import timezone
    from app.ingestion import live_monitor
    from app.adapters.national_assembly.base import SourcePayload
    e = entry(); write(config, [e])
    monkeypatch.setattr("app.adapters.live_sources.capture_allowed", lambda _: allowed)
    fixtures = Path(__file__).parent / "fixtures"
    listing = json.loads((fixtures / "synthetic_assembly_live_list.json").read_text())
    for row in listing["xlist"]: row.update(xstat="0", xcgcd="")
    listing["xlist"].append(dict(xname="새위", xbill=e["committee_id"], xcode=e["channel_code"],
                                xcgcd=e["meeting_external_id"], xstat="0" if recess else "1",
                                xdesc="정회" if recess else "속개"))
    play = json.loads((fixtures / "synthetic_assembly_live_play.json").read_text())
    play.update(xcode=e["channel_code"], xcgcd="WRONG" if mismatch else e["meeting_external_id"])
    calls = []
    def fetch(key, url):
        calls.append(key)
        content = listing if key == "assembly_live_list" else play if key == "assembly_live_play" else []
        return SourcePayload(key, json.dumps(content).encode(), "application/json", datetime.now(timezone.utc), url, 200)
    monkeypatch.setattr(live_monitor, "fetch_public_source", fetch)
    sink = Mock(); sink.observe_broadcast.return_value = "test-broadcast"
    live_monitor.probe_assembly_live_once(tmp_path / "raw", tmp_path / "status.json", sink)
    assert sink.observe_broadcast.call_count == observed
    assert e["meeting_external_id"] in sink.finish_poll.call_args.args[0]
    if not allowed or recess: assert "assembly_live_play" not in calls
