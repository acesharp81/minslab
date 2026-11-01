import io,hashlib,json
from pathlib import Path
from types import SimpleNamespace
import pytest
from PIL import Image,ImageDraw,ImageFont,ImageFilter
from app import pixel_text as p,pixel_confirm as c

FONT=Path('/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc')

def raw_word(text,font=FONT,blur=0):
    if not font.exists():pytest.skip('Independent font fixture unavailable')
    face=ImageFont.truetype(str(font),48,index=1)
    im=Image.new('RGB',(max(200,len(text)*54),90),'white');ImageDraw.Draw(im).text((12,0),text,font=face,fill='black')
    if blur:im=im.filter(ImageFilter.GaussianBlur(blur))
    out=io.BytesIO();im.save(out,format='PNG');return out.getvalue(),im

def region(text):return dict(rect=[0,0,1,1],text=text,source='paddle-detector',detection_score=.95)

def test_real_shapes_distinguish_misspelled_vowel_without_dictionary():
    raw,_=raw_word('안젼한 하루');r=p.inspect_regions(raw,[region('안전한 하루')])[0]
    assert r['shape_conflict'] and r['shape_text']=='안젼한 하루'
    raw,_=raw_word('안전한 하루');r=p.inspect_regions(raw,[region('안전한 하루')])[0]
    assert not r.get('shape_conflict') and not r['blur_observed']

def test_clear_normal_food_and_different_final_are_not_collapsed():
    for literal,ocr in [('비빔밥','비빙밥'),('비빔밤','비빙밤')]:
        raw,_=raw_word(literal);r=p.inspect_regions(raw,[region(ocr)])[0]
        assert r['shape_text']==literal

def test_blur_is_measured_from_source_even_if_transcript_is_readable():
    raw,_=raw_word('문자 가독성 검사',blur=3);r=p.inspect_regions(raw,[region('문자 가독성 검사')])[0]
    assert r['blur_observed'] and r['metrics']['edge_strength']<1.5
    raw,_=raw_word('문자 가독성 검사');assert not p.inspect_regions(raw,[region('문자 가독성 검사')])[0]['blur_observed']

def test_blank_unknown_font_and_short_crop_do_not_create_quality_pass():
    im=Image.new('RGB',(200,90),'white');b=io.BytesIO();im.save(b,format='PNG')
    assert p.inspect_regions(b.getvalue(),[region('읽혔다고 주장')])==[]
    raw,_=raw_word('기울임 글자',Path('/usr/share/fonts/opentype/noto/NotoSerifCJK-Light.ttc'))
    assert not any(x.get('blur_observed') for x in p.inspect_regions(raw,[region('기울임 글자')]))

def test_confirmation_hides_words_and_is_one_call_with_no_retry():
    raw,_=raw_word('안젼한 하루');regions=p.inspect_regions(raw,[region('안전한 하루')]);audit=dict(status='COMPLETED',regions=regions)
    run={'pixel_text':audit,'calls':[]};calls=[]
    def call(model,prompt,images,workload):
        assert model=='gpt-5.4' and workload=='text-pixel-confirm'
        assert '안전' not in prompt and '안젼' not in prompt
        body=json.loads(prompt);calls.append(body)
        return {'results':[dict(region_id=t['region_id'],choice_id='NONE',quality='UNCERTAIN',evidence='구분 보류') for t in body['tasks']]},{'event_id':'test'}
    engine=SimpleNamespace(provider=SimpleNamespace(call=call),checkpoint=lambda *a:None)
    c.confirm(engine,{'id':'j'},run,raw);c.confirm(engine,{'id':'j'},run,raw)
    assert len(calls)==1 and not any(r.get('shape_confirmed') for r in regions)

def test_rotated_detector_polygon_is_unsupported_not_a_defect():
    raw,_=raw_word('안젼한 하루')
    r={**region('안전한 하루'),'polygon_px':[[0,0],[300,45],[300,90],[0,45]]}
    assert p.inspect_regions(raw,[r])==[]

def test_unconfirmed_shape_cannot_be_forced_to_fail_or_pass():
    evidence=dict(id='PXT001',rect=[.1,.1,.4,.2],shape_conflict=True,shape_confirmed=False)
    for status in ('FAIL','PASS'):
        row=dict(rule_id='D-02-l',evidence_ids=['PXT001'],status=status)
        p.protect({'pixel_text':{'regions':[evidence]}},[row],['D-02-l'])
        assert row['status']=='REVIEW' and row['error_type']=='OCR_MISMATCH'

def test_missing_atlas_does_not_abort_checklist(monkeypatch):
    raw,_=raw_word('안젼한 하루');regions=p.inspect_regions(raw,[region('안전한 하루')])
    def unavailable():raise OSError('missing asset')
    monkeypatch.setattr(p,'atlas',unavailable)
    run={'pixel_text':{'status':'COMPLETED','regions':regions},'calls':[]}
    engine=SimpleNamespace(checkpoint=lambda *a:None)
    c.confirm(engine,{'id':'j'},run,raw)
    assert run['pixel_text']['confirmation']['status']=='UNAVAILABLE' and not run['calls']
