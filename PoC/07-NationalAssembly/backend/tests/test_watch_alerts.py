from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.db.watch_repository import (
    _allows_kakao_delivery, build_watch_fallback_summary, normalize_watch_briefing_presentation,
    watch_key_sentence,
)
from app.services.watch_matcher import match_watch_rule, normalize_watch_text
from app.services.watch_test_script import build_watch_test_script
from app.services.watch_replay_script import build_hasi_ai_replay_script
from app.services.watch_kakao import KakaoNotificationProvider
from app.services.watch_summary import MistralWatchSummaryClient, OpenRouterWatchSummaryClient


class WatchMatcherTests(unittest.TestCase):
    def test_watch_report_fallback_limits_and_focuses_key_phrases(self) -> None:
        matches = [
            {
                "match_id": index, "speaker_label": f"화자 {index}",
                "matched_term": "AI 민주정부",
                "excerpt": ("앞 문맥 " * 100) + f"AI 민주정부 추진 전략 {index}을 점검합니다." + (" 뒤 문맥" * 100),
            }
            for index in range(8)
        ]
        items = build_watch_fallback_summary(matches)
        self.assertEqual(5, len(items))
        self.assertTrue(all("AI 민주정부" in item["summary"] for item in items))
        self.assertTrue(all(len(item["summary"]) <= 222 for item in items))
        self.assertTrue(all(item["summary_kind"] == "KEY_SENTENCE_FALLBACK" for item in items))

    def test_watch_briefing_display_normalizes_known_cjk_residue(self) -> None:
        summary, claims = normalize_watch_briefing_presentation(
            "쟁점은各 기관의 조치입니다.",
            [{"title": "各 기관", "text": "各 기관이 보고했습니다.", "evidence_ids": ["1"]}],
        )
        self.assertEqual("쟁점은 각 기관의 조치입니다.", summary)
        self.assertEqual("각 기관", claims[0]["title"])
        self.assertEqual("각 기관이 보고했습니다.", claims[0]["text"])
        self.assertEqual(["1"], claims[0]["evidence_ids"])

    def test_watch_key_sentence_keeps_short_evidence_unchanged(self) -> None:
        self.assertEqual("짧은 AI 발언", watch_key_sentence("짧은 AI 발언", "AI"))

    def test_matches_phrase_after_spacing_normalization(self) -> None:
        rule = {"include_terms": ["AI 민주정부"], "exclude_terms": []}
        match = match_watch_rule("행안부는 AI   민주정부 추진계획을 보고했습니다.", rule)
        self.assertIsNotNone(match)
        self.assertEqual(match.term, "AI 민주정부")

    def test_exclusion_wins(self) -> None:
        rule = {
            "include_terms": ["가상자산"],
            "exclude_terms": ["단순 통계"],
        }
        self.assertIsNone(match_watch_rule("가상자산 단순 통계 자료입니다.", rule))

    def test_normalizer_is_case_insensitive(self) -> None:
        self.assertEqual(normalize_watch_text("  AI\n정부  "), "ai 정부")

    def test_korean_spacing_and_punctuation_are_normalized(self) -> None:
        rule = {"include_terms": ["지방교부세"], "exclude_terms": []}
        self.assertIsNotNone(match_watch_rule("지방 교부세·산정 방식을 검토합니다.", rule))

    def test_short_english_acronym_uses_word_boundary(self) -> None:
        rule = {"include_terms": ["AI"], "exclude_terms": []}
        self.assertIsNone(match_watch_rule("chairman 발언입니다.", rule))
        self.assertIsNotNone(match_watch_rule("AI 정부 전략입니다.", rule))

    def test_test_script_contains_keyword_in_multiple_speaker_turns(self) -> None:
        script = build_watch_test_script("지역화폐")
        matched = [item for item in script if "지역화폐" in item["text"]]
        self.assertGreaterEqual(len(matched), 4)
        self.assertGreaterEqual(len({item["speaker"] for item in matched}), 3)

    def test_test_script_has_deterministic_live_draft_hints_without_llm(self) -> None:
        script = build_watch_test_script("AI 민주정부")
        self.assertTrue(all(item.get("insight", {}).get("topic_id") for item in script))
        self.assertGreaterEqual(len({item["insight"]["topic_id"] for item in script}), 4)
        self.assertTrue(any(item["insight"].get("task") for item in script))

    def test_hasi_replay_keeps_real_ai_caption_window_with_accelerated_timing(self) -> None:
        script = build_hasi_ai_replay_script()
        transcript = " ".join(item["text"] for item in script)
        self.assertEqual(7, len(script))
        self.assertIn("AI 대여센터", transcript)
        self.assertIn("인공지능 데이터센터산업", transcript)
        self.assertIn("행안부에서도 적극적으로 의견 개진", transcript)
        self.assertGreaterEqual(script[-1]["elapsed_seconds"], 40)
        self.assertLess(script[-1]["elapsed_seconds"], 60)
        self.assertEqual({"질의 위원", "행정안전부 장관"}, {item["speaker"] for item in script})
        self.assertEqual({"QUESTION", "ANSWER"}, {item["insight"]["role"] for item in script})
        self.assertTrue(all(item["insight"].get("summary") for item in script))
        self.assertTrue(all(item.get("insight", {}).get("topic_id") for item in script))

    def test_only_explicit_replay_mode_can_send_test_kakao(self) -> None:
        self.assertFalse(_allows_kakao_delivery("poc07.test"))
        self.assertFalse(_allows_kakao_delivery("poc07.replay.local"))
        self.assertTrue(_allows_kakao_delivery("poc07.replay.kakao"))
        self.assertTrue(_allows_kakao_delivery("assembly.webcast.go.kr"))


class WatchSchemaTests(unittest.TestCase):
    def test_schema_has_idempotency_and_outbox_contracts(self) -> None:
        migration = Path(__file__).resolve().parents[1] / "migrations" / "0030_watch_alerts_and_test_broadcasts.sql"
        sql = migration.read_text(encoding="utf-8")
        self.assertIn("UNIQUE (rule_id, revision_id)", sql)
        self.assertIn("CREATE TABLE notification_outbox", sql)
        self.assertIn("CREATE TABLE watch_test_broadcasts", sql)
        replay_migration = migration.parent / "0040_watch_committee_replay.sql"
        replay_sql = replay_migration.read_text(encoding="utf-8")
        self.assertIn("kakao_delivery_enabled boolean NOT NULL DEFAULT false", replay_sql)
        self.assertIn("HASI_AI_REPLAY", replay_sql)

    def test_completion_schema_has_rule_versions_digest_and_official_status(self) -> None:
        migration = (
            Path(__file__).resolve().parents[1]
            / "migrations"
            / "0031_watch_completion_features.sql"
        )
        sql = migration.read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE watch_rule_revisions", sql)
        self.assertIn("FIRST_PER_SPEAKER", sql)
        self.assertIn("INTERVAL_60_MINUTES", sql)
        self.assertIn("notification_type IN ('MATCH', 'DIGEST')", sql)
        self.assertIn("CREATE TABLE watch_match_official_verifications", sql)

    def test_external_operations_schema_has_isolated_provider_and_review_history(self) -> None:
        migration = (
            Path(__file__).resolve().parents[1]
            / "migrations"
            / "0032_watch_external_and_operations.sql"
        )
        sql = migration.read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE watch_kakao_accounts", sql)
        self.assertIn("access_token_ciphertext", sql)
        self.assertIn("CREATE TABLE watch_summary_versions", sql)
        self.assertIn("UNIQUE (session_id, evidence_set_hash)", sql)
        self.assertIn("CREATE TABLE watch_review_decisions", sql)
        self.assertIn("automatic_status", sql)
        self.assertIn("CREATE TABLE live_regression_audits", sql)

    def test_kakao_configuration_reports_names_without_secret_values(self) -> None:
        settings = SimpleNamespace(
            watch_kakao_enabled=True,
            watch_kakao_rest_api_key="secret-rest-key",
            watch_kakao_client_secret="secret-client-key",
            watch_kakao_redirect_uri="https://example.test/callback",
            watch_kakao_token_encryption_key="secret-cipher-key",
            watch_public_base_url="https://example.test/poc",
        )
        result = KakaoNotificationProvider(settings).configuration()
        self.assertTrue(result["configured"])
        self.assertNotIn("secret-rest-key", str(result))
        self.assertNotIn("secret-cipher-key", str(result))

    def test_kakao_requires_talk_message_consent(self) -> None:
        settings = SimpleNamespace(
            watch_kakao_enabled=True,
            watch_kakao_rest_api_key="rest-key",
            watch_kakao_client_secret="client-secret",
            watch_kakao_redirect_uri="https://example.test/callback",
            watch_kakao_token_encryption_key="cipher-key",
            watch_public_base_url="https://example.test/poc",
        )
        provider = KakaoNotificationProvider(settings)
        with patch.object(provider, "_request", return_value={"scopes": []}):
            with self.assertRaisesRegex(Exception, "카카오 메시지 전송에 동의"):
                provider._granted_scopes("access-token", "")

    def test_kakao_send_requires_provider_success_result_code(self) -> None:
        settings = SimpleNamespace(
            watch_kakao_enabled=True, watch_kakao_rest_api_key="rest-key",
            watch_kakao_client_secret="client-secret",
            watch_kakao_redirect_uri="https://example.test/callback",
            watch_kakao_token_encryption_key="cipher-key",
            watch_public_base_url="https://example.test/poc",
        )
        provider = KakaoNotificationProvider(settings)
        provider.access_token = Mock(return_value="access-token")
        delivery = {"account": {}, "session_id": "session-1", "title": "감지 알림", "body": "본문"}
        with patch.object(provider, "_request", return_value={"result_code": -1}):
            with self.assertRaisesRegex(Exception, "메시지를 접수하지 않았습니다"):
                provider.send(delivery, Mock())
        with patch.object(provider, "_request", return_value={"result_code": 0}):
            provider.send(delivery, Mock())

    def test_poc7_kakao_has_no_master_press_runtime_dependency(self) -> None:
        project = Path(__file__).resolve().parents[2]
        paths = [
            project / "backend" / "app" / "config.py",
            project / "backend" / "app" / "services" / "watch_kakao.py",
            project / "scripts" / "deploy_api.sh",
            project / "scripts" / "deploy_secure_workers.sh",
            project / "docker-compose.yml",
        ]
        combined = "\n".join(path.read_text(encoding="utf-8") for path in paths)
        self.assertNotIn("MASTER_PRESS_", combined)
        self.assertNotIn("ROOT_ENV", combined)

    def test_poc7_example_and_bootstrap_contain_complete_kakao_settings(self) -> None:
        project = Path(__file__).resolve().parents[2]
        example = (project / ".env.example").read_text(encoding="utf-8")
        bootstrap = (project / "scripts" / "bootstrap_poc07_env.py").read_text(
            encoding="utf-8"
        )
        for key in (
            "WATCH_KAKAO_REST_API_KEY",
            "WATCH_KAKAO_CLIENT_SECRET",
            "WATCH_KAKAO_TOKEN_ENCRYPTION_KEY",
            "WATCH_KAKAO_REDIRECT_URI",
            "WATCH_PUBLIC_BASE_URL",
        ):
            self.assertIn(key, example)
            self.assertIn(key, bootstrap)
        self.assertIn("secret values were not displayed", bootstrap)

    def test_existing_kakao_account_does_not_auto_import_browser_rules(self) -> None:
        project = Path(__file__).resolve().parents[2]
        api = (project / "backend" / "app" / "main.py").read_text(encoding="utf-8")
        callback = api.split("def watch_kakao_callback(", 1)[1].split(
            '@app.delete("/api/watch/kakao"', 1
        )[0]
        self.assertIn("rules remain authoritative", callback)
        self.assertNotIn("source_rules", callback)
        self.assertNotIn("target_repository.create_rule", callback)

        web = (project / "web" / "watch-alerts.js").read_text(encoding="utf-8")
        synchronization = web.split(
            "function synchronizeLocalRules(", 1,
        )[1].split("function renderRules(", 1)[0]
        self.assertIn("localStorage is only a cache", synchronization)
        self.assertIn("saveLocalRules(unique)", synchronization)
        self.assertNotIn('method: "POST"', synchronization)
        deletion = web.split("async function deleteRule(", 1)[1].split(
            "function ruleReportMarkdown(", 1,
        )[0]
        self.assertIn("if (!result.deleted)", deletion)
        self.assertIn("loadRules()", deletion)

    def test_kakao_disconnect_is_local_and_bootstrap_does_not_reuse_other_app(self) -> None:
        project = Path(__file__).resolve().parents[2]
        api = (project / "backend" / "app" / "main.py").read_text(encoding="utf-8")
        provider = (
            project / "backend" / "app" / "services" / "watch_kakao.py"
        ).read_text(encoding="utf-8")
        bootstrap = (project / "scripts" / "bootstrap_poc07_env.py").read_text(
            encoding="utf-8"
        )
        disconnect = api.split('def watch_kakao_disconnect(', 1)[1].split(
            '@app.get("/api/watch/admin/reviews"', 1
        )[0]
        self.assertIn("repository.disconnect(subscriber_id)", disconnect)
        self.assertNotIn(".unlink(", disconnect)
        self.assertNotIn("/v1/user/unlink", provider)
        self.assertNotIn('"KAKAO_REST_API_KEY"', bootstrap)
        self.assertNotIn('"MASTER_PRESS_KAKAO_REST_API_KEY"', bootstrap)

    def test_watch_summary_rejects_claims_without_known_evidence(self) -> None:
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "id": "request-1",
            "choices": [{"message": {"content": '{"claims":[{"text":"근거 요약","evidence_ids":["unknown"]}]}'}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }
        client = MistralWatchSummaryClient(
            "test-key", model="mistral-test", base_url="https://example.test",
        )
        with patch("app.services.watch_summary.requests.post", return_value=response):
            with self.assertRaises(ValueError):
                client.summarize([{
                    "match_id": "known", "speaker_label": "위원",
                    "excerpt": "예산 집행을 점검해 주십시오.",
                }])

    def test_watch_briefing_rejects_latin_text_absent_from_evidence(self) -> None:
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "choices": [{"message": {"content": '{"overview":"법률안 논의를 보고했습니다.","claims":[{"title":"법률안 정비","text":"검사 근거 legalization을 논의했습니다.","evidence_ids":["known"]},{"title":"후속 조치","text":"법률안을 계속 검토합니다.","evidence_ids":["known"]}]}'}}],
        }
        client = MistralWatchSummaryClient(
            "test-key", model="mistral-test", base_url="https://example.test",
        )
        with patch("app.services.watch_summary.requests.post", return_value=response):
            with self.assertRaisesRegex(ValueError, "unsupported Latin"):
                client.summarize([{
                    "match_id": "known", "speaker_label": "위원",
                    "excerpt": "법률안의 검사 근거를 논의했습니다.",
                }])

    def test_openrouter_watch_report_returns_topic_titles_and_denies_collection(self) -> None:
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "id": "request-openrouter", "provider": "test-provider",
            "choices": [{"message": {"content": '{"overview":"各 기관의 예산 집행 상황과 후속 점검 요구가 확인됐다.","claims":[{"title":"예산 집행","text":"집행 상황을 점검했다.","evidence_ids":["known"]}]}'}}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 7, "cost": 0},
        }
        client = OpenRouterWatchSummaryClient(
            "test-key", model="free-test", base_url="https://example.test",
        )
        with patch("app.services.watch_summary.requests.post", return_value=response) as post:
            result = client.summarize([{
                "match_id": "known", "speaker_label": "위원",
                "excerpt": "예산 집행 상황을 점검해 주십시오.",
            }])
        self.assertEqual("예산 집행", result.claims[0]["title"])
        self.assertEqual("각 기관의 예산 집행 상황과 후속 점검 요구가 확인됐다.", result.summary)
        request_body = post.call_args.kwargs["json"]
        self.assertEqual("deny", request_body["provider"]["data_collection"])
        self.assertTrue(request_body["provider"]["zdr"])
        self.assertFalse(request_body["provider"]["allow_fallbacks"])
        self.assertTrue(request_body["provider"]["require_parameters"])
        self.assertNotIn("plugins", request_body)

    def test_watch_report_prioritizes_claims_and_collapses_full_evidence(self) -> None:
        project = Path(__file__).resolve().parents[2]
        script = (project / "web" / "watch-alerts.js").read_text(encoding="utf-8")
        styles = (project / "web" / "watch-alerts.css").read_text(encoding="utf-8")
        repository = (project / "backend" / "app" / "db" / "watch_summary_repository.py").read_text(encoding="utf-8")
        self.assertIn("현재까지의 종합 판단", script)
        self.assertIn("전체 근거 원문 보기", script)
        self.assertIn("reportEvidenceDetails", script)
        self.assertIn("appendHighlightedTerms", script)
        self.assertIn("watch-keyword-highlight", script)
        self.assertIn("watch-rule-report-overview", styles)
        self.assertIn("watch-rule-report-claim", styles)
        self.assertIn("24 hours", repository)
        self.assertIn("lifecycle_status", repository)
        self.assertIn("report_summary_requested_at", repository)
        migration = (project / "backend" / "migrations" / "0034_watch_report_summary_requests.sql").read_text(encoding="utf-8")
        self.assertIn("report_summary_requested_at", migration)
        versioned = (project / "backend" / "migrations" / "0035_watch_summary_versioned_cache.sql").read_text(encoding="utf-8")
        self.assertIn("watch_summary_versions_identity_key", versioned)
        self.assertIn("prompt_version", versioned)
        service = (project / "backend" / "app" / "services" / "watch_summary.py").read_text(encoding="utf-8")
        self.assertIn("watch-briefing-report/3.3", service)
        self.assertIn("2~4개 큰 논점", service)
        worker = (project / "backend" / "app" / "ingestion" / "watch_summary_worker.py").read_text(encoding="utf-8")
        self.assertIn("quality_retry=attempt > 0", worker)
        self.assertIn("retry_reserved", worker)
        self.assertIn("isinstance(exc, WatchSummaryQualityError)", worker)
        self.assertIn("repository.clear_request(session_id)", worker)

    def test_external_routes_and_separate_workers_are_wired(self) -> None:
        project = Path(__file__).resolve().parents[2]
        api = (project / "backend" / "app" / "main.py").read_text(encoding="utf-8")
        deploy = (project / "scripts" / "deploy_secure_workers.sh").read_text(encoding="utf-8")
        self.assertIn('@app.post("/api/watch/kakao/authorize"', api)
        self.assertIn('@app.get("/api/watch/admin/reviews"', api)
        self.assertIn("automatic_judgment_preserved", api)
        self.assertIn("app.ingestion.notification_worker", deploy)
        self.assertIn("app.ingestion.watch_summary_worker", deploy)
        summary_repository = (
            project / "backend" / "app" / "db" / "watch_summary_repository.py"
        ).read_text(encoding="utf-8")
        self.assertIn("'poc07.replay.local'", summary_repository)
        self.assertIn("'poc07.replay.kakao'", summary_repository)
        watch_repository = (
            project / "backend" / "app" / "db" / "watch_repository.py"
        ).read_text(encoding="utf-8")
        self.assertIn('source == "poc07.replay.kakao"', watch_repository)
        self.assertIn('"poc07.replay.local"', watch_repository)

    def test_test_source_is_filtered_from_public_queries(self) -> None:
        repository = Path(__file__).resolve().parents[1] / "app" / "db" / "live_repository.py"
        source = repository.read_text(encoding="utf-8")
        self.assertIn("'poc07.replay.local'", source)
        self.assertIn("'poc07.replay.kakao'", source)
        self.assertIn("include_test=True", source)
        review_repository = Path(__file__).resolve().parents[1] / "app" / "db" / "review_repository.py"
        self.assertIn(
            "'poc07.replay.kakao'",
            review_repository.read_text(encoding="utf-8"),
        )

    def test_replay_waits_for_video_and_live_report_uses_closed_turns(self) -> None:
        project = Path(__file__).resolve().parents[2]
        api = (project / "backend" / "app" / "main.py").read_text(encoding="utf-8")
        repository = (
            project / "backend" / "app" / "db" / "watch_test_repository.py"
        ).read_text(encoding="utf-8")
        dashboard = (project / "web" / "app.js").read_text(encoding="utf-8")
        watch = (project / "web" / "watch-alerts.js").read_text(encoding="utf-8")
        self.assertIn('/playback-ready", tags=["watch"]', api)
        self.assertIn('"QUEUED" if is_replay else "LIVE"', repository)
        self.assertIn('watch-replay-playback-ready', dashboard)
        self.assertIn('activateReplay(String(event.detail?.testId', watch)
        self.assertIn('latestItem?.lifecycle_status === "LIVE"', dashboard)
        self.assertIn('summary: hint.summary || item.summary', dashboard)

    def test_test_broadcast_is_admin_only_without_daily_limit(self) -> None:
        project = Path(__file__).resolve().parents[2]
        api = (project / "backend" / "app" / "main.py").read_text(encoding="utf-8")
        repository = (
            project / "backend" / "app" / "db" / "watch_test_repository.py"
        ).read_text(encoding="utf-8")
        html = (project / "web" / "index.html").read_text(encoding="utf-8")
        watch = (project / "web" / "watch-alerts.js").read_text(encoding="utf-8")
        self.assertIn('@app.get("/api/watch/admin/session"', api)
        self.assertGreaterEqual(api.count("_watch_admin(x_watch_admin_token)"), 9)
        self.assertNotIn("daily_count", repository)
        self.assertNotIn("하루 3회", repository)
        self.assertIn('id="watchTestControl" hidden', html)
        self.assertIn("restoreAdminSession", watch)
        self.assertIn("adminWatchFetch", watch)
        self.assertIn('fetch("/api/admin/session"', watch)
        self.assertIn("TEST_PRESENTATION_RETENTION_MS = 60 * 1000", watch)
        self.assertIn("testPresentationRemaining", watch)
        self.assertIn("scheduleTestPresentationClear", watch)

    def test_watch_path_does_not_import_llm_clients(self) -> None:
        app_dir = Path(__file__).resolve().parents[1] / "app"
        paths = [
            app_dir / "db" / "watch_repository.py",
            app_dir / "db" / "watch_test_repository.py",
            app_dir / "ingestion" / "watch_worker.py",
        ]
        combined = "\n".join(path.read_text(encoding="utf-8") for path in paths)
        self.assertNotIn("Mistral", combined)
        self.assertNotIn("OpenRouter", combined)
        self.assertNotIn("Gemini", combined)

    def test_notification_history_can_be_pruned_by_its_owner(self) -> None:
        app_dir = Path(__file__).resolve().parents[1] / "app"
        repository = (app_dir / "db" / "watch_repository.py").read_text(encoding="utf-8")
        api = (app_dir / "main.py").read_text(encoding="utf-8")
        self.assertIn("def delete_notification(", repository)
        self.assertIn("def clear_read_notifications(", repository)
        self.assertIn("def prune_notification_history(", repository)
        self.assertIn("NOTIFICATION_RETENTION_LIMIT = 50", repository)
        self.assertIn("DELETE FROM watch_notifications", repository)
        self.assertIn('@app.delete("/api/watch/notifications/{notification_id}"', api)
        self.assertIn('@app.delete("/api/watch/notifications"', api)

    def test_free_completion_path_has_digest_metrics_and_export(self) -> None:
        app_dir = Path(__file__).resolve().parents[1] / "app"
        repository = (app_dir / "db" / "watch_repository.py").read_text(encoding="utf-8")
        worker = (app_dir / "ingestion" / "watch_worker.py").read_text(encoding="utf-8")
        api = (app_dir / "main.py").read_text(encoding="utf-8")
        self.assertIn("def finalize_ended_sessions(", repository)
        self.assertIn("def refresh_official_verifications(", repository)
        self.assertIn("def metrics(", repository)
        self.assertIn("official_matches_verified", worker)
        self.assertIn('@app.get("/api/watch/metrics"', api)
        self.assertIn('@app.get("/api/live/broadcasts/{broadcast_id}/brief.md"', api)
        self.assertIn('"X-LLM-Calls": "0"', api)
        self.assertIn("def latest_rule_report(", repository)
        self.assertIn('@app.get("/api/watch/rules/{rule_id}/report"', api)
        self.assertIn('"llm_calls_on_view": 0', repository)


if __name__ == "__main__":
    unittest.main()
