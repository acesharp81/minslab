import csv
import importlib.util
import io
import json
import re
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.pool import StaticPool
from backend.app import ROOT, create_app
from backend.db import Base

DOCS=ROOT/'docs/verification'
spec=importlib.util.spec_from_file_location('official_review',ROOT/'scripts/verify_official_20261105.py')
review=importlib.util.module_from_spec(spec);spec.loader.exec_module(review)


def test_comparison_rejects_incomparable_values_and_preserves_unknown():
    assert review.compare(99000,81131,False)==('집계기준불일치',None)
    assert review.compare(1350000,1350000,True)==('일치',0)
    assert review.compare(99000,100000,True,'>=')==('하한충족',1000)
    assert review.compare(99000,None,True)==('DB항목없음',None)
    assert review.compare(10,0,True)==('불일치',-10)


def test_complete_reference_rows_and_original_columns_preserved():
    for original,result,idkey,count in [('성과검증기준','metrics','검증ID',77),('사업별검증기준','projects','사업 검증ID',28),('공식발표목록','sources','자료ID',24)]:
        before=list(csv.DictReader((DOCS/'20261105_inputs'/(original+'.csv')).open(encoding='utf-8')))
        after=list(csv.DictReader((DOCS/f'20261105_{result}.csv').open(encoding='utf-8-sig')))
        assert len(after)==count and len({r[idkey] for r in after})==count
        for old,new in zip(before,after):
            assert all(new[k]==v for k,v in old.items()), (old[idkey],[(k,new[k],v) for k,v in old.items() if new[k]!=v])


def test_results_are_evidenced_and_dont_promote_plans_or_duplicate_districts():
    d=json.loads((DOCS/'20261105_verification.json').read_text());e=json.loads((DOCS/'20261105_evidence.json').read_text())
    rows={r['id']:r for r in d['metrics']+d['projects']}
    assert dict(Counter(r['판정'] for r in rows.values()))==d['manifest']['counts']
    assert set(rows)=={f'K{i:03}' for i in range(1,78)}|{f'P{i:03}' for i in range(1,29)}
    assert d['manifest']['snapshot']['transaction_read_only']=='on' and d['manifest']['business_writes']==0
    assert all(r['원문_근거요약'] and r['DB_검색완료'] for r in rows.values())
    assert all('재확인' not in r['원문_증거_위치'] for r in rows.values())
    assert rows['K061']['시스템값']==28634 and rows['K062']['시스템값']==19507
    assert rows['K063']['판정']=='불일치' and rows['K063']['차이값']==-1.3
    assert rows['P006']['원문검증상태']=='공식자료간차이' and len(e['evidence']['P006']['source_conflict'])==2
    for id in ('K002','K011','K013','K058','P001','P008','P023'):
        assert rows[id]['판정']=='집계기준불일치' and rows[id]['차이값'] is None
    for id in ('P014','P015','P016'):
        assert rows[id]['공식값']=='' and rows[id]['시스템값'] is None
        assert '입주' in rows[id]['원문_근거요약']
    for i in range(17,23):
        assert rows[f'P{i:03}']['시스템값'] is None
    assert len(e['previous'])==40 and all(p['comparison']=='동일' for p in e['previous'])


def test_withdrawn_verification_is_not_published_or_downloadable():
    html=(ROOT/'docs/데이터 신뢰도 확인.html').read_text()
    assert 'official-verification-data' not in html
    assert '11월 공식자료 대조' not in html
    assert '/integrity-documents/verification/' not in html
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with TestClient(create_app(engine,auto_collect=False)) as client:
        for authorized in (False,True):
            with patch('backend.app.authenticated',return_value=authorized):
                for name in ['metrics.csv','projects.csv','sources.csv','summary.md','reconciliation.md','evidence.json','verification.json']:
                    assert client.get('/poc/home/integrity-documents/verification/20261105_'+name).status_code==404
        assert client.get('/poc/home/integrity-documents/reliability').status_code==200
