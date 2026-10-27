from app.services.meeting_progress import stage_progress
from app.services.structure_review import annotate_review_state


def test_review_second_pass_is_not_counted_as_complete():
    brief = {'topic_structure': {'uncertain': [{'atom_id':'a', 'uncertainty_reason':'pending'}],
             'document_requests': [], 'rejected': []}, 'structure_review_items': []}
    annotate_review_state(brief, {'a','b'})
    review = brief['topic_structure']['automatic_review']
    assert review['total_atom_count'] == 2
    assert review['completed_atom_count'] == 1


def test_stage_counts_and_future_steps_do_not_reuse_analysis_counts():
    structure = {'topics':[{},{}], 'topic_structure':{'automatic_review':{
        'status':'COMPLETED','completed_atom_count':44,'total_atom_count':44}},
        'narrative_coverage':{'issue_count':62,'summarized_issue_count':59,'status':'PENDING'}}
    stages = {s['key']:s for s in stage_progress({'phase':'NARRATIVE','status':'DEFERRED',
        'integration_batches_total':8,'integration_batches_done':8}, structure, {'status':'COMPLETED'}, [])}
    assert stages['INTEGRATION']['completed'] == 8
    assert stages['REVIEWING']['completed'] == 44
    assert stages['NARRATIVE'] == {'key':'NARRATIVE','status':'WAITING','completed':59,'total':62,'unit':'쟁점'}
    assert stages['FINALIZING']['status'] == 'PENDING'


def test_unknown_totals_are_absent_and_completion_is_explicit():
    stages=stage_progress({'phase':'STRUCTURING','status':'PROCESSING'})
    assert 'total' not in stages[2]
    assert stages[2]['status']=='PENDING'
    assert all(s['status']=='COMPLETED' for s in stage_progress({'phase':'COMPLETED','status':'COMPLETED'}))
