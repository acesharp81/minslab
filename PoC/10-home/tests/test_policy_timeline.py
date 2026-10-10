import unittest
from datetime import date

from backend.policy_monitor import build_monitor
from test_policy_monitor import policy, project, notice


class PolicyTimelineTests(unittest.TestCase):
    def data(self,rows,goals=(),reports=(),**extra):
        return build_monitor(rows,[policy()],goals,[],date(2026,10,3),reports=reports,**extra)["items"][0]["timeline"]

    def test_annual_supply_is_not_cumulative_or_mixed_with_move_in(self):
        row=project(rows=[dict(units=40,supply_month="2026-07",move_in_month="2028-03"),
                          dict(units=60,supply_month="2027-07",move_in_month="2029-03")])
        annual={r["year"]:r for r in self.data([row])["annual"]}
        self.assertEqual(annual[2026]["SUPPLY"]["units"],40)
        self.assertEqual(annual[2027]["SUPPLY"]["units"],60)
        self.assertIsNone(annual[2028]["SUPPLY"]["units"])
        self.assertEqual(annual[2028]["MOVE_IN"]["units"],40)
        self.assertEqual(annual[2029]["MOVE_IN"]["units"],60)

    def test_manual_goal_replaces_source_in_year_without_double_counting(self):
        goals=[dict(project_id="P",targets=[dict(year=2026,stage="SUPPLY",units=50,basis="관리자",evidence_url="https://example.com")])]
        annual={r["year"]:r for r in self.data([project()],goals)["annual"]}
        self.assertEqual(annual[2026]["SUPPLY"]["units"],50)
        self.assertEqual(annual[2026]["SUPPLY"]["manual_units"],50)
        self.assertIsNone(annual[2026]["SUPPLY"]["source_units"])

    def test_cross_source_block_counted_once_but_contract_progress_retained(self):
        contract=project("C",source_id="lh_construction",district="고양창릉",block="A1",rows=[],progress_pct=25,
                         start_plan_date="2025-03-01",completion_plan_date="2028-09-01")
        t=self.data([project(),contract])
        self.assertEqual(t["block_count"],1)
        b=t["regions"][0]["cities"][0]["blocks"][0]
        self.assertEqual(b["target_units"],100)
        self.assertEqual(b["actuals"][0]["pct"],25)
        self.assertEqual(b["intervals"][0]["end"],"2028-09-01")
        self.assertEqual(next(a for a in t["annual"] if a["year"]==2026)["SUPPLY"]["units"],100)

    def test_report_year_last_snapshot_no_carry_forward_future_or_false_zero(self):
        row=project(source_id="lh_construction",rows=[],progress_pct=None)
        reports=[dict(current_project_id="P",report_date=stamp,progress_pct=pct,evidence_url="https://example.com/"+stamp)
                 for stamp,pct in [("2025-03-01",10),("2025-12-01",20),("2026-11-01",90)]]
        t=self.data([row],reports=reports)
        b=t["regions"][0]["cities"][0]["blocks"][0]
        self.assertEqual([(a["year"],a["pct"]) for a in b["actuals"]],[(2025,20)])
        self.assertNotIn(2026,[a["year"] for a in b["actuals"]])
        self.assertIsNone(next(a for a in t["annual"] if a["year"]==2026)["SUPPLY"]["units"])

    def test_two_contract_rates_are_not_averaged_and_notices_are_not_progress(self):
        rows=[project("C1",source_id="lh_construction",rows=[],progress_pct=20),
              project("C2",source_id="lh_construction",rows=[],progress_pct=80)]
        t=build_monitor(rows,[policy()],[],[notice()],date(2026,10,3))["items"][0]["timeline"]
        b=t["regions"][0]["cities"][0]["blocks"][0]
        self.assertEqual({a["pct"] for a in b["actuals"]},{20,80})
        self.assertIsNone(b["target_units"])
        t=self.data([project()]);self.assertEqual(t["regions"][0]["cities"][0]["blocks"][0]["actuals"],[])

    def test_city_from_official_membership_not_prefix_and_release_excluded(self):
        boundaries=[dict(id="AREA",region="경기도",name="고양시",district_names=[])]
        t=self.data([project(),project("R",mapping={"policy_id":"POL","status":"RELEASED"})],municipalities=boundaries)
        self.assertEqual(t["block_count"],1)
        self.assertEqual(t["regions"][0]["cities"][0]["name"],"고양시")
        t=self.data([project(municipality="지역 상세 확인 필요")],municipalities=boundaries)
        self.assertEqual(t["regions"][0]["cities"][0]["name"],"시군구 연결 검토")

    def test_policy_origin_year_and_official_start_goal_kept_separate(self):
        pol=policy("POL_2025_0907")
        row=project(mapping={"policy_id":pol["policy_id"],"status":"REVIEW"})
        result=build_monitor([row],[pol],[],[],date(2026,10,3))["items"][0]
        self.assertEqual(result["timeline"]["years"][0],2025)
        a=next(a for a in result["timeline"]["annual"] if a["year"]==2026)
        self.assertEqual(a["official_start_units"],270000)
        self.assertEqual(a["SUPPLY"]["units"],100)
        self.assertIn("착공",result["overview"]["period"])

    def test_ambiguous_multisite_has_no_fabricated_progress_or_units(self):
        row=project(source_id="lh_construction",rows=[],progress_pct=70,warnings=["MULTI_SITE_CONTRACT"])
        b=self.data([row])["regions"][0]["cities"][0]["blocks"][0]
        self.assertIsNone(b["target_units"]);self.assertEqual(b["actuals"],[]);self.assertEqual(b["events"],[])
