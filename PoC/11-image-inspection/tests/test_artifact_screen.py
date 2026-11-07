import copy
import io
from pathlib import Path
from types import SimpleNamespace
import pytest
import numpy as np
from PIL import Image,ImageDraw,ImageFont,ImageFilter
from app import artifact_screen as a, text_routing, verification
from app.config import Settings
from app.rules import STEPS

FONT=Path('/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc')

def fixture(text='한',blur=0,transcript=None):
    if not FONT.exists():pytest.skip('Independent Korean font unavailable')
    face=ImageFont.truetype(str(FONT),48,index=1)
    image=Image.new('RGB',(max(100,len(text)*54+24),90),'white')
    ImageDraw.Draw(image).text((12,0),text,font=face,fill='black')
    if blur:image=image.filter(ImageFilter.GaussianBlur(blur))
    data=io.BytesIO();image.save(data,format='PNG')
    region={'id':'OCR1','rect':[0,0,1,1],'source':'paddle-detector','detection_score':.95,'recognition_score':.99,'text':text if transcript is None else transcript}
    obj={'id':'sign','text':region['text'],'rects':[region['rect']],'label':'안내문','quality':'CLEAR'}
    run={'selected':['D-02-l'],'observation':{'objects':[obj]},'pixel_text':{'status':'COMPLETED','detector_regions':[region]},'calls':[],'results':[{'id':'f','status':'PASS'}]}
    return data.getvalue(),run


def test_single_syllable_and_empty_transcript_keep_source_blur_without_verdicts():
    for transcript in ('한',''):
        raw,run=fixture(blur=3,transcript=transcript);before=copy.deepcopy(run)
        report=a.collect(raw,run)
        assert 'LOCAL_BLUR_SIGNAL' in report['signals']
        assert all(c['status']=='CANDIDATE_ONLY' and not c['automatic_fail'] for c in report['candidates'])
        assert run==before and report['api_calls']==0
        if not transcript:assert 'DETECTED_UNREAD' in report['signals']


def test_clear_text_low_confidence_and_blank_do_not_become_blur():
    raw,run=fixture('한글');run['pixel_text']['detector_regions'][0]['recognition_score']=.01
    assert 'LOCAL_BLUR_SIGNAL' not in a.collect(raw,run)['signals']
    data=io.BytesIO();Image.new('RGB',(200,90),'white').save(data,format='PNG')
    run['pixel_text']['detector_regions'][0]['text']=''
    result=a.collect(data.getvalue(),run)
    assert 'LOCAL_BLUR_SIGNAL' not in result['signals']
    assert result['candidates'][0]['signals']==['DETECTED_UNREAD']


def test_overlapping_long_windows_and_inverse_coordinates_are_bounded():
    image=Image.new('RGB',(1800,60));boxes=list(a.windows(image))
    assert len(boxes)==6 and boxes[0][0]==0 and boxes[-1][2]==1800
    # Shorter lines have 50% overlap; long lines preserve endpoint coverage under cap.
    boxes=list(a.windows(Image.new('RGB',(400,60))))
    assert all(b[0]<prev[2] for prev,b in zip(boxes,boxes[1:]))
    inverse=np.array([[1.,0,10],[0,1.,20],[0,0,1.]])
    assert a.map_box([0,0,100,50],inverse,(200,100))==[.05,.2,.55,.7]


def test_rotated_geometry_is_supplementary_and_maps_to_original():
    raw,run=fixture('한글 테스트',blur=3);image=Image.open(io.BytesIO(raw));w,h=image.size
    r=run['pixel_text']['detector_regions'][0]
    r['polygon_px']=[[0,0],[w,20],[w,h],[0,h-20]]
    crop,inverse,rectified=a.oriented_crop(image,r)
    assert rectified and crop.width>0
    mapped=a.map_box([0,0,crop.width,crop.height],inverse,image.size)
    assert all(0<=v<=1 for v in mapped) and mapped[2]>.99 and mapped[3]>.99
    result=a.collect(raw,run);assert result['diagnostics'][0]['state']=='MEASURED'
    assert all(c['automatic_fail'] is False for c in result['candidates'])


def test_invalid_geometry_and_limits_are_not_errors_in_the_image():
    raw,run=fixture();r=run['pixel_text']['detector_regions'][0]
    r['polygon_px']=[[0,0],[float('nan'),0],[100,90],[0,90]]
    run['pixel_text']['detector_regions'].append({**r,'id':'second'})
    report=a.collect(raw,run,max_regions=1)
    assert [d['state'] for d in report['diagnostics']]==['INVALID_POLYGON','REGION_LIMIT']
    assert not report['candidates']


def test_natural_hidden_hands_do_not_generate_candidates_and_anomalies_keep_object_location():
    raw,run=fixture();run['selected']=['D-02-c'];run['pixel_text']={}
    hand={'visible_structure':'NATURAL','visibility':'PARTIAL','pose':'GRASP','anomaly_evidence':''}
    obj={'id':'person','label':'인물','hands':[hand],'rects':[[.2,.2,.4,.6]]};run['observation']['objects']=[obj]
    assert not a.collect(raw,run)['candidates']
    hand.update(visible_structure='ANOMALOUS',anomaly_evidence='손목에서 손바닥이 두 방향으로 갈라져 보임')
    candidate=a.collect(raw,run)['candidates'][0]
    assert candidate['rects']==obj['rects'] and candidate['object_ids']==['person']
    assert candidate['location_scope']=='EXISTING_OBJECT_REGION'
    obj.pop('rects');assert not a.collect(raw,run)['candidates']


def test_default_shadow_does_not_change_routing_but_opt_in_keeps_ocr_and_quality_separate():
    raw,run=fixture(blur=3);run['artifact_screen']=a.collect(raw,run)
    assert text_routing.prepare(run)['regions'][0]['state']=='AGREED'
    assert text_routing.prepare(run,True)['regions'][0]['state']=='QUALITY_CONFLICT'
    assert run['results'][0]['status']=='PASS'


def test_screen_cache_inputs_and_disable_flag(tmp_path,monkeypatch):
    raw,run=fixture();calls=[];real=a.collect
    monkeypatch.setattr(a,'collect',lambda *args,**kw:(calls.append(1),real(*args,**kw))[1])
    engine=SimpleNamespace(s=Settings({'DATA_DIR':str(tmp_path)}),checkpoint=lambda *args:None)
    a.inspect(engine,{'id':'j'},run,raw);a.inspect(engine,{'id':'j'},run,raw);assert len(calls)==1
    run['pixel_text']['detector_regions'][0]['text']='';a.inspect(engine,{'id':'j'},run,raw);assert len(calls)==2
    engine.s=Settings({'DATA_DIR':str(tmp_path),'ARTIFACT_SCREEN_ENABLED':'false'})
    a.inspect(engine,{'id':'j'},run,raw);assert len(calls)==2


def test_opt_in_candidate_recheck_still_obeys_reuse_and_shared_cap(tmp_path):
    raw,run=fixture(blur=3);run['artifact_screen']=a.collect(raw,run);run['options']={'text_sensitivity':'strict'}
    engine=SimpleNamespace(s=Settings({'DATA_DIR':str(tmp_path),'ARTIFACT_RECHECK_ENABLED':'true','AUTO_VERIFY_MAX_CALLS':'0'}),
        checkpoint=lambda *args:None,provider=SimpleNamespace(call=lambda *a,**k:pytest.fail('No external call allowed')))
    text_routing.recheck(engine,{'id':'j'},run,raw)
    assert run['text_routing']['regions'][0]['deferred_reason']=='SHARED_CROP_CALL_LIMIT'
    assert not run['calls']


def test_optional_screen_failure_never_changes_saved_findings(tmp_path,monkeypatch):
    raw,run=fixture();original=copy.deepcopy(run['results'])
    def broken(*args,**kwargs):raise KeyError('malformed imported detector record')
    monkeypatch.setattr(a,'collect',broken)
    engine=SimpleNamespace(s=Settings({'DATA_DIR':str(tmp_path)}),checkpoint=lambda *args:None)
    a.inspect(engine,{'id':'j'},run,raw)
    assert run['artifact_screen']['status']=='UNAVAILABLE'
    assert run['results']==original and not run['calls']
