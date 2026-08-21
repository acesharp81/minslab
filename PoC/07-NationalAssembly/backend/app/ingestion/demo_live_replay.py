from __future__ import annotations

import argparse
import json
import time
import uuid
from datetime import datetime, timezone

from ..adapters.national_assembly.base import SourcePayload
from ..db.live_repository import CaptionRevision, LiveBroadcastObservation, LiveRepository
from ..db.schedule_repository import SourceVersionInput


DEMO_SEGMENTS = (
    {
        "id": "demo-1", "speaker": "시뮬레이션 위원",
        "text": "집중호우 피해 지역의 복구 속도와 주민 지원 현황은 어떻게 관리하고 있습니까?",
        "insight": {"topic_id": "disaster-recovery", "topic": "집중호우 피해 복구", "role": "QUESTION"},
    },
    {
        "id": "demo-2", "speaker": "시뮬레이션 정부위원",
        "text": "행정안전부가 지방자치단체와 피해 현황을 매일 갱신하고 현재 복구 실적을 공개하고 있습니다.",
        "insight": {"topic_id": "disaster-recovery", "topic": "집중호우 피해 복구", "role": "ANSWER"},
    },
    {
        "id": "demo-3", "speaker": "시뮬레이션 위원",
        "text": "재난 복구 예산이 현장에 적기에 집행되도록 어떤 조치를 하겠습니까?",
        "insight": {"topic_id": "recovery-budget", "topic": "재난 복구 예산 집행", "role": "QUESTION"},
    },
    {
        "id": "demo-4", "speaker": "시뮬레이션 정부위원",
        "text": "집행 실적을 주 단위로 점검하고 추가 재원 소요를 국회에 보고하겠습니다.",
        "insight": {"topic_id": "recovery-budget", "topic": "재난 복구 예산 집행", "role": "ANSWER", "task_id": "budget-weekly-report", "task": "복구 예산 집행 실적 주간 점검 및 추가 재원 보고", "task_status": "OPEN", "ministries": ["기획재정부", "행정안전부"]},
    },
    {
        "id": "demo-5", "speaker": "시뮬레이션 위원",
        "text": "피해 주민의 법률 지원과 권리 보호 대책은 어떻게 마련하겠습니까?",
        "insight": {"topic_id": "legal-support", "topic": "피해 주민 법률 지원", "role": "QUESTION"},
    },
    {
        "id": "demo-6", "speaker": "시뮬레이션 정부위원",
        "text": "지원이 누락된 지역을 확인하고 법률구조 상담 창구의 보완 방안을 마련하겠습니다.",
        "insight": {"topic_id": "legal-support", "topic": "피해 주민 법률 지원", "role": "ANSWER", "task_id": "legal-support-gap-review", "task": "지원 누락 지역 확인 및 법률구조 상담 창구 보완", "task_status": "OPEN", "ministries": ["법무부"]},
    },
)


def _source(payload: SourcePayload, artifact: object, parser_version: str) -> SourceVersionInput:
    return SourceVersionInput(
        source_type=payload.source_key, source_url=payload.source_url,
        content_hash=artifact.content_hash, raw_path=artifact.content_path,
        retrieved_at=payload.retrieved_at, parser_version=parser_version,
        content_type=payload.content_type, metadata={"simulation": True},
    )


def main() -> None:
    from ..config import get_settings
    from ..db.connection import connect
    from ..db.migrate import apply_migrations
    from ..storage.raw_store import RawStore

    parser = argparse.ArgumentParser(description="Replay an isolated POC-07 LIVE E2E demo")
    parser.add_argument("--event-interval", type=float, default=3.0)
    parser.add_argument("--hold-seconds", type=int, default=900)
    args = parser.parse_args()
    if not 0.5 <= args.event_interval <= 30 or not 60 <= args.hold_seconds <= 3600:
        parser.error("invalid demo timing")
    settings = get_settings()
    apply_migrations(settings.database_url)
    store = RawStore(settings.raw_data_dir)
    started_at = datetime.now(timezone.utc)
    external_id = "DEMO-" + started_at.strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]
    observation_data = {
        "simulation": True, "external_id": external_id,
        "title": "[DEMO] 법제사법위원회 실시간 자막 E2E",
    }
    content = json.dumps(observation_data, ensure_ascii=False, sort_keys=True).encode("utf-8")
    payload = SourcePayload(
        source_key="demo_live_observation", content=content, content_type="application/json",
        retrieved_at=started_at, source_url=f"simulation://poc07/{external_id}", http_status=200,
    )
    artifact = store.save(payload, parser_version="demo-live-e2e/1.0")
    with connect(settings.database_url) as connection:
        broadcast_id = LiveRepository(connection).observe_broadcast(LiveBroadcastObservation(
            institution="LEGISLATURE", external_id=external_id,
            committee_name="법제사법위원회", title=observation_data["title"],
            caption_source_status="SIMULATION", caption_websocket_url=None,
            thumbnail_url="assets/magazine/sim-committee-hearing.png",
            observed_at=started_at, source=_source(payload, artifact, "demo-live-e2e/1.0"),
            source_system="poc07.demo",
        ))
    print(json.dumps({"event": "demo.live.started", "broadcast_id": str(broadcast_id)}, ensure_ascii=False), flush=True)
    for segment in DEMO_SEGMENTS:
        segment_id = segment["id"]
        speaker = segment["speaker"]
        final_text = segment["text"]
        partial_text = final_text[: max(16, len(final_text) // 2)].rstrip()
        for is_final, text in ((False, partial_text), (True, final_text)):
            received_at = datetime.now(timezone.utc)
            message = {
                "simulation": True, "segment_id": segment_id,
                "speaker_label": speaker, "text": text, "is_final": is_final,
                "insight": segment["insight"],
            }
            message_content = json.dumps(message, ensure_ascii=False, sort_keys=True).encode("utf-8")
            message_payload = SourcePayload(
                source_key="demo_caption_message", content=message_content,
                content_type="application/json", retrieved_at=received_at,
                source_url=f"simulation://poc07/{external_id}/{segment_id}/{int(is_final)}",
                http_status=200,
            )
            message_artifact = store.save(message_payload, parser_version="demo-caption/1.0")
            with connect(settings.database_url) as connection:
                LiveRepository(connection).append_caption_revision(broadcast_id, CaptionRevision(
                    source_segment_id=segment_id, text=text, speaker_label=speaker,
                    is_final=is_final, received_at=received_at, source_payload=message,
                    source=_source(message_payload, message_artifact, "demo-caption/1.0"),
                ))
            print(json.dumps({"event": "demo.caption", "segment": segment_id, "final": is_final}, ensure_ascii=False), flush=True)
            time.sleep(args.event_interval)
    print(json.dumps({"event": "demo.live.holding", "seconds": args.hold_seconds}, ensure_ascii=False), flush=True)
    time.sleep(args.hold_seconds)
    ended_at = datetime.now(timezone.utc)
    with connect(settings.database_url) as connection:
        LiveRepository(connection).finish_broadcast(broadcast_id, ended_at)
    print(json.dumps({"event": "demo.live.ended", "broadcast_id": str(broadcast_id)}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
