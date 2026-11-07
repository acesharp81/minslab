import copy
import io
import json
from types import SimpleNamespace

import httpx
from PIL import Image
from app import glyph_audit as g, text_location as loc
from app.config import Settings
from app.providers import Provider
from test_provider import Meter


def reading(**overrides):
    return dict(region_id='GLY001',coverage='COMPLETE',units=[dict(char='안',strokes='ㅇ,ㅏ,ㄴ이 분리됨',certain=True)],quality='CLEAR',evidence='획 경계 확인',defect_rects=[],**overrides)


def region():
    return dict(id='GLY001',rect=[.2,.3,.5,.4],crop_rect=[.18,.28,.52,.42],detector_text='안',detector_score=.99,source_ids=['label'])


def test_agreement_cannot_certify_quality_and_uncertain_is_not_defect():
    r=region();a=g.assess(r,reading())
    assert a['status']!='PASS' and not a['issue'] and a['transcription_confirmed']
    v=reading();v.update(quality='DEFECT',defect_rects=[[.1,.2,.4,.8]],evidence='받침 획이 본문 획에 붙음')
    a=g.assess(r,v);assert a['status']=='FAIL' and a['location_verified']
    v['coverage']='PARTIAL';assert g.assess(r,v)['status']=='REVIEW'
    v['coverage']='COMPLETE';v['defect_rects']=[[0.,0.,.1,.1]]
    assert g.assess(r,v)['status']=='REVIEW' # crop edge / padding is not source damage
    v['defect_rects']=[[.1,.2,2.,.8]];assert g.assess(r,v)['status']=='REVIEW'


def test_character_contract_disagreement_and_missing_target():
    r=region();v=reading();v['units'][0]['char']='안전'
    a=g.assess(r,v);assert a['literal_text']=='□' and not a['transcription_confirmed']
    v=reading();r['detector_text']='앉';a=g.assess(r,v)
    assert a['error_type']=='OCR_MISMATCH' and a['status']=='REVIEW'
    v['coverage']='MISSING';assert not g.assess(r,v)['location_verified']


def test_unreadable_transcription_keeps_observed_blur_but_not_reading_failure_visible():
    from app.rules import PACK
    r=region();v=reading()
    v.update(units=[dict(char='□',strokes='번짐으로 획 분리 불가',certain=False)],
             quality='DEFECT',evidence='첫 블록 내부 획 경계가 넓게 번져 합쳐짐',defect_rects=[[.1,.2,.4,.8]])
    r['assessment']=g.assess(r,v)
    run={'glyph_audit':{'model':'gpt-5.4','regions':[r]},'rule_pack':PACK,'reference_snapshot':[]}
    row=g.protect(run,[],['D-02-l'],'gpt-5.4-mini')[0]
    assert not r['assessment']['transcription_confirmed']
    assert row['status']=='FAIL' and row['visual_issue'] and not row['diagnostic_only']
    v.update(quality='UNCERTAIN',evidence='작아서 읽지 못함',defect_rects=[])
    r['assessment']=g.assess(r,v)
    row=g.protect(run,[],['D-02-l'],'gpt-5.4-mini')[0]
    assert row['status']=='REVIEW' and row['diagnostic_only'] and not row['visual_issue']
    assert row['error_type']=='OCR_UNCERTAIN'
    assert 'OCR 전사가 다릅니다' not in row['reason']


def test_overlapping_windows_preserve_pixels_without_synthetic_strokes():
    im=Image.new('RGB',(180,20),'white');im.putpixel((55,7),(1,2,3));out=io.BytesIO();im.save(out,format='PNG')
    raw,starts=g.windows(out.getvalue());sheet=Image.open(io.BytesIO(raw))
    assert starts[0]==0 and starts[-1]+sheet.width==180
    assert all(b-a<sheet.width for a,b in zip(starts,starts[1:]))
    for i,x in enumerate(starts):
        assert sheet.crop((0,i*28,60,i*28+20)).tobytes()==im.crop((x,0,x+60,20)).tobytes()


def test_provider_shape_path_original_and_metered(tmp_path,monkeypatch):
    s=Settings({'DATA_DIR':str(tmp_path),'OPENAI_API_KEY':'test','OPENAI_BASE_URL':'https://example.org/v1'})
    real=httpx.Client;seen=[]
    def respond(req):
        b=json.loads(req.content);seen.append(b)
        assert b['text']['format']['schema']['$defs']['ShapeReading']['properties']['region_id']['enum']==['GLY001']
        return httpx.Response(200,json={'status':'completed','usage':{'input_tokens':12,'output_tokens':20},'output':[{'type':'message','content':[{'type':'output_text','text':json.dumps({'results':[reading()]})}]}]})
    monkeypatch.setattr('app.providers.httpx.Client',lambda **kw:real(transport=httpx.MockTransport(respond),**kw))
    _,meta=Provider(s,Meter()).call('gpt-5.4',json.dumps({'tasks':[{'region_id':'GLY001','image_index':0,'windows_image_index':1}]}),[b'image',b'image'],workload='text-shape')
    assert meta['usage']=={'input_tokens':12,'output_tokens':20}
    assert seen[0]['reasoning']['effort']=='medium'
    assert all(c['detail']=='original' for c in seen[0]['input'][0]['content'] if c['type']=='input_image')


def test_blind_payload_has_no_ocr_transcript_or_scene_label(tmp_path,monkeypatch):
    s=Settings({'DATA_DIR':str(tmp_path),'GLYPH_AUDIT_MAX_REGIONS':'4'})
    r=region();r['detector_text']='SECRET-PRIOR-READING'
    monkeypatch.setattr(g,'candidates',lambda *a:[r])
    out=io.BytesIO();Image.new('RGB',(500,500),'white').save(out,format='PNG')
    def call(model,prompt,images,workload):
        assert model=='gpt-5.4' and workload=='text-shape' and len(images)==2
        assert 'SECRET' not in prompt and 'label' not in prompt
        return {'results':[reading()]},{'model':model}
    engine=SimpleNamespace(s=s,provider=SimpleNamespace(call=call),checkpoint=lambda *a:None)
    run={'calls':[]};g.run_audit(engine,{'id':'j'},run,out.getvalue())
    assert run['glyph_audit']['status']=='COMPLETED'
    assert run['glyph_audit']['regions'][0]['assessment']['error_type']=='OCR_MISMATCH'


def test_localizer_rebinds_unique_source_not_suggested_correction():
    r=region();r['assessment']=g.assess(r,reading());run={'glyph_audit':{'regions':[r]}}
    row=dict(rule_id='D-02-l',status='FAIL',evidence_ids=['wrong'],rects=[[.8,.8,.9,.9]],official_term_check={'literal':'안','canonical':'앉'})
    loc.protect(run,[row]);assert row['rects']==[r['rect']] and row['evidence_ids']==['GLY001']
    assert row['location_evidence']['previous']['evidence_ids']==['wrong']
    assert row['status']=='FAIL'
    row=dict(rule_id='D-02-l',status='FAIL',evidence_ids=['label'],rects=[[.8,.8,.9,.9]],official_term_check={'literal':'앉','canonical':'안'})
    loc.protect(run,[row]);assert row['location_unresolved'] and row['rects']==[] and row['status']=='FAIL'


def test_duplicate_text_stays_unlocated_and_unchecked_regions_unchanged():
    r=region();r['assessment']=g.assess(r,reading());r2=copy.deepcopy(r);r2['id']='GLY002';r2['rect']=[.6,.6,.8,.7]
    row=dict(rule_id='D-02-l',status='FAIL',evidence_ids=['label'],rects=[[.2,.3,.5,.4]],official_term_check={'literal':'안'})
    loc.protect({'glyph_audit':{'regions':[r,r2]}},[row]);assert row['location_unresolved']
    original=dict(rule_id='D-02-l',status='FAIL',evidence_ids=['unchecked'],rects=[[.8,.8,.9,.9]],official_term_check={'literal':'찾기'})
    row=copy.deepcopy(original);loc.protect({'glyph_audit':{'regions':[r]}},[row]);assert row==original

def test_location_uses_existing_independent_crop_without_another_model_call():
    check=dict(object_id='label',status='COMPLETED',coverage='COMPLETE',quality='CLEAR',transcription_inferred=False,text='행정안정부',crop_rect=[.4,.4,.8,.6],cell_ids=['R04C03','R04C04'])
    row=dict(rule_id='D-02-l',status='FAIL',evidence_ids=['other'],rects=[[.1,.1,.2,.2]],official_term_check={'literal':'행정안정부'})
    loc.protect({'verification':{'results':[check]}},[row])
    assert row['evidence_ids']==['label'] and all(r[0]>=.4 for r in row['rects'])
    assert row['location_evidence']['method']=='independent-crop-reading'
    check['cell_ids']=['R01C01','R08C08'];assert loc.verified_regions({'verification':{'results':[check]}})==[]
    check['cell_ids']=['R04C03'];check['coverage']='PARTIAL'
    assert loc.verified_regions({'verification':{'results':[check]}})==[]

def test_audit_reuses_one_rule_row_instead_of_duplicating_the_same_concern():
    from app.rules import PACK
    r=region();r['detector_text']='앉';r['assessment']=g.assess(r,reading())
    run={'glyph_audit':{'model':'gpt-5.4','regions':[r]},'rule_pack':PACK,'reference_snapshot':[]}
    rows=g.protect(run,[],['D-02-l'],'gpt-5.4-mini')
    rows=g.protect(run,rows,['D-02-l'],'gpt-5.4-mini')
    assert len(rows)==1 and rows[0]['status']=='REVIEW' and rows[0]['glyph_audit_evidence']['id']==r['id']


def test_partial_localized_source_damage_is_reviewed_not_hidden_or_certified():
    from app.rules import PACK
    r=region();v=reading();v.update(coverage='PARTIAL',quality='DEFECT',defect_rects=[[.1,.2,.4,.8]],evidence='원본 내부 받침 획 융합')
    r['assessment']=g.assess(r,v)
    run={'glyph_audit':{'model':'gpt-5.4','regions':[r]},'rule_pack':PACK,'reference_snapshot':[]}
    row=g.protect(run,[],['D-02-l'],'gpt-5.4-mini')[0]
    assert row['status']=='REVIEW' and row['visual_issue'] and not row['diagnostic_only']
    assert row['rects'] and not row['location_unresolved']


def test_long_transcription_prefix_is_not_a_false_ocr_conflict():
    r=region();r['detector_text']='가나다라마바사아자차카타파하'
    v=reading();v['units']=[dict(char=c,strokes='원본 획',certain=True) for c in r['detector_text'][:12]]
    a=g.assess(r,v)
    assert not a['transcription_confirmed'] and a['error_type']=='OCR_UNCERTAIN'
    assert '12음절' in a['reason']


def test_concrete_conflict_replaces_generic_review_without_duplicate_or_extra_warning():
    from app.rules import PACK
    r=region();r['detector_text']='앉';r['assessment']=g.assess(r,reading())
    run={'glyph_audit':{'model':'gpt-5.4','regions':[r]},'rule_pack':PACK,'reference_snapshot':[]}
    generic=dict(rule_id='D-02-l',status='REVIEW',reason='문자는 또렷하나 사람 검토 필요',
                 evidence_ids=['GLY001'],review_basis='DOCUMENT_CHECK',error_type='NONE',
                 visual_issue=False,document_review=True,diagnostic_only=True,rects=[])
    rows=g.protect(run,[copy.deepcopy(generic)],['D-02-l'],'gpt-5.4-mini')
    assert len(rows)==1 and rows[0]['status']=='REVIEW'
    assert rows[0]['reason']==r['assessment']['reason']
    assert rows[0]['error_type']=='OCR_MISMATCH' and rows[0]['review_basis']=='OBSERVED_ANOMALY'
    assert rows[0]['visual_issue'] and not rows[0]['document_review'] and not rows[0]['diagnostic_only']
    assert rows[0]['rects']==r['assessment']['rects']
    before=copy.deepcopy(rows[0]['before_glyph_audit'])
    g.protect(run,rows,['D-02-l'],'gpt-5.4-mini')
    assert len(rows)==1 and rows[0]['before_glyph_audit']==before
    # Mere unreadability without a concrete source defect stays diagnostic.
    v=reading();v.update(units=[dict(char='□',strokes='잘 보이지 않음',certain=False)],quality='UNCERTAIN')
    r['assessment']=g.assess(r,v)
    rows=g.protect(run,[copy.deepcopy(generic)],['D-02-l'],'gpt-5.4-mini')
    assert rows[0]['reason']==generic['reason'] and not rows[0]['visual_issue']


def test_later_uncertain_syllables_keep_earlier_detector_conflict_location():
    r=region();r['detector_text']='김처찌개'
    original=dict(issue=True,error_type='OCR_MISMATCH',location_verified=True,literal_text='김치찌개',rects=[r['rect']])
    r['before_isolated_assessment']=original
    r['assessment']=dict(issue=True,error_type='OCR_MISMATCH',transcription_confirmed=False,reason='세 번째 음절 판독 차이',rects=[[.35,.3,.4,.4]])
    r['isolated_glyphs']={'parts':[{'rect':[.2+i*.05,.3,.25+i*.05,.4]} for i in range(4)]}
    g.retain_detector_conflict(r)
    assert r['isolated_glyphs']['parts'][1]['rect'] in r['assessment']['rects']
    assert '김처찌개' in r['assessment']['reason'] and '김치찌개' in r['assessment']['reason']
    before=copy.deepcopy(r);g.retain_detector_conflict(r);assert r==before
    # Agreement of the independent readers may resolve the earlier conflict.
    r['assessment'].update(transcription_confirmed=True,reason='독립 판독 일치',rects=[])
    g.retain_detector_conflict(r);assert not r['assessment']['rects']
