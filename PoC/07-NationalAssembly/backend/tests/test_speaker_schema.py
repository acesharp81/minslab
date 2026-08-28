from __future__ import annotations

import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).parents[2]


class SpeakerSchemaTests(unittest.TestCase):
    def test_manual_speaker_names_are_a_separate_read_model(self):
        migration = (
            PROJECT_DIR / "backend" / "migrations"
            / "0018_transcript_speaker_overrides.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE transcript_speaker_overrides", migration)
        self.assertIn("UNIQUE (broadcast_id, source_speaker_label)", migration)
        self.assertNotIn("UPDATE transcript_segments", migration)

    def test_public_read_and_admin_write_contracts_are_exposed(self):
        api = (PROJECT_DIR / "backend" / "app" / "main.py").read_text(encoding="utf-8")
        self.assertIn('@app.get("/api/live/overview"', api)
        self.assertIn('/speakers/{source_label}"', api)
        self.assertIn("group_transcript_segments", api)

    def test_web_groups_turns_and_exposes_speaker_editor(self):
        script = (PROJECT_DIR / "web" / "app.js").read_text(encoding="utf-8")
        html = (PROJECT_DIR / "web" / "index.html").read_text(encoding="utf-8")
        self.assertIn("groupTranscriptSegments", script)
        self.assertIn("normalizePreparedTranscriptGroups", script)
        self.assertIn("preparedGroups.length", script)
        self.assertIn("renderSpeakerEditor", script)
        self.assertIn('method: "PUT"', script)
        self.assertIn('method: "DELETE"', script)
        self.assertNotIn("api/live/overview?days=7", script)
        self.assertNotIn('id="liveCollectionOverview"', html)


    def test_live_turn_is_full_length_and_follows_the_latest_caption(self):
        script = (PROJECT_DIR / "web" / "app.js").read_text(encoding="utf-8")
        styles = (PROJECT_DIR / "web" / "styles.css").read_text(encoding="utf-8")
        workspace = (PROJECT_DIR / "web" / "workspace.css").read_text(encoding="utf-8")
        for marker in (
            "현재 발언 · 실시간 누적",
            "scheduleTranscriptSummaryRefresh",
            "raw.open = true",
            "lines.scrollTop = lines.scrollHeight",
            "renderCompactLiveInsights",
            "toggleCinemaMode",
            "expandedOriginalIds",
            "syncLiveInsightHeight",
            "ResizeObserver",
            "activeSummary.scrollTop = activeSummary.scrollHeight",
            "실시간 자막 + 발언 묶음별 요약",
        ):
            self.assertIn(marker, script)
        self.assertNotIn("assemblyCaptionOverlay", script)
        self.assertNotIn("OFFICIAL LIVE CAPTION", script)
        self.assertNotIn("OFFICIAL HLS STREAM", script)
        self.assertNotIn("화자 이름 확인·수정", script)
        self.assertIn("live-compact-head-actions", workspace)
        self.assertIn("cinema-mode-exit", script)
        self.assertNotIn(".live-caption-overlay", styles)
        self.assertNotIn(".live-caption-overlay", workspace)
        self.assertIn(".transcript-line.is-active-turn", styles)
        self.assertIn(".raw-transcript.is-live .transcript-lines", workspace)
        self.assertIn("height: clamp(280px,34vh,360px)", workspace)
        self.assertIn("max-height: 112px", workspace)
        self.assertIn("height: clamp(300px,42vh,420px)", workspace)
        self.assertIn("#liveExpandedStage.transcript-stage { overflow: hidden; contain: paint", workspace)
        self.assertIn(".raw-transcript.is-live { position: relative; z-index: 1; overflow: hidden; contain: paint", workspace)
        self.assertIn(".transcript-stage.is-cinema .live-insights", workspace)
        self.assertIn('matchMedia("(min-width: 1101px)")', script)
        self.assertIn("source_parent_segment_id", script)
        self.assertIn("minmax(600px,51%)", workspace)
        self.assertIn("height: clamp(180px,30vh,250px)", workspace)
        self.assertIn("body { overflow-x: clip; }", workspace)
        self.assertIn(".meeting-evidence-panel { position: relative", workspace)
        self.assertIn("@media (min-width: 761px)", workspace)
        self.assertIn("max-height: calc(100dvh - 108px)", workspace)
        desktop_follow = workspace.split("@media (min-width: 761px)", 1)[1]
        self.assertIn(".meeting-evidence-panel", desktop_follow)
        self.assertIn("position: sticky", desktop_follow)
        self.assertNotIn("min-height: 240px", styles)
        self.assertNotIn("live-compact-task", script)

if __name__ == "__main__":
    unittest.main()
