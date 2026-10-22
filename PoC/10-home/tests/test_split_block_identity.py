from datetime import date
import pytest
from backend.block_identity import normalize_block, title_blocks
from backend.evidence_bridge import match_key
from backend.supply_dashboard import block_key, inventory, linked_notices
from backend.lh_notice_detail import candidates, parse_detail


def project(block):
    return dict(id=block, source_id='lh_construction', name='인천검단 '+block+'BL',
                region='인천광역시', district='인천검단', block=block, planned_units=702 if block.endswith('-1') else 964)


def test_split_identity_is_preserved_across_inventory_and_bridge():
    ps=[project('AA13-1'),project('AA13-2')]
    assert {match_key(p) for p in ps}=={('인천광역시','인천검단','AA13-1'),('인천광역시','인천검단','AA13-2')}
    assert len(inventory(ps)[0])==2
    assert normalize_block('AA-013－02BL')=='AA13-2'
    assert normalize_block('Ab-031')=='AB31'
    assert title_blocks('인천검단 AA13-1BL 및 AA13-2BL')=={'AA13-1','AA13-2'}
    assert match_key(dict(ps[0],warnings=['MULTI_SITE_CONTRACT'])) is None
    assert match_key(dict(ps[0],name='인천검단 AA13-1BL 및 AA13-2BL')) is None
    assert match_key(dict(ps[0],region=None)) is None
    assert block_key(dict(ps[0],region=None)) is None


def test_split_tabs_keep_their_own_households_and_months():
    notice=dict(id='n',name='인천검단 AA13-1 및 AA13-2 국민임대',region='인천광역시',
                notice_no='n', revision_no=1, notice_type='국민임대', source_date='2026-07-01',evidence_url='https://apply.lh.or.kr/')
    html='<li><strong>공고일</strong>2026.07.01</li>'
    for index,block,units,month in [(0,'AA13-1',702,'2027.01'),(1,'AA13-2',964,'2027.02')]:
        html+=f'<div id="wrtancSbdTab{index}"><h4>인천검단 {block}BL</h4><ul><li>총 세대수 : {units}</li><li>입주예정월 : {month}</li></ul></div>'
    selected=candidates([project('AA13-1'),project('AA13-2')],[notice])
    assert len(selected)==2
    parsed=[parse_detail(html.encode(),n,k) for n,k in selected]
    assert {(p['block'],p['planned_units'],p['move_in_month']) for p in parsed}=={
        ('AA13-1',702,'2027-01'),('AA13-2',964,'2027-02')}
    with pytest.raises(ValueError):parse_detail(html.encode(),notice,('인천광역시','인천검단','AA13'))


def test_parent_and_sibling_cannot_claim_single_block_notice():
    rows=[dict(project(b),source_id='lh_rent') for b in ('AA13','AA13-1','AA13-2')]
    notice=dict(id='n',name='인천검단 AA13-1BL 국민임대',source_date='2026-07-01',
                developer='한국토지주택공사',region='인천광역시',units=702)
    links=linked_notices(rows,[notice],date(2026,10,21))
    assert set(links)=={'AA13-1'}
    assert not linked_notices(rows,[dict(notice,name='인천검단 AA13-1BL 및 AA13-2BL 국민임대')],date(2026,10,21))


def test_valid_source_block_prefix_and_contract_scope_are_not_silently_replaced():
    p=dict(project('Ab35'),region='경기도',district='평택고덕국제화계획',name='평택고덕 A-35BL 민간참여 공공주택건설사업')
    assert block_key(p)[2]=='AB35'
    contract=dict(project('A1'),region='경기도',district='화성동탄2',name='화성동탄2 C-14 민간참여 공공주택 건설사업')
    assert block_key(contract)[2]=='A1'
