import io,json,re
from pathlib import Path
import pytest
from PIL import Image
from app.config import ROOT
from app.imaging import normalize,cell_rect,crop,global_rect
from app.rules import PACK,STEPS,Batch,validate_batch,rollup,placeholder

def finding(rule='D-02-e',**extra):
    return {'rule_id':rule,'instance_id':'hand1','status':'PASS','observation':'손 구조 확인','reason':'명확한 관찰 근거','evidence_quality':'CLEAR','cell_ids':['R07C03'],'reference_ids':[],'recommended_action':'검토',**extra}

def test_original_25_and_every_atomic_action_preserved():
    text=(ROOT/'docs/requirements.md').read_text()
    assert len(PACK['parents'])==25 and len(STEPS)==156
    assert {p['category']:sum(x['category']==p['category'] for x in PACK['parents']) for p in PACK['parents']}==dict(H=9,E=7,P=5,D=4)
    for p in PACK['parents']:assert '**원문:** '+p['original'] in text
    expected=re.findall(r'^- `([HEPD]-\d\d-[a-z]+)`',text,re.M)
    assert set(expected)==set(STEPS)

@pytest.mark.parametrize('bad',['R00C01','R01C13','R13C01','R1C1','../x','bbox'])
def test_invalid_grid_rejected(bad):
    with pytest.raises(ValueError):validate_batch({'results':[finding(cell_ids=[bad])]},['D-02-e'],[])

def test_model_coordinates_and_unknown_rules_rejected():
    with pytest.raises(ValueError):Batch.model_validate({'results':[finding(bbox=[0,0,1,1])]})
    with pytest.raises(ValueError):validate_batch({'results':[finding(rule='D-02-j')]},['D-02-e'],[])

def test_missing_steps_and_duplicate_instances():
    rows=validate_batch({'results':[finding()]},['D-02-e','D-02-f'],[])
    assert rows[1]['status']=='ERROR'
    with pytest.raises(ValueError):validate_batch({'results':[finding(),finding()]},['D-02-e'],[])

def test_all_instances_preserved():
    rows=validate_batch({'results':[finding(instance_id=f'hand-{i}') for i in range(4)]},['D-02-e'],[])
    assert len(rows)==4

@pytest.mark.parametrize('rule',['H-04-i','D-01-c','D-03-e','E-01-a'])
def test_evidence_or_context_cannot_be_automatic_pass(rule):
    assert validate_batch({'results':[finding(rule)]},[rule],[])[0]['status']=='REVIEW'

@pytest.mark.parametrize('quality',['UNCERTAIN','OCCLUDED','NOT_VISIBLE'])
def test_uncertainty_not_pass(quality):
    assert validate_batch({'results':[finding(evidence_quality=quality)]},['D-02-e'],[])[0]['status']=='REVIEW'

def test_only_approved_references_and_scope():
    ref={'id':'ref1','status':'APPROVED','kind':'official-symbols','parent_ids':['H-04']}
    f=finding('H-04-i',reference_ids=['ref1'])
    assert validate_batch({'results':[f]},['H-04-i'],[ref])[0]['status']=='PASS'
    ref['parent_ids']=['H-01']
    assert validate_batch({'results':[f]},['H-04-i'],[ref])[0]['status']=='REVIEW'
    ref['status']='DRAFT'
    with pytest.raises(ValueError):validate_batch({'results':[f]},['H-04-i'],[ref])

def test_rollup_never_hides_error_or_not_run():
    rows=[placeholder('D-02-e','REVIEW'),placeholder('D-02-f','ERROR'),placeholder('D-02-g','NOT_RUN')]
    parent=next(p for p in rollup(rows) if p['id']=='D-02')
    assert parent['status']=='REVIEW' and not parent['complete']
    assert parent['counts']==dict(REVIEW=1,ERROR=1,NOT_RUN=1)
    rows.append(placeholder('D-02-h','FAIL'))
    assert next(p for p in rollup(rows) if p['id']=='D-02')['status']=='FAIL'

def test_image_normalization_and_crop_transform():
    im=Image.new('RGB',(1200,600));buf=io.BytesIO();exif=im.getexif();exif[274]=6;im.save(buf,format='JPEG',exif=exif)
    raw,meta=normalize(buf.getvalue(),'image.jpg','image/jpeg',24000000)
    assert (meta['width'],meta['height'])==(600,1200)
    assert not Image.open(io.BytesIO(raw)).getexif()
    sub,rect=crop(raw,['R02C02','R03C03']);assert Image.open(io.BytesIO(sub)).size==(100,200)
    result=global_rect('R01C01',rect)
    assert result[:2]==rect[:2] and result[2]<rect[2]
    with pytest.raises(ValueError):normalize(buf.getvalue(),'x.png','image/png',24000000)
    with pytest.raises(ValueError):normalize(buf.getvalue(),'x.jpg','image/jpeg',100)

def test_no_box_for_na_or_document():
    assert not validate_batch({'results':[finding(status='NOT_APPLICABLE')]},['D-02-e'],[])[0]['rects']
    assert not validate_batch({'results':[finding(evidence_quality='DOCUMENT')]},['D-02-e'],[])[0]['rects']


def test_license_document_requirement_is_not_absence():
    result=validate_batch({'results':[finding('D-03-e',status='NOT_APPLICABLE',observation='',reason='증빙 없음')]},['D-03-e'],[])[0]
    assert result['status']=='REVIEW' and result['evidence_quality']=='DOCUMENT'
    assert not result['rects'] and '라이선스' in result['recommended_action']
