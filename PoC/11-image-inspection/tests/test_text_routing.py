import copy
import io
import json
from types import SimpleNamespace
from PIL import Image
from app import text_routing as t, text_ocr, pixel_text, spelling_audit
from app.config import Settings
from app.rules import PACK


def fixture(tmp_path):
    rect=[.1,.2,.4,.3]
    run=dict(options={'text_sensitivity':'strict'},rule_pack=PACK,reference_snapshot=[],calls=[],
             observation={'objects':[dict(id='sign',label='기관명 간판',text='행정안전부',quality='CLEAR',rects=[rect])]},
             pixel_text={'status':'COMPLETED','detector_regions':[dict(id='OCR001',rect=rect,text='행정안정부',recognition_score=.98,detection_score=.9,source='paddle-detector')]})
    settings=Settings({'DATA_DIR':str(tmp_path)})
    seen=[]
    def call(model,prompt,images,workload):
        p=json.loads(prompt);seen.append((model,p,images,workload))
        assert '행정안전부' not in prompt and '행정안정부' not in prompt
        return {'results':[dict(region_id=x['region_id'],text_present=True,literal_text='행정안정부',uncertain_characters=[],inferred=False,glyph_quality='CLEAR',glyph_evidence='받침과 모음 획 구분',spelling='UNCERTAIN',suggested_text='',spelling_evidence='기관명 기준 필요') for x in p['tasks']]},dict(event_id='fake-only',workload=workload,model=model,usage={'input_tokens':10,'output_tokens':10})
    engine=SimpleNamespace(s=settings,provider=SimpleNamespace(call=call),checkpoint=lambda *a:None)
    buf=io.BytesIO();Image.new('RGB',(500,400),'white').save(buf,format='PNG')
    return engine,run,buf.getvalue(),seen


def test_disagreement_is_kept_with_geometric_binding_and_blind_crop(tmp_path):
    engine,run,raw,seen=fixture(tmp_path)
    routing=t.prepare(run);assert routing['counts']=={'DISAGREEMENT':1}
    t.recheck(engine,{'id':'j'},run,raw)
    assert len(seen)==1 and seen[0][0]=='gpt-5.4' and seen[0][3]=='text-ocr'
    assert len(seen[0][2])==1 and run['text_ocr']['status']=='COMPLETED'
    assert run['text_routing']['regions'][0]['action']=='RECHECKED'
    assert run['text_ocr']['regions'][0]['verdict']['status']=='REVIEW'


def test_same_words_in_different_places_are_not_bound_to_the_first_occurrence(tmp_path):
    _,run,_,_=fixture(tmp_path);region=run['pixel_text']['detector_regions'][0]
    objects=[dict(id='wrong',text=region['text'],rects=[[.6,.7,.9,.8]]),dict(id='right',text=region['text'],rects=[region['rect']])]
    assert [o['id'] for o in t.linked_objects(region,objects)]==['right']
    objects.append({**objects[1],'id':'overlap'})
    assert len(t.linked_objects(region,objects))==2


def test_missing_scene_text_and_empty_ocr_survive_as_recheck_candidates(tmp_path):
    _,run,_,_=fixture(tmp_path);run['observation']['objects']=[]
    assert t.prepare(run)['regions'][0]['state']=='NO_SCENE_MATCH'
    run['pixel_text']['detector_regions'][0]['text']=''
    assert t.prepare(run)['regions'][0]['state']=='UNREAD'


def test_no_new_calls_when_reusing_or_crop_budget_is_exhausted(tmp_path):
    engine,run,raw,seen=fixture(tmp_path)
    run['observation_reused_from']={'run_id':'old'};t.recheck(engine,{'id':'j'},run,raw)
    assert not seen and run['text_routing']['regions'][0]['deferred_reason']=='OBSERVATION_REUSED'
    run.pop('observation_reused_from');run['calls']=[{'workload':'image-verification'}]*3
    t.recheck(engine,{'id':'j'},run,raw)
    assert not seen and run['text_routing']['regions'][0]['deferred_reason']=='SHARED_CROP_CALL_LIMIT'


def test_many_candidates_share_one_three_region_call_and_keep_deferrals(tmp_path):
    engine,run,raw,seen=fixture(tmp_path)
    region=run['pixel_text']['detector_regions'][0]
    run['pixel_text']['detector_regions']=[{**region,'id':f'OCR{i:03}'} for i in range(9)]
    t.recheck(engine,{'id':'j'},run,raw)
    assert len(seen)==1 and len(seen[0][2])==3
    assert sum(r.get('deferred_reason')=='REGION_LIMIT' for r in run['text_routing']['regions'])==6


def test_failure_is_not_retried_and_does_not_downgrade_unrelated_text(tmp_path):
    engine,run,raw,seen=fixture(tmp_path)
    def fail(*args,**kwargs):seen.append('attempt');raise RuntimeError('preflight blocked')
    engine.provider.call=fail;t.recheck(engine,{'id':'j'},run,raw)
    assert seen==['attempt'] and run['text_ocr']['status']=='UNAVAILABLE'
    row=dict(rule_id='H-06-b',status='PASS',reason='다른 영역',evidence_ids=['other'],rects=[[.7,.7,.9,.8]])
    assert text_ocr.protect_rows(run,[row],['H-06-b'],'reader')[0]['status']=='PASS'


def test_pixel_measurement_accounts_for_unsupported_and_limited_regions(tmp_path):
    _,run,raw,_=fixture(tmp_path);r=run['pixel_text']['detector_regions'][0]
    regions=[{**r,'polygon_px':[[0,0],[100,25],[100,50],[0,25]]},{**r,'id':'second'}]
    diag=[];assert pixel_text.inspect_regions(raw,regions,1,diag)==[]
    assert [r['state'] for r in diag]==['UNSUPPORTED_ROTATION','REGION_LIMIT']


def test_unconfirmed_independent_spelling_candidate_cannot_become_image_fail(tmp_path):
    engine,run,raw,_=fixture(tmp_path);t.recheck(engine,{'id':'j'},run,raw)
    region=run['text_ocr']['regions'][0];region['text']='행정안전부';region['vision']['literal_text']='행정안정부'
    tasks=spelling_audit.candidates(run)
    assert len(tasks)==1 and tasks[0]['transcription_confirmed'] is False
    run['spelling_audit']={'status':'COMPLETED','tasks':tasks,'results':[dict(id=tasks[0]['id'],literal='행정안정부',verdict='TYPO',kind='COMMON_WORD',correction='행정안전부',reason='후보 철자 차이')]}
    rows=spelling_audit.protect(run,[],['D-02-l'])
    assert rows[0]['status']=='REVIEW' and rows[0]['diagnostic_only']


def test_duplicate_agreed_words_are_spelling_checked_at_the_correct_object(tmp_path):
    _,run,_,_=fixture(tmp_path);region=run['pixel_text']['detector_regions'][0]
    run['observation']['objects']=[dict(id='left',label='왼쪽 안내',text=region['text'],rects=[region['rect']]),dict(id='right',label='오른쪽 안내',text=region['text'],rects=[[.6,.6,.9,.7]])]
    assert spelling_audit.candidates(run)[0]['object_id']=='left'


def test_confirmed_crop_name_is_checked_even_when_scene_reader_auto_corrected_it(tmp_path):
    from app import evidence_guards
    engine,run,raw,_=fixture(tmp_path);t.recheck(engine,{'id':'j'},run,raw)
    run['analysis_observation']=copy.deepcopy(run['observation']);text_ocr.attach_observations(run)
    crop=next(o for o in run['analysis_observation']['objects'] if o['id']=='OCR001')
    assert crop['text']=='행정안정부' and crop['quality']=='CLEAR'
    rows=evidence_guards.protect(run,[],['D-02-l'])
    assert any(r['status']=='FAIL' and r['evidence_ids']==['OCR001'] for r in rows)


def test_union_covers_text_across_cells_without_bridging_disconnected_gaps():
    rect=[.626953125,.8125,.6979166667,.857421875]
    cells=[[7/12,9/12,8/12,10/12],[7/12,10/12,8/12,11/12]]
    assert .55<t.covered_fraction(rect,cells)<.57
    objects=[dict(id='food',text='김치찌개',rects=cells)]
    assert t.linked_objects(dict(rect=rect,text='김처찌개'),objects)==objects
    assert t.covered_fraction([0.,0.,1.,1.],[[0.,0.,.2,1.],[.8,0.,1.,1.]])<.41
    assert t.covered_fraction(rect,cells*3)==t.covered_fraction(rect,cells)


def test_conflict_stays_visible_at_exact_location_without_claiming_typo(tmp_path):
    _,run,_,_=fixture(tmp_path)
    run['pixel_text']['detector_regions'][0]['recognition_score']=.77
    run['observation']['objects'][0]['cell_ids']=['R03C03']
    row=dict(rule_id='D-02-l',status='PASS',evidence_ids=['sign'],reason='일치')
    result=t.protect_conflicts(run,[row],['D-02-l'])[0]
    assert result['status']=='REVIEW' and result['visual_issue'] and not result['diagnostic_only']
    assert result['rects']==[run['pixel_text']['detector_regions'][0]['rect']]
    result['status']='FAIL'
    assert t.protect_conflicts(run,[result],['D-02-l'])[0]['status']=='FAIL'


def test_geometric_ambiguity_is_not_resolved_using_a_convenient_transcript(tmp_path):
    _,run,_,_=fixture(tmp_path);region=run['pixel_text']['detector_regions'][0]
    objects=run['observation']['objects'];objects.append({**objects[0],'id':'ambiguous','text':region['text']})
    assert len(t.linked_objects(region,objects))==2
    assert t.protect_conflicts(run,[],['D-02-l'])==[]


def test_coarse_anchor_cell_can_locate_a_cross_boundary_line_without_loosening_measured_boxes():
    region=dict(rect=[.626953125,.8125,.6979166667,.857421875],text='김처찌개')
    obj=dict(id='sign',cell_ids=['R11C08'],text='김치찌개')
    assert t.covered_fraction(region['rect'],t.object_rects(obj))<.5
    assert t.linked_objects(region,[obj])==[obj]
    measured={**obj,'rects':t.object_rects(obj)}
    assert not t.linked_objects(region,[measured])
    assert not t.linked_objects(region,[{**obj,'cell_ids':['R11C09']}])


def test_adjacent_equal_transcript_invalidates_coarse_anchor_without_rebinding():
    region={'id':'OCR1','text':'행정안정부','rect':[.11,.8877,.1895,.9355]}
    objects=[dict(id='middle',text='한글의 가치',cell_ids=['R11C02','R11C03']),dict(id='lower',text='행정안정부',cell_ids=['R12C02','R12C03'])]
    assert t.linked_objects(region,objects)==[]
    issue=t.anchor_binding_issue(region,objects)
    assert issue['coarse_object_id']=='middle' and issue['nearby_candidate_ids']==['lower']
    # A precise measured box does not inherit the coarse-grid ambiguity rule.
    measured={**objects[0],'rects':[region['rect']]}
    assert t.linked_objects(region,[measured,objects[1]])==[measured]
    # Distant repeated words cannot invalidate or select this location.
    far={**objects[1],'cell_ids':['R01C10']}
    assert t.linked_objects(region,[objects[0],far])==[objects[0]]


def test_reconcile_only_retires_unproven_cross_object_review_and_preserves_fail():
    region={'id':'OCR1','text':'행정안정부','rect':[.11,.8877,.1895,.9355]}
    objects=[dict(id='middle',text='한글의 가치',cell_ids=['R11C02','R11C03']),dict(id='lower',text='행정안정부',cell_ids=['R12C02','R12C03'])]
    proof={'region_id':'OCR1','object_id':'middle','status':'UNRESOLVED'}
    row=dict(id='r',rule_id='D-02-l',status='REVIEW',reason='같은 글자 판독 차이',independent_reading_conflicts=[copy.deepcopy(proof)])
    fail={**copy.deepcopy(row),'id':'fail','status':'FAIL','reason':'독립 공식 명칭 오류'}
    run={'observation':{'objects':objects},'pixel_text':{'detector_regions':[region]},'glyph_audit':{'regions':[dict(id='g',rect=region['rect'],detector_text=region['text'],source_ids=['middle'])]}}
    t.reconcile_stored_bindings(run,[row,fail]);assert row['diagnostic_only'] and row['binding_uncertain']
    assert row['before_binding_reconcile']['reason']=='같은 글자 판독 차이'
    assert fail['status']=='FAIL' and fail['reason']=='독립 공식 명칭 오류' and not fail.get('binding_uncertain')
    assert run['glyph_audit']['regions'][0]['source_ids']==[]
    snapshot=copy.deepcopy([run,row,fail]);t.reconcile_stored_bindings(run,[row,fail]);assert snapshot==[run,row,fail]
