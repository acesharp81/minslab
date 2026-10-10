"""Disposable UI workflow server. Uses SQLite /tmp, never the HOME database."""
import os
from datetime import datetime, timezone

import uvicorn
from backend.db import Base, Batch, Mapping, engine_for, upsert_revision
from backend.service import HomeService
from backend.sources import POLICIES
from backend.history_data import POLICY_EVENTS

os.environ["POC10_DATABASE_URL"] = "sqlite:////tmp/home-workflow-fixture.sqlite"
os.environ["POC10_INTERNAL_SECRET"] = "fixture-only-admin"
os.environ["POC10_AUTO_COLLECT"] = "false"
engine = engine_for()
Base.metadata.create_all(engine)
service = HomeService(engine, "/tmp/home-workflow-data")
with service.sessions.begin() as session:
    batch = Batch(id="fixture", source_id="lh_sale", status="SUCCESS", finished_at=datetime.now(timezone.utc),
                  stats={}, manifest=[])
    session.add(batch)
    for source_id, spec in POLICIES.items():
        upsert_revision(session,"policy",source_id,spec["id"],dict(spec,base_date=spec["announced_at"],
            evidence_url="https://www.korea.kr/",lifecycle_status="REVIEW"),"fixture")
    for event in POLICY_EVENTS:
        upsert_revision(session,"policy_event","policy_history",event["event_id"],dict(event,
            base_date=event["event_date"],evidence_url=event["url"]),"fixture")
    for block, units in (("A1",100),("A2",200)):
        payload=dict(name="테스트 고양창릉 "+block,region="경기도",municipality="고양시",program="3기 신도시",
                     planned_units=units,source_id="lh_sale",base_date="2026-01-01",date_precision="YEAR",
                     stage="PLANNED_SUPPLY",stage_label="공급계획",warnings=[],proposed_policy="POL_2025_0907",
                     mapping_basis="테스트 원천 제안",evidence_url="https://apply.lh.or.kr/",
                     rows=[dict(units=units,supply_month="2026-07",move_in_month="2028-03")])
        row,_=upsert_revision(session,"project","lh_sale",block,payload,"fixture")
        session.add(Mapping(project_id=row.entity_id,policy_id="POL_2025_0907",status="REVIEW",
                            basis="테스트 원천 제안",evidence_url="https://apply.lh.or.kr/"))
    upsert_revision(session,"notice","cheongyak","N",dict(name="테스트 고양창릉 A1블록 공공분양주택",
        region="경기도",base_date="2026-08-01",source_date="2026-08-01",developer="한국토지주택공사",
        units=40,sample_kind="notice",house_manage_no="TEST-H1",evidence_url="https://apply.lh.or.kr/"),"fixture")

from backend.app import create_app
uvicorn.run(create_app(engine,auto_collect=False),host="0.0.0.0",port=8000,log_level="warning")
