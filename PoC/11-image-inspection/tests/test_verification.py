import copy
import hashlib
import io
import json
from types import SimpleNamespace
from PIL import Image
from app.config import Settings
from app.engine import Engine
from app.storage import Store
from app.rules import PACK
from app import verification as v


def recheck(oid='flag1'):
    return dict(object_id=oid,coverage='COMPLETE',text='01',text_legibility='CLEAR',legibility_evidence='획이 구분됨',transcription_inferred=False,quality='CLEAR',description='확대 원본에서 확인',cell_ids=['R04C04'],comparisons=[])


def png():
    b=io.BytesIO();Image.new('RGB',(1200,900),'white').save(b,format='PNG');return b.getvalue()


def setup_run(tmp_path,count=7):
    from test_observations import inventory
    refs=tmp_path/'references';refs.mkdir(exist_ok=True)
    data=png();(refs/'flag.png').write_bytes(data)
    ref=dict(id='flag-ref',name='대한민국 태극기 — 공식 도안',status='APPROVED',kind='official-symbols',parent_ids=['H-04'],image_file='flag.png',image_hash=hashlib.sha256(data).hexdigest(),content='태극과 4괘')
    obs=inventory();obs['objects']=[{**obs['objects'][0],'id':'o'+str(i),'text':'FIRST-PRIVATE-TRANSCRIPT'} for i in range(count)]
    run=dict(observation=obs,reference_snapshot=[ref],rule_pack=copy.deepcopy(PACK),selected=['H-04-i'],options={'vision_model':'gpt-5.4','text_sensitivity':'strict'},calls=[],observation_model='gpt-5.4')
    calls=[]
    def call(model,prompt,images,workload):
        p=json.loads(prompt);calls.append((p,images))
        assert workload=='image-verification' and 'FIRST-PRIVATE-TRANSCRIPT' not in prompt
        assert len(images)<=8 and len(p['tasks'])<=3
        assert p['reference_images'][0]['reference_id']=='flag-ref'
        result=[]
        for t in p['tasks']:
            r=recheck(t['object_id']);r['comparisons']=[dict(reference_id='flag-ref',rule_ids=['H-04-i'],status='MISMATCH',evidence='왼쪽 위 괘의 분절 구성 불일치')];result.append(r)
        return {'results':result},{'event_id':str(len(calls)),'workload':workload}
    engine=SimpleNamespace(s=Settings({'DATA_DIR':str(tmp_path),'AUTO_VERIFY_MAX_OBJECTS':'6'}),provider=SimpleNamespace(call=call),checkpoint=lambda *a:None)
    return engine,run,calls,data


def test_batched_verification_has_context_and_scoped_proof_and_preserves_first_read(tmp_path):
    engine,run,calls,data=setup_run(tmp_path)
    original=copy.deepcopy(run['observation'])
    v.run_verification(engine,{'id':'job','metadata':{}},run,data)
    assert len(calls)==2 and len(run['verification']['results'])==6 and len(run['verification']['deferred'])==1
    first=run['verification']['results'][0]
    assert first['crop_rect']==[0,1/12,6/12,6/12]
    assert first['transcription_disagreement'] and first['first_text']=='FIRST-PRIVATE-TRANSCRIPT'
    assert v.direct_comparisons(run,'H-04-i',['o0'],['flag-ref'])
    assert not v.direct_comparisons(run,'H-04-h',['o0'],['flag-ref'])
    assert not v.direct_comparisons(run,'H-04-i',['o6'],['flag-ref'])
    effective=v.effective_observation(run)
    assert run['observation']==original and effective['objects'][0]['text']=='01'
    assert effective['objects'][0]['rects'] and effective['objects'][0]['first_text']=='FIRST-PRIVATE-TRANSCRIPT'
    run['reference_snapshot'][0]['image_hash']='changed'
    assert not v.direct_comparisons(run,'H-04-i',['o0'],['flag-ref'])


def test_missing_reference_file_and_provider_failure_are_deferred(tmp_path):
    engine,run,calls,data=setup_run(tmp_path,1)
    (tmp_path/'references'/'flag.png').unlink()
    v.run_verification(engine,{'id':'job','metadata':{}},run,data)
    assert not calls and not run['verification']['results'] and run['verification']['deferred']
    (tmp_path/'references'/'flag.png').write_bytes(data)
    def failure(*a,**kw):
        exc=RuntimeError('공급자 실패');exc.call_meta={'event_id':'failed','usage':{'input_tokens':100}};raise exc
    engine.provider.call=failure
    v.run_verification(engine,{'id':'job','metadata':{}},run,data)
    assert run['calls'][0]['event_id']=='failed' and run['verification']['deferred']


def test_official_verdict_needs_same_object_action_and_reference_image(tmp_path):
    fake,run,calls,data=setup_run(tmp_path,2)
    v.run_verification(fake,{'id':'job','metadata':{}},run,data)
    run['analysis_observation']=v.effective_observation(run)
    engine=Engine(fake.s,Store(tmp_path/'test.sqlite3'))
    group=dict(target_presence='PRESENT',rule_ids=['H-04-i'],status='FAIL',evidence_ids=['o0'],reference_ids=['flag-ref'],reason='괘의 공식 배치와 다름',recommended_action='제작 의도와 도안 확인')
    result=engine.decisions(run,None,'gpt-5.4',['H-04-i'],{'results':[group]})[0]
    assert result['status']=='FAIL' and result['evidence_status']=='VERIFIED'
    group['status']='PASS'
    assert engine.decisions(run,None,'gpt-5.4',['H-04-i'],{'results':[group]})[0]['status']=='REVIEW'
    run['verification']['results'][0]['comparisons'][0]['status']='MATCH'
    assert engine.decisions(run,None,'gpt-5.4',['H-04-i'],{'results':[group]})[0]['status']=='PASS'
    run['verification']['results']=run['verification']['results'][1:]
    result=engine.decisions(run,None,'gpt-5.4',['H-04-i'],{'results':[group]})[0]
    assert result['status']=='REVIEW' and result['evidence_status']=='UNAVAILABLE'
    engine.pool.shutdown()


def test_contradictory_or_out_of_scope_comparison_is_not_evidence(tmp_path):
    engine,run,calls,data=setup_run(tmp_path,1);original=engine.provider.call
    def invalid(*a,**kw):
        body,meta=original(*a,**kw);r=body['results'][0]
        r['comparisons'].append({**r['comparisons'][0],'status':'MATCH'})
        return body,meta
    engine.provider.call=invalid
    v.run_verification(engine,{'id':'job','metadata':{}},run,data)
    assert run['verification']['results'][0]['comparison_conflicts']
    assert not v.direct_comparisons(run,'H-04-i',['o0'],['flag-ref'])


def test_alignment_preserves_all_atomic_actions_and_removes_duplicate_id_definitions():
    from scripts.align_rule_pack import align
    from app.rule_editor import to_markdown,parse_markdown
    p=copy.deepcopy(PACK);p['parents'][0]['original']='`H-01-a` 다른 행동을 설명한 상위 예시'
    p['guidance']='v2.3 공통 검수 지침입니다.'
    before=to_markdown(p);after=parse_markdown(align(before))
    assert len(after['parents'])==25 and len(after['steps'])==156
    assert [s['objective'] for s in after['steps']]==[s['objective'] for s in p['steps']]
    assert '`H-01-a`' not in after['parents'][0]['original']
    assert '최대 3회' in after['guidance'] and '독립 OCR' not in after['guidance'] # no promise of another engine


def test_recheck_selection_covers_text_hands_faces_mascots_and_missing_reference():
    steps={r['rule_id']:r for r in PACK['steps']}
    selected=list(steps)
    def obj(oid,label,description='',**kw):
        return dict(id=oid,label=label,description=description,text='',quality='CLEAR',cell_ids=['R04C04'],**kw)
    objects=[obj('text','작은 안내 문구',text_legibility='DEGRADED'),obj('hand','왼손'),obj('face','가려진 얼굴'),obj('mascot','다행이 캐릭터','행안부 다행이'),obj('unknown','출처 불명 기관 마크'),obj('title','태극기 퀴즈 제목','올바른 태극기를 찾아라')]
    objects[1]['quality']='UNCERTAIN';objects[2]['quality']='OCCLUDED'
    refs=[dict(id='mascot-ref',name='다행이 공식 캐릭터',status='APPROVED',image_file='mascot.png',parent_ids=['H-07','D-02'],kind='official-emblems'),dict(id='flag-ref',name='태극기 도안',status='APPROVED',image_file='flag.png',parent_ids=['H-04'],kind='official-symbols')]
    tasks=v.candidates({'objects':objects},refs,steps,selected)
    by_id={t['object']['id']:t for t in tasks}
    assert {'text','hand','face','mascot'}<=by_id.keys()
    assert by_id['mascot']['references'][0]['id']=='mascot-ref'
    assert not by_id['unknown']['references'] and not by_id['title']['references']
    assert not by_id['text']['references'] and not by_id['hand']['references']
    assert not v.reference_candidates(obj('caption','문구','',text_legibility='CLEAR')|{'text':'태극기 다행이 부리부리'},refs)


def test_partial_recheck_never_erases_prior_typo_or_unexamined_text(tmp_path):
    engine,run,calls,data=setup_run(tmp_path,1)
    original=copy.deepcopy(run['observation'])
    original_call=engine.provider.call
    def partial(*a,**kw):
        body,meta=original_call(*a,**kw)
        body['results'][0].update(coverage='PARTIAL',text='일부 정상 글자')
        return body,meta
    engine.provider.call=partial
    v.run_verification(engine,{'id':'job','metadata':{}},run,data)
    assert v.effective_observation(run)==original
    assert not v.direct_comparisons(run,'H-04-i',['o0'],['flag-ref'])
    assert run['verification']['deferred'] and run['verification']['results'][0]['text']=='일부 정상 글자'


def test_measured_object_crop_keeps_entire_shape_and_context():
    data=png();bounds=[.22,.32,.48,.54]
    cropped,rect=v.expanded_crop(data,['R05C03'],bounds)
    assert rect[0]<bounds[0] and rect[1]<bounds[1] and rect[2]>bounds[2] and rect[3]>bounds[3]
    assert Image.open(io.BytesIO(cropped)).width>300


def test_changing_action_invalidates_previous_comparison(tmp_path):
    engine,run,calls,data=setup_run(tmp_path,1)
    v.run_verification(engine,{'id':'job','metadata':{}},run,data)
    assert v.direct_comparisons(run,'H-04-i',['o0'],['flag-ref'])
    next(s for s in run['rule_pack']['steps'] if s['rule_id']=='H-04-i')['objective']='변경된 세부 행동 기준을 별도로 검사한다.'
    assert not v.direct_comparisons(run,'H-04-i',['o0'],['flag-ref'])


def test_standard_skips_clear_text_but_strict_checks_glyphs_independently():
    steps={r['rule_id']:r for r in PACK['steps']}
    clear=dict(id='clear',label='안내 문구',description='선명한 안내',text='환영합니다',quality='CLEAR',text_legibility='CLEAR',transcription_inferred=False,visual_concerns='',cell_ids=['R02C03'])
    hand=dict(id='hand',label='왼손',description='손가락 여섯 갈래',text='',quality='CLEAR',text_legibility='NOT_TEXT',visual_concerns='손가락 과다 의심',cell_ids=['R05C06'])
    tasks=v.candidates({'objects':[clear,hand]},[],steps,list(steps),strict=False)
    assert [t['object']['id'] for t in tasks]==['hand']
    assert {t['object']['id'] for t in v.candidates({'objects':[clear,hand]},[],steps,list(steps),strict=True)}=={'clear','hand'}


def test_strict_small_text_and_hands_are_checked_even_after_clear_first_read():
    steps={r['rule_id']:r for r in PACK['steps']}
    def o(i,label,description,text=''):
        return dict(id=i,label=label,description=description,text=text,quality='CLEAR',text_legibility='CLEAR' if text else 'NOT_TEXT',visual_concerns='선명하게 잘 보입니다.',cell_ids=['R06C06'])
    objects=[o('plain','큰 제목','선명한 문구','환영합니다'),o('small','음식 안내 표지','작은 표지판','김치찌개'),o('hand','가족 인물','한 손으로 브이 포즈'),o('map','지도판 지명','섬과 해역의 표기','동해'),o('badge','제복 인물','경찰 문양과 표식','POLICE')]
    tasks=v.candidates({'objects':objects},[],steps,list(steps),strict=True)
    assert {t['object']['id'] for t in tasks}=={'plain','small','hand','map','badge'}
    assert not v.candidates({'objects':objects},[],steps,list(steps),strict=False)


def test_verbose_normal_captions_do_not_starve_other_domains_or_leak_corrected_label(tmp_path):
    engine,run,calls,data=setup_run(tmp_path,1)
    run['observation']['objects'][0]['label']='FIRST-PRIVATE-TRANSCRIPT를 뜻하는 표지'
    run['observation']['objects'][0]['description']='태극기 도안'
    v.run_verification(engine,{'id':'job','metadata':{}},run,data)
    assert calls and 'FIRST-PRIVATE-TRANSCRIPT' not in json.dumps(calls[0][0],ensure_ascii=False)
    # A large number of flag candidates cannot consume the entire bounded pass.
    steps={r['rule_id']:r for r in PACK['steps']}
    base=run['observation']['objects'][0]
    objs=[{**base,'id':str(i),'label':'태극기','description':'태극기 도안'} for i in range(20)]
    objs += [{**base,'id':'hand','label':'오른손','description':'손가락 브이'}, {**base,'id':'map','label':'지도판 지명','description':'한반도 지도'}]
    ids=[t['object']['id'] for t in v.candidates({'objects':objs},run['reference_snapshot'],steps,list(steps))[:6]]
    assert 'hand' in ids and 'map' in ids


def test_scoped_colour_comparison_survives_uncertain_other_parts(tmp_path):
    fake,run,calls,data=setup_run(tmp_path,1)
    v.run_verification(fake,{'id':'job','metadata':{}},run,data)
    result=run['verification']['results'][0]
    result['quality']='UNCERTAIN';result['comparisons'][0]['quality']='CLEAR'
    run['analysis_observation']=v.effective_observation(run)
    engine=Engine(fake.s,Store(tmp_path/'test.sqlite3'))
    decision=dict(target_presence='PRESENT',rule_ids=['H-04-i'],status='FAIL',evidence_ids=['o0'],reference_ids=['flag-ref'],reason='이 행동의 직접 비교는 명확함',recommended_action='확인된 도안 차이 수정')
    row=engine.decisions(run,None,'gpt-5.4-mini',['H-04-i'],{'results':[decision]})[0]
    assert row['status']=='FAIL' and row['evidence_quality']=='CLEAR'
    decision['status']='REVIEW'
    assert engine.decisions(run,None,'gpt-5.4-mini',['H-04-i'],{'results':[decision]})[0]['status']=='FAIL'
    decision['status']='FAIL'
    result['comparisons'][0]['quality']='UNCERTAIN'
    assert engine.decisions(run,None,'gpt-5.4-mini',['H-04-i'],{'results':[decision]})[0]['status']=='REVIEW'
    engine.pool.shutdown()


def test_clear_short_sign_and_context_symbol_are_not_skipped():
    steps={r['rule_id']:r for r in PACK['steps']}
    base=dict(description='독립된 작은 물체',text='',quality='CLEAR',text_legibility='NOT_TEXT',cell_ids=['R02C03'],visual_concerns='')
    objects=[dict(base,id='sign',label='체험 안내판',text='전통 문화',text_legibility='CLEAR'),dict(base,id='symbol',label='수송수단의 부속 표식',visual_concerns='본체의 국가 정체성 설명과 다른 국기 유사 표식이 혼동을 일으킴')]
    tasks=v.candidates({'objects':objects},[],steps,list(steps))
    assert {t['object']['id']:t['domain'] for t in tasks}=={'sign':'text','symbol':'context_symbol'}
    native,rect=v.expanded_crop(png(),['R08C08','R09C08'],focus='text')
    old,old_rect=v.expanded_crop(png(),['R08C08','R09C08'])
    assert Image.open(io.BytesIO(native)).width<Image.open(io.BytesIO(old)).width
    assert rect[0]<7/12 and rect[2]>8/12 and rect[1]<7/12 and rect[3]>9/12


def test_selected_recheck_preserves_other_verified_evidence(tmp_path):
    engine,run,calls,data=setup_run(tmp_path,2)
    v.run_verification(engine,{'id':'job','metadata':{}},run,data)
    other=copy.deepcopy(next(r for r in run['verification']['results'] if r['object_id']=='o1'))
    run['options']['recheck_object_ids']=['o0'];calls.clear()
    v.run_verification(engine,{'id':'job','metadata':{}},run,data)
    assert len(calls)==1 and [t['object_id'] for t in calls[0][0]['tasks']]==['o0']
    assert next(r for r in run['verification']['results'] if r['object_id']=='o1')==other
    assert len(run['verification']['results'])==2


def test_partial_name_disagreement_cannot_be_pass_or_disappear(tmp_path):
    engine,run,calls,data=setup_run(tmp_path,1)
    obj=run['observation']['objects'][0]
    obj.update(id='ministry-text',label='기관명',text='행정안정부',description='원본 기관명',quality='CLEAR')
    run['verification']={'results':[dict(object_id=obj['id'],status='COMPLETED',coverage='PARTIAL',text='행정안전부',event_id='partial')]}
    row=dict(rule_id='D-02-l',status='PASS',evidence_ids=[obj['id']],reason='정상')
    protected=v.protect_transcription_conflicts(run,[row],['D-02-l'],'test')
    assert protected[0]['status']=='REVIEW'
    assert '행정안정부' in protected[0]['reason'] and '행정안전부' in protected[0]['reason']
    assert protected[0]['visual_issue'] and not protected[0]['document_review']
    omitted=v.protect_transcription_conflicts(run,[],['D-02-l'],'test')
    assert len(omitted)==1 and omitted[0]['evidence_ids']==['ministry-text']
    assert omitted[0]['model']=='system/transcription-conflict'
    row['status']='FAIL'
    assert v.protect_transcription_conflicts(run,[row],['D-02-l'],'test')[0]['status']=='FAIL'
    run['verification']['results'][0]['text']='행정 안정부'
    assert not v.protect_transcription_conflicts(run,[],['D-02-l'],'test')


def test_map_context_and_real_flag_take_priority_over_compass_and_pole(tmp_path):
    engine,run,calls,data=setup_run(tmp_path,1)
    template=run['observation']['objects'][0]
    objects=[{**template,'id':oid,'label':label,'description':description,'text':text,'quality':'CLEAR','visual_concerns':'','text_legibility':'CLEAR' if text else 'NOT_TEXT'} for oid,label,description,text in [
        ('pole','태극기 깃대','태극기를 지지하는 깃대',''),
        ('flag','대형 태극기','흰 깃면 중앙 태극',''),
        ('compass','지도판 방향표','지도에 나침반','NWES'),
        ('map','한반도 지도 본체','지도판의 육지 색상',''),
        ('name','표지석 한글 기관명','원문을 읽음','행정안정부'),
    ]]
    steps={s['rule_id']:s for s in PACK['steps']}
    tasks=v.candidates({'objects':objects},run['reference_snapshot'],steps,list(steps))
    by_id={t['object']['id']:t for t in tasks}
    assert by_id['map']['domain']=='map'
    assert 'compass' not in by_id or by_id['compass']['domain']!='map'
    assert 'pole' not in by_id or not by_id['pole']['references']
    assert by_id['flag']['references']
    assert by_id['name']['domain']=='text'
    assert tasks.index(by_id['name'])<3
    assert v.expanded_crop(data,['R06C06'],focus='map')==(data,[0.,0.,1.,1.])


def test_distinct_comparison_aspects_do_not_confuse_color_match_and_direction_error(tmp_path):
    engine,run,calls,data=setup_run(tmp_path,1);original=engine.provider.call
    def with_aspects(*args,**kwargs):
        body,meta=original(*args,**kwargs);r=body['results'][0]
        r['comparisons'][0]['aspect']='DIRECTION'
        r['comparisons'].append({**r['comparisons'][0],'aspect':'COLOR','status':'MATCH','evidence':'색은 같지만 방향은 반대'})
        return body,meta
    engine.provider.call=with_aspects
    v.run_verification(engine,{'id':'job','metadata':{}},run,data)
    assert len(run['verification']['results'])==1
    proof=v.direct_comparisons(run,'H-04-i',['o0'],['flag-ref'])
    assert proof and all(c['status']=='MISMATCH' for c in proof)


def test_one_bad_object_does_not_discard_other_paid_readings(tmp_path):
    engine,run,calls,data=setup_run(tmp_path,2);original=engine.provider.call
    def one_bad(*args,**kwargs):
        body,meta=original(*args,**kwargs);r=body['results'][0]
        r['comparisons'].append({**r['comparisons'][0],'status':'MATCH'})
        return body,meta
    engine.provider.call=one_bad
    v.run_verification(engine,{'id':'job','metadata':{}},run,data)
    assert [r['object_id'] for r in run['verification']['results']]==['o0','o1']
    assert run['verification']['results'][0]['comparison_conflicts']
    assert not v.direct_comparisons(run,'H-04-i',['o0'],['flag-ref'])
    assert v.direct_comparisons(run,'H-04-i',['o1'],['flag-ref'])


def test_mixed_map_label_keeps_reference_and_nontext_heart_is_not_ocr():
    steps={s['rule_id']:s for s in PACK['steps']}
    base=dict(id='map',label='지도 본체와 주요 지명',description='한반도 지도와 섬',text='동해',quality='CLEAR',text_legibility='CLEAR',cell_ids=['R06C11'])
    ref=dict(id='map-ref',name='대한민국 지도 — 위치',status='APPROVED',kind='official-map',parent_ids=['H-03'],image_file='map.png')
    tasks=v.candidates({'objects':[base]},[ref],steps,list(steps))
    assert tasks[0]['domain']=='map' and tasks[0]['references']==[ref]
    assert v.expanded_crop(png(),base['cell_ids'],focus=tasks[0]['domain'])[1]==[0,0,1,1]
    heart={**base,'label':'붓글씨 옆 하트 기호','description':'작은 붉은 하트','text':'','text_legibility':'NOT_TEXT'}
    assert not v.is_text(heart) and not v.candidates({'objects':[heart]},[],steps,list(steps))
    bus={**base,'label':'관광버스 전면 광고 문구','text':'서울의 매력을 세계로!'}
    assert v.candidates({'objects':[bus]},[],steps,list(steps))[0]['domain']=='text'


def test_police_keeps_three_distinct_reference_subjects():
    obj=dict(id='police',label='경찰 제복 인물',description='모자 문양, 가슴 배지, 어깨 계급장',text='')
    refs=[dict(id=str(i),name=n,status='APPROVED',kind='official-emblems',image_file=str(i)+'.png') for i,n in enumerate(['경찰 기관문양','경찰 계급장','경찰 가슴표장'])]
    assert v.reference_candidates(obj,refs)==refs


def test_independent_subparts_do_not_cancel_observed_difference():
    base=dict(reference_id='ref',rule_ids=['H-07-b'],aspect='BADGE_SHAPE',quality='CLEAR')
    result={'comparisons':[{**base,'part':'outline','status':'MISMATCH','evidence':'외곽이 다름'},{**base,'part':'center','status':'UNCERTAIN','evidence':'중앙 가림'}]}
    v.reconcile_comparison_aspects(result)
    assert [c['status'] for c in result['comparisons']]==['MISMATCH','UNCERTAIN']
    assert len(result['raw_comparisons'])==2
    result['comparisons'].append({**base,'part':'outline','status':'MATCH','evidence':'외곽 일치'})
    v.reconcile_comparison_aspects(result)
    assert result['comparisons'][0]['status']=='UNCERTAIN'


def test_text_center_cells_retain_horizontal_context_without_neighboring_lines():
    raw=png();_,rect=v.expanded_crop(raw,['R05C03','R05C04','R05C05','R05C06'],focus='text')
    assert rect[0] < .1 and rect[2] > .6
    assert .30 < rect[1] < .34 and .41 < rect[3] < .45


def test_named_custom_reference_is_matched_without_treating_any_logo_as_official():
    ref=dict(name='가상 안내단 문양 — 제작자 제공 기준',status='APPROVED',image_file='ref.png')
    obj=dict(label='가상 안내단 표식',description='방패 모양의 문양')
    assert v.reference_candidates(obj,[ref])==[ref]
    obj['label']='알 수 없는 로고'
    assert v.reference_candidates(obj,[ref])==[]


def test_budget_rejection_splits_before_http_and_never_exceeds_call_cap(tmp_path):
    from app.usage import BudgetError
    engine,run,calls,data=setup_run(tmp_path,4);original=engine.provider.call;attempts=[]
    def limited(model,prompt,images,workload):
        tasks=json.loads(prompt)['tasks'];attempts.append(len(tasks))
        if len(tasks)>1:raise BudgetError('admission limit')
        return original(model,prompt,images,workload)
    engine.provider.call=limited
    v.run_verification(engine,{'id':'job','metadata':{}},run,data)
    assert attempts==[3,1,1,1] and len(calls)==3
    assert len(run['verification']['results'])==3 and run['verification']['call_count']==3
    assert run['verification']['budget_splits'] and run['verification']['deferred']


def test_image_scoped_author_reference_does_not_apply_to_other_uploads():
    ref=dict(name='제작자 도안',status='APPROVED',image_file='ref.png',kind='official-emblems',target_image_sha256='current')
    obj=dict(label='좌측 심볼',description='원형 표식')
    assert v.reference_candidates(obj,[ref],'current')==[ref]
    assert v.reference_candidates(obj,[ref],'another')==[]
    assert v.reference_candidates(obj,[ref])==[]


def test_hand_center_crop_keeps_fingertips_and_wrist_context():
    _,rect=v.expanded_crop(png(),['R07C04'],focus='anatomy')
    assert rect[0] <= 1/12 and rect[1] <= 4/12
    assert rect[2] >= 6/12 and rect[3] >= 9/12
