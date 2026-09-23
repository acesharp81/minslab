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


def test_official_diff_counts_replacement_once_and_keeps_official_copy() -> None:
    changed = official_utterance_diff(
        "관련 사업에 20억 원을 편성한다.",
        "관련 사업에 30억 원을 편성한다.",
    )
    assert changed["change_count"] == 1
    assert "".join(span["text"] for span in changed["spans"]) == (
        "관련 사업에 30억 원을 편성한다."
    )
    assert not any(span["kind"] == "deleted" for span in changed["spans"])


def test_official_diff_ignores_procedural_boundary_but_preserves_real_live_only_text() -> None:
    procedural = official_utterance_diff(
        "이 사건은 중요합니다 예 이상입니다 수고하셨습니다",
        "이 사건은 중요합니다.",
    )
    assert procedural["comparison_status"] == "NON_SUBSTANTIVE"
    assert procedural["change_count"] == 0

    grammatical = official_utterance_diff(
        "것입니다 둘째 예산을 검토합니다",
        "둘째, 예산을 검토합니다.",
    )
    assert grammatical["comparison_status"] == "NON_SUBSTANTIVE"
    assert grammatical["change_count"] == 0
    assert grammatical["live_only_fragments"] == []

    substantive = official_utterance_diff(
        "법무부는 예산을 편성하고 별도 피해조사를 실시한다.",
        "법무부는 예산을 편성한다.",
    )
    assert substantive["change_count"] == 1
    assert substantive["live_only_fragments"] == ["하고 별도 피해조사를 실시"]
    assert "".join(span["text"] for span in substantive["spans"]) == (
        "법무부는 예산을 편성한다."
    )


def test_official_diff_ignores_clause_order_and_marks_only_real_moved_append() -> None:
    reordered = official_utterance_diff(
        "대법원과 법원행정처의 비상계엄 관련 회의 및 입장을 점검했다.",
        "비상계엄 관련 회의 및 입장: 대법원·법원행정처 점검.",
    )
    assert reordered["comparison_status"] == "STYLE_ONLY"
    assert reordered["change_count"] == 0

    changed = official_utterance_diff(
        "법무부는 예산을 점검했다. 행정안전부는 재난 대책을 검토했다.",
        "행정안전부는 재난 대책을 검토했다. "
        "법무부는 예산을 점검했고 개선안을 제출했다.",
    )
    marked = "".join(
        span["text"] for span in changed["spans"] if span["kind"] != "equal"
    )
    assert changed["change_count"] == 1
    assert "개선안을 제출" in marked
    assert "행정안전부는 재난 대책" not in marked


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


def test_official_presentation_compares_the_matched_segment_not_whole_speaker_turn() -> None:
    official_id = "official-local"
    live = [{
        "utterance_id": "grouped-live-turn",
        "speaker_label": "화자 0",
        "text": "앞선 다른 발언입니다. 실제 대응 문장입니다. 뒤의 다른 발언입니다.",
        "segment_count": 3,
        "official_reconciliations": [{
            "status": "MATCHED",
            "official_utterance_id": official_id,
            "live_revision_id": "revision-2",
            "live_text": "실제 대응 문장입니다",
        }],
    }]
    official = [{
        "utterance_id": official_id,
        "sequence_number": 2,
        "speaker_name": "김 위원",
        "text": "실제 대응 문장입니다.",
    }]
    result = build_official_evidence_presentations(
        live, official, [official_id],
        publication_stage="FINAL", authority_status="OFFICIAL",
    )
    assert result[0]["live_text"] == "실제 대응 문장입니다"
    assert result[0]["live_utterance_count"] == 1
    assert result[0]["comparison_status"] == "STYLE_ONLY"
    assert result[0]["change_count"] == 0


def test_cached_official_references_are_remapped_without_mutating_source() -> None:
    source = {
        "official_evidence_ids": ["old-1"],
        "nested": [{"official_utterance_ids": ["old-1", "kept"]}],
    }
    result = remap_official_references(source, {"old-1": "new-1"})
    assert result["official_evidence_ids"] == ["new-1"]
    assert result["nested"][0]["official_utterance_ids"] == ["new-1", "kept"]
    assert source["official_evidence_ids"] == ["old-1"]
