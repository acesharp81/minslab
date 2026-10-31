import copy
import io
import json
from types import SimpleNamespace
import httpx
from PIL import Image
from app import text_ocr as o
from app.config import Settings
from app.providers import Provider
from app.rules import PACK
from test_provider import Meter


def reading(**kw):
    return dict(region_id='OCR001',text_present=True,literal_text='신청 안내',uncertain_characters=[],inferred=False,
                glyph_quality='CLEAR',glyph_evidence='각 글자의 획이 분리되어 보임',spelling='NORMAL',suggested_text='',spelling_evidence='',**kw)


def region():
    return dict(id='OCR001',text='신청 안내',recognition_score=.99,source='paddle-detector',rect=[.2,.3,.5,.4],vision=reading())


def test_same_readable_transcript_never_hides_source_glyph_damage():
    r=region();r['vision'].update(glyph_quality='DEFECT',glyph_evidence='청의 받침 ㅇ이 아래 획과 붙어 있음')
    assert o.verdict(r)['status']=='FAIL' and o.verdict(r)['error_type']=='VISUAL_TEXT_DEFECT'
    r['vision']['glyph_quality']='UNCERTAIN'
    assert o.verdict(r)['status']=='REVIEW'


def test_disagreement_omission_uncertainty_and_typo_are_different():
    r=region();r['text']='신청 안네'
    assert o.verdict(r)['error_type']=='OCR_MISMATCH' and o.verdict(r)['status']=='REVIEW'
    r['second_vision']=copy.deepcopy(r['vision'])
    assert o.verdict(r)['error_type']=='OCR_RECOGNITION_ERROR'
    r['text']='';assert o.verdict(r)['error_type']=='OCR_OMISSION'
    r=region();r['vision']['inferred']=True;assert o.verdict(r)['status']=='REVIEW'
    r=region();r['text']='김처찌개';r['vision'].update(literal_text='김처찌개',spelling='ERROR',suggested_text='김치찌개',spelling_evidence='처로 쓰인 철자가 치와 다름')
    assert o.verdict(r)['error_type']=='TYPO_CONFIRMED'
    r['vision']['literal_text']='김치찌개';assert o.verdict(r)['status']=='REVIEW'


def test_no_model_or_low_ocr_score_cannot_produce_blue():
    r=region();r.pop('vision');assert o.verdict(r)['status']=='REVIEW'
    r=region();r['recognition_score']=.2;assert o.verdict(r)['status']=='REVIEW'
    r=region();r['vision']['glyph_evidence']='';assert o.verdict(r)['status']=='REVIEW'
    assert o.verdict(region())['status']=='PASS'


def test_crop_is_native_lossless_and_padded_not_grid_resized():
    im=Image.new('RGB',(2400,1600));im.putpixel((1000,500),(251,23,3));b=io.BytesIO();im.save(b,format='PNG')
    cropped,rect,size=o.native_crop(b.getvalue(),[.4,.3,.5,.4]);out=Image.open(io.BytesIO(cropped))
    assert size==list(out.size) and out.getpixel((1000-round(rect[0]*2400),500-round(rect[1]*1600)))==(251,23,3)
    assert rect[0]<.4 and rect[2]>.5


def test_provider_original_and_high_effort_only_on_retry(tmp_path,monkeypatch):
    s=Settings({'DATA_DIR':str(tmp_path),'OPENAI_API_KEY':'test','OPENAI_BASE_URL':'https://example.org/v1'})
    real=httpx.Client;seen=[]
    def respond(req):
        body=json.loads(req.content);seen.append(body)
        schema=body['text']['format']['schema'];assert schema['$defs']['TextReading']['properties']['region_id']['enum']==['OCR001']
        return httpx.Response(200,json={'status':'completed','usage':{'input_tokens':10,'output_tokens':10},'output':[{'type':'message','content':[{'type':'output_text','text':json.dumps({'results':[reading()]})}]}]})
    monkeypatch.setattr('app.providers.httpx.Client',lambda **kw:real(transport=httpx.MockTransport(respond)))
    for workload in ('text-ocr','text-ocr-recheck'):
        Provider(s,Meter()).call('gpt-5.4',json.dumps({'tasks':[{'region_id':'OCR001','image_index':0}]}),[b'image'],workload=workload)
    assert [b['reasoning']['effort'] for b in seen]==['low','high']
    assert all(b['input'][0]['content'][1]['detail']=='original' for b in seen)


def test_pipeline_blind_to_ocr_and_preserves_empty_recognition(tmp_path,monkeypatch):
    s=Settings({'DATA_DIR':str(tmp_path),'OCR_VISION_MAX_REGIONS':'6','OCR_HIGH_EFFORT_RECHECK':'false','NAVER_OCR_ENABLED':'false'})
    raw=io.BytesIO();Image.new('RGB',(600,400),'white').save(raw,format='PNG')
    r=region();r.pop('vision');r['text']='PRIVATE-OCR-ANSWER'
    r2={**copy.deepcopy(r),'id':'OCR002','text':''}
    monkeypatch.setattr(o,'local_ocr',lambda *a:{'status':'COMPLETED','regions':[r,r2],'candidate_count':2})
    def call(model,prompt,images,workload):
        assert 'PRIVATE-OCR-ANSWER' not in prompt and len(images)==2
        assert all(0<v<1 for v in json.loads(prompt)['tasks'][0]['target_rect_in_crop'])
        return {'results':[{**reading(),'region_id':t['region_id']} for t in json.loads(prompt)['tasks']]},{}
    e=SimpleNamespace(s=s,provider=SimpleNamespace(call=call),checkpoint=lambda *a:None)
    run={'options':{'vision_model':'gpt-5.4'},'calls':[],'observation':{'objects':[]}}
    o.run_text_ocr(e,{'id':'job'},run,raw.getvalue())
    assert run['text_ocr']['regions'][1]['verdict']['error_type']=='OCR_OMISSION'
    assert run['text_ocr']['vision_checked']==2


def test_missing_ocr_process_fails_open_for_workflow_but_never_for_quality(tmp_path,monkeypatch):
    s=Settings({'DATA_DIR':str(tmp_path),'OCR_PYTHON':'/missing/python'})
    run={'options':{},'calls':[],'observation':{'objects':[]}}
    e=SimpleNamespace(s=s,checkpoint=lambda *a:None)
    o.run_text_ocr(e,{'id':'job'},run,b'')
    assert run['text_ocr']['status']=='UNAVAILABLE'
    rows=[{'rule_id':'D-02-l','status':'PASS','reason':'clear','evidence_ids':[],'rects':[]}]
    assert o.protect_rows(run,rows,[],'model')[0]['status']=='REVIEW'


def test_defect_region_survives_analyzer_absent_and_precise_location():
    r=region();r['vision'].update(glyph_quality='DEFECT',glyph_evidence='획이 붙음');r['verdict']=o.verdict(r)
    run={'rule_pack':PACK,'text_ocr':{'status':'COMPLETED','regions':[r]}}
    rows=o.protect_rows(run,[{'rule_id':'D-02-l','status':'NOT_APPLICABLE','reason':'none','evidence_ids':[],'rects':[]}],['D-02-l'],'gpt-5.4-mini')
    assert len(rows)==1 and rows[0]['status']=='FAIL' and rows[0]['rects']==[[.2,.3,.5,.4]]
    run['analysis_observation']={'objects':[]};o.attach_observations(run)
    assert run['analysis_observation']['objects'][0]['id']=='OCR001'


def test_readable_ocr_does_not_erase_existing_typo_finding():
    r=region();r['verdict']=o.verdict(r)
    run={'rule_pack':PACK,'text_ocr':{'status':'COMPLETED','regions':[r]}}
    original={'rule_id':'D-02-l','status':'FAIL','reason':'공식 기관명 오탈자','evidence_ids':['O1'],'rects':[r['rect']]}
    rows=o.protect_rows(run,[original],['D-02-l'],'gpt-5.4-mini')
    assert rows[0]['status']=='FAIL' and rows[0]['reason']=='공식 기관명 오탈자'
    assert rows[1]['status']=='REVIEW'


def test_ocr_regions_are_usable_evidence_for_text_rules_only():
    objects=[{'id':'scene'},{'id':'OCR001','ocr_region':True}]
    run={'analysis_observation':{'objects':objects,'summary':'scene'}}
    assert [o['id'] for o in o.analysis_observation(run,['D-02-l'])['objects']]==['scene','OCR001']
    assert [o['id'] for o in o.analysis_observation(run,['H-04-h'])['objects']]==['scene']
    assert len(run['analysis_observation']['objects'])==2


def test_untranscribable_source_defect_is_distinct_from_engine_failure():
    r=region();r['vision'].update(literal_text='□□',uncertain_characters=['전체 번짐'],glyph_quality='DEFECT',glyph_evidence='원본 줄 전체 획 경계가 번져 있음')
    assert o.verdict(r)['status']=='FAIL'
    r['vision'].update(glyph_quality='UNCERTAIN',glyph_evidence='작은 글자라 손상 여부 판단 불가')
    assert o.verdict(r)['status']=='REVIEW'


def test_meaning_uncertainty_does_not_hide_reference_name_error():
    r=region();r['vision']['spelling']='UNCERTAIN';r['verdict']=o.verdict(r)
    run={'rule_pack':PACK,'text_ocr':{'status':'COMPLETED','regions':[r]}}
    original={'rule_id':'D-02-l','status':'FAIL','reason':'승인 명칭과 다름','evidence_ids':['OCR001'],'rects':[r['rect']]}
    assert o.protect_rows(run,[copy.deepcopy(original)],['D-02-l'],'gpt-5.4')[0]['status']=='FAIL'
    r['vision']['inferred']=True;r['verdict']=o.verdict(r)
    assert o.protect_rows(run,[copy.deepcopy(original)],['D-02-l'],'gpt-5.4')[0]['status']=='REVIEW'


def test_naver_word_order_is_stable_across_y_bin_boundary():
    a={'text':'가','rect':[.1,.199,.2,.23],'score':.99}
    b={'text':'나','rect':[.3,.201,.4,.231],'score':.99}
    c={'text':'다','rect':[.5,.198,.6,.23],'score':.99}
    assert [f['text'] for _,f in o.reading_order([(0,c),(1,b),(2,a)])]==['가','나','다']
