from __future__ import annotations

import unittest

from app.services.meeting_topic_groups import (
    GROUPING_METHOD,
    GROUPING_VERSION,
    attach_meeting_topic_groups,
    build_meeting_topic_groups,
    build_meeting_topic_ontology,
)


def topic(topic_id: str, title: str, *, evidence_id: str | None = None) -> dict:
    return {
        "id": topic_id,
        "title": title,
        "summary": f"{title}에 관한 발언을 정리했다.",
        "evidence_ids": [evidence_id or f"evidence-{topic_id}"],
        "speaker_points": [],
    }


class MeetingTopicGroupTests(unittest.TestCase):
    def test_visual_ontology_covers_every_target_once_and_reports_usage(self):
        result = build_meeting_topic_ontology([{
            "topics": [
                topic("topic-1", "한미 핵 공유 및 전술핵 재배치 제안 비판"),
                topic("topic-2", "주택 세제 개편과 실거주 판정"),
            ],
            "tasks": [],
        }])

        keys = [key for domain in result["domains"] for key in domain["group_keys"]]
        self.assertEqual(len(result["domains"]), 5)
        self.assertEqual(len(result["groups"]), 60)
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(set(keys), {group["key"] for group in result["groups"]})
        self.assertEqual(result["metrics"]["topic_count"], 2)
        self.assertEqual(result["metrics"]["ontology_topic_count"], 2)
        self.assertEqual(result["metrics"]["integrity_failure_count"], 0)

    def test_new_policy_terms_classify_distinct_targets_and_procedure_artifacts(self):
        brief = {"topics": [
            topic("energy", "지역별 재생에너지 발전 현황"),
            topic("bridge", "지천 다리 공사 주민 참여"),
            topic("housing", "청년 주거난 및 주택 대책"),
            topic("turn", "질의자 교체"),
            topic("unclear", "감천 건설 취소 방침 반대"),
        ], "tasks": []}
        grouped = attach_meeting_topic_groups(brief)
        assignments = {
            topic_id: (group["key"], group["assignment_method"])
            for group in grouped["topic_groups"]
            for topic_id in group["topic_ids"]
        }
        self.assertEqual(assignments["energy"], ("energy-electricity", "ONTOLOGY"))
        self.assertEqual(assignments["bridge"], ("transport-infrastructure", "ONTOLOGY"))
        self.assertEqual(assignments["housing"], ("housing-real-estate", "ONTOLOGY"))
        self.assertEqual(assignments["turn"][1], "REPORT_ARTIFACT")
        self.assertEqual(assignments["unclear"], ("water-resources-climate", "ONTOLOGY"))
        self.assertEqual(grouped["topic_grouping"]["integrity_status"], "PASS")

    def test_source_checked_language_repairs_classify_only_supported_targets(self):
        brief = {"topics": [
            topic("fund", "정책편드 통합 및 관리 체계 개선 논의"),
            topic("dam", "감천 - 건설 정책과 기후 변화 대응 능력 논의"),
            topic("tariff", "광세 협상 및 자금 지급 자료 확인"),
            topic("mine", "서해5도 무인도 유실지 문제"),
            topic("drought", "가 대응 및 소방력 강화"),
            topic("wages", "채불 노동자 대출 조건 최종 확인"),
            topic("preface", "재재청 요구 가능 여부 논의 시작"),
            topic("justice", "윤석열 정부 검찰 결정 및 사법부 오염 논란"),
            topic("prison", "교육과 잠자리 문제의 분리 및 개선 요구"),
        ], "tasks": []}
        grouped = attach_meeting_topic_groups(brief)
        assignments = {
            topic_id: (group["key"], group["assignment_method"])
            for group in grouped["topic_groups"]
            for topic_id in group["topic_ids"]
        }
        self.assertEqual(assignments["fund"], ("budget-public-finance", "ONTOLOGY"))
        self.assertEqual(assignments["dam"], ("water-resources-climate", "ONTOLOGY"))
        self.assertEqual(assignments["tariff"], ("trade-climate-industry", "ONTOLOGY"))
        self.assertEqual(assignments["mine"], ("public-safety-health", "ONTOLOGY"))
        self.assertEqual(assignments["drought"], ("water-resources-climate", "ONTOLOGY"))
        self.assertEqual(assignments["wages"], ("youth-employment", "ONTOLOGY"))
        self.assertEqual(assignments["preface"][1], "REPORT_ARTIFACT")
        self.assertEqual(assignments["justice"], ("prosecution-judiciary", "ONTOLOGY"))
        self.assertEqual(assignments["prison"], ("public-safety-health", "ONTOLOGY"))
        self.assertEqual(brief["topics"][0]["title"], "정책편드 통합 및 관리 체계 개선 논의")
        self.assertEqual(grouped["topics"][0]["title"], "정책펀드 통합 및 관리 체계 개선 논의")

    def test_groups_detail_topics_by_policy_target_without_collapsing_them(self):
        brief = {
            "topics": [
                topic("topic-1", "한미 핵 공유 및 전술핵 재배치 제안 비판"),
                topic("topic-2", "북한 핵 잠수함 공개 및 탐지 능력 우려"),
                topic("topic-3", "북핵 위협에 대한 실질적 핵 억제력 확보 요구"),
                topic("topic-4", "남북 관계 및 선제적 조치"),
            ],
            "tasks": [],
        }

        groups = build_meeting_topic_groups(brief)

        nuclear = next(group for group in groups if group["key"] == "north-korea-nuclear")
        self.assertEqual(nuclear["title"], "북핵 위협·억제 대응")
        self.assertEqual(nuclear["topic_ids"], ["topic-1", "topic-2", "topic-3"])
        self.assertEqual(nuclear["topic_count"], 3)
        self.assertEqual(len(groups), 2)
        self.assertEqual(len(brief["topics"]), 4)

    def test_keeps_opposing_stances_as_separate_children(self):
        brief = {
            "topics": [
                topic("for", "호르무즈 파병 필요성 제안"),
                topic("against", "한국의 이란 관련 파병 검토 반대 입장"),
            ],
            "tasks": [],
        }

        groups = build_meeting_topic_groups(brief)

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["title"], "중동 정세·파병")
        self.assertEqual(groups[0]["topic_ids"], ["for", "against"])

    def test_title_fallback_merges_only_the_same_extracted_target(self):
        brief = {
            "topics": [
                topic("one", "공공데이터 공개 관련 문제점"),
                topic("two", "공공데이터 공개 개선 방안"),
                topic("three", "별도 신규 정책 검토"),
            ],
            "tasks": [],
        }

        groups = build_meeting_topic_groups(brief)

        data_group = next(group for group in groups if group["title"] == "공공데이터 공개")
        self.assertEqual(data_group["topic_ids"], ["one", "two"])
        self.assertEqual(len(groups), 2)

    def test_dynamically_groups_unknown_targets_only_with_strong_shared_anchors(self):
        brief = {
            "topics": [
                topic("one", "공공 와이파이 음영지역 해소"),
                topic("two", "공공 와이파이 이용자 인증 개선"),
                topic("three", "반려동물 등록칩 교체 주기"),
            ],
            "tasks": [],
        }

        groups = build_meeting_topic_groups(brief)

        platform = next(
            group for group in groups
            if group["assignment_method"] == "DYNAMIC_SEMANTIC"
        )
        self.assertEqual(platform["topic_ids"], ["one", "two"])
        self.assertEqual(platform["topic_count"], 2)
        self.assertEqual(
            next(group for group in groups if "three" in group["topic_ids"])[
                "assignment_method"
            ],
            "TITLE_FALLBACK",
        )

    def test_does_not_force_weakly_related_unknown_topics_into_one_group(self):
        brief = {
            "topics": [
                topic("one", "공소장 직제 입법예고 절차"),
                topic("two", "공유재산 임대료 산정 기준"),
                topic("three", "방송사 재허가 심사 기준"),
            ],
            "tasks": [],
        }

        groups = build_meeting_topic_groups(brief)

        self.assertEqual(len(groups), 3)
        self.assertTrue(all(group["topic_count"] == 1 for group in groups))

    def test_does_not_treat_evaluation_or_legislation_words_as_targets(self):
        brief = {
            "topics": [
                topic("one", "청년도약계좌 전환 정책의 신뢰성 문제"),
                topic("two", "ISA 세제 전환 정책의 신뢰성 문제"),
                topic("three", "청탁 판단의 부당성 검토"),
                topic("four", "기소유예 처분의 부당성 검토"),
                topic("five", "방송법 개정안 처리"),
                topic("six", "공유재산법 개정안 처리"),
                topic("seven", "2026년 반려동물 등록칩 교체"),
                topic("eight", "2026년 해양레저 면허 갱신"),
            ],
            "tasks": [],
        }

        groups = build_meeting_topic_groups(brief)

        self.assertFalse(any(
            group["assignment_method"] == "DYNAMIC_SEMANTIC"
            for group in groups
        ))

    def test_every_detail_topic_is_assigned_once_and_evidence_is_unioned(self):
        brief = {
            "topics": [
                topic("one", "경찰 수사관행 개선", evidence_id="evidence-1"),
                topic("two", "경찰 수사 인력 확충", evidence_id="evidence-2"),
                topic("three", "주택 공급 확대", evidence_id="evidence-3"),
            ],
            "tasks": [
                {"id": "task-1", "topic_id": "one"},
                {"id": "task-2", "topic_id": "two"},
            ],
        }

        groups = build_meeting_topic_groups(brief)
        assigned = [topic_id for group in groups for topic_id in group["topic_ids"]]
        police = next(group for group in groups if group["key"] == "police-investigation")

        self.assertCountEqual(assigned, ["one", "two", "three"])
        self.assertEqual(len(assigned), len(set(assigned)))
        self.assertEqual(police["evidence_ids"], ["evidence-1", "evidence-2"])
        self.assertEqual(police["task_ids"], ["task-1", "task-2"])

    def test_groups_promoted_plenary_topics_by_policy_target(self):
        brief = {
            "topics": [
                topic("ev-1", "국산 전기차 생태계 보존과 지원 정책 전환"),
                topic("ev-2", "전기차 전략산업 확인 요청"),
                topic("ship-1", "조선업 전략적 위치와 정부의 대응"),
                topic("ship-2", "미국 파견 인력 비자 문제 및 조선소 배치 연계 논의"),
                topic("ship-3", "한국형 화물창 선박 발주 계획"),
                topic("ai-1", "AI 산업 대전환과 경제 안보 인프라 구축"),
                topic("ai-2", "AI 규제 유예 논의"),
                topic("ai-3", "GTC 코리아 개최를 통한 글로벌 AI 투자 유치"),
            ],
            "tasks": [],
        }

        groups = build_meeting_topic_groups(brief)

        self.assertEqual(len(groups), 3)
        self.assertEqual(
            next(group for group in groups if group["key"] == "automotive-ev")[
                "topic_count"
            ],
            2,
        )
        self.assertEqual(
            next(
                group for group in groups if group["key"] == "shipbuilding-maritime"
            )["topic_count"],
            3,
        )
        self.assertEqual(
            next(
                group for group in groups if group["key"] == "ai-digital-infrastructure"
            )["topic_count"],
            3,
        )

    def test_repairs_truncated_shipbuilding_terms_in_read_model(self):
        brief = {
            "headline": "로 소송 및 회유 전략",
            "summary": "한국형 하물창과 마스카 사안을 논의했다.",
            "topics": [
                {
                    **topic("royalty", "로 자금 활용 및 내국인 인력 충원"),
                    "summary": "외국 기업에 지급된 로가 내국인 인건비로 전환 가능하다.",
                },
                topic("lawsuit", "로 소송 및 회유 전략 대응"),
            ],
            "tasks": [
                {
                    "id": "task-1",
                    "topic_id": "royalty",
                    "title": "로 자금 내국인 인건비 전환 방안 검토",
                }
            ],
        }

        attached = attach_meeting_topic_groups(brief)

        self.assertEqual(attached["headline"], "로열티 관련 소송 및 회유 전략")
        self.assertIn("한국형 화물창", attached["summary"])
        self.assertIn("마스가(MASGA)", attached["summary"])
        self.assertEqual(
            attached["topics"][0]["title"],
            "로열티 자금 활용 및 내국인 인력 충원",
        )
        self.assertIn("지급된 로열티가", attached["topics"][0]["summary"])
        self.assertEqual(
            attached["topic_groups"][0]["title"], "조선업·해양산업"
        )
        self.assertEqual(brief["headline"], "로 소송 및 회유 전략")

    def test_attach_adds_versioned_read_model_without_mutating_source(self):
        brief = {"topics": [topic("one", "주택 공급 확대")], "tasks": []}

        attached = attach_meeting_topic_groups(brief)

        self.assertNotIn("topic_groups", brief)
        self.assertEqual(attached["topic_grouping"]["version"], GROUPING_VERSION)
        self.assertEqual(attached["topic_grouping"]["method"], GROUPING_METHOD)
        self.assertEqual(attached["topic_grouping"]["group_count"], 1)
        self.assertEqual(attached["topic_grouping"]["detailed_topic_count"], 1)
        self.assertEqual(attached["topic_grouping"]["ontology_topic_count"], 1)
        self.assertEqual(attached["topic_grouping"]["ontology_coverage"], 1.0)
        self.assertEqual(attached["topic_grouping"]["integrity_status"], "PASS")
        self.assertEqual(attached["topic_grouping"]["assigned_topic_count"], 1)
        self.assertEqual(attached["topic_grouping"]["missing_topic_count"], 0)
        self.assertEqual(attached["topic_grouping"]["duplicate_topic_count"], 0)
        self.assertEqual(attached["topic_grouping"]["missing_live_topic_count"], 0)
        self.assertEqual(attached["topic_grouping"]["unlinked_task_count"], 0)
        self.assertEqual(attached["topic_grouping"]["quality_status"], "PASS")

    def test_flags_low_ontology_coverage_for_review(self):
        brief = {
            "topics": [
                topic("one", "반려동물 등록칩 교체 주기"),
                topic("two", "도시양봉 허가 기준"),
                topic("three", "공공 와이파이 음영지역 해소"),
                topic("four", "해양레저 면허 갱신"),
                topic("five", "게임물 등급 분류 절차"),
            ],
            "tasks": [],
        }

        grouping = attach_meeting_topic_groups(brief)["topic_grouping"]

        self.assertEqual(grouping["quality_status"], "REVIEW_REQUIRED")
        self.assertEqual(grouping["ontology_topic_count"], 0)
        self.assertEqual(grouping["unclassified_topic_count"], 5)
        self.assertIn("ONTOLOGY_COVERAGE_LOW", grouping["review_reasons"])

    def test_hearing_common_words_do_not_swallow_policy_targets(self):
        brief = {
            "topics": [
                topic("appointment", "법무부장관 후보자의 직무 적합성 검증"),
                topic("pharma", "식약처 임상시험 자료와 후보자 해명 검증"),
                topic("disability", "후보자 가족의 발달장애인 서비스기관 선정"),
                topic("funds", "후보자 후원금과 정치자금 규정 검토"),
                topic("evidence", "후보자 관련 녹취록과 불기소장 검토"),
                topic("procedure", "인사청문회 자료 제출 및 증인 출석 요구"),
            ],
            "tasks": [],
        }

        groups = build_meeting_topic_groups(brief)
        by_topic = {
            topic_id: group["key"]
            for group in groups
            for topic_id in group["topic_ids"]
        }

        self.assertEqual("public-appointments", by_topic["appointment"])
        self.assertEqual("medical-pharma-regulation", by_topic["pharma"])
        self.assertEqual("disability-care-services", by_topic["disability"])
        self.assertEqual("public-integrity-funds", by_topic["funds"])
        self.assertEqual("criminal-case-procedure", by_topic["evidence"])
        self.assertEqual("assembly-procedure", by_topic["procedure"])

    def test_historical_targets_are_classified_without_forcing_noise(self):
        brief = {
            "topics": [
                topic("dam", "지천댐 건설과 주민 의견 수렴"),
                topic("investment", "대미투자 일정 차질"),
                topic("hospital", "서울대 의대병원 이전 일정"),
                topic("agency", "공공기관 통합 시 시너지 효과"),
                topic("absence", "국무위원들의 국회 불출석"),
                topic("juvenile", "소년보호처분 제도 개선"),
                topic("noise", "진나라 청구 연대"),
            ],
            "tasks": [],
        }

        groups = build_meeting_topic_groups(brief)
        by_topic = {
            topic_id: group
            for group in groups
            for topic_id in group["topic_ids"]
        }

        self.assertEqual("water-resources-climate", by_topic["dam"]["key"])
        self.assertEqual("trade-climate-industry", by_topic["investment"]["key"])
        self.assertEqual("healthcare-medical-system", by_topic["hospital"]["key"])
        self.assertEqual("government-operations", by_topic["agency"]["key"])
        self.assertEqual("assembly-procedure", by_topic["absence"]["key"])
        self.assertEqual("children-digital-safety", by_topic["juvenile"]["key"])
        self.assertEqual("TITLE_FALLBACK", by_topic["noise"]["assignment_method"])

    def test_groups_plenary_details_under_shared_policy_targets(self):
        brief = {
            "topics": [
                topic("medical-1", "공공병원 확충 정책"),
                topic("medical-2", "국립의전원 교육 체제 설계 방향"),
                topic("media-1", "정부 광고 개혁 및 집행 기준"),
                topic("media-2", "TBS 정상화 지연"),
                topic("labor-1", "플랫폼 노동자의 폭염 노동 보호 공백"),
                topic("labor-2", "일하는 사람 기본법 발의"),
                topic("water-1", "용수 공급 계획 변경 및 확대"),
                topic("water-2", "가뭄 대응 물 관리 원칙"),
                topic("education-1", "교권 개선 논의 현황"),
                topic("education-2", "지방인재장학금의 수도권 공립대생 배제"),
            ],
            "tasks": [],
        }

        groups = build_meeting_topic_groups(brief)
        by_key = {group["key"]: group for group in groups}

        self.assertEqual(2, by_key["healthcare-medical-system"]["topic_count"])
        self.assertEqual(2, by_key["media-public-communication"]["topic_count"])
        self.assertEqual(2, by_key["youth-employment"]["topic_count"])
        self.assertEqual(2, by_key["water-resources-climate"]["topic_count"])
        self.assertEqual(2, by_key["education"]["topic_count"])
        self.assertEqual("assembly-meeting-topic-grouping/1.7", GROUPING_VERSION)

    def test_classifies_operational_policy_gaps_without_procedure_swallowing_subject(self):
        brief = {
            "topics": [
                topic("witness", "증인 협의 일정 연기 문제 논의"),
                topic("military", "군 생활 개선 요청"),
                topic("sales", "방문 판매 등에 관한 법률 일부 개정"),
                topic("fraud", "전자금융거래법 및 전기통신금융사기방지법 개정"),
                topic("victim", "미성년 성폭력 피해자 증거능력 조문 개정"),
                topic("hearing", "아동 청소년 성보호법 개정안 상정 절차 진행"),
                topic("golf", "이재명 대통령 일행의 태릉CC 사용 정황 분석"),
                topic("ethics", "후보자 배우자 주식 보유 현황 및 재원 출처"),
                topic("rights", "수사에서의 인권보장과 효율성 균형"),
                topic("eligibility", "후보자의 적격성과 사과 필요성"),
                topic("vote", "행정안전위원회 제안 법안 12건 의결"),
            ],
            "tasks": [],
        }

        groups = build_meeting_topic_groups(brief)
        by_topic = {
            topic_id: group["key"]
            for group in groups
            for topic_id in group["topic_ids"]
        }

        self.assertEqual("assembly-procedure", by_topic["witness"])
        self.assertEqual("military-personnel-reform", by_topic["military"])
        self.assertEqual("consumer-financial-protection", by_topic["sales"])
        self.assertEqual("consumer-financial-protection", by_topic["fraud"])
        self.assertEqual("sexual-violence-victim-protection", by_topic["victim"])
        self.assertEqual("sexual-violence-victim-protection", by_topic["hearing"])
        self.assertEqual("presidential-accountability", by_topic["golf"])
        self.assertEqual("public-integrity-funds", by_topic["ethics"])
        self.assertEqual("criminal-case-procedure", by_topic["rights"])
        self.assertEqual("public-appointments", by_topic["eligibility"])
        self.assertEqual("assembly-procedure", by_topic["vote"])

    def test_separates_report_artifacts_from_policy_coverage_and_flags_review(self):
        brief = {
            "topics": [
                topic("policy", "주택 공급 확대"),
                topic("artifact-1", "사실 관계 확인의 필요성"),
                topic("artifact-2", "불명확한 반복 발언으로 인한 의사소통 장애"),
            ],
            "tasks": [],
        }

        attached = attach_meeting_topic_groups(brief)
        grouping = attached["topic_grouping"]
        artifact = next(
            group for group in attached["topic_groups"]
            if group["assignment_method"] == "REPORT_ARTIFACT"
        )

        self.assertEqual(3, grouping["detailed_topic_count"])
        self.assertEqual(1, grouping["policy_topic_count"])
        self.assertEqual(2, grouping["report_artifact_topic_count"])
        self.assertEqual(0, grouping["unclassified_topic_count"])
        self.assertEqual(1.0, grouping["ontology_coverage"])
        self.assertEqual(["artifact-1", "artifact-2"], artifact["topic_ids"])
        self.assertIn("REPORT_ARTIFACT_SOURCE_UNVERIFIED", grouping["review_reasons"])

    def test_officially_sourced_report_artifact_is_counted_without_review_warning(self):
        artifact = topic("intro", "질의자 교체")
        artifact["official_evidence_ids"] = ["official-utterance-1"]
        grouped = attach_meeting_topic_groups({"topics": [artifact], "tasks": []})
        audit = grouped["topic_grouping"]
        self.assertEqual(audit["report_artifact_topic_count"], 1)
        self.assertEqual(audit["policy_topic_count"], 0)
        self.assertEqual(audit["quality_status"], "PASS")

    def test_law_format_words_do_not_merge_unrelated_unknown_targets(self):
        brief = {
            "topics": [
                topic("one", "도시양봉 허가 일부개정법률안"),
                topic("two", "반려동물 등록칩 일부개정법률안"),
                topic("three", "해양레저 면허 일부개정법률안"),
            ],
            "tasks": [],
        }

        groups = build_meeting_topic_groups(brief)

        self.assertEqual(3, len(groups))
        self.assertFalse(any(
            group["assignment_method"] == "DYNAMIC_SEMANTIC"
            for group in groups
        ))

    def test_exposes_observed_keyword_usage_for_ontology_audit(self):
        result = build_meeting_topic_ontology([{
            "topics": [
                topic("one", "증인 협의 일정 연기"),
                topic("two", "기관증인 출석 일정 확정"),
            ],
            "tasks": [],
        }])
        procedure = next(
            group for group in result["groups"]
            if group["key"] == "assembly-procedure"
        )

        self.assertEqual(2, procedure["topic_count"])
        self.assertEqual(
            {"증인협의": 1, "증인출석": 1},
            {
                item["keyword"]: item["topic_count"]
                for item in procedure["matched_keywords"]
            },
        )


if __name__ == "__main__":
    unittest.main()
