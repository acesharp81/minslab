import json
from types import SimpleNamespace
from app import spelling_audit as s

def fixture():
    run={'observation':{'objects':[dict(id='o1',text='힘께 만드는 미래',label='안내 문구',transcription_inferred=False)]},
         'pixel_text':{'status':'COMPLETED','detector_regions':[dict(id='OCR1',source='paddle-detector',recognition_score=.96,detection_score=.9,text='힘께 만드는 미래',rect=[.4,.8,.55,.86])]},'calls':[]}
    response=dict(id='OCR1',literal='힘께 만드는 미래',verdict='TYPO',kind='COMMON_WORD',correction='함께 만드는 미래',reason='일반 부사 표기의 모음이 다릅니다.')
    calls=[]
    def call(model,prompt,images=(),workload=''):
        assert model=='gpt-5.4-mini' and workload=='text-spelling-audit' and images==()
        calls.append(json.loads(prompt));return {'results':[response.copy()]},{'event_id':'test','model':model,'workload':workload}
    engine=SimpleNamespace(provider=SimpleNamespace(call=call),checkpoint=lambda *a:None)
    return run,response,engine,calls

def test_only_independently_agreed_source_is_sent_once():
    run,response,engine,calls=fixture();s.inspect(engine,{'id':'j'},run);s.inspect(engine,{'id':'j'},run)
    assert len(calls)==1 and run['spelling_audit']['status']=='COMPLETED'
    run['observation']['objects'][0]['text']='함께 만드는 미래';assert s.candidates(run)==[]

def test_spelling_fail_changes_readability_pass_with_precise_source_location():
    run,response,engine,calls=fixture();s.inspect(engine,{'id':'j'},run)
    row=dict(rule_id='D-02-l',status='PASS',evidence_ids=['o1']);s.protect(run,[row],['D-02-l'])
    assert row['status']=='FAIL' and row['rects']==[[.4,.8,.55,.86]]
    assert row['spelling_audit_evidence']['literal']=='힘께 만드는 미래'

def test_unknown_name_does_not_turn_into_error_and_physical_defect_survives():
    run,response,engine,calls=fixture();response.update(verdict='REVIEW',kind='NAME_OR_STYLE',correction='')
    s.inspect(engine,{'id':'j'},run)
    row=dict(rule_id='D-02-l',status='PASS',evidence_ids=['o1']);s.protect(run,[row],['D-02-l']);assert row['status']=='PASS'
    row.update(status='FAIL',error_type='VISUAL_TEXT_DEFECT',glyph_evidence={'source':'pixels'})
    s.protect(run,[row],['D-02-l']);assert row['status']=='FAIL'

def test_mutated_literal_and_large_rewrite_cannot_be_source_evidence():
    run,response,engine,calls=fixture();response['literal']='함께 만드는 미래';s.inspect(engine,{'id':'j'},run)
    assert run['spelling_audit']['status']=='UNAVAILABLE'
    run,response,engine,calls=fixture();response['correction']='완전히 새로 만든 긴 문장입니다';s.inspect(engine,{'id':'j'},run)
    assert run['spelling_audit']['results'][0]['verdict']=='REVIEW'

def test_spacing_disagreement_is_not_a_source_typo():
    run,response,engine,calls=fixture()
    run['observation']['objects'][0]['text']='공공 안내 이미지'
    run['pixel_text']['detector_regions'][0]['text']='공공 안내이미지'
    response.update(literal='공공 안내이미지',kind='SPACING',correction='공공 안내 이미지')
    s.inspect(engine,{'id':'j'},run)
    row=dict(rule_id='D-02-l',status='PASS',evidence_ids=['o1']);s.protect(run,[row],['D-02-l'])
    assert row['status']=='PASS' and run['spelling_audit']['results'][0]['verdict']=='REVIEW'
