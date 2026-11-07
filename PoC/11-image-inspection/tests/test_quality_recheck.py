import copy
import io
import json
from types import SimpleNamespace
from PIL import Image
from app import quality_recheck as q, verification as v, text_routing, artifact_screen
from app.config import Settings
from app.rules import PACK


def obj(oid='hand',label='남성 오른손 손짓',text=''):
    return dict(id=oid,label=label,text=text,description='보이는 영역',quality='CLEAR',cell_ids=['R06C03'],visual_concerns='',text_legibility='CLEAR' if text else 'NOT_TEXT',hands=[])


def saved():
    return dict(observation={'objects':[obj(),obj('sign','체험 표지판','한복 체험')]},selected=['D-02-c','D-02-l'],
                options={'vision_model':'gpt-5.4','text_sensitivity':'strict','quality_recheck':True,'recheck_object_ids':['hand','sign']},
                rule_pack=PACK,reference_snapshot=[],calls=[],observation_reused_from={'run_id':'old'},
                verification={'results':[],'deferred':[]})


def response(oid):
    return dict(object_id=oid,coverage='COMPLETE',text='',text_legibility='NOT_TEXT',legibility_evidence='',
                transcription_inferred=False,quality='CLEAR',description='보이는 구조',cell_ids=['R04C04'],comparisons=[],hands=[],glyph_checks=[])


def run_mock(tmp_path,run,reply):
    calls=[]
    def call(model,prompt,images,workload):
        payload=json.loads(prompt);calls.append(payload)
        assert '한복 체험' not in prompt  # No prior reading supplied.
        assert all('quality_protocol' in t for t in payload['tasks'])
        assert len(payload['tasks'])<=3 and len(images)<=8
        return {'results':[reply(t) for t in payload['tasks']]},{'event_id':str(len(calls)),'workload':workload,'model':model}
    engine=SimpleNamespace(s=Settings({'DATA_DIR':str(tmp_path)}),provider=SimpleNamespace(call=call),checkpoint=lambda *a:None)
    data=io.BytesIO();Image.new('RGB',(1200,900),'white').save(data,format='PNG')
    v.run_verification(engine,{'id':'job','metadata':{}},run,data.getvalue())
    return calls


def test_plan_keeps_clear_and_unassessed_hands_selectable_without_making_findings():
    run=saved();before=copy.deepcopy(run);plan=q.plan(run)
    assert {e['object_id'] for e in plan['entries']}=={'hand','sign'}
    assert all(e['state']=='NOT_RECHECKED' for e in plan['entries'])
    assert plan['recommended_ids']==['hand','sign'] and run==before
    assert all('status' not in e for e in plan['entries'])


def test_partial_observation_first_and_clear_prior_can_be_overruled_by_new_read():
    run=saved();run['verification']['results']=[{**response('sign'),'status':'COMPLETED','coverage':'PARTIAL'},
        {**response('hand'),'status':'COMPLETED','hands':[{'visible_structure':'NATURAL'}]}]
    entries=q.plan(run)['entries']
    assert entries[0]['object_id']=='sign' and entries[0]['state']=='PARTIAL'
    assert entries[1]['state']=='PREVIOUSLY_CHECKED' and entries[1]['selectable']


def test_missing_position_and_disabled_budget_do_not_create_requests():
    run=saved();run['observation']['objects'][0]['cell_ids']=[]
    plan=q.plan(run,max_objects=0,max_calls=0)
    assert not plan['recommended_ids'] and not plan['entries'][0]['selectable']


def test_fragment_match_is_not_a_disagreement_or_a_complete_normal_certification():
    run=saved();region=dict(id='r',rect=[.16,.42,.24,.49],text='체험',recognition_score=.99)
    run['observation']['objects']=[obj('sign','체험 안내','한복 체험')]
    run['pixel_text']={'detector_regions':[region]}
    row=text_routing.prepare(run)['regions'][0]
    assert row['state']=='FRAGMENT_MATCH' and row['action']=='RECHECK'
    assert q.measured_text_rect(run['observation']['objects'][0],run) is None
    raw=io.BytesIO();Image.new('RGB',(200,200),'white').save(raw,format='PNG')
    assert not artifact_screen.collect(raw.getvalue(),run)['candidates']
    region['text']='한북 체험'
    assert text_routing.prepare(run)['regions'][0]['state']=='DISAGREEMENT'


def test_uniquely_bound_full_line_uses_detector_rectangle_not_cell_center():
    run=saved();run['observation']['objects']=run['observation']['objects'][1:]
    rect=[.16,.42,.24,.49];run['pixel_text']={'detector_regions':[dict(id='r',rect=rect,text='한복체험')]}
    assert q.plan(run)['entries'][0]['measured_rect']==rect


def test_missing_structural_fields_cannot_count_as_complete_and_does_not_erase_prior(tmp_path):
    run=saved();old={**response('hand'),'coverage':'PARTIAL','status':'COMPLETED','description':'기존 유효 관찰'}
    run['verification']['results']=[old]
    calls=run_mock(tmp_path,run,lambda t:response(t['object_id']))
    assert len(calls)==1
    assert next(r for r in run['verification']['results'] if r['object_id']=='hand')==old
    assert run['verification']['attempt_results'][0]['coverage']=='PARTIAL'
    assert all(r['coverage']=='PARTIAL' for r in run['verification']['results'])
    assert any('관찰 누락' in r['reason'] for r in run['verification']['deferred'])


def test_concrete_hand_evidence_from_crop_reaches_analysis_and_old_evidence_is_unchanged(tmp_path):
    run=saved();run['options']['recheck_object_ids']=['hand'];before=copy.deepcopy(run['observation'])
    def reply(task):
        return {**response(task['object_id']),'hands':[dict(side='RIGHT',pose='V_SIGN',visibility='PARTIAL',
            visible_structure='ANOMALOUS',occlusion_reason='접힌 손가락 일부 가림',anomaly_evidence='손바닥에서 한 손가락이 두 갈래로 연결되어 보임')]}
    run_mock(tmp_path,run,reply)
    assert run['verification']['results'][0]['coverage']=='COMPLETE'
    assert v.effective_observation(run)['objects'][0]['hands'][0]['visible_structure']=='ANOMALOUS'
    assert run['observation']==before


def test_focused_batches_use_at_most_two_calls_and_do_not_upgrade_model(tmp_path):
    run=saved();run['observation']['objects']=[obj(str(i)) for i in range(8)]
    run['options']['recheck_object_ids']=[str(i) for i in range(8)] # Engine rejects >6; verify the inner guard too.
    calls=run_mock(tmp_path,run,lambda t:response(t['object_id']))
    assert len(calls)==2 and len(run['calls'])==2
    assert {c['model'] for c in run['calls']}=={'gpt-5.4'}
    assert run['verification']['max_calls']==2
    assert sum('객체 한도' in d['reason'] for d in run['verification']['deferred'])==2


def test_partial_retry_preserves_localized_glyph_defect_without_erasing_old_text(tmp_path):
    from app.evidence_guards import protect_glyphs
    run=saved();run['options']['recheck_object_ids']=['sign']
    old={**response('sign'),'coverage':'COMPLETE','status':'COMPLETED','text':'한복 체험','crop_rect':[.1,.2,.4,.6]}
    run['verification']['results']=[old]
    def reply(task):
        return {**response('sign'),'coverage':'PARTIAL','text':'□ 체험','glyph_checks':[dict(literal='□',quality='DEFECT',origin='SOURCE',evidence='원본 안쪽 모음 획이 서로 융합됨',cell_ids=['R04C04'])]}
    run_mock(tmp_path,run,reply)
    assert run['verification']['results'][0]==old
    rows=protect_glyphs(run,[],['D-02-l'])
    assert rows and rows[0]['status']=='FAIL' and rows[0]['glyph_evidence']['event_id']=='1'


def test_partial_hand_anomaly_retains_original_text_and_is_not_suppressed(tmp_path):
    run=saved();run['options']['recheck_object_ids']=['hand']
    def reply(task):
        return {**response('hand'),'coverage':'PARTIAL','hands':[dict(side='RIGHT',pose='V_SIGN',visibility='PARTIAL',
                visible_structure='ANOMALOUS',occlusion_reason='손바닥 일부 가림',anomaly_evidence='보이는 손가락 뿌리에서 두 갈래로 분기') ]}
    run_mock(tmp_path,run,reply);effective=v.effective_observation(run)
    assert effective['objects'][0]['hands'][0]['visible_structure']=='ANOMALOUS'
    assert effective['objects'][0]['partial_hand_evidence']['coverage']=='PARTIAL'
    assert effective['objects'][0]['cell_ids']==run['observation']['objects'][0]['cell_ids']


def test_focused_text_pass_keeps_prior_reference_comparison_provenance(tmp_path):
    import hashlib
    run=saved();run['options']['recheck_object_ids']=['sign']
    action=next(s['objective'] for s in PACK['steps'] if s['rule_id']=='H-04-i')
    ref=dict(id='ref',kind='official-symbols',image_hash='hash')
    run['reference_snapshot']=[ref]
    old={**response('sign'),'status':'COMPLETED','crop_rect':[.1,.2,.4,.6],
         'reference_hashes':{'ref':'hash'},'rule_hashes':{'H-04-i':hashlib.sha256(action.encode()).hexdigest()},
         'event_id':'original-compare','comparisons':[dict(reference_id='ref',rule_ids=['H-04-i'],status='MISMATCH',quality='CLEAR',evidence='기존 문양 비교')]}
    run['verification']['results']=[old]
    def reply(task):
        return {**response('sign'),'coverage':'COMPLETE','text':'한복 체험','glyph_checks':[dict(literal='한복 체험',quality='CLEAR',origin='SOURCE',evidence='확인한 획',cell_ids=['R04C04'])]}
    run_mock(tmp_path,run,reply)
    assert run['verification']['reference_results'][0]==old
    assert v.direct_comparisons(run,'H-04-i',['sign'],['ref'])
