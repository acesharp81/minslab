from pathlib import Path
import pytest
from backend.ih_public import parse_list,parse_notice,parse_project,notice_round,is_housing_notice,explicit_quantities,official_url

FIXTURES=Path(__file__).parent/'fixtures/ih'


def test_official_housing_listing_native_ids_and_page_validation():
    data=(FIXTURES/'housing.html').read_bytes()
    rows,meta=parse_list(data,'housing',1)
    assert meta['total']==29 and meta['pages']==3 and len(rows)==10
    assert rows[0]['source_object_id']=='sale_lease:177'
    assert rows[0]['source_date']=='2026-08-25'
    assert 'pgno' not in rows[0]['evidence_url']
    with pytest.raises(ValueError):parse_list(data,'housing',2)
    with pytest.raises(ValueError):parse_list(data,'rental',1)


def test_official_rental_list_excludes_result_names_and_commercial():
    rows,meta=parse_list((FIXTURES/'rental.html').read_bytes(),'rental',1)
    assert meta['total']==938
    assert not is_housing_notice(rows[0]['name'])
    assert not is_housing_notice('임대아파트 단지 내 상가 입주자 모집 공고')
    assert not is_housing_notice('천원주택 예비입주자 선정 결과')
    assert is_housing_notice('천원주택 예비입주자 모집 공고')


def test_rounds_never_treat_reserved_or_reissued_units_as_net_new():
    assert notice_round('청년 예비입주자 모집')=='RESERVE'
    assert notice_round('B1 입주자 모집 정정공고')=='CORRECTION'
    assert notice_round('잔여세대 추가 입주자 모집')=='ADDITIONAL'
    assert notice_round('B1 입주자 모집공고')=='MAIN'


def test_detail_pins_native_attachment_and_preserves_unknown_quantity():
    rows,_=parse_list((FIXTURES/'housing.html').read_bytes(),'housing',1)
    record=parse_notice((FIXTURES/'detail.html').read_bytes(),rows[0])
    assert record['notice_round']=='CORRECTION' and record['planned_units'] is None
    assert record['facts'][0]['kind']=='DOCUMENT'
    assert record['attachments'][0]['url'].endswith('bcd=sale_lease&msg_seq=177&fileno=1')
    with pytest.raises(ValueError):parse_notice((FIXTURES/'detail.html').read_bytes(),dict(rows[0],name='다른 주택 공고'))


def test_project_future_half_year_is_plan_without_invented_actual():
    r=parse_project((FIXTURES/'project-detail.html').read_bytes(),
        'https://www.ih.co.kr/main/land/landDetail.do?land_seq=136&landDiv=1120','136')
    assert r['planned_units']==1006 and r['block']=='AA7'
    assert r['proposed_policy']=='UNASSIGNED' and r['policy_candidate_only']
    assert r['source_date'] is None
    assert all(f['kind']=='PLAN' and f['date_precision']=='HALF_YEAR' for f in r['facts'])
    assert r['facts'][0]['date']=='2028-12'
    assert not r.get('start_actual_date')


def test_project_area_groups_sum_once_and_ambiguous_totals_stay_unresolved():
    body=(FIXTURES/'project-detail.html').read_text()
    import re
    body=re.sub(r'1,006\s*세대(?:\s*\([^<]*\))?', '614세대(전용면적 60㎡ 이하), 135세대(60~85㎡ 이하)', body)
    r=parse_project(body.encode(), 'https://www.ih.co.kr/main/land/landDetail.do?land_seq=130', '130')
    assert r['planned_units']==749
    assert not any(f['kind']=='ACTUAL' for f in r['facts'])
    ambiguous=body.replace('614세대(전용면적 60㎡ 이하), 135세대(60~85㎡ 이하)',
                           '총 749세대 중 614세대(60㎡ 이하), 135세대(60~85㎡ 이하)')
    assert parse_project(ambiguous.encode(),r['evidence_url'],'130')['planned_units'] is None


def test_quantities_require_explicit_unambiguous_scope():
    assert explicit_quantities('총세대수: 577세대. 금회 공급: 381호')==dict(offered_units=381,complex_total_units=577)
    assert explicit_quantities('예비 입주자 100명. 신청자 300명')['offered_units'] is None
    assert explicit_quantities('금회 공급 100호. 금회 공급 200호')['offered_units'] is None


def test_attachments_require_same_https_official_host():
    assert official_url('/main/bbs/bbsMsgFileDown.do').startswith('https://www.ih.co.kr/')
    for href in ('https://evil.example/notice','http://www.ih.co.kr/notice','//evil.example/file'):
        with pytest.raises(ValueError):official_url(href)
