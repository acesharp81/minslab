from datetime import date

from app.services.specific_policy_issues import build_specific_policy_issues


def record(
    broadcast_id: str,
    meeting_date: date,
    title: str,
    *,
    summary: str = "구체 정책의 추진 상황과 후속 조치를 점검했다.",
    evidence_id: str = "utterance-1",
    official_evidence_id: str | None = None,
    task: str | None = None,
) -> dict[str, object]:
    topic = {
        "id": "topic-1",
        "title": title,
        "summary": summary,
        "evidence_ids": [evidence_id],
        "official_evidence_ids": (
            [official_evidence_id] if official_evidence_id else []
        ),
    }
    tasks = []
    if task:
        tasks.append({
            "topic_id": "topic-1",
            "title": task,
            "ministries": ["행정안전부"],
        })
    return {
        "broadcast_id": broadcast_id,
        "meeting_title": "테스트 전체회의",
        "meeting_date": meeting_date,
        "committee_name": "행정안전위원회",
        "institution": "NATIONAL_ASSEMBLY",
        "brief": {"topics": [topic], "tasks": tasks},
        "authority_status": "PROVISIONAL",
    }


def test_concrete_topic_persists_across_meetings_without_broad_category() -> None:
    records = [
        record("b-1", date(2026, 8, 10), "AI 민주정부 공공서비스 전환 추진"),
        record("b-2", date(2026, 8, 24), "AI 민주정부 공공서비스 전환 추진"),
    ]

    result = build_specific_policy_issues(records, {})

    assert result["count"] == 1
    assert result["items"][0]["topic"] == "AI 민주정부 공공서비스 전환 추진"
    assert result["items"][0]["trend_status"] == "지속"
    assert result["items"][0]["meeting_count"] == 2
    assert result["additional_llm_calls"] == 0


def test_wording_variants_of_same_specific_topic_are_clustered() -> None:
    result = build_specific_policy_issues(
        [
            record(
                "b-1",
                date(2026, 8, 20),
                "이차전지 업체 지원 강화를 위한 세제 개편 요구",
            ),
            record(
                "b-2",
                date(2026, 8, 26),
                "이차전지 업체 지원과 세제개편안의 문제점",
            ),
        ],
        {},
    )

    assert result["count"] == 1
    assert result["items"][0]["meeting_count"] == 2
    assert "이차전지 업체 지원" in result["items"][0]["topic"]
    assert result["items"][0]["trend_status"] == "신규 관측"


def test_new_topic_is_not_called_a_surge_without_previous_baseline() -> None:
    records = [
        record(f"b-{index}", date(2026, 8, 20 + index), "재난 문자 전달체계 개선")
        for index in range(3)
    ]

    result = build_specific_policy_issues(records, {})

    assert result["items"][0]["current_meeting_count"] == 3
    assert result["items"][0]["previous_meeting_count"] == 0
    assert result["items"][0]["trend_status"] == "신규 관측"


def test_surge_requires_previous_baseline_and_material_increase() -> None:
    records = [
        record("old", date(2026, 8, 10), "재난 문자 전달체계 개선"),
        record("new-1", date(2026, 8, 20), "재난 문자 전달체계 개선"),
        record("new-2", date(2026, 8, 24), "재난 문자 전달체계 개선"),
        record("new-3", date(2026, 9, 1), "재난 문자 전달체계 개선"),
    ]

    result = build_specific_policy_issues(records, {})

    assert result["items"][0]["current_meeting_count"] == 3
    assert result["items"][0]["previous_meeting_count"] == 1
    assert result["items"][0]["trend_status"] == "급증"


def test_procedural_topic_is_excluded() -> None:
    result = build_specific_policy_issues(
        [record("b-1", date(2026, 8, 24), "위원회 간사 선임 및 회의 진행")],
        {},
    )

    assert result["items"] == []


def test_test_broadcast_and_generic_accounting_agenda_are_excluded() -> None:
    test_broadcast = record(
        "b-test", date(2026, 8, 27), "재난 취약계층 대피 체계 개선"
    )
    test_broadcast["meeting_title"] = "[테스트] 제900회 국무회의 · 5분 라이브"
    generic = record(
        "b-1",
        date(2026, 8, 24),
        "2025회계연도 행정안전부 및 소관 기관 결산 보고",
    )

    result = build_specific_policy_issues([test_broadcast, generic], {})

    assert result["items"] == []


def test_multi_bill_umbrella_title_is_excluded() -> None:
    result = build_specific_policy_issues(
        [
            record(
                "b-1",
                date(2026, 8, 24),
                "지방자치법·재난안전기본법 등 19건 법률안 의결",
            )
        ],
        {},
    )

    assert result["items"] == []


def test_official_evidence_promotes_topic_to_direct_bill_stage() -> None:
    result = build_specific_policy_issues(
        [
            record(
                "b-1",
                date(2026, 8, 24),
                "중대범죄수사청 조직 운영 법률 개정",
                official_evidence_id="official-1",
            )
        ],
        {
            "official-1": [{
                "bill_id": "bill-1",
                "bill_name": "중대범죄수사청법안",
                "process_stage_code": "COMMITTEE_PASSED",
                "official_url": "https://example.test/bill-1",
            }]
        },
    )

    item = result["items"][0]
    assert item["transition_stage"] == "BILL_LINKED"
    assert item["transition_label"] == "공식 의안 직접 연결"
    assert item["bills"][0]["bill_name"] == "중대범죄수사청법안"
    assert item["bills"][0]["verification_status"] == "TOPIC_TITLE_VERIFIED"
    assert item["discussion_events"][0]["meeting_title"] == "테스트 전체회의"


def test_unrelated_structural_agenda_link_is_not_exposed_as_direct_bill() -> None:
    result = build_specific_policy_issues(
        [record(
            "b-1", date(2026, 8, 26),
            "소상공인기본법 개정안의 국세청 정보 제공 항목 삭제 사유 재검토",
            official_evidence_id="official-1",
        )],
        {"official-1": [{
            "bill_id": "wrong-bill",
            "bill_name": "스토킹범죄의 처벌 등에 관한 법률 일부개정법률안",
            "agenda_name": "28. 스토킹범죄의 처벌 등에 관한 법률 일부개정법률안",
        }]},
    )

    item = result["items"][0]
    assert item["transition_stage"] == "FORMALIZATION_MENTIONED"
    assert item["bills"] == []
    assert item["rejected_bill_link_count"] == 1


def test_verified_bill_exposes_official_process_timeline() -> None:
    result = build_specific_policy_issues(
        [record(
            "b-1", date(2026, 8, 26),
            "소상공인기본법 개정안의 국세청 정보 제공 항목 삭제 사유 재검토",
            official_evidence_id="official-1",
        )],
        {"official-1": [{
            "bill_id": "right-bill",
            "bill_number": "2200001",
            "bill_name": "소상공인기본법 일부개정법률안",
            "agenda_name": "15. 소상공인기본법 일부개정법률안(대안)",
            "proposal_date": date(2026, 8, 20),
            "proposer_name": "산업통상자원중소벤처기업위원장",
            "committee_process_date": date(2026, 8, 26),
            "committee_name": "법제사법위원회",
            "committee_result": "수정가결",
            "process_stage_code": "COMMITTEE_PASSED",
        }]},
    )

    bill = result["items"][0]["bills"][0]
    assert [step["key"] for step in bill["process_steps"]] == ["PROPOSED", "COMMITTEE"]
    assert bill["process_steps"][-1]["status"] == "CURRENT"
    assert bill["current_status"] == "수정가결"


def test_committee_alternative_is_ordered_before_chair_submission() -> None:
    result = build_specific_policy_issues(
        [record(
            "b-1", date(2026, 8, 26), "소상공인기본법 개정안 재검토",
            official_evidence_id="official-1",
        )],
        {"official-1": [{
            "bill_id": "alternative",
            "bill_name": "소상공인기본법 일부개정법률안(대안)",
            "proposal_date": date(2026, 8, 27),
            "proposer_kind": "위원장",
            "committee_process_date": date(2026, 3, 12),
            "committee_result": "대안가결",
        }]},
    )

    steps = result["items"][0]["bills"][0]["process_steps"]
    assert [step["label"] for step in steps] == ["소관위원회 대안 의결", "위원장 대안 제출"]


def test_follow_up_task_is_shown_as_transition_without_claiming_bill_link() -> None:
    result = build_specific_policy_issues(
        [
            record(
                "b-1",
                date(2026, 8, 24),
                "전국 실종사건 전수조사 및 시스템 개선",
                task="실종사건 전수조사 추진계획 수립",
            )
        ],
        {},
    )

    item = result["items"][0]
    assert item["transition_stage"] == "FOLLOW_UP_TASK"
    assert item["transition_label"] == "후속 과제 도출"
    assert item["ministries"] == ["행정안전부"]
    assert item["bills"] == []


def test_bill_wording_is_not_mislabeled_as_a_completed_decision() -> None:
    result = build_specific_policy_issues(
        [
            record(
                "b-1",
                date(2026, 8, 24),
                "5·18 보상법 시행령 미비 문제",
                summary="법 개정 뒤 시행령이 마련되지 않아 후속 정비가 요구됐다.",
            )
        ],
        {},
    )

    item = result["items"][0]
    assert item["transition_stage"] == "FORMALIZATION_MENTIONED"
    assert item["transition_label"] == "보고서상 법안·제도개편"


def test_plain_execution_discussion_is_not_a_completed_decision() -> None:
    result = build_specific_policy_issues(
        [
            record(
                "b-1",
                date(2026, 8, 24),
                "세제개편안의 문제점과 보완 요구",
                summary="세제개편안의 절차·시행 및 정책 목적에 대한 논란이 제기되었다.",
            )
        ],
        {},
    )

    assert result["items"][0]["transition_stage"] == "FORMALIZATION_MENTIONED"


def test_completed_decision_wording_is_labeled_separately() -> None:
    result = build_specific_policy_issues(
        [
            record(
                "b-1",
                date(2026, 8, 24),
                "도로교통법 개정안 의결",
                summary="개정안이 위원회에서 의결되었다.",
            )
        ],
        {},
    )

    item = result["items"][0]
    assert item["transition_stage"] == "DECISION_MENTIONED"
    assert item["transition_label"] == "보고서상 의결·시행"
