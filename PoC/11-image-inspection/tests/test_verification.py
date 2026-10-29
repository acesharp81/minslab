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
    assert not run['verification']['results'] and '상충' in run['verification']['deferred'][0]['reason']


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


def test_clear_ordinary_text_skips_paid_recheck_but_observed_defects_do_not():
    steps={r['rule_id']:r for r in PACK['steps']}
    clear=dict(id='clear',label='안내 문구',description='선명한 안내',text='환영합니다',quality='CLEAR',text_legibility='CLEAR',transcription_inferred=False,visual_concerns='',cell_ids=['R02C03'])
    hand=dict(id='hand',label='왼손',description='손가락 여섯 갈래',text='',quality='CLEAR',text_legibility='NOT_TEXT',visual_concerns='손가락 과다 의심',cell_ids=['R05C06'])
    tasks=v.candidates({'objects':[clear,hand]},[],steps,list(steps),strict=True)
    assert [t['object']['id'] for t in tasks]==['hand']


def test_strict_small_text_and_hands_are_checked_even_after_clear_first_read():
    steps={r['rule_id']:r for r in PACK['steps']}
    def o(i,label,description,text=''):
        return dict(id=i,label=label,description=description,text=text,quality='CLEAR',text_legibility='CLEAR' if text else 'NOT_TEXT',visual_concerns='선명하게 잘 보입니다.',cell_ids=['R06C06'])
    objects=[o('plain','큰 제목','선명한 문구','환영합니다'),o('small','음식 안내 표지','작은 표지판','김치찌개'),o('hand','가족 인물','한 손으로 브이 포즈'),o('map','지도판 지명','섬과 해역의 표기','동해'),o('badge','제복 인물','경찰 문양과 표식','POLICE')]
    tasks=v.candidates({'objects':objects},[],steps,list(steps),strict=True)
    assert {t['object']['id'] for t in tasks}=={'small','hand','map','badge'}
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
