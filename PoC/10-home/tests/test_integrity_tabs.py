from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from backend.app import create_app, ROOT
from backend.db import Base


def test_public_document_allowlist_content_and_revalidation():
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool);Base.metadata.create_all(engine)
    with TestClient(create_app(engine,auto_collect=False)) as client:
        for slug,name in [('procedures','공급유형별_추진절차.html'),('reliability','데이터 신뢰도 확인.html')]:
            path='/poc/home/integrity-documents/'+slug
            r=client.get(path)
            assert r.status_code==200 and r.content==(ROOT/'docs'/name).read_bytes()
            assert "frame-ancestors 'self'" in r.headers['content-security-policy']
            assert "script-src 'unsafe-inline'" in r.headers['content-security-policy']
            cached=client.get(path,headers={'If-None-Match':r.headers['etag']})
            assert cached.status_code==304 and cached.content==b''
        assert client.get('/poc/home/integrity-documents/secret').status_code==404
        assert "script-src 'self'" in client.get('/poc/home/').headers['content-security-policy']


def test_assessment_endpoints_require_admin_not_just_a_hidden_tab():
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool);Base.metadata.create_all(engine)
    with TestClient(create_app(engine,auto_collect=False)) as client:
        for path in ['', '/diagnostics','/construction-audit','/rounds/test','/rounds/test/report.md','/rounds/test/report.html']:
            r=client.get('/poc/home/api/data-integrity'+path)
            assert r.status_code==401 and r.headers['cache-control']=='no-store'
        with patch('backend.app.authenticated',return_value=True):
            assert client.get('/poc/home/api/data-integrity').status_code==200
            assert client.get('/poc/home/api/data-integrity/diagnostics').status_code==200
