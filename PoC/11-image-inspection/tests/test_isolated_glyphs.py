import copy,io,json
from types import SimpleNamespace
from PIL import Image,ImageDraw
from app import isolated_glyphs as iso


def test_segmentation_groups_disconnected_jamo_without_using_expected_count():
    im=Image.new('RGB',(150,60),'white');d=ImageDraw.Draw(im)
    for x in (10,54,98):
        d.rectangle((x,12,x+17,47),fill='black');d.rectangle((x+23,12,x+28,47),fill='black')
    b=io.BytesIO();im.save(b,format='PNG');pieces=iso.split_word(b.getvalue(),[0,0,1,1])
    assert len(pieces)==3
    for raw,rect in pieces:
        part=Image.open(io.BytesIO(raw));assert part.height>=36 and part.width>=29
        assert 0<=rect[0]<rect[2]<=1 and 0<=rect[1]<rect[3]<=1
    tiny=io.BytesIO();Image.new('RGB',(20,10),'white').save(tiny,format='PNG')
    assert iso.split_word(tiny.getvalue(),[0,0,1,1])==[]


def test_two_blind_readers_cannot_overwrite_visual_defect_or_use_transcript(monkeypatch):
    from app.glyph_audit import assess
    from test_glyph_audit import reading,region
    r=region();r['detector_text']='비빙밤';r['assessment']=assess(r,reading())
    monkeypatch.setattr(iso,'split_word',lambda *a:[(b'a',[.2,.3,.3,.4]),(b'b',[.3,.3,.4,.4])])
    def call(model,prompt,images,workload):
        assert '비빙밤' not in prompt and 'source' not in prompt and workload=='text-glyph-isolated'
        return {'results':[dict(region_id=t['region_id'],coverage='COMPLETE',units=[dict(char='밤',strokes='ㅂ ㅏ ㅁ',certain=True)],quality='CLEAR',evidence='자모 확인',defect_rects=[]) for t in json.loads(prompt)['tasks']]},{'model':model}
    engine=SimpleNamespace(provider=SimpleNamespace(call=call),checkpoint=lambda *a:None)
    run={'glyph_audit':{'regions':[r]},'calls':[]}
    iso.run_isolated(engine,{'id':'j'},run,b'raw')
    assert r['isolated_glyphs']['agreed'] and not r['assessment']['transcription_confirmed']
    assert '줄 단위 판독' in r['assessment']['reason']
    assert r['assessment']['literal_text']=='밤밤' and r['assessment']['status']=='REVIEW'
    r['assessment']['status']='FAIL';before=copy.deepcopy(r['assessment'])
    iso.run_isolated(engine,{'id':'j'},run,b'raw');assert r['assessment']==before


def test_reader_disagreement_does_not_promote_transcription(monkeypatch):
    from app.glyph_audit import assess
    from test_glyph_audit import reading,region
    r=region();r['detector_text']='비빙밤';r['assessment']=assess(r,reading());before=copy.deepcopy(r['assessment'])
    monkeypatch.setattr(iso,'split_word',lambda *a:[(b'a',[.2,.3,.3,.4]),(b'b',[.3,.3,.4,.4])])
    def call(model,prompt,images,workload):
        return {'results':[dict(region_id=t['region_id'],coverage='COMPLETE',units=[dict(char='밤' if model=='gpt-5.4' else '밥',strokes='받침 확인',certain=True)],quality='CLEAR',evidence='획 확인',defect_rects=[]) for t in json.loads(prompt)['tasks']]},{}
    engine=SimpleNamespace(provider=SimpleNamespace(call=call),checkpoint=lambda *a:None)
    run={'glyph_audit':{'regions':[r]},'calls':[]};iso.run_isolated(engine,{'id':'j'},run,b'raw')
    assert not r['isolated_glyphs']['agreed'] and not r['assessment']['transcription_confirmed']
    assert r['assessment']['literal_text']==before['literal_text'] and r['assessment']['status']=='REVIEW'
