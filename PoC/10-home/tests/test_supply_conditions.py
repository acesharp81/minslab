from bs4 import BeautifulSoup
from backend.lh_notice_detail import supply_terms
from backend.supply_conditions import conditions

def test_price_columns_do_not_confuse_counts_with_prices_or_invent_missing_prices():
    soup=BeautifulSoup('<table><thead><tr><th>주택형</th><th>전용면적(㎡)</th><th>세대수</th><th>금회공급 세대수</th><th>평균분양가격(원)</th></tr></thead><tbody><tr><td>59A</td><td>59.88</td><td>321</td><td>300</td><td>548,653,000</td></tr><tr><td>84A</td><td>84.1</td><td>70</td><td>20</td><td>-</td></tr></tbody></table>','html.parser')
    rows=supply_terms(soup)
    assert len(rows)==1
    assert rows[0]['average_price_won']==548653000
    assert rows[0]['units']==321 and rows[0]['offered_units']==300


def test_same_block_conditions_keep_area_totals_and_source_scope():
    p=dict(id='P',name='성남금토 A2',region='경기도',district='성남금토',block='A2',source_id='lh_rent',tenure='행복주택',planned_units=438,developer='LH',rows=[dict(area='36',units=100,org='경기지역본부')])
    class Service:
        def projects(self):return [p,dict(p,id='C',source_id='lh_construction',contractor='시공사',rows=[],planned_units=633),dict(p,id='OTHER',block='A3',contractor='다른 시공사',rows=[])]
        def rows(self,kind):return []
    c=conditions(Service(),p,dict(latitude=37.407,longitude=127.081))
    assert c['contractors']==['시공사']
    assert c['groups'][0]['units']==438 and c['groups'][0]['area_total']==100
    assert c['prices']==[]
    assert c['facility_plans'][0]['name']=='금토초등학교'


def test_archived_notice_prices_link_across_source_ids_and_supply_their_area_rows():
    p=dict(id='P',name='고양창릉 S-5BL 건설공사',region='경기도',district='고양창릉',block='S-05',source_id='lh_construction',planned_units=759,developer='LH')
    class Service:
        def projects(self):return [p]
        def rows(self,kind):return [dict(id='N',name='공고',district='고양창릉',block='S5',region='경기도',source_id='lh_notice_terms',tenure='공공분양',source_date='2025-02-01',terms=[dict(area='59.88',units=321,average_price_won=548653000,price_basis='평균분양가격')])]
    c=conditions(Service(),p,None)
    assert c['prices'][0]['value']=='548,653,000원'
    assert c['groups'][0]['name']=='공공분양'
    assert c['groups'][0]['areas'][0]['units']==321
