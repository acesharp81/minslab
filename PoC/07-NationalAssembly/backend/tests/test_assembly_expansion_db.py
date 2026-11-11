"""Real SQL in disposable tables; production rows and LLMs are never modified."""
import json
import os
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import psycopg
from psycopg import sql
import pytest

from app.domain import assembly_expansion as scope
from app.db.live_repository import LiveRepository


def test_capture_disable_history_and_final_report_queue(tmp_path, monkeypatch):
    dsn = os.environ.get("SHARED_TEST_DATABASE_URL")
    if not dsn: pytest.skip("explicit isolated PostgreSQL test connection required")
    schema = "test_expansion_" + uuid4().hex
    path = tmp_path / "scope.json"
    monkeypatch.setattr(scope, "config_path", lambda: path)
    now = datetime.now(timezone.utc)
    entry = {"committee_id": "TEST-COMMITTEE", "committee_name": "새위원회", "channel_code": "99",
             "meeting_external_id": "TEST-SELECTED", "enabled": True,
             "capture_from": (now-timedelta(hours=1)).isoformat(),
             "capture_until": (now+timedelta(hours=1)).isoformat()}
    def save(): path.write_text(json.dumps({"schema_version": scope.SCHEMA, "entries": [entry]}))
    save()
    with psycopg.connect(dsn.replace("postgresql+psycopg://", "postgresql://"), autocommit=True) as c:
        c.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        try:
            c.execute(sql.SQL("SET search_path TO {}, public").format(sql.Identifier(schema)))
            for table in ["live_broadcasts", "transcript_segments"]:
                c.execute(sql.SQL("CREATE TABLE {} (LIKE public.{} INCLUDING DEFAULTS)").format(sql.Identifier(table), sql.Identifier(table)))
            bids = {}
            for external, name in [("CORE", "행정안전위원회"), ("TEST-SELECTED", "새위원회"), ("TEST-OTHER", "새위원회")]:
                bids[external] = uuid4()
                c.execute("""INSERT INTO live_broadcasts
                    (id,institution,source_system,external_id,committee_name,title,lifecycle_status,
                     caption_source_status,detected_at,last_seen_at,latest_source_document_version_id,
                     caption_websocket_url,capture_status)
                    VALUES (%s,'LEGISLATURE','assembly.webcast.go.kr',%s,%s,'fixture','LIVE','READY_TO_CAPTURE',
                            now(),now(),%s,'wss://example.invalid/test','READY')""", (bids[external],external,name,uuid4()))
            repo = LiveRepository(c)
            # Watch/event FK checks retain KEY SHARE while projecting a digest.
            # Caption health changes no key and must not wait behind that lock.
            with psycopg.connect(dsn.replace("postgresql+psycopg://", "postgresql://")) as blocker:
                blocker.execute(sql.SQL("SELECT id FROM {}.live_broadcasts WHERE id=%s FOR KEY SHARE").format(sql.Identifier(schema)), (bids["CORE"],))
                c.execute("SET lock_timeout='700ms'")
                assert repo.mark_official_caption_received(bids["CORE"]) == "ACTIVE"
                first_claim = repo.claim_caption_capture("test")
                assert first_claim["external_id"] == "CORE"
                c.execute("SET lock_timeout=0")
            claims = [first_claim] + [repo.claim_caption_capture("test") for _ in range(2)]
            assert {r["external_id"] for r in claims if r} == {"CORE", "TEST-SELECTED"}
            assert repo.heartbeat_capture(bids["TEST-SELECTED"], "test")
            entry["enabled"] = False; save()
            assert not repo.heartbeat_capture(bids["TEST-SELECTED"], "test")
            assert repo.heartbeat_capture(bids["CORE"], "test")
            assert c.execute("SELECT lifecycle_status FROM live_broadcasts WHERE id=%s", (bids["TEST-SELECTED"],)).fetchone()[0] == "LIVE"
            # Real end is independent of capture permission; keep result access.
            c.execute("UPDATE live_broadcasts SET lifecycle_status='ENDED',ended_at=now()")
            regular = repo.list_ended_broadcasts(collection="regular")
            tests = repo.list_ended_broadcasts(collection="expansion_test")
            assert [r["external_id"] for r in regular] == ["CORE"]
            assert [r["external_id"] for r in tests] == ["TEST-SELECTED"]
            for external in bids:
                c.execute("""INSERT INTO transcript_segments
                    (id,broadcast_id,source_segment_id,current_text,is_final,first_received_at,last_received_at)
                    VALUES (%s,%s,'1','테스트 발언',true,now(),now())""", (uuid4(),bids[external]))
            from app.ingestion import meeting_brief_worker as worker
            monkeypatch.setattr(worker, "connect", lambda _: nullcontext(c))
            monkeypatch.setattr(worker, "get_settings", lambda: SimpleNamespace(database_url="test", meeting_brief_provider="auto"))
            monkeypatch.setattr(worker, "meeting_brief_identity", lambda _: ("openrouter", "test", "test"))
            assert set(worker.eligible_broadcast_ids(limit=20)) == {bids["CORE"], bids["TEST-SELECTED"]}
        finally:
            c.execute("SET search_path TO public")
            c.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
