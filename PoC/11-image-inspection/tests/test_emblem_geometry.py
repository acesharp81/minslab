import copy
import hashlib
import io
from PIL import Image,ImageDraw
from app import emblem_geometry as geometry
from app.rules import PACK


def drawing(bars=3,size=300):
    image=Image.new('RGB',(size,size),'white');d=ImageDraw.Draw(image);s=size/300
    box=lambda xs:tuple(round(x*s) for x in xs)
    d.ellipse(box((15,15,285,285)),fill=(15,140,130))
    d.polygon([box(p) for p in [(150,65),(70,175),(230,175)]],fill='white')
    for y in [190,215,240][:bars]:d.rectangle(box((75,y,225,y+8)),fill='white')
    out=io.BytesIO();image.save(out,format='PNG');return out.getvalue()


def fixture(tmp_path,bars=2):
    raw=drawing(bars);source=drawing();(tmp_path/'references').mkdir()
    (tmp_path/'references/template.png').write_bytes(source)
    ref=dict(id='ref',name='테스트안내단 문양',kind='official-emblems',status='APPROVED',parent_ids=['H-07'],
             image_file='template.png',image_hash=hashlib.sha256(source).hexdigest())
    obj=dict(id='logo',label='테스트안내단 문양',description='정면 도형',quality='CLEAR',cell_ids=['R07C07'])
    return raw,ref,obj


def test_missing_component_is_measured_and_normal_scale_is_not_flagged(tmp_path):
    raw,ref,obj=fixture(tmp_path)
    result=geometry.inspect(raw,{'objects':[obj]},[ref],tmp_path)
    check=result['checks'][0]
    assert check['status']=='MISMATCH' and check['reference_components']==4 and check['observed_components']==3
    normal=geometry.inspect(drawing(3,180),{'objects':[obj]},[ref],tmp_path)
    assert normal['checks'][0]['status']=='MATCH'
    assert not geometry.inspect(drawing(3,60),{'objects':[obj]},[ref],tmp_path)['checks']
    obj['text']='기관 이름'
    assert not geometry.inspect(raw,{'objects':[obj]},[ref],tmp_path)['checks']
    obj.pop('text')
    obj['quality']='OCCLUDED'
    assert not geometry.inspect(raw,{'objects':[obj]},[ref],tmp_path)['checks']


def test_wrong_reference_hash_and_unrelated_location_never_generate_verdict(tmp_path):
    raw,ref,obj=fixture(tmp_path)
    ref['image_hash']='invalid'
    assert not geometry.inspect(raw,{'objects':[obj]},[ref],tmp_path)['checks']
    ref['image_hash']=hashlib.sha256(drawing()).hexdigest();obj['cell_ids']=['R01C01']
    assert not geometry.inspect(raw,{'objects':[obj]},[ref],tmp_path)['checks']


def test_colour_change_or_cropped_circle_cannot_be_certified_as_matching(tmp_path):
    raw,ref,obj=fixture(tmp_path,3)
    image=Image.open(io.BytesIO(raw));pixels=image.load()
    for y in range(image.height):
        for x in range(image.width):
            if pixels[x,y]==(15,140,130):pixels[x,y]=(20,185,173)
    out=io.BytesIO();image.save(out,format='PNG')
    assert not geometry.inspect(out.getvalue(),{'objects':[obj]},[ref],tmp_path)['checks']
    cropped=Image.open(io.BytesIO(raw)).crop((80,0,300,300));out=io.BytesIO();cropped.save(out,format='PNG')
    assert not geometry.inspect(out.getvalue(),{'objects':[obj]},[ref],tmp_path)['checks']


def test_measurement_preserves_original_model_opinion_and_other_actions(tmp_path):
    raw,ref,obj=fixture(tmp_path)
    run=dict(rule_pack=copy.deepcopy(PACK),observation={'objects':[obj]},reference_snapshot=[ref],observation_model='gpt-5.4',
             emblem_geometry=geometry.inspect(raw,{'objects':[obj]},[ref],tmp_path))
    prior=dict(rule_id='H-07-b',status='PASS',evidence_ids=['logo'],reason='모델의 원래 의견')
    unrelated=dict(rule_id='D-02-l',status='REVIEW',reason='별도 문자 문제')
    rows=geometry.protect(run,[prior,unrelated],['H-07-b'])
    row=next(r for r in rows if r['rule_id']=='H-07-b')
    assert row['status']=='FAIL' and row['model']=='system/emblem-geometry'
    assert row['model_verdicts_before_geometry']==[prior] and unrelated in rows
    assert not geometry.protect(run,[],['D-02-l'])


def test_confirmed_match_retracts_only_repeated_count_claim_without_inventing_pass(tmp_path):
    raw,ref,obj=fixture(tmp_path,3)
    run=dict(rule_pack=copy.deepcopy(PACK),observation={'objects':[obj]},reference_snapshot=[ref],
             emblem_geometry=geometry.inspect(raw,{'objects':[obj]},[ref],tmp_path))
    rows=[dict(rule_id='D-02-m',status='FAIL',evidence_ids=['logo'],reason='하단 막대가 4개로 기준과 다르다.'),
          dict(rule_id='D-02-o',status='FAIL',evidence_ids=['logo'],reason='막대 수가 다르고 색상도 다르다.'),
          dict(rule_id='D-02-l',status='FAIL',evidence_ids=['logo'],reason='실제 문자 결함')]
    result=geometry.protect(run,rows,['D-02-m','D-02-o','D-02-l'])
    assert result[0]['status']=='REVIEW' and not result[0]['visual_issue'] and result[0]['document_review']
    assert result[0]['model_verdicts_before_geometry'][0]['status']=='FAIL'
    assert result[1]['status']=='FAIL' and result[2]['status']=='FAIL'
