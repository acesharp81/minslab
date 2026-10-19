from copy import deepcopy

from app.services.live_topic_recovery import recover_live_topic_coverage
from app.services.meeting_brief import link_tasks_to_topics, promote_unassigned_live_topics
from app.services.meeting_topic_groups import _ontology_match, attach_meeting_topic_groups, build_meeting_topic_ontology


def sample():
    return {
        "topics": [{"id": "topic-24", "title": "법령해석 절차", "summary": "절차를 점검했다.", "evidence_ids": ["u-1"], "live_topic_cluster_ids": ["c-1"]}],
        "tasks": [],
        "live_topic_lineage": {"clusters": [
            {"id": "c-1", "title": "법령해석 절차", "utterance_ids": ["u-1"], "utterance_count": 1, "mapping_status": "DIRECT_EVIDENCE", "final_topic_ids": ["topic-24"]},
            {"id": "c-2", "title": "군판사 인력 부족", "utterance_ids": ["u-2", "u-3"], "utterance_count": 2, "tasks": ["군판사 충원 현황 확인 요청"], "mapping_status": "UNMAPPED", "final_topic_ids": []},
            {"id": "c-3", "title": "군 내 불법도박 대책", "utterance_ids": ["u-4"], "utterance_count": 1, "mapping_status": "AMBIGUOUS", "final_topic_ids": []},
            {"id": "c-4", "title": "군 관계자 감사 표명", "utterance_ids": ["u-5"], "utterance_count": 1, "mapping_status": "UNMAPPED", "final_topic_ids": []},
            {"id": "c-5", "title": "군사기밀 암구호 유출", "utterance_ids": [], "mapping_status": "UNMAPPED", "final_topic_ids": []},
            {"id": "c-6", "title": "기소 관련 논의", "utterance_ids": ["u-6"], "mapping_status": "UNMAPPED", "final_topic_ids": []},
        ]},
        "live_topic_assignment": {"semantic_mapping_status": "COMPLETED", "semantic_unresolved_cluster_ids": ["c-2", "c-3"]},
    }


def test_recovery_preserves_provenance_and_model_results_without_mutating_source():
    raw=sample();before=deepcopy(raw)
    out=recover_live_topic_coverage(raw,_ontology_match)
    assert raw==before
    extra=out["topics"][-1]
    assert extra["evidence_ids"]==["u-2","u-3"]
    assert extra["official_evidence_ids"]==[]
    assert extra["authority_status"]=="PROVISIONAL"
    assert extra["classification_evidence"]["target_key"]=="military-justice"
    assert out["topics"][0]==raw["topics"][0]
    assert out["live_topic_assignment"]==raw["live_topic_assignment"]
    assert out["tasks"]==[]
    assert out["live_topic_lineage"]["mapped_cluster_count"]==2
    assert out["live_topic_lineage"]["ambiguous_cluster_count"]==1
    assert out["live_topic_lineage"]["unmapped_cluster_count"]==3
    assert out["live_topic_coverage"]["additional_llm_calls"]==0
    assert recover_live_topic_coverage(out,_ontology_match)==out


def test_recovery_is_explicit_and_never_makes_cross_topic_or_procedural_matches():
    raw=sample()
    assert len(attach_meeting_topic_groups(raw)["topics"])==1
    out=attach_meeting_topic_groups(raw,recover_live_topics=True)
    assert len(out["topics"])==2
    assert out["topic_grouping"]["integrity_status"]=="PASS"
    assert {c["id"] for c in out["live_topic_lineage"]["clusters"] if c["mapping_status"]=="SUPPLEMENTARY_EVIDENCE"}=={"c-2"}
    assert out["live_topic_lineage"]["clusters"][2]==raw["live_topic_lineage"]["clusters"][2]


def test_duplicate_ids_split_references_by_evidence_and_keep_uncertain_ref_unlinked():
    raw={"topics":[
        {"id":"topic-24","title":"군사법원 업무보고","evidence_ids":["u-1"]},
        {"id":"topic-24","title":"내란전담수사본부 정보사 조사","evidence_ids":["u-2"]},
    ],"tasks":[{"id":"task-1","title":"재수사 요청","evidence_ids":["u-2"]}],"live_topic_lineage":{"clusters":[
        {"id":"a","title":"업무보고","utterance_ids":["u-1"],"mapping_status":"SYNTHESIS_ASSIGNED","final_topic_ids":["topic-24"]},
        {"id":"b","title":"수사 결과","utterance_ids":["u-2"],"mapping_status":"DIRECT_EVIDENCE","final_topic_ids":["topic-24"]},
        {"id":"c","title":"군공항 소음 피해 보상","utterance_ids":["u-3"],"mapping_status":"DIRECT_EVIDENCE","final_topic_ids":["topic-24"]},
    ]}}
    before=deepcopy(raw);out=link_tasks_to_topics(raw)
    assert raw==before
    ids=[t["id"] for t in out["topics"]];assert len(set(ids))==2
    a,b,c=out["live_topic_lineage"]["clusters"]
    assert a["final_topic_ids"]==[ids[0]]
    assert b["final_topic_ids"]==[ids[1]]
    assert c["final_topic_ids"]==[] and c["mapping_status"]=="MULTIPLE_FINAL_TOPICS"
    assert c["source_final_topic_ids"]==["topic-24"]
    assert out["tasks"][0]["topic_id"]==ids[1]
    assert link_tasks_to_topics(out)==out
    assert attach_meeting_topic_groups(out)["topic_grouping"]["integrity_status"]=="PASS"


def test_promotion_does_not_reuse_an_id_when_invalid_topics_left_numeric_gaps():
    raw={"topics":[{"id":"topic-1","title":"주택 공급"},{"id":"topic-3","title":"통신망 품질"}]}
    out=promote_unassigned_live_topics(raw,[{"id":"live-1","title":"군판사 인력 부족","utterance_ids":["u-1"]}],{"u-1"})
    ids=[t["id"] for t in out["topics"]]
    assert len(ids)==3 and len(set(ids))==3


def test_military_targets_do_not_absorb_civilian_defense_counsel_or_unrelated_topics():
    cases={
        "군판사 진급 차별":"military-justice",
        "군사법원 독립성":"military-justice",
        "군사기밀 암구호 유출":"military-security",
        "군 내 불법도박 문제":"military-gambling",
        "장성 사격장 이전":"military-facilities",
        "성폭력 피해 신고 절차":"sexual-violence-victim-protection",
        "전시작전권 전환":"alliance-defense",
        "보조생식술 접근 제한":"healthcare-medical-system",
        "따릉이 유출 사고":"privacy-communications",
        "생활폐기물 반입":"environment-waste",
    }
    for title,key in cases.items():assert _ontology_match({"title":title})["key"]==key
    assert _ontology_match({"title":"국선변호인 접촉 횟수"}) is None
    assert _ontology_match({"title":"험지 대응 장비 투자"}) is None
    ontology=build_meeting_topic_ontology();keys=[key for d in ontology["domains"] for key in d["group_keys"]]
    assert len(keys)==len(set(keys))==70
