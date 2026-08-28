from __future__ import annotations

import unittest
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[2]


class MeetingBriefSchemaTests(unittest.TestCase):
    def test_brief_is_separate_provisional_read_model_with_cache_key(self):
        migration = (
            PROJECT_DIR / "backend/migrations/0022_meeting_briefs.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE meeting_briefs", migration)
        self.assertIn("authority_status = 'PROVISIONAL'", migration)
        self.assertIn(
            "UNIQUE (broadcast_id, transcript_hash, provider, model, prompt_version)",
            migration,
        )
        self.assertIn("CREATE TABLE meeting_brief_failures", migration)
        progress_migration = (
            PROJECT_DIR / "backend/migrations/0025_meeting_brief_progress.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE meeting_brief_progress", progress_migration)
        self.assertIn("processed_utterances", progress_migration)

        repository = (
            PROJECT_DIR / "backend/app/db/meeting_brief_repository.py"
        ).read_text(encoding="utf-8")
        self.assertIn("(provider = 'mistral') DESC", repository)
    def test_api_and_beta_ui_link_results_to_evidence(self):
        api = (PROJECT_DIR / "backend/app/main.py").read_text(encoding="utf-8")
        html = (PROJECT_DIR / "web/index.html").read_text(encoding="utf-8")
        script = (PROJECT_DIR / "web/app.js").read_text(encoding="utf-8")
        styles = (PROJECT_DIR / "web/workspace.css").read_text(encoding="utf-8")
        self.assertIn('/brief/evidence"', api)
        self.assertIn('/brief/official"', api)
        worker = (
            PROJECT_DIR / "backend/app/ingestion/meeting_brief_worker.py"
        ).read_text(encoding="utf-8")
        self.assertIn('item["meeting_brief"]', api)
        self.assertNotIn("오늘부터 최근 결과까지", html)
        self.assertIn('id="todayScheduleBoard"', html)
        self.assertIn('id="meetingRailPrev"', html)
        self.assertNotIn('id="liveCollectionOverview"', html)
        self.assertIn("renderMeetingBrief", script)
        self.assertIn("openMeetingBriefEvidence", script)
        self.assertIn("renderOfficialMeetingPanel", script)
        self.assertIn("expandExecutiveBriefing", script)
        self.assertIn("LIVE 저장본", script)
        self.assertIn("전체 발언 기록 보기", script)
        self.assertIn("appendHighlightedPhrase", script)
        self.assertIn("bestMeetingHighlightPhrase", script)
        self.assertIn("MAX_MEETING_EVIDENCE_HIGHLIGHTS = 3", script)
        self.assertIn("build_fallback_meeting_brief", worker)
        self.assertIn("renderMeetingBriefProcessing", script)
        self.assertIn("briefPollTimer", script)
        self.assertIn("결과 정리 중", script)
        self.assertIn('item.get("segment_ids")', api)
        self.assertIn("official_speakers=False", api)
        self.assertIn("filter: blur(5px)", styles)
        self.assertIn("자동 정리 · 잠정", script)
        self.assertIn('item["provider"] == "mistral"', api)
        self.assertIn("progress_map", api)
        self.assertIn("meetingBriefIsReady", script)
        self.assertIn("전체 발언은 확인할 수 있습니다", script)
        self.assertIn("개 발언 중", script)
        self.assertIn("meeting-topic-task-processing", styles)
        self.assertIn(".meeting-processing-card", styles)
        self.assertRegex(
            script,
            r"};\s+loadBrief\(\);\s+if \(!options\.auto\)",
        )
        self.assertNotIn("brief ? expandMeetingBrief(ended, row)", script)
        self.assertIn("selectMeetingEvidenceHighlights", script)
        self.assertIn("highlightPlan.get(utteranceIndex)", script)
        self.assertIn("meeting-topic-task-overview", script)
        self.assertIn("meeting-topic-detail-", script)
        self.assertIn("meeting-topic-task-detail", script)
        self.assertIn('magazineElement("strong", "", "과제")', script)
        self.assertIn('magazineElement("i", "", "원문 보기")', script)
        self.assertNotIn('magazineElement("span", "", topic.summary)', script)
        self.assertIn('"meeting-evidence-transcript"', script)
        self.assertNotIn('magazineElement("p", "", summaryText)', script)
        self.assertIn("official_presentations or live_utterances", api)
        self.assertIn('"OFFICIAL_TRANSCRIPT_PRESENTATION"', api)
        self.assertIn("build_official_evidence_presentations", api)
        self.assertIn("and not current_official_ids", api)
        self.assertIn("appendOfficialInlineDiff", script)
        self.assertIn("appendHighlightedPhrase(transcript, utterance.text, importantRange)", script)
        self.assertIn("LIVE 대비 수정 문구", script)
        self.assertIn("task.topic_title === topic.title", script)
        self.assertIn("sourceView.append(topicTaskOverview, actions, workspace)", script)
        self.assertNotIn("meeting-task-section", script)
        self.assertIn(".meeting-topic-task-row", styles)
        self.assertIn(".meeting-topic-task-detail", styles)
        self.assertIn("white-space: nowrap", styles)
        self.assertIn("scroll-margin-top: 92px", styles)
        self.assertIn(".meeting-result-workspace", styles)
        self.assertIn(".meeting-evidence-panel", styles)
        self.assertIn("position: sticky", styles)


if __name__ == "__main__":
    unittest.main()
