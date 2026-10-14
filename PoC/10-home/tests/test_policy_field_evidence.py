from backend.policy_field_evidence import evidence_for, extract_evidence, OBJECTIVE, SHA256
from backend.policy_907_sources import PDF_URL
from backend.policy_profile import source_fields


def original():
    return dict(policy_id='POL_2025_0907',evidence_url=PDF_URL,base_date='2025-09-07',period_start='2026-01-01',period_end='2030-12-31',target_units=1350000,annual=[],region_allocations={})


def test_verified_original_citation_and_field_value():
    plan=original();citation=evidence_for(plan,'overview',None)
    assert citation['excerpt']==OBJECTIVE
    assert (citation['printed_page'],citation['pdf_page'])==(4,7)
    assert citation['document_sha256']==SHA256
    assert source_fields(plan)['overview']==OBJECTIVE
    goal=evidence_for(plan,'target_units',1350000)
    assert '135만호' in goal['excerpt']
    assert (goal['printed_page'],goal['pdf_page'])==(43,46)


def test_table_conversion_and_unknown_are_distinct_from_quotes():
    year=evidence_for(original(),'annual:서울특별시:2026',68000)
    assert year['excerpt_type']=='TABLE_VALUE'
    assert '68,000호' in year['excerpt']
    unknown=evidence_for(original(),'region:인천광역시',None)
    assert '분리 공표되지' in unknown['excerpt']
    assert '0호' not in unknown['excerpt']


def test_unknown_document_never_receives_a_fabricated_page():
    plan=dict(original(),evidence_url='https://example.org/new.pdf')
    result=evidence_for(plan,'overview','원천값')
    assert result['excerpt']=='원천값'
    assert 'pdf_page' not in result
    assert 'document_sha256' not in result


def test_collection_extracts_actual_pages_when_document_changes():
    evidence=extract_evidence(['표지','선호 입지에 내집 마련의 기회를 대폭 늘리고, 위축된 주택공급 여건을 개선하여 주택시장 안정 및 국민 주거안정 도모\n- 9 -','｢주택공급 확대방안｣을 통해 ’30년까지 총 135만호 규모의 신규주택 착공 추진\n134.9 26.9 33.5\n- 10 -'],'new-sha')
    assert evidence['sections']['overview']['printed_page']==9
    assert evidence['sections']['overview']['pdf_page']==2
    assert evidence['sha256']=='new-sha'
    current=evidence_for(dict(original(),field_evidence=evidence),'overview',None)
    assert current['printed_page']==9
