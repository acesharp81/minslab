from app import anatomy
from app.observations import clean_inventory


def hand(state='NATURAL',evidence=''):
    return dict(side='RIGHT',pose='THUMBS_UP',visibility='PARTIAL',visible_structure=state,occlusion_reason='네 손가락은 접힘',anomaly_evidence=evidence)


def test_natural_partial_hand_keeps_existing_verdict_and_observation_scope():
    run={'observation':{'objects':[{'id':'h','hands':[hand()]}]}}
    for status in ['PASS','REVIEW','FAIL','ERROR']:
        row=dict(rule_id='D-02-e',status=status,evidence_ids=['h'])
        anatomy.protect(run,[row]);assert row['status']==status and row['hand_scope']['hands'][0]['pose']=='THUMBS_UP'


def test_concrete_anomaly_cannot_disappear_as_a_natural_pose():
    run={'observation':{'objects':[{'id':'h','hands':[hand('ANOMALOUS','검지가 손목에서 직접 갈라짐')]}]}}
    row=dict(rule_id='D-02-g',status='PASS',evidence_ids=['h'])
    anatomy.protect(run,[row]);assert row['status']=='REVIEW' and row['review_basis']=='OBSERVED_ANOMALY'
    other=dict(rule_id='D-02-l',status='PASS',evidence_ids=['h'])
    anatomy.protect(run,[other]);assert other['status']=='PASS'


def test_old_inventory_remains_compatible_with_optional_hand_details():
    data=dict(summary='손 자세',context='안내',limitations='일부 가림',objects=[dict(id='h',label='손',description='엄지',text='',visual_concerns='',quality='CLEAR',cell_ids=['R01C01'])])
    assert clean_inventory(data)['objects'][0]['hands']==[]
    data['objects'][0]['hands']=[hand()]
    assert clean_inventory(data)['objects'][0]['hands'][0]['visibility']=='PARTIAL'
