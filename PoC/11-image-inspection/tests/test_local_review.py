import copy
from app.local_review import revised_run


def test_local_revision_preserves_original_decisions_reviews_and_cost_provenance():
    source=dict(id='source',results=[dict(id='a',rule_id='D-04-e',status='REVIEW',review_basis='OBSERVED_ANOMALY',reason='동의 근거 없음'),dict(id='b',rule_id='D-02-l',status='FAIL',reason='별도 오탈자 근거')],
                calls=[dict(event_id='e',status='FAILED',usage_unknown=True)],reviews=[dict(finding_id='b',status='FAIL')],observation={'objects':[]},options={'analysis_model':'gpt-5.4-mini'},analysis=[])
    before=copy.deepcopy(source);r=revised_run(source)
    assert source==before and r['id']!=source['id'] and r['calls']==[]
    assert r['results'][0]['review_basis']=='DOCUMENT_CHECK' and r['results'][0]['status']=='REVIEW'
    assert r['results'][1]==source['results'][1] and r['reviews']==source['reviews']
    assert r['local_revision']['inherited_failed_calls']==source['calls']
    assert r['analysis_reused_from']['run_id']=='source' and r['observation_reused_from']['run_id']=='source'
