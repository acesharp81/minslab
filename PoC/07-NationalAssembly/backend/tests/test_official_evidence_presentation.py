from __future__ import annotations

from app.services.official_evidence_presentation import (
    build_official_evidence_presentations,
    official_material_hash,
    official_utterance_diff,
    remap_official_references,
)


def test_material_hash_ignores_formatting_but_detects_content_change() -> None:
    base = [{
        "sequence_number": 1, "speaker_name": "김 위원",
        "speaker_role": "위원", "text": "예산을 검토하겠습니다.",
    }]
    formatting = [{
        **base[0], "speaker_name": "김위원", "text": "예산을  검토하겠습니다",
    }]
    changed = [{**base[0], "text": "예산을 즉시 집행하겠습니다."}]
    assert official_material_hash(base) == official_material_hash(formatting)
    assert official_material_hash(base) != official_material_hash(changed)


def test_official_diff_ignores_style_only_and_marks_meaningful_change() -> None:
    style_only = official_utterance_diff(
        "예산을 검토 하겠습니다", "예산을 검토하겠습니다.",
    )
    assert style_only["comparison_status"] == "STYLE_ONLY"
    assert style_only["change_count"] == 0

    changed = official_utterance_diff(
        "예산을 검토하겠습니다",
        "예산 20억 원을 즉시 집행하겠습니다.",
    )
    assert changed["comparison_status"] == "COMPARED"
    assert changed["change_count"] > 0
    assert any(span["kind"] in {"added", "changed"} for span in changed["spans"])


def test_official_presentation_uses_final_speaker_text_and_live_baseline() -> None:
    official_id = "official-1"
    live = [{
        "utterance_id": "live-1",
        "speaker_label": "화자 0",
        "text": "재난 복구 예산을 신속히 검토하겠습니다",
        "segment_count": 4,
        "official_reconciliations": [{
            "status": "MATCHED",
            "official_utterance_id": official_id,
        }],
    }]
    official = [{
        "utterance_id": official_id,
        "sequence_number": 7,
        "speaker_name": "행정안전부장관",
        "speaker_role": "국무위원",
        "text": "재난 피해 복구 예산을 신속히 편성하겠습니다.",
    }]
    result = build_official_evidence_presentations(
        live, official, [official_id],
        publication_stage="FINAL", authority_status="OFFICIAL",
    )
    assert len(result) == 1
    assert result[0]["speaker_label"] == "행정안전부장관"
    assert result[0]["speaker_role"] == "국무위원"
    assert result[0]["text"] == official[0]["text"]
    assert result[0]["live_text"] == live[0]["text"]
    assert result[0]["segment_count"] == 4
    assert result[0]["publication_stage"] == "FINAL"


def test_cached_official_references_are_remapped_without_mutating_source() -> None:
    source = {
        "official_evidence_ids": ["old-1"],
        "nested": [{"official_utterance_ids": ["old-1", "kept"]}],
    }
    result = remap_official_references(source, {"old-1": "new-1"})
    assert result["official_evidence_ids"] == ["new-1"]
    assert result["nested"][0]["official_utterance_ids"] == ["new-1", "kept"]
    assert source["official_evidence_ids"] == ["old-1"]
