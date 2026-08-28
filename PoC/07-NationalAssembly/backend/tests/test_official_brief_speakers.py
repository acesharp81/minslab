from app.services.official_brief_speakers import (
    apply_official_speakers_to_brief,
    merge_validation_repairs,
    remove_unsupported_official_claims,
)


def test_official_speakers_preserve_abstractive_summary_without_excerpting() -> None:
    brief = {
        "topics": [{
            "id": "topic-1",
            "speaker_points": [{
                "id": "point-1", "speaker_label": "화자 0 · 이름 미확인",
                "summary": "질의와 답변", "evidence_ids": ["segment-1"],
            }],
        }],
    }
    segments = [
        {
            "segment_id": "segment-1", "revision_id": "revision-1",
            "broadcast_id": "broadcast-1", "speaker_label": "화자 0 · 이름 미확인",
            "source_speaker_label": "0", "text": "예산 편성 기준을 질의합니다.",
            "cursor": 1, "received_at": None, "is_final": True,
        },
        {
            "segment_id": "segment-2", "revision_id": "revision-2",
            "broadcast_id": "broadcast-1", "speaker_label": "화자 0 · 이름 미확인",
            "source_speaker_label": "0", "text": "기준을 보완하겠습니다.",
            "cursor": 2, "received_at": None, "is_final": True,
        },
    ]
    matches = [
        {"segment_id": "segment-1", "official_speaker_name": "김의원",
         "official_utterance_id": "official-1"},
        {"segment_id": "segment-2", "official_speaker_name": "박장관",
         "official_utterance_id": "official-2"},
    ]

    result = apply_official_speakers_to_brief(brief, segments, matches)

    points = result["topics"][0]["speaker_points"]
    assert len(points) == 1
    assert points[0]["speaker_label"] == "김의원 · 박장관"
    assert points[0]["summary"] == "질의와 답변"
    assert points[0]["official_evidence_ids"] == ["official-1", "official-2"]
    assert points[0]["speaker_official"] is True


def test_official_speaker_relabels_without_splitting() -> None:
    brief = {
        "topics": [{
            "speaker_points": [{
                "id": "point-1", "speaker_label": "화자 1 · 이름 미확인",
                "summary": "답변", "evidence_ids": ["segment-1"],
            }],
        }],
    }
    segments = [{
        "segment_id": "segment-1", "revision_id": "revision-1",
        "broadcast_id": "broadcast-1", "speaker_label": "화자 1 · 이름 미확인",
        "source_speaker_label": "1", "text": "조치하겠습니다.",
        "cursor": 1, "received_at": None, "is_final": True,
    }]
    matches = [{
        "segment_id": "segment-1", "official_speaker_name": "이장관",
        "official_utterance_id": "official-1",
    }]

    result = apply_official_speakers_to_brief(brief, segments, matches)

    points = result["topics"][0]["speaker_points"]
    assert len(points) == 1
    assert points[0]["speaker_label"] == "이장관"
    assert points[0]["summary"] == "답변"
    assert points[0]["official_evidence_ids"] == ["official-1"]
    assert points[0]["speaker_official"] is True


def test_topic_and_task_evidence_are_promoted_to_official_ids() -> None:
    brief = {
        "topics": [{
            "id": "topic-1", "evidence_ids": ["segment-1"],
            "speaker_points": [],
        }],
        "tasks": [{
            "id": "task-1", "evidence_ids": ["segment-1"],
        }],
    }
    segments = [{
        "segment_id": "segment-1", "revision_id": "revision-1",
        "broadcast_id": "broadcast-1", "speaker_label": "화자 0",
        "source_speaker_label": "0", "text": "후속 조치를 추진하겠습니다.",
        "cursor": 1, "received_at": None, "is_final": True,
    }]
    matches = [{
        "segment_id": "segment-1", "official_speaker_name": "김장관",
        "official_utterance_id": "official-1",
    }]

    result = apply_official_speakers_to_brief(brief, segments, matches)

    assert result["topics"][0]["official_evidence_ids"] == ["official-1"]
    assert result["tasks"][0]["official_evidence_ids"] == ["official-1"]


def test_unsupported_joined_names_are_removed_with_official_diff() -> None:
    brief = {
        "topics": [{
            "id": "topic-1", "official_evidence_ids": ["official-1"],
            "summary": "각하율은 82.3%이고 SNS 차단·삭제를 논의했다. 손봉기·선봉기 후보를 고집했다.",
        }],
    }
    rows = [{
        "utterance_id": "official-1", "text": "각하율은 82.3%이고 SNS 차단·삭제를 논의했습니다.",
    }]

    result, repairs = remove_unsupported_official_claims(brief, rows)

    assert result["topics"][0]["summary"] == "각하율은 82.3%이고 SNS 차단·삭제를 논의했다."
    assert len(repairs) == 1


def test_validation_repair_replaces_prior_change_for_same_field() -> None:
    changes = [{
        "entity_type": "topic", "entity_id": "topic-1", "field": "summary",
        "operation": "UPDATE", "after": "검증 전 공식 변경",
    }]
    repairs = [{
        "entity_type": "topic", "entity_id": "topic-1", "field": "summary",
        "operation": "UPDATE", "validation_rule": "UNSUPPORTED_JOINED_PERSON_NAMES",
        "after": "검증된 최종 변경",
    }]

    result = merge_validation_repairs(changes, repairs)

    assert len(result) == 1
