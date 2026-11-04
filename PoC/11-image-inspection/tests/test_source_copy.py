import copy,hashlib,json
import pytest
from app import source_copy as s
from app.rules import PACK

RAW=b'image-fixture'

def run(first='안젼한 하루',second='안젼한 하루',expected='안전한 하루'):
    ref=dict(id='copy',name='승인 원고',kind='source-data',status='APPROVED',parent_ids=['D-02'],content=json.dumps(dict(schema=s.SCHEMA,image_sha256=hashlib.sha256(RAW).hexdigest(),entries=[dict(label='큰 제목',text=expected)]),ensure_ascii=False))
    obj=dict(id='title',label='큰 제목',text=first,quality='CLEAR',text_legibility='CLEAR',cell_ids=['R01C01'])
    return dict(rule_pack=PACK,selected=['D-02-l'],reference_snapshot=[ref],observation={'objects':[obj]},verification={'results':[dict(object_id='title',status='COMPLETED',coverage='COMPLETE',text=second,quality='CLEAR',text_legibility='CLEAR',event_id='read')]})


def test_copy_diff_after_independent_read_and_preserves_whitespace():
    r=run();c=s.inspect(r,RAW)['results'][0]
    assert c['status']=='FAIL' and c['differences'][0]['observed']=='젼' and c['differences'][0]['expected']=='전'
    rows=s.protect(r,[],['D-02-l']);assert rows[0]['status']=='FAIL' and rows[0]['evidence_ids']==['title']
    assert s.differences('안전한하루','안전한 하루')[0]['expected']==' '
    assert s.normalized('가')=='가'


def test_wrong_image_unapproved_generic_and_conflicting_copy_never_enforced():
    r=run();assert not s.inspect(r,b'other')['results']
    r['reference_snapshot'][0]['status']='DRAFT';assert not s.inspect(r,RAW)['results']
    r=run();r['reference_snapshot'].append(copy.deepcopy(r['reference_snapshot'][0]));r['reference_snapshot'][1]['content']=r['reference_snapshot'][1]['content'].replace('안전한','편안한')
    assert not s.inspect(r,RAW)['results'] and r['source_copy']['unresolved']
    r=run();r['reference_snapshot'][0]['content']='공식 문구는 안전한 하루입니다.';assert not s.inspect(r,RAW)['results']


def test_ambiguous_target_and_partial_unknown_or_disagreement_not_typo_fail():
    r=run();r['observation']['objects'].append({**r['observation']['objects'][0],'id':'duplicate'})
    assert not s.inspect(r,RAW)['results'] and r['source_copy']['unresolved']
    for first,second in [('안젼한 하루','안전한 하루'),('안□한 하루','안□한 하루')]:
        r=run(first,second);assert s.inspect(r,RAW)['results'][0]['status']!='FAIL'
    r=run();r['verification']['results'][0]['coverage']='PARTIAL';assert s.inspect(r,RAW)['results'][0]['status']=='REVIEW'
    r=run();r['verification']['results'][0]['text_legibility']='DEGRADED';assert s.inspect(r,RAW)['results'][0]['status']=='REVIEW'


def test_matching_copy_does_not_erase_glyph_damage_or_create_pass():
    r=run('안전한 하루','안전한 하루');s.inspect(r,RAW)
    rows=[dict(rule_id='D-02-l',status='FAIL',reason='획 손상',evidence_ids=['title'])]
    assert s.protect(r,rows,['D-02-l'])==rows
    assert not s.protect(r,[],['D-02-l'])


def test_invalid_explicit_schema_is_actionable_and_legacy_is_allowed():
    assert s.parse('원본 데이터: 20만 원') is None
    with pytest.raises(ValueError,match='64자리'):s.parse(json.dumps({'schema':s.SCHEMA}))
    r=run();doc=json.loads(r['reference_snapshot'][0]['content']);doc['entries'][0]['text']=''
    with pytest.raises(ValueError,match='전체'):s.parse(json.dumps(doc))


def test_explicit_object_binding_disambiguates_repeated_labels_but_not_wrong_targets():
    r=run();r['observation']['objects'].append({**r['observation']['objects'][0],'id':'other'})
    doc=json.loads(r['reference_snapshot'][0]['content']);doc['entries'][0]['object_id']='title'
    r['reference_snapshot'][0]['content']=json.dumps(doc)
    assert s.inspect(r,RAW)['results'][0]['object_id']=='title'
    doc['entries'][0]['object_id']='missing';r['reference_snapshot'][0]['content']=json.dumps(doc)
    assert not s.inspect(r,RAW)['results'] and s.inspect(r,RAW)['unresolved']


def test_explicit_source_rect_is_checked_and_does_not_bind_far_away_text():
    r=run();doc=json.loads(r['reference_snapshot'][0]['content']);doc['entries'][0]['rect']=[.8,.8,.9,.9]
    r['reference_snapshot'][0]['content']=json.dumps(doc)
    assert not s.inspect(r,RAW)['results']
    doc['entries'][0]['rect']=[0,0,2,1]
    with pytest.raises(ValueError,match='rect'):s.parse(json.dumps(doc))
