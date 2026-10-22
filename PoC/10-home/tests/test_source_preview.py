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

def test_document_cards_preview_matches_authority_and_host_and_keeps_latest_50(service):
    with service.sessions.begin() as session:
        for i in range(55):
            upsert_revision(session,'document_evidence','external_officer','doc'+str(i),
                {'name':'문서 '+str(i),'evidence_url':'https://www.newsis.com/a','number':i,'nested':{'token':'private'}},'test')
        upsert_revision(session,'document_evidence','external_officer','doc0',
            {'name':'수정 문서','evidence_url':'https://www.newsis.com/a','number':100},'test')
        upsert_revision(session,'document_evidence','external_officer','official',{'evidence_url':'https://www.lh.or.kr/a'},'test')
    result=source_preview(service,'document:NONOFFICIAL:www.newsis.com')
    assert result['total']==55 and len(result['items'])==50
    assert result['items'][0]['data']['number']==100
    assert all(r['data'].get('nested',{}).get('token')!='private' for r in result['items'])
    assert source_preview(service,'document:OFFICIAL:www.lh.or.kr')['total']==1
    with pytest.raises(KeyError):source_preview(service,'document:OFFICIAL:www.newsis.com')
    with pytest.raises(KeyError):source_preview(service,'document:NONOFFICIAL:missing.example')


def test_exact_record_keeps_pinned_revision_and_never_falls_back_to_other_samples(service):
    from backend.source_preview import collected_record
    from backend.db import entity_id
    eid=entity_id('permit','building_hub','permit1')
    with service.sessions.begin() as session:
        upsert_revision(session,'permit','building_hub','permit1',{'units':12,'api_key':'secret','dates':{'착공일':'2025-01-01'}},'test')
        upsert_revision(session,'permit','building_hub','permit1',{'units':15},'test')
    assert collected_record(service,eid,1)['data']['units']==12
    assert collected_record(service,eid)['data']['units']==15
    assert 'secret' not in str(collected_record(service,eid,1))
    with pytest.raises(KeyError):collected_record(service,'missing')
    with pytest.raises(KeyError):collected_record(service,eid,99)


def test_project_preview_follows_exact_original_and_excludes_unrelated_policy(service,monkeypatch):
    from backend.source_preview import collected_record,project_collected_records
    from backend.db import entity_id
    url='https://www.data.go.kr/data/15136560/openapi.do'
    with service.sessions.begin() as session:
        raw,_=upsert_revision(session,'permit','building_hub','raw',{'units':12,'evidence_url':url},'test')
        ref=raw.entity_id;revision=raw.id
        upsert_revision(session,'permit','building_hub','raw',{'units':15,'evidence_url':url},'test')
        p,_=upsert_revision(session,'project','building_hub','p',{'planned_units':999,'source_reference_id':ref,'source_reference_revision_id':revision},'test')
        pid=p.entity_id
        pol,_=upsert_revision(session,'policy','policy_907','policy',{'target':1350000,'evidence_url':'https://www.korea.kr/a'},'test')
        policy_id=pol.entity_id
    record=collected_record(service,pid)
    assert record['id']==ref and record['data']['units']==12 and 'planned_units' not in record['data']
    monkeypatch.setattr('backend.project_collection.collection_matrix',lambda *a,**k:{'items':[{'cells':{'POLICY':{'sources':[dict(source_entity_id=policy_id,evidence_url=url)]}}}]})
    result=project_collected_records(service,pid,url)
    assert len(result['items'])==1 and result['items'][0]['id']==ref
