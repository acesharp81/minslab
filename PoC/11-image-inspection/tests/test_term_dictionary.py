import copy,json
import pytest
from app import term_dictionary as t,evidence_guards as g
from test_evidence_guards import run_for_name


def doc():
    return dict(schema=t.SCHEMA,version='test-v1',terms=[dict(id='agency',canonical='행정안전부',aliases=['행정안정부'],context=['책등'],sources=['https://example.org/agency'],rule_ids=['D-02-l'],valid_from='2026-01-01',valid_until='2026-12-31',severity='REVIEW')])


def test_only_approved_in_period_dictionary_is_applied_with_rule_scope():
    run=run_for_name();run['observation']['objects'][0]['label']='책등';run['created_at']='2026-11-04T00:00:00Z'
    run['reference_snapshot']=[dict(id='dict',status='DRAFT',kind='language',parent_ids=['D-02'],content=json.dumps(doc()))]
    assert len(t.active(run,g.TERMS))==2
    run['reference_snapshot'][0]['status']='APPROVED';terms=t.active(run,g.TERMS);assert len(terms)==3
    assert terms[-1]['rule_ids']==['D-02-l'] and terms[-1]['dictionary_reference_id']=='dict'
    run['inspection_date']='2027-01-01';assert len(t.active(run,g.TERMS))==2


def test_normalization_preserves_literal_fullwidth_and_decomposed_spans():
    assert t.find_literals('표기: ＫＯＲＥＡ ＡＩＲ', ['KOREA AIR'])==['ＫＯＲＥＡ ＡＩＲ']
    assert t.find_literals('가나', ['가'])==['가']


def test_invalid_dictionary_cannot_be_used_as_an_approved_criterion():
    for field,value in [('canonical',''),('sources',['http://unsafe.example']),('valid_until','2025-01-01')]:
        d=doc();d['terms'][0][field]=value
        with pytest.raises(ValueError):t.parse(json.dumps(d))


def test_historical_quote_keeps_a_diagnostic_review_instead_of_a_typo_fail():
    run=run_for_name();run['observation']['objects'][0].update(label='책등',description='잘못된 표현의 예를 담은 역사적 인용')
    row=g.protect(run,[],['D-02-l'])[0]
    assert row['status']=='REVIEW' and row['diagnostic_only'] and not row['visual_issue']
