from __future__ import annotations

import os
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import psycopg
from app.db.live_repository import CaptionRevision, LiveRepository
from app.db.watch_lifecycle_repository import WatchLifecycleRepository
from app.db.watch_repository import WatchRepository
from app.db.watch_test_repository import WatchTestRepository
from app.ingestion.watch_worker import process_revisions
from app.services.watch_lifecycle import (
    compact_message,
    completion_ready,
    declaration_kind,
    rank_topics,
    topic_projection,
)

NOW = datetime(2026, 10, 22, 1, tzinfo=timezone.utc)


def utterance(index, topic, *, minutes=0, ready=True):
    return {
        "utterance_id": str(index),
        "segment_ids": [str(index)],
        "revision_ids": [str(index)],
        "speaker_label": f"화자 {index}",
        "summary": f"요약 {index}",
        "text": f"발언 {index}",
        "ready": ready,
        "end_at": NOW + timedelta(minutes=minutes),
        "live_insight": {"topic": topic, "topic_key": topic},
    }


class LifecycleTests(unittest.TestCase):
    def test_five_minutes_after_transition_and_answer_without_keyword(self):
        items = [
            utterance(1, "인공지능"),
            utterance(2, "인공지능", minutes=1),
            utterance(3, "홍수", minutes=2),
        ]
        self.assertFalse(
            completion_ready(items, {"1"}, now=NOW + timedelta(minutes=6, seconds=59))
        )
        self.assertTrue(completion_ready(items, {"1"}, now=NOW + timedelta(minutes=7)))
        self.assertEqual(2, len(topic_projection(items, {"1"})[0]["points"]))

    def test_silence_is_not_topic_completion(self):
        self.assertFalse(
            completion_ready(
                [utterance(1, "인공지능")], {"1"}, now=NOW + timedelta(hours=1)
            )
        )

    def test_related_statement_resets_grace_and_missing_summary_blocks(self):
        items = [
            utterance(1, "인공지능"),
            utterance(2, "홍수", minutes=2),
            utterance(3, "인공지능", minutes=6),
        ]
        self.assertFalse(completion_ready(items, {"1"}, now=NOW + timedelta(minutes=8)))
        items.append(utterance(4, "홍수", minutes=7, ready=False))
        self.assertFalse(
            completion_ready(
                items, {"1"}, now=NOW + timedelta(minutes=20), boundary=True
            )
        )

    def test_boundary_flushes_ready_topics(self):
        self.assertTrue(
            completion_ready([utterance(1, "인공지능")], {"1"}, now=NOW, boundary=True)
        )

    def test_new_unprocessed_turn_does_not_starve_completed_five_minute_window(self):
        items = [utterance(1, "인공지능"), utterance(2, "홍수", minutes=1),
                 utterance(3, "홍수", minutes=5), utterance(4, "", minutes=7, ready=False)]
        self.assertTrue(completion_ready(items, {"1"}, now=NOW + timedelta(minutes=8)))
        items[-1]["start_at"] = NOW + timedelta(minutes=5)
        self.assertFalse(completion_ready(items, {"1"}, now=NOW + timedelta(minutes=8)))
        self.assertFalse(completion_ready(items, {"1"}, now=NOW + timedelta(minutes=8), boundary=True))

    def test_only_presiding_declaration(self):
        self.assertEqual(
            "RECESS", declaration_kind("잠시 정회를 선포합니다.", "위원장 홍길동")
        )
        self.assertIsNone(declaration_kind("정회를 선포합니다.", "위원 홍길동"))
        self.assertIsNone(declaration_kind("정회를 요청합니다.", "위원장"))
        self.assertIsNone(
            declaration_kind("어제 정회를 선포합니다라고 말했습니다.", "위원장")
        )

    def test_rank_merges_evidence_and_limits_five(self):
        topics = []
        for i in range(7):
            topics += topic_projection([utterance(i, f"주제-{i}", minutes=i)], {str(i)})
        ranked = rank_topics(topics + topics[:1])
        self.assertEqual(5, len(ranked))
        self.assertEqual("주제-6", ranked[0]["title"])
        self.assertTrue(all(t["utterance_count"] == 1 for t in ranked))

    def test_split_source_segment_matches_parent_detection(self):
        item = utterance("abc:0", "인공지능")
        self.assertEqual(1, len(topic_projection([item], {"abc"})))

    def test_kakao_length_and_link_hint(self):
        text = compact_message("주제 완료", "긴 요약 " * 100)
        self.assertLessEqual(len(text), 200)
        self.assertIn("전체 요약은 링크", text)


@unittest.skipUnless(
    os.getenv("WATCH_TEST_DATABASE_URL"), "isolated PostgreSQL required"
)
class LifecycleDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.connection = psycopg.connect(os.environ["WATCH_TEST_DATABASE_URL"])
        self.repo = WatchRepository(self.connection)
        self.lifecycle = WatchLifecycleRepository(self.connection)
        self.now = datetime.now(timezone.utc) + timedelta(seconds=1)
        self.subscriber, _ = self.repo.create_subscriber()
        self.rule = self.repo.create_rule(
            self.subscriber,
            name="AI",
            include_terms=["AI"],
            exclude_terms=[],
            institution=None,
            committee_name=None,
        )
        self.broadcast = WatchTestRepository(self.connection).start(
            self.subscriber, "AI", self.now
        )["broadcast_id"]
        self.sequence = 0

    def tearDown(self):
        self.connection.rollback()
        self.connection.close()

    def emit(self, text="AI 정책", topic="인공지능", minutes=0, speaker=None):
        self.sequence += 1
        at = self.now + timedelta(minutes=minutes)
        source = WatchTestRepository._source(
            f"{self.broadcast}/{self.sequence}", {}, at
        )
        LiveRepository(self.connection).append_caption_revision(
            self.broadcast,
            CaptionRevision(
                source_segment_id=f"test-{self.sequence}",
                text=text,
                speaker_label=speaker or f"화자 {self.sequence}",
                is_final=True,
                received_at=at,
                source_payload={"insight": {"topic": topic, "topic_key": topic}},
                source=source,
            ),
        )
        process_revisions(self.connection)

    def stages(self):
        return [
            r[0]
            for r in self.connection.execute(
                "SELECT stage FROM watch_dispatches WHERE subscriber_id=%s ORDER BY sequence",
                (self.subscriber,),
            ).fetchall()
        ]

    def test_three_stages_repeated_matches_and_restart_delete_idempotency(self):
        self.emit()
        self.emit("AI 질문에 답변합니다", minutes=1)
        self.emit("관련 정책을 시행합니다", minutes=2)
        self.emit("홍수 대비", topic="홍수", minutes=3)
        self.emit("추가 홍수 대비", topic="홍수", minutes=4)
        self.assertEqual([1], self.stages())
        self.lifecycle.reconcile(now=self.now + timedelta(minutes=7, seconds=59))
        self.assertEqual([1], self.stages())
        self.lifecycle.reconcile(now=self.now + timedelta(minutes=8))
        self.assertEqual([1, 2], self.stages())
        details = self.connection.execute(
            "SELECT details FROM watch_dispatches WHERE stage=2 AND subscriber_id=%s",
            (self.subscriber,),
        ).fetchone()[0]
        self.assertEqual(3, details["topics"][0]["utterance_count"])
        LiveRepository(self.connection).finish_broadcast(
            self.broadcast, self.now + timedelta(minutes=9)
        )
        self.lifecycle.reconcile(now=self.now + timedelta(minutes=9))
        self.assertEqual([1, 2, 3], self.stages())
        self.connection.execute(
            "DELETE FROM watch_notifications WHERE subscriber_id=%s", (self.subscriber,)
        )
        WatchLifecycleRepository(self.connection).reconcile(
            now=self.now + timedelta(minutes=10)
        )
        self.assertEqual([1, 2, 3], self.stages())
        dispatch_id = self.connection.execute(
            "SELECT id FROM watch_dispatches WHERE subscriber_id=%s LIMIT 1",
            (self.subscriber,),
        ).fetchone()[0]
        self.assertIsNone(self.lifecycle.detail(uuid.uuid4(), dispatch_id))
        self.assertIsNotNone(self.lifecycle.detail(self.subscriber, dispatch_id))

    def test_recess_resume_and_end_have_separate_cumulative_digests(self):
        self.emit()
        self.emit("정회를 선포합니다.", topic="회의 운영", minutes=1, speaker="위원장")
        self.lifecycle.reconcile(now=self.now + timedelta(minutes=1))
        self.assertEqual([1, 2, 3], self.stages())
        self.emit("AI 다시 질의", minutes=10)
        self.emit("답변", minutes=11)
        LiveRepository(self.connection).finish_broadcast(
            self.broadcast, self.now + timedelta(minutes=12)
        )
        self.connection.execute(
            "UPDATE watch_broadcast_signals SET state='LIVE' WHERE broadcast_id=%s",
            (self.broadcast,),
        )
        self.lifecycle.reconcile(now=self.now + timedelta(minutes=12))
        self.assertEqual([1, 2, 3, 1, 2, 3], self.stages())
        latest = self.connection.execute(
            "SELECT details FROM watch_dispatches WHERE subscriber_id=%s AND stage=3 ORDER BY sequence DESC LIMIT 1",
            (self.subscriber,),
        ).fetchone()[0]
        self.assertEqual(3, latest["topics"][0]["utterance_count"])

    def test_delayed_detection_after_boundary_is_not_repeated(self):
        # A monitor boundary can precede watch-worker consumption of the captions.
        with patch(
            "app.db.watch_lifecycle_repository.WatchLifecycleRepository.on_detection",
            return_value=None,
        ):
            self.emit()
            self.emit("AI 반복", minutes=1)
        self.connection.execute(
            "DELETE FROM watch_detection_events WHERE broadcast_id=%s",
            (self.broadcast,),
        )
        self.lifecycle.record_boundary(
            self.broadcast, "RECESS", self.now + timedelta(minutes=2), {"test": True}
        )
        first = self.connection.execute(
            "SELECT MIN(r.event_cursor) FROM transcript_segment_revisions r JOIN transcript_segments s ON s.id=r.segment_id WHERE s.broadcast_id=%s",
            (self.broadcast,),
        ).fetchone()[0]
        self.connection.execute(
            "UPDATE watch_worker_state SET event_cursor=%s WHERE worker_name='watch-alerts'",
            (first - 1,),
        )
        process_revisions(self.connection)
        self.assertEqual([1], self.stages())
        self.lifecycle.reconcile(now=self.now + timedelta(minutes=2))
        self.assertEqual([1, 2, 3], self.stages())

    def test_obsolete_settings_are_not_exposed(self):
        for key in ("notification_policy", "digest_enabled", "cooldown_minutes"):
            self.assertNotIn(key, self.repo.list_rules(self.subscriber)[0])
        self.repo.update_rule(
            self.subscriber, self.rule["rule_id"], notification_policy="EVERY_MATCH"
        )
        self.emit()
        self.emit(minutes=1)
        self.assertEqual([1], self.stages())

    def test_missing_summary_waits_instead_of_sending_partial_digest(self):
        self.emit()
        self.emit("질의 답변", minutes=1)
        self.connection.execute(
            "UPDATE live_broadcasts SET source_system='assembly.webcast.go.kr' WHERE id=%s",
            (self.broadcast,),
        )
        LiveRepository(self.connection).finish_broadcast(
            self.broadcast, self.now + timedelta(minutes=2)
        )
        self.lifecycle.reconcile(now=self.now + timedelta(minutes=2))
        self.assertEqual([1], self.stages())
        self.connection.execute(
            "UPDATE live_broadcasts SET source_system='poc07.test' WHERE id=%s",
            (self.broadcast,),
        )
        self.lifecycle.reconcile(now=self.now + timedelta(minutes=3))
        self.assertEqual([1, 2, 3], self.stages())

    def test_production_source_short_turns_use_saved_ai_summaries_through_all_stages(self):
        from app.db.summary_repository import SummaryRepository
        self.emit("AI 예산 자료를 제출하십시오")
        self.emit("네, 제출하겠습니다", minutes=1)
        self.connection.execute("UPDATE live_broadcasts SET source_system='assembly.webcast.go.kr' WHERE id=%s", (self.broadcast,))
        self.lifecycle.record_boundary(self.broadcast, "RECESS", self.now + timedelta(minutes=2), {"method": "OFFICIAL_STATUS"})
        self.lifecycle.reconcile(now=self.now + timedelta(minutes=2))
        self.assertEqual([1], self.stages())
        cutoff = self.connection.execute("SELECT cutoff_cursor FROM watch_meeting_boundaries WHERE broadcast_id=%s", (self.broadcast,)).fetchone()[0]
        turns = self.lifecycle.utterances(self.broadcast, "ENDED", cutoff=cutoff)
        self.assertTrue(all(len(u["text"]) < 180 for u in turns))
        SummaryRepository(self.connection).save_many(self.broadcast, [{
            "content_hash": u["content_hash"], "source_speaker_label": "", "summary": "예산 자료 제출에 관해 질의·답변했다.",
            "live_insight": {"topic": "AI 예산 자료 제출", "topic_key": "AI 예산 자료"},
            "original_char_count": len(u["text"]), "segment_count": len(u["segment_ids"]),
        } for u in turns], provider="fixture", model="fixture", prompt_version="fixture")
        self.lifecycle.reconcile(now=self.now + timedelta(minutes=3))
        self.assertEqual([1, 2, 3], self.stages())
        self.lifecycle.reconcile(now=self.now + timedelta(minutes=4))
        self.assertEqual([1, 2, 3], self.stages())

    def test_official_recess_corrects_transient_end_without_duplicate_digest(self):
        self.emit()
        self.emit("관련 답변", minutes=1)
        self.lifecycle.record_boundary(self.broadcast, "ENDED", self.now + timedelta(minutes=2), {"method": "BROADCAST_LIFECYCLE"})
        self.lifecycle.record_boundary(self.broadcast, "RECESS", self.now + timedelta(minutes=2, seconds=30), {"method": "OFFICIAL_STATUS"})
        self.lifecycle.reconcile(now=self.now + timedelta(minutes=3))
        self.assertEqual([1, 2, 3], self.stages())
        detail = self.connection.execute("SELECT details FROM watch_dispatches WHERE subscriber_id=%s AND stage=3", (self.subscriber,)).fetchone()[0]
        self.assertEqual(detail["boundary_kind"], "RECESS")

    def test_inferred_broadcast_end_waits_for_official_recess_correction(self):
        self.emit()
        self.emit("관련 답변", minutes=1)
        self.connection.execute("UPDATE live_broadcasts SET source_system='assembly.webcast.go.kr' WHERE id=%s", (self.broadcast,))
        LiveRepository(self.connection).finish_broadcast(self.broadcast, self.now + timedelta(minutes=2))
        self.lifecycle.reconcile(now=self.now + timedelta(minutes=2, seconds=10))
        self.assertEqual(0, self.connection.execute("SELECT count(*) FROM watch_meeting_boundaries WHERE broadcast_id=%s", (self.broadcast,)).fetchone()[0])
        self.lifecycle.record_boundary(self.broadcast, "RECESS", self.now + timedelta(minutes=2, seconds=30), {"method": "OFFICIAL_STATUS"})
        self.assertEqual("RECESS", self.connection.execute("SELECT kind FROM watch_meeting_boundaries WHERE broadcast_id=%s", (self.broadcast,)).fetchone()[0])
        self.lifecycle.reconcile(now=self.now + timedelta(minutes=7))
        # The late lifecycle fallback retains its evidence; only the corrected
        # recess is eligible for a digest once summaries become ready.
        self.assertEqual(2, self.connection.execute("SELECT count(*) FROM watch_meeting_boundaries WHERE broadcast_id=%s", (self.broadcast,)).fetchone()[0])
        self.assertEqual([1], self.stages())

    def test_kakao_stage_order_waits_for_retry_and_permanent_failure_releases_queue(
        self,
    ):
        from app.db.watch_delivery_repository import WatchDeliveryRepository

        delivery = WatchDeliveryRepository(self.connection)
        delivery.save_account(
            self.subscriber,
            {
                "kakao_user_id": str(uuid.uuid4()),
                "access_token_ciphertext": "fixture",
                "refresh_token_ciphertext": "fixture",
                "access_token_expires_at": self.now + timedelta(days=1),
                "refresh_token_expires_at": self.now + timedelta(days=2),
                "scopes": ["talk_message"],
            },
        )
        self.connection.execute(
            "UPDATE watch_rules SET kakao_enabled=true WHERE id=%s",
            (self.rule["rule_id"],),
        )
        self.connection.execute(
            "UPDATE live_broadcasts SET source_system='poc07.replay.kakao' WHERE id=%s",
            (self.broadcast,),
        )
        self.emit()
        self.emit("답변", minutes=1)
        LiveRepository(self.connection).finish_broadcast(
            self.broadcast, self.now + timedelta(minutes=2)
        )
        self.lifecycle.reconcile(now=self.now + timedelta(minutes=2))
        first = delivery.claim("fixture-worker")
        self.assertIn("키워드 감지", first["title"])
        delivery.finish(
            first["outbox_id"], sent=False, retryable=True, error="fixture retry"
        )
        self.assertIsNone(delivery.claim("fixture-worker"))
        delivery.finish(
            first["outbox_id"], sent=False, retryable=False, error="fixture permanent"
        )
        second = delivery.claim("fixture-worker")
        self.assertIn("주제 완료", second["title"])
        delivery.finish(second["outbox_id"], sent=True)
        third = delivery.claim("fixture-worker")
        self.assertIn("회의 종료", third["title"])

    def test_digest_merges_rules_but_kakao_only_contains_opted_in_topics(self):
        self.connection.execute(
            "UPDATE watch_rules SET kakao_enabled=true WHERE id=%s",
            (self.rule["rule_id"],),
        )
        self.repo.create_rule(
            self.subscriber,
            name="홍수",
            include_terms=["홍수"],
            exclude_terms=[],
            institution=None,
            committee_name=None,
        )
        self.emit()
        self.emit("AI 답변", minutes=1)
        self.emit("홍수 대책", topic="홍수", minutes=2)
        LiveRepository(self.connection).finish_broadcast(
            self.broadcast, self.now + timedelta(minutes=3)
        )
        self.lifecycle.reconcile(now=self.now + timedelta(minutes=3))
        rows = self.connection.execute(
            "SELECT details FROM watch_dispatches WHERE subscriber_id=%s AND stage=3",
            (self.subscriber,),
        ).fetchall()
        self.assertEqual(1, len(rows))
        self.assertEqual(2, len(rows[0][0]["topics"]))
        self.assertNotIn("홍수", rows[0][0]["kakao_body"])
        self.assertIn("인공지능", rows[0][0]["kakao_body"])

    def test_dispatch_api_is_owner_scoped_and_removed_options_absent(self):
        from contextlib import nullcontext

        from app.main import WatchRulePayload, WatchRuleUpdatePayload, app
        from fastapi.testclient import TestClient

        self.emit()
        dispatch_id = self.connection.execute(
            "SELECT id FROM watch_dispatches WHERE subscriber_id=%s", (self.subscriber,)
        ).fetchone()[0]
        with (
            patch(
                "app.main.connect", side_effect=lambda _: nullcontext(self.connection)
            ),
            patch("app.main._watch_subscriber", return_value=self.subscriber),
        ):
            response = TestClient(app).get(f"/api/watch/dispatches/{dispatch_id}")
        self.assertEqual(200, response.status_code)
        self.assertEqual(1, response.json()["stage"])
        with (
            patch(
                "app.main.connect", side_effect=lambda _: nullcontext(self.connection)
            ),
            patch("app.main._watch_subscriber", return_value=uuid.uuid4()),
        ):
            self.assertEqual(
                404,
                TestClient(app).get(f"/api/watch/dispatches/{dispatch_id}").status_code,
            )
        for model in [WatchRulePayload, WatchRuleUpdatePayload]:
            for key in ["notification_policy", "digest_enabled", "cooldown_minutes"]:
                self.assertNotIn(key, model.model_json_schema()["properties"])

    def test_distinct_keywords_in_same_rule_do_not_suppress_each_other(self):
        self.repo.update_rule(
            self.subscriber, self.rule["rule_id"], include_terms=["AI", "홍수"]
        )
        self.emit("AI 정책")
        self.emit("홍수 대책", topic="홍수", minutes=1)
        self.emit("AI와 홍수 모두 다시 언급", topic="홍수", minutes=2)
        self.assertEqual([1, 1], self.stages())
        self.assertEqual(
            2,
            self.connection.execute(
                "SELECT COUNT(*) FROM watch_topic_episodes"
            ).fetchone()[0],
        )

    def test_two_keywords_in_single_revision_each_detect_once(self):
        self.repo.update_rule(
            self.subscriber, self.rule["rule_id"], include_terms=["AI", "홍수"]
        )
        self.emit("AI 홍수 대응")
        self.emit("AI 홍수 대응 반복", minutes=1)
        self.assertEqual([1, 1], self.stages())

    def test_user_deletion_keeps_active_deduplication_state(self):
        self.emit()
        notification = self.repo.list_notifications(self.subscriber)["items"][0]
        self.repo.delete_notification(self.subscriber, notification["notification_id"])
        self.emit("AI 다시 언급", minutes=1)
        self.assertEqual([1], self.stages())
        self.assertEqual(
            1,
            self.connection.execute(
                "SELECT COUNT(*) FROM watch_topic_episodes"
            ).fetchone()[0],
        )

    def test_same_keyword_in_different_topics_completes_each_topic_independently(self):
        self.emit("AI 정책 질의", topic="인공지능", minutes=0)
        self.emit("정책 답변", topic="인공지능", minutes=1)
        self.emit("AI 홍수 예측", topic="홍수예측", minutes=2)
        self.emit("홍수예측 답변", topic="홍수예측", minutes=3)
        self.emit("별도 교통 논의", topic="교통", minutes=4)
        self.emit("교통 답변", topic="교통", minutes=5)
        self.assertEqual([1], self.stages())
        self.lifecycle.reconcile(now=self.now + timedelta(minutes=7))
        self.assertEqual([1, 2], self.stages())
        self.lifecycle.reconcile(now=self.now + timedelta(minutes=9))
        self.assertEqual([1, 2, 2], self.stages())
        LiveRepository(self.connection).finish_broadcast(
            self.broadcast, self.now + timedelta(minutes=10)
        )
        self.lifecycle.reconcile(now=self.now + timedelta(minutes=10))
        self.assertEqual([1, 2, 2, 3], self.stages())
