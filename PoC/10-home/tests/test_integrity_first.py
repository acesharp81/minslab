from copy import deepcopy
import pytest
from sqlalchemy import create_engine,select
from backend.db import Base,IntegrityRound
from backend.service import HomeService
from backend.integrity_first import calculate,publish,ID
from backend.data_integrity import get_round


def result():
    previous={'categories':[{'id':'self','name':'자체','items':[{'id':'S'+str(i),'name':'자체항목','weight':2.5,'fraction':.5,'score':1.25,'reason':'검증 근거'} for i in range(40)]}],
        'classification_metrics':dict(sample_size=20,tp=9,fp=0,fn=0,tn=11,accuracy=100,precision=100,recall=100,f1=100),'assessed_at':'2026-10-20'}
    official=[dict(id='O'+str(i),name='공식항목',weight=2,numerator=1 if i<5 else 0,denominator=1,reason='원장 확인',evidence='test.csv') for i in range(1,9)]
    col=dict(registered_sources=1,successful_sources=1,failed_sources=0,api_sources=1,official_web_sources=0,unofficial_web_sources=0,extracted_cells=3,linked_records=1)
    return calculate(previous,{'project_count':1,'metrics':{}},[],col,official,'2026-10-22T00:00:00+09:00')


def test_weighted_score_uses_six_official_metrics_and_no_fixed_sample_bonus():
    r=result();assert r['self_score']==25
    assert r['official_score']==pytest.approx(50*4/6)
    assert r['total_score']==pytest.approx(25+50*4/6)
    assert len(r['official_items'])==6
    assert sum(i['weight'] for i in r['official_items'])==pytest.approx(50)
    # 100% fixed-sample classification is not an extra score.
    assert r['total_score']<100


def test_atomic_replacement_archives_old_round_and_rejects_changed_inputs(tmp_path):
    engine=create_engine('sqlite://');Base.metadata.create_all(engine);s=HomeService(engine,tmp_path)
    with s.sessions.begin() as db:db.add(IntegrityRound(id='OLD',sequence=0,actor='old',reason='old',score='1',result={},report_html='<html></html>',digest='oldhash'))
    with pytest.raises(ValueError):publish(s,result(),{'OLD':'stalehash'})
    with s.sessions() as db:assert db.get(IntegrityRound,'OLD') is not None
    output=publish(s,result(),{'OLD':'oldhash'});assert output['retired_count']==1
    with s.sessions() as db:assert [r.id for r in db.scalars(select(IntegrityRound))]==[ID]
    assert list((tmp_path/'remediation/retired-before-first-20261022').glob('OLD-*.json'))
    assert get_round(s,ID)['result']['display_score']==result()['display_score']


def test_revision_excludes_o5_and_caps_unreconciled_progress_at_half():
    from backend.integrity_first import revise_scoring
    evidence={k:dict(units=v,evidence_file=k+'.csv',sha256='verified') for k,v in [('sale',14451),('rental',4461)]}
    before=result();after=revise_scoring(before,evidence,'2026-10-22')
    assert len(after['official_items'])==5 and all(i['id']!='O5' for i in after['official_items'])
    assert after['self_score']==before['self_score']
    o6=next(i for i in after['official_items'] if i['id']=='O6')
    assert o6['fraction']==pytest.approx((14451/14800+4461/14700)/4)
    assert o6['score']<o6['weight']/2
    assert all(c['match_status']=='UNVERIFIED' for c in o6['partial_components'])
    evidence['sale']['units']=30000
    cap=revise_scoring(before,evidence,'2026-10-22')
    assert next(i for i in cap['official_items'] if i['id']=='O6')['partial_components'][0]['fraction']==.5
