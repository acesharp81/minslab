import os
import tempfile
import unittest
from datetime import date
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.pool import StaticPool

from backend.app import create_app
from backend.db import Base, Mapping, Audit, upsert_revision
from backend.service import HomeService, today
from backend.policy_monitor import catalogue, automatic_proposal, build_monitor
from backend.connection_audit import connection_audit


def policy(pid="POL", **extra):
    return dict(policy_id=pid, id=pid, name=pid, announced_at="2025-09-07", target_units=100000,
                target_scope="수도권 (인천 포함)", metric="착공", monitor_kind="POLICY", evidence_url="https://www.korea.kr/", **extra)


def project(pid="P", **extra):
    row=dict(id=pid, source_id="lh_sale", name="고양창릉 A1", region="경기도", municipality="고양시",
             program="3기 신도시", planned_units=100, base_date="2026-01-01", date_precision="YEAR",
             warnings=[], stage="PLANNED_SUPPLY", stage_label="공급계획",
             evidence_url="https://apply.lh.or.kr/", proposed_policy="POL", mapping_basis="원문 제안",
             mapping={"policy_id":"POL", "status":"REVIEW"},
             rows=[dict(units=100, supply_month="2026-07", move_in_month="2028-03")])
    return dict(row, **extra)


def notice(**extra):
    return dict(dict(id="N", name="고양창릉 A1블록 공공분양주택", region="경기도", units=40,
                     developer="한국토지주택공사", source_date="2026-08-01"), **extra)


class MonitorMetricTests(unittest.TestCase):
    def test_five_catalogue_items_require_collected_origin_evidence(self):
        policies=[policy("P1"),policy("P2"),policy("P3")]
        self.assertEqual(len(catalogue(policies,[])),3)
        rows=catalogue(policies,[{"origin_id":"THIRD_NEW_TOWN"},{"origin_id":"URBAN_COMPLEX"}])
        self.assertEqual(len(rows),5)
        self.assertIsNone(rows[-1]["target_units"])
        self.assertEqual(rows[-1]["monitor_kind"],"PROGRAMME")

    def test_automatic_proposal_prioritizes_source_policy_and_no_name_guess(self):
        self.assertEqual(automatic_proposal(project(),{"POL","MON_THIRD_NEW_TOWN"})["policy_id"],"POL")
        self.assertEqual(automatic_proposal(project(),{"MON_THIRD_NEW_TOWN"})["policy_id"],"MON_THIRD_NEW_TOWN")
        self.assertEqual(automatic_proposal(project(program="알 수 없음"),{"MON_THIRD_NEW_TOWN"})["policy_id"],"UNASSIGNED")

    def test_pending_included_approval_same_numbers_release_excluded(self):
        row=project()
        def data(row):return build_monitor([row],[policy()],[],[notice()],date(2026,10,3))
        review=data(row)
        self.assertEqual(review["items"][0]["annual_achievement_pct"],40)
        self.assertEqual(review["items"][0]["cumulative_achievement_pct"],40)
        confirmed=data(dict(row,mapping={"policy_id":"POL","status":"CONFIRMED"}))
        self.assertEqual(confirmed["items"][0]["target_units"],review["items"][0]["target_units"])
        released=data(dict(row,mapping={"policy_id":"POL","status":"RELEASED"}))
        self.assertEqual(released["project_count"],0)
        self.assertIsNone(released["items"][0]["target_units"])
        self.assertEqual(released["released_count"],1)

    def test_policy_adjustment_moves_primary_stats_programme_overlap_explicit(self):
        row=project(mapping={"policy_id":"OTHER","status":"REVIEW"})
        programme=dict(policy("MON_THIRD_NEW_TOWN"),monitor_kind="PROGRAMME")
        data=build_monitor([row],[policy(),policy("OTHER"),programme],[],[notice()],date(2026,10,3))
        self.assertIsNone(data["items"][0]["target_units"])
        self.assertEqual(data["items"][1]["target_units"],100)
        self.assertEqual(data["items"][2]["target_units"],100)
        self.assertIn("합산하지",data["notice"])

    def test_annual_goal_uses_full_year_manual_override_not_sum(self):
        row=project(rows=[dict(units=100,supply_month="2026-12")])
        goals=[dict(project_id="P",targets=[dict(year=2026,stage="SUPPLY",units=50)])]
        data=build_monitor([row],[policy()],goals,[notice()],date(2026,10,3))["items"][0]
        self.assertEqual(data["annual_goal_units"],50)
        self.assertEqual(data["annual_achievement_pct"],80)

    def test_main_notice_counts_as_supply_actual_even_without_planned_capacity(self):
        row=project(planned_units=None,rows=[])
        data=build_monitor([row],[policy()],[],[notice()],date(2026,10,3))["items"][0]
        self.assertEqual(data["actual_supply_units"],40)
        self.assertEqual(data["actual_supply_annual_units"],40)
        self.assertIsNone(data["cumulative_observed_units"])
        self.assertEqual(data["actual_supply_status"],"REVIEW")

    def test_preannouncement_notice_is_context_not_policy_period_supply(self):
        data=build_monitor([project()],[policy()],[],[notice(source_date="2024-08-01")],date(2026,10,3))["items"][0]
        self.assertEqual(data["actual_supply_units"],40)
        self.assertIsNone(data["actual_supply_period_units"])

    def test_old_notice_not_this_year_and_actuals_remain_unknown(self):
        data=build_monitor([project()],[policy()],[],[notice(source_date="2025-08-01")],date(2026,10,3))["items"][0]
        self.assertEqual(data["cumulative_observed_units"],40)
        self.assertEqual(data["annual_observed_units"],0)
        self.assertIsNone(data["actual_cumulative_achievement_pct"])
        missing=build_monitor([project()],[policy()],[],[],date(2026,10,3))["items"][0]
        self.assertIsNone(missing["annual_observed_units"])
        self.assertIsNone(missing["annual_achievement_pct"])

    def test_partial_completion_schedule_never_predicts_whole_completion(self):
        rows=[project(),project("P2",name="고양창릉 A2",rows=[])]
        data=build_monitor(rows,[policy()],[],[],date(2026,10,3))["items"][0]
        self.assertIsNone(data["latest_known_completion_month"])
        self.assertEqual(data["earliest_move_in_start_month"],"2028-03")
        self.assertIsNone(data["expected_completion_month"])
        self.assertEqual(data["completion_schedule_projects"],0)
        self.assertEqual(data["completion_capacity_projects"],2)

    def test_programme_does_not_recount_cross_source_block(self):
        construction=project("C",source_id="lh_construction",rows=[],district="고양창릉",block="A1",planned_units=110)
        data=build_monitor([project(),construction],[policy()],[],[notice()],date(2026,10,3))["items"][0]
        self.assertEqual(data["target_units"],100)
        self.assertEqual(data["cumulative_observed_units"],40)

    def test_partial_block_units_schedule_not_whole_completion(self):
        row=project(rows=[dict(units=60,move_in_month="2028-03"),dict(units=40,move_in_month=None)])
        data=build_monitor([row],[policy()],[],[],date(2026,10,3))["items"][0]
        self.assertIsNone(data["expected_completion_month"])
        self.assertEqual(data["completion_schedule_projects"],0)
        self.assertIsNone(data["latest_known_completion_month"])
        self.assertEqual(data["earliest_move_in_start_month"],"2028-03")

    def test_older_notice_keeps_newer_annual_move_in_plan(self):
        row=project()
        data=build_monitor([row],[policy()],[],[notice(source_date="2025-08-01",move_in_plan_month="202905")],date(2026,10,3))["items"][0]
        self.assertIsNone(data["latest_known_completion_month"])
        self.assertEqual(data["earliest_move_in_start_month"],"2028-03")

    def test_additional_key_presence_does_not_claim_connected_or_leak_value(self):
        with patch.dict(os.environ,{"POC10_BUILDING_REGISTER_SERVICE_KEY":"do-not-expose"}):
            data=connection_audit([])
        self.assertNotIn("do-not-expose",str(data))
        register=data["planned"][0]
        self.assertTrue(register["key_configured"])
        self.assertEqual(register["readiness"],"CONNECTOR_PENDING")
        self.assertIsNone(next(r for r in data["planned"] if r["id"]=="sh_files")["key_env"])


class MappingWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.tmp=tempfile.TemporaryDirectory()
        self.service=HomeService(self.engine,self.tmp.name)
        with self.service.sessions.begin() as session:
            upsert_revision(session,"policy","policy_test","POL",dict(policy(),id="POL",base_date="2025-09-07"),"test")
        self.client=TestClient(create_app(self.engine,auto_collect=False))

    def tearDown(self):
        self.client.close();self.engine.dispose();self.tmp.cleanup()

    def collect(self,payload=None):
        with patch("backend.service.collect",return_value=([("project","NEW",payload or project())],{})):
            self.assertEqual(self.service.collect_one({"id":"lh_sale","url":"https://apply.lh.or.kr/"})["status"],"SUCCESS")
        return self.service.projects()[0]

    def test_new_project_gets_review_automatic_audit_and_statistics_before_approval(self):
        row=self.collect()
        self.assertEqual(row["mapping"]["status"],"REVIEW")
        self.assertEqual(self.service.policy_monitor()["project_count"],1)
        self.assertEqual(self.service.mapping_history(row["id"])[0]["action"],"MAPPING_AUTO")

    def test_recollection_does_not_overwrite_staff_decision(self):
        row=self.collect()
        result=self.service.confirm_mapping(row["id"],"POL",1,"CONFIRMED","담당자 검토","https://www.korea.kr/")
        again=self.collect(project(planned_units=120,proposed_policy="OTHER"))
        self.assertEqual(again["mapping"]["status"],"CONFIRMED")
        self.assertEqual(again["mapping"]["revision_no"],result["revision_no"])
        self.assertEqual(len(self.service.mapping_history(row["id"])),2)

    def test_public_queue_and_monitor_readable_writes_require_admin(self):
        row=self.collect()
        self.assertEqual(self.client.get("/poc/home/api/mappings").json()["items"][0]["statistics_included"],True)
        self.assertEqual(self.client.get("/poc/home/api/policy-monitor").json()["review_count"],1)
        self.assertEqual(self.client.get("/poc/home/api/connections").status_code,200)
        payload=dict(policy_id="POL",revision_no=1,status="CONFIRMED",basis="검토",evidence_url="https://www.korea.kr/")
        self.assertEqual(self.client.post("/poc/home/api/admin/mappings/"+row["id"],json=payload,headers={"x-home-admin":"forged"}).status_code,401)
        self.service.confirm_mapping(row["id"],"POL",1,"RELEASED","대상 제외","https://www.korea.kr/")
        self.assertEqual(self.service.supply_dashboard(measure="SUPPLY")["items"],[])
        self.assertEqual(self.service.roadmap()["total"],0)
        self.assertFalse(self.service.mappings()["items"][0]["statistics_included"])
