import copy
import importlib.util
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('diagnostic_revision',Path(__file__).resolve().parents[1]/'scripts/attach_diagnostic_evidence.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def fixture():
    row=dict(id='old',rule_id='TEXT-rule',evidence_ids=['sign'],status='PASS',reason='원래 결과')
    source=dict(id='source',analysis_observation={'objects':[dict(id='sign',label='표지',cell_ids=['R01C01'])]},
        rule_pack={'steps':[dict(rule_id='TEXT-rule',parent_id='TEXT',version='1')]},results=[row],reviews=[],options={},calls=[])
    d=dict(object_id='sign',kind='glyph',event_id='call1',model='reader',rect=[.1,.1,.2,.2],rule_ids=['TEXT-rule'],word_text='가나',
        characters=[dict(literal_text='가',glyph_evidence='첫 글자'),dict(literal_text='너',glyph_evidence='모음 획')])
    return source,dict(diagnostics=[d],calls=[dict(event_id='call1')],image_sha256='hash')


def test_revision_preserves_original_and_only_reviews_disagreement():
    source,manifest=fixture();before=copy.deepcopy(source);run=m.revise(source,manifest)
    assert source==before
    assert run['results'][0]['status']=='REVIEW'
    assert run['results'][0]['model']=='system/independent-evidence'
    assert run['results'][0]['supersedes_findings']==['old']
    assert run['analysis_observation']['objects'][0]['text_disagreement']
    assert run['calls']==manifest['calls']


def test_reviewed_finding_and_confirmed_failure_are_not_overwritten():
    for reviewed in (True,False):
        source,manifest=fixture()
        if reviewed:source['reviews']=[dict(finding_id='old',status='PASS')]
        else:source['results'][0]['status']='FAIL'
        run=m.revise(source,manifest)
        assert run['results'][0]['id']=='old'
        assert run['results'][0]['status']==source['results'][0]['status']
        assert run['results'][0]['supplemental_evidence']


def test_unbound_evidence_is_rejected_and_agreement_does_not_create_pass():
    source,manifest=fixture();manifest['diagnostics'][0]['event_id']='unknown'
    with pytest.raises(ValueError):m.revise(source,manifest)
    source,manifest=fixture();manifest['diagnostics'][0]['word_text']='가너';source['results'][0]['status']='REVIEW'
    run=m.revise(source,manifest)
    assert run['results'][0]['status']=='REVIEW'
    assert run['evidence_revision']['changed_reviews']==0
