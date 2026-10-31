import copy,io,hashlib
from pathlib import Path
import numpy as np
from PIL import Image
from app import evidence_guards as g,symbol_geometry as geom
from app.rules import PACK


def run_for_name(first='행정안정부',second='행정안정부'):
    obj=dict(id='name',label='기관명',text=first,quality='CLEAR',transcription_inferred=False,cell_ids=['R10C10'])
    return dict(rule_pack=copy.deepcopy(PACK),observation={'objects':[obj]},reference_snapshot=[],verification={'results':[dict(object_id='name',status='COMPLETED',coverage='PARTIAL',text=second,quality='CLEAR',transcription_inferred=False)]})


def test_official_name_check_is_independent_of_llm_pass_and_visual_legibility():
    run=run_for_name();rows=[dict(rule_id='D-02-l',evidence_ids=['name'],status='PASS')]
    assert g.protect(run,rows,['D-02-l'])[0]['status']=='FAIL'
    assert rows[0]['official_term_check']['independent_reading_agrees']
    assert '행정안정부' in rows[0]['reason'] and '행정안전부' in rows[0]['reason']
    assert g.protect(run_for_name(second='행정안전부'),[],['D-02-l'])[0]['status']=='REVIEW'
    assert not g.protect(run_for_name('행정안전부','행정안전부'),[],['D-02-l'])
    run['observation']['objects'][0]['label']='본문 일반 문구'
    assert not g.protect(run,[],['D-02-l'])


def test_direction_comparison_detects_mirror_and_ignores_identical_template():
    asset=Path(__file__).resolve().parents[1]/'rules/reference-library/flag.gif'
    out=io.BytesIO();Image.open(asset).convert('RGB').save(out,format='PNG')
    template=max(geom.components(out.getvalue()),key=lambda x:x['pixels'])['mask']
    normal=geom.compare(template,template);mirror=geom.compare(np.fliplr(template),template)
    assert not normal['mirrored'] and normal['normal_score']>.99
    assert mirror['mirrored'] and mirror['mirrored_score']>.99
    assert not geom.compare(np.zeros_like(template),template)['mirrored']


def test_mirror_suspicion_does_not_claim_backside_is_a_defect():
    run=run_for_name('정상 문구','정상 문구')
    run['symbol_geometry']={'checks':[dict(object_id='flag',mirrored=True,rect=[.6,.1,.7,.2])]}
    rows=[dict(rule_id='H-04-e',status='PASS',evidence_ids=['flag'])]
    assert g.protect(run,rows,['H-04-e'])[0]['status']=='REVIEW'
    assert '뒷면' in rows[0]['reason'] and rows[0]['visual_issue']
    rows[0]['status']='FAIL'
    assert g.protect(run,rows,['H-04-e'])[0]['status']=='FAIL'


def test_map_scope_mismatch_is_not_lost_when_analysis_only_checked_title():
    run=run_for_name('정상 문구','정상 문구')
    run['observation']['objects'].append(dict(id='map',label='지도 본체',description='한반도와 주변 육지',text='',quality='CLEAR',cell_ids=['R06C09']))
    ref=dict(id='map-ref',name='공식 지도',kind='official-map',status='APPROVED',parent_ids=['H-03'])
    run['reference_snapshot']=[ref]
    run['verification']['results'].append(dict(object_id='map',status='COMPLETED',coverage='PARTIAL',quality='CLEAR',comparisons=[dict(reference_id='map-ref',rule_ids=['H-03-c'],aspect='TERRITORIAL_SCOPE',status='MISMATCH',evidence='제목의 대상보다 강조한 육지 범위가 넓어 오인 가능')],highlighted_landmasses='한반도와 주변 대륙',territorial_context='제목과 강조 범위 충돌'))
    rows=g.protect(run,[],['H-03-c'])
    assert len(rows)==1 and rows[0]['status']=='REVIEW'
    assert rows[0]['evidence_ids']==['map'] and rows[0]['visual_issue']
    assert not rows[0]['document_review']
    assert rows[0]['map_scope_check']['coverage']=='PARTIAL'


def test_readable_identical_text_does_not_erase_glyph_defect_and_keeps_local_position():
    run=run_for_name('우리나라','우리나라')
    c=run['verification']['results'][0]
    c.update(model='reader',event_id='event',crop_rect=[.5,.3,1.,.5],glyph_checks=[dict(literal='우리나라',quality='DEFECT',evidence='리의 ㄹ 아래 획이 끊김',cell_ids=['R04C05'])])
    rows=[dict(rule_id='D-02-l',evidence_ids=['name'],status='PASS',reason='읽힘')]
    result=g.protect_glyphs(run,rows,['D-02-l'])[0]
    assert result['status']=='FAIL' and result['error_type']=='VISUAL_TEXT_DEFECT'
    assert result['rects'][0][0]>=.5 and result['glyph_evidence']['event_id']=='event'
    c['glyph_checks'][0]['quality']='UNCERTAIN'
    assert g.protect_glyphs(run,[],['D-02-l'])[0]['status']=='REVIEW'
    c['glyph_checks'][0]['quality']='CLEAR'
    assert not g.protect_glyphs(run,[],['D-02-l'])
    c['coverage']='MISSING';c['glyph_checks'][0]['quality']='DEFECT'
    assert not g.protect_glyphs(run,[],['D-02-l'])


def test_airline_name_requires_identity_context_and_does_not_reject_new_livery():
    run=run_for_name('KOREA AIR','KOREA AIR')
    run['observation']['objects'][0].update(label='비행기 동체 로고',description='대한항공 여객기')
    assert g.protect(run,[],['D-02-l'])[0]['status']=='FAIL'
    run['observation']['objects'][0]['description']='정체 불명 비행기'
    assert not g.protect(run,[],['D-02-l'])
    run['observation']['objects'][0].update(description='대한항공 여객기',text='KOREAN')
    assert not g.protect(run,[],['D-02-l'])


def test_crop_edge_is_not_source_damage_and_country_name_rule_is_not_generic_ocr():
    run=run_for_name('안내 문구','내 문구');c=run['verification']['results'][0]
    c.update(crop_rect=[.1,.2,.8,.4],glyph_checks=[dict(literal='내 문구',quality='DEFECT',origin='CROP_EDGE',evidence='crop 왼쪽에서 첫 음절이 잘려 있음',cell_ids=['R04C01'])])
    out=g.protect_glyphs(run,[],['D-02-l','H-04-n'])
    assert len(out)==1 and out[0]['rule_id']=='D-02-l' and out[0]['status']=='REVIEW'
    assert out[0]['glyph_evidence']['checks'][0]['source_defect_unconfirmed']
    assert c['glyph_checks'][0]['quality']=='DEFECT'  # preserve raw response
    c['glyph_checks'][0].update(origin='SOURCE',evidence='중앙 음절의 실제 획이 융합됨')
    assert g.protect_glyphs(run,[],['D-02-l'])[0]['status']=='FAIL'


def test_author_source_name_with_particle_is_checked_in_body_text():
    run=run_for_name('행정안정부가 안내합니다','행정안정부가 안내합니다')
    run['observation']['objects'][0]['label']='첫 번째 안내 문구'
    assert not g.protect(run,[],['D-02-l'])
    run['reference_snapshot']=[dict(id='author',status='APPROVED',kind='source-data',parent_ids=['D-02'],content='발행 기관: 행정안전부')]
    row=g.protect(run,[],['D-02-l'])[0]
    assert row['status']=='FAIL' and row['official_term_check']['literal']=='행정안정부'
    assert '행정안전부' in row['reason']
    run['verification']['results'][0]['text']='행정안전부가 안내합니다'
    assert g.protect(run,[],['D-02-l'])[0]['status']=='REVIEW'


def test_model_crop_defect_fail_is_retracted_but_independent_typo_is_preserved():
    run=run_for_name('안내 문구','내 문구');c=run['verification']['results'][0]
    c.update(crop_rect=[.1,.2,.8,.4],glyph_checks=[dict(literal='내 문구',quality='DEFECT',origin='CROP_EDGE',evidence='crop 가장자리 잘림',cell_ids=['R04C01'])])
    row=dict(rule_id='D-02-l',evidence_ids=['name'],status='FAIL',reason='잘린 글자',error_type='VISUAL_TEXT_DEFECT')
    assert g.protect_glyphs(run,[row],['D-02-l'])[0]['status']=='REVIEW'
    row.update(status='FAIL',error_type='TYPO_CONFIRMED',reason='독립 확인된 다른 철자 오타',rects=[[.3,.3,.4,.4]])
    assert g.protect_glyphs(run,[row],['D-02-l'])[0]['status']=='FAIL'
    assert row['error_type']=='TYPO_CONFIRMED' and row['rects']==[[.3,.3,.4,.4]]
