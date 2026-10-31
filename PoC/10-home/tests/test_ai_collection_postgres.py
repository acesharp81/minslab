"""Production JSON compatibility in an isolated schema; never touches business rows."""
import os,uuid
import pytest
from sqlalchemy import create_engine,text
from backend.db import upsert_revision
from backend.service import HomeService
from backend.ai_collection import register


def test_discovery_deduplicates_legacy_json_with_escaped_nul(tmp_path):
    url=os.environ.get('HOME_TEST_POSTGRES_URL')
    if not url:pytest.skip('Explicit isolated PostgreSQL test URL required')
    schema='test_ai_'+uuid.uuid4().hex
    admin=create_engine(url)
    with admin.begin() as c:c.execute(text('CREATE SCHEMA '+schema))
    engine=create_engine(url,connect_args={'options':'-csearch_path='+schema+',public'})
    try:
        with engine.begin() as c:
            for table in ('home_revision','home_audit'):
                c.execute(text(f'CREATE TABLE {table} (LIKE public.{table} INCLUDING ALL)'))
        service=HomeService(engine,tmp_path)
        evidence='https://www.seoul.go.kr/review?idx=1234'
        with service.sessions.begin() as db:
            row,_=upsert_revision(db,'document_evidence','legacy','id',dict(name='기존 공개 자료',evidence_url=evidence,raw_excerpt='PDF\x00원문'),'test')
            original=row.entity_id
        found,created=register(service,dict(name='다시 수집한 제목',evidence_url=evidence),'test')
        assert found==original and created is False
        found,created=register(service,dict(name='새 공개 자료',evidence_url=evidence+'5'),'test')
        assert found!=original and created is True
    finally:
        engine.dispose()
        with admin.begin() as c:c.execute(text('DROP SCHEMA '+schema+' CASCADE'))
        admin.dispose()
