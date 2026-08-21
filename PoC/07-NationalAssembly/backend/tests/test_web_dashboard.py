from __future__ import annotations

import json
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[2]


class WebDashboardTests(unittest.TestCase):
    def test_dashboard_assets_and_mount_points_are_present(self):
        html = (PROJECT_DIR / "web" / "index.html").read_text(encoding="utf-8")
        for marker in (
            'id="meetingMetric"',
            'id="committeeMeetingList"',
            'id="billExplorer"',
            'src="assets/dashboard.js?v=',
            'href="assets/dashboard.css?v=',
        ):
            self.assertIn(marker, html)

    def test_workspace_makes_recording_continuity_and_readability_explicit(self):
        html = (PROJECT_DIR / "web" / "index.html").read_text(encoding="utf-8")
        script = (PROJECT_DIR / "web" / "app.js").read_text(encoding="utf-8")
        styles = (PROJECT_DIR / "web" / "workspace.css").read_text(encoding="utf-8")
        for marker in (
            'href="assets/workspace.css?v=',
            'id="topTabLive"',
            "정부 정책 브리핑",
            "정부와 국회, 같은 주제에서 보기",
            "위원회 논의와 의안 결과",
        ):
            self.assertIn(marker, html)
        for tab in ("live", "cabinet", "assembly"):
            self.assertIn(f'data-workspace-tab="{tab}"', html)
            self.assertIn(f'data-workspace-panel="{tab}"', html)
        self.assertIn("activateWorkspaceTab", script)
        self.assertIn('event.key === "ArrowRight"', script)
        self.assertIn('role="tablist"', html)
        self.assertIn('role="tabpanel"', html)
        self.assertNotIn("hero-panel compact-title", html)
        self.assertNotIn("workspace-tabs", html)
        self.assertIn('liveNavTab?.classList.toggle("has-live", anyLive)', script)
        self.assertIn("처음부터 현재까지 · 자동 갱신", script)
        self.assertIn("처음부터 끝까지 · 공식본 대조", script)
        self.assertIn("font-size: 16px", styles)
        self.assertIn("aspect-ratio: 16 / 9", styles)
        self.assertIn("dark only for media", styles)

    def test_dashboard_uses_only_public_api_routes(self):
        script = (PROJECT_DIR / "web" / "dashboard.js").read_text(encoding="utf-8")
        self.assertIn('api/committees/meetings', script)
        self.assertIn('api/bills?', script)
        self.assertNotIn("NATIONAL_ASSEMBLY_API_KEY", script)
        self.assertNotIn("DATABASE_URL", script)


    def test_live_flow_and_official_vote_summary_are_exposed(self):
        schedule_script = (PROJECT_DIR / "web" / "app.js").read_text(encoding="utf-8")
        dashboard_script = (PROJECT_DIR / "web" / "dashboard.js").read_text(encoding="utf-8")
        html = (PROJECT_DIR / "web" / "index.html").read_text(encoding="utf-8")
        votes = json.loads(
            (PROJECT_DIR / "web" / "data" / "vote_summaries.json").read_text(encoding="utf-8")
        )
        self.assertIn("department-scope-change", schedule_script)
        self.assertIn("loadOfficialRotations", schedule_script)
        self.assertIn('getJson("api/live/status"', schedule_script)
        self.assertIn("renderDetectedAssemblyLive", schedule_script)
        self.assertIn("api/live/transcript/snapshot?", schedule_script)
        self.assertIn("api/live/transcript/delta?", schedule_script)
        self.assertIn("assemblyTranscriptState.cursor", schedule_script)
        self.assertIn("buildLiveTopics", schedule_script)
        self.assertIn("미해결 후속 과제", schedule_script)
        self.assertIn('task_status === "OPEN"', schedule_script)
        self.assertIn("resolution: resolved", schedule_script)
        self.assertIn("liveItem?.stream_url", schedule_script)
        self.assertIn("OFFICIAL HLS STREAM", schedule_script)
        self.assertIn("api/live/broadcasts?", schedule_script)
        self.assertIn("/transcript`, { cache", schedule_script)
        self.assertIn("LAST LIVE REVIEW", schedule_script)
        self.assertIn("renderBroadcastRows", schedule_script)
        self.assertIn("expandLiveBroadcast", schedule_script)
        self.assertIn("expandEndedBroadcast", schedule_script)
        self.assertIn("renderOfficialContext", schedule_script)
        self.assertIn("LIVE 저장본 · PROVISIONAL", schedule_script)
        self.assertIn("공식 회의록 원문", schedule_script)
        self.assertIn("live-utterance-list", schedule_script)
        self.assertIn("word-break: keep-all", (PROJECT_DIR / "web" / "styles.css").read_text(encoding="utf-8"))
        self.assertIn("@container (max-width: 900px)", (PROJECT_DIR / "web" / "styles.css").read_text(encoding="utf-8"))
        self.assertIn("liveInsightFilterState", schedule_script)
        self.assertIn("renderInsightToolbar", schedule_script)
        self.assertIn("담당 부서별 LIVE 인사이트 필터", schedule_script)
        self.assertIn('id="followUpTasks"', html)
        self.assertIn('id="followUpMinistry"', html)
        self.assertIn("api/live/tasks?", schedule_script)
        self.assertIn("renderFollowUpTasks", schedule_script)
        self.assertIn("openTaskBroadcast", schedule_script)
        self.assertIn("officialReconciliation", schedule_script)
        self.assertIn("공식본 일치", schedule_script)
        self.assertIn("공식본 미확인", schedule_script)
        self.assertIn("대조된 공식 발언 보기", schedule_script)
        self.assertIn('id="liveBroadcastRows"', html)
        self.assertIn('id="liveExpanded"', html)
        self.assertNotIn('id="liveReviewDialog"', html)
        self.assertIn("showMagazineCard", schedule_script)
        self.assertIn("AUTO REVIEW", schedule_script)
        self.assertIn("official_published", schedule_script)
        self.assertIn("공식 원문 확인", schedule_script)
        self.assertIn('id="live"', html)
        self.assertIn('id="presidential"', html)
        self.assertIn("renderAssemblyFallback", dashboard_script)
        self.assertIn('id="executiveMagazine"', html)
        self.assertIn('id="assemblyMagazine"', html)
        self.assertIn("votePanel", dashboard_script)
        self.assertIn("committee-row", dashboard_script)
        self.assertIn("bill-row", dashboard_script)
        self.assertIn("inlineVoteText", dashboard_script)
        self.assertIn("bill-hover-detail", dashboard_script)
        self.assertIn("assets/data/vote_summaries.json", dashboard_script)
        self.assertEqual(votes["resource"], "nojepdqqaweusdfbi")
        self.assertEqual(votes["items"][0]["yes"], 215)
        self.assertEqual(votes["items"][0]["no"], 2)
        self.assertNotIn("KEY=", votes["items"][0]["source_url"])

    def test_committee_rows_expose_official_transcript_dialog(self):
        html = (PROJECT_DIR / "web" / "index.html").read_text(encoding="utf-8")
        script = (PROJECT_DIR / "web" / "dashboard.js").read_text(encoding="utf-8")
        styles = (PROJECT_DIR / "web" / "dashboard.css").read_text(encoding="utf-8")
        self.assertIn("officialTranscriptDialog", html)
        self.assertIn("openOfficialTranscript", script)
        self.assertIn("official_utterance_count", script)
        self.assertIn("official-utterance", styles)
        self.assertIn("AUTO CLASSIFICATION · DRAFT", script)
        self.assertIn("payload.insights.topics", script)

    def test_integrated_policy_flow_has_visual_and_evidence_contract(self):
        html = (PROJECT_DIR / "web" / "index.html").read_text(encoding="utf-8")
        script = (PROJECT_DIR / "web" / "dashboard.js").read_text(encoding="utf-8")
        styles = (PROJECT_DIR / "web" / "dashboard.css").read_text(encoding="utf-8")
        self.assertIn('id="committeePolicyFlow"', html)
        self.assertIn("api/committees/policy-flow?", script)
        self.assertIn("policy_statement_count", script)
        self.assertIn("item.evidence.source_span_id", script)
        self.assertIn("payload.linked_bill_count", script)
        self.assertIn("EXACT AGENDA → BILL → VOTE", script)
        self.assertIn("voteSummaries.get(bill.bill_id)", script)
        self.assertIn("policy-signal-bar", styles)
        self.assertIn("policy-bill-flow", styles)

    def test_official_executive_briefings_fill_presidential_flow(self):
        html = (PROJECT_DIR / "web" / "index.html").read_text(encoding="utf-8")
        script = (PROJECT_DIR / "web" / "dashboard.js").read_text(encoding="utf-8")
        live_script = (PROJECT_DIR / "web" / "app.js").read_text(encoding="utf-8")
        styles = (PROJECT_DIR / "web" / "styles.css").read_text(encoding="utf-8")
        self.assertIn('id="executiveLatestMeeting"', html)
        self.assertIn('id="executiveMessageMetric"', html)
        self.assertIn('new URLSearchParams({ limit: "10" })', script)
        self.assertIn('fetch("api/executive/briefings?" + params', script)
        self.assertIn("RULE LINK", script)
        self.assertIn("executive-meeting-list", script)
        self.assertIn("OFFICIAL MESSAGE", script)
        self.assertIn("message.source_span_id", script)
        self.assertIn("executive-policy-row", styles)
        self.assertIn('id="executiveFilterForm"', html)
        self.assertIn("executiveMinistryFilter", script)
        self.assertIn("executive-filter-bar", styles)
        self.assertIn("item.official_document?.sections", script)
        self.assertIn("OFFICIAL PDF TEXT", script)
        self.assertIn("bill-official-text", styles)
        self.assertIn("DEMO LIVE · SIMULATION", live_script)
        self.assertIn("E2E 데모 LIVE", live_script)

    def test_cross_institution_flow_exposes_both_official_evidence_sides(self):
        html = (PROJECT_DIR / "web" / "index.html").read_text(encoding="utf-8")
        script = (PROJECT_DIR / "web" / "dashboard.js").read_text(encoding="utf-8")
        styles = (PROJECT_DIR / "web" / "styles.css").read_text(encoding="utf-8")
        self.assertIn('id="crossInstitutionFlow"', html)
        self.assertIn("api/policy/cross-institution-flow?", script)
        self.assertIn("EXECUTIVE · OFFICIAL", script)
        self.assertIn("LEGISLATURE · OFFICIAL TEXT", script)
        self.assertIn("item.shared_evidence_keywords", script)
        self.assertIn("item.temporal_label", script)
        self.assertIn("cross-flow-evidence", styles)
        self.assertIn("cross-flow-rule", styles)

if __name__ == "__main__":
    unittest.main()
