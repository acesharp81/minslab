from unittest.mock import patch
import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from backend.db import Base, upsert_revision
from backend.service import HomeService
from backend.source_preview import source_preview

@pytest.fixture
def service():
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return HomeService(engine)

def test_current_source_limit_and_payload(service):
    with service.sessions.begin() as session:
        for i in range(55):
            upsert_revision(session,'sample','lh_notice',str(i),{'number':i,'empty':None,'raw':{'값':False}},'test')
        upsert_revision(session,'sample','lh_notice','0',{'number':100,'new_field':'수정'},'test')
        upsert_revision(session,'sample','cheongyak','other',{'private_source':True},'test')
    result=source_preview(service,'lh_notice')
    assert result['total']==55
    assert len(result['items'])==50
    assert result['items'][0]['data']['number']==100
    assert 'new_field' in result['fields']
    assert not any('private_source' in r['data'] for r in result['items'])
    assert len({r['id'] for r in result['items']})==50
    assert source_preview(service,'lh_notice')==result

def test_empty_unknown_and_credentials(service):
    assert source_preview(service,'lh_notice')['items']==[]
    with pytest.raises(KeyError): source_preview(service,'not_a_source')
    with service.sessions.begin() as session:
        upsert_revision(session,'sample','lh_notice','secret',{'url':'https://example.org?serviceKey=hidden&n=2','nested':{'token':'hidden'},'text':'key=secretvalue'},'test')
    with patch.dict('os.environ',{'EXAMPLE_API_KEY':'secretvalue'}):
        data=source_preview(service,'lh_notice')['items'][0]['data']
    assert data['url']=='https://example.org?n=2'
    assert data['nested']['token']=='[REDACTED]'
    assert 'secretvalue' not in data['text']
