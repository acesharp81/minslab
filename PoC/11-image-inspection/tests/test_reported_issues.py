import copy
import pytest
from scripts.attach_reported_issues import revise
from app.rules import PACK


def fixture():
    row=dict(id='finding',rule_id='D-02-l',evidence_ids=['text'],status='PASS',reason='모델 정상',rects=[],model='mini')
    run=dict(id='source',rule_pack=copy.deepcopy(PACK),observation={'objects':[dict(id='text',label='문구',cell_ids=['R02C03'])]},results=[row],reviews=[],reference_snapshot=[])
    manifest={'targets':[dict(object_id='text',rule_ids=['D-02-l'],kind='text',parts=[dict(part='획',reason='사용자가 끊김을 지적함',rect=[.1,.2,.3,.4])])]}
    return run,manifest


def test_feedback_does_not_claim_model_detection_or_mutate_previous_run():
    source,manifest=fixture();out=revise(source,manifest);row=out['results'][0]
    assert source['results'][0]['status']=='PASS' and out['id']!=source['id']
    assert row['status']=='REVIEW' and row['model']=='system/reported-issue'
    assert row['reported_issues']['prior_model_status']=='PASS'
    assert row['rects']==[[.1,.2,.3,.4]] and row['visual_issue']
    assert out['calls']==[]


def test_human_review_and_existing_fail_are_not_overwritten():
    source,manifest=fixture();source['reviews']=[{'finding_id':'finding'}]
    assert revise(source,manifest)['results'][0]['status']=='PASS'
    source['reviews']=[];source['results'][0]['status']='FAIL'
    assert revise(source,manifest)['results'][0]['status']=='FAIL'
    manifest['targets'][0]['parts'][0]['rect']=[.5,.3,.1,.2]
    with pytest.raises(ValueError):revise(source,manifest)
