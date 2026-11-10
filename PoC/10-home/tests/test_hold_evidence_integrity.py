import csv,io,json,hashlib
from unittest.mock import patch
from copy import deepcopy
from test_ai_collection import env
from test_stage_reconciliation import proposal
from backend import ai_agents_inbox as inbox,stage_reconciliation as sr
from backend.hold_evidence_integrity import package,quote_check,load_registry,resolve,sha
from backend.db import upsert_revision

def test_final_csv_hash_is_of_formula_escaped_redacted_body(env):
    s,store,did,_=env
    body='- 1 -\r\n총 100호\r\n이메일 담당자@example.com\r\n'
    record=dict(role='collection',subject=did,state='HOLD',stage='DOCUMENT_ERROR',body_text=body,evidence=['총 100호'],source_revision_no=1,result={})
    with patch.object(inbox,'items',return_value=[record]):
        row=list(csv.DictReader(io.StringIO(inbox.export_csv(s,store,'collection').lstrip('\ufeff'))))[0]
    p=json.loads(row['증빙패키지_JSON']);assert row['수집본문'].startswith("'- 1 -")
    assert p['exported_body_sha256']==sha(row['수집본문'])
    assert p['stored_body_sha256']==sha(body) and p['hash_basis']['formula_escaped']
    q=p['quote_checks'][0];a=q['anchor'];assert row['수집본문'][a['start']:a['end']]=='총 100호'
    assert 'example.com' not in row['수집본문']

def test_whitespace_quote_anchors_are_reproducible_not_fuzzy():
    body='지구명\n총  100\t호 공급';q=quote_check(body,'총100호')
    assert q['status']=='WHITESPACE_ONLY' and not q['exact']
    a=q['anchor'];assert ''.join(body[a['start']:a['end']].split())=='총100호'
    assert quote_check(body,'총101호')['status']=='NOT_FOUND'
    assert quote_check('', '총100호')['status']=='MISSING_BODY'

def test_registry_pins_old_revision_and_flags_changed_current(env):
    s,_,did,_=env;p=proposal(env);ref=p['source_ref']
    with s.sessions.begin() as db:
        old=sr.current(db,'document_evidence',did)
        upsert_revision(db,'document_evidence','seoul_press_watch','test',dict(old.payload,text='정정 공고'), 'correction')
    value=resolve(ref,load_registry(s,[ref]))
    assert value['status']=='PINNED_REVISION_MATCHED' and not value['current_matches']
    assert value['body']==p['proof']['body']
    wrong=dict(ref,hash='f'*64)
    assert resolve(wrong,load_registry(s,[wrong]))['status']=='HASH_MISMATCH'
    assert not resolve(wrong,load_registry(s,[wrong]))['body']

def test_stage_export_same_contract_and_preserves_observation_semantics(env):
    s,store,_,_=env;p=proposal(env);p['proof']['body']='- 1 -\n'+p['proof']['body'];p['proposed']['date_basis']='OBSERVED_BY';p['human_hold']=True
    sr.propose(s,p)
    rows=list(csv.DictReader(io.StringIO(sr.export_csv(s).lstrip('\ufeff'))));assert len(rows)==1
    ep=json.loads(rows[0]['증빙패키지_JSON']);assert sha(rows[0]['수집본문'])==ep['exported_body_sha256']
    assert ep['evidence_registry'][0]['status']=='PINNED_REVISION_MATCHED'
    assert json.loads(rows[0]['새근거_JSON'])['date_basis']=='OBSERVED_BY' and rows[0]['자동반영가능']=='False'
    assert not s.rows('project_profile')

def test_no_text_is_not_replaced_by_structured_metadata(env):
    s,_,did,_=env
    with s.sessions() as db:ref=sr.reference(sr.current(db,'document_evidence',did))
    value=resolve(ref,load_registry(s,[ref]));assert value['body']=='' and value['unverifiable_reason']

def test_quote_delimiters_are_distinguished_from_verbatim():
    q=quote_check('총 100호 공급','“총 100호”')
    assert q['status']=='QUOTE_DELIMITERS_ONLY' and not q['exact'] and not q['whitespace_normalized']
    assert q['anchor']['matched_text']=='총 100호'

def test_registry_endpoint_requires_auth_and_is_bound_to_proposal(env):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.stage_reconciliation_api import install
    s,_,_,_=env;sr.propose(s,proposal(env));pid=sr.list_items(s)[0]['id']
    app=FastAPI();install(app,s,lambda request:request.headers.get('x-test-auth')=='yes','/poc/home')
    with TestClient(app) as c:
        url='/poc/home/api/admin/stage-reviews/'+pid+'/evidence'
        assert c.get(url).status_code==401
        response=c.get(url,headers={'x-test-auth':'yes'});assert response.status_code==200
        assert response.json()['evidence_registry'][0]['status']=='PINNED_REVISION_MATCHED'
        assert response.headers['cache-control']=='no-store'
        assert c.get('/poc/home/api/admin/stage-reviews/arbitrary/evidence',headers={'x-test-auth':'yes'}).status_code==404

def test_registry_reads_only_pinned_and_current_versions(env):
    s,_,did,_=env;p=proposal(env);ref=p['source_ref']
    for i in range(4):
        with s.sessions.begin() as db:
            old=sr.current(db,'document_evidence',did)
            upsert_revision(db,'document_evidence','seoul_press_watch','test',dict(old.payload,text='정정'+str(i)), 'correction')
    history=load_registry(s,[ref])
    assert len(history[('document_evidence',did)])==2

def test_news_navigation_is_not_article_evidence():
    from backend.publication_evidence import text_quality
    assert text_quality('이시간 핫 뉴스 '+('다른 기사 목록 '*20)+'Copyright NEWSIS.COM')=='BOILERPLATE'

def test_new_report_provenance_does_not_publish_private_attachment(tmp_path):
    import pytest
    from backend.review_report_artifacts import artifact_path,manifest
    report='EVIDENCE_REVIEW_20261106'
    private=artifact_path(tmp_path,report,include_private=True);private.parent.mkdir(parents=True);private.write_bytes(b'private source')
    with pytest.raises(ValueError):artifact_path(tmp_path,report)
    value=manifest(tmp_path,report)
    assert value['status']=='PRESENT' and value['download_url'] is None and value['access']=='PRIVATE_REVIEW_ARCHIVE'


def test_business_revalidation_flag_does_not_claim_version_change(env):
    s,_,did,_=env;p=proposal(env);ref=p['source_ref']
    row=dict(subject='STA_test',result=p,body_text=p['proof']['body'],evidence=['없는 요약문'],
        cross_review=dict(refs=[ref],selected_source_ref=ref,evidence_revalidation_required=True))
    pkg=package(row,[row],load_registry(s,[ref]));v=pkg['reference_validation']
    assert v['selected_comparison']=='UNCHANGED' and v['business_revalidation_required']
    assert not v['current_drift_refs']
    assert not pkg['quote_checks'][0]['direct_evidence_verified'] and not pkg['quote_checks'][0]['business_fact_verified']


def test_alternative_quote_carries_ref_hash_and_reproducible_anchor(env):
    s,_,did,_=env;p=proposal(env);ref=p['source_ref']
    row=dict(subject=did,result={},body_text='선택 본문',evidence=['총 100호'])
    other=dict(subject=did,role='officer',body_text='다른 저장 본문 총 100호 공급',body_ref=ref)
    q=package(row,[row,other],{})['quote_checks'][0]
    assert q['cause_classification']=='OTHER_STORED_VERSION' and not q['direct_evidence_verified']
    match=q['other_agent_body_matches'][0];a=match['anchor']
    assert match['requested_ref']==ref and other['body_text'][a['start']:a['end']]=='총 100호'


def test_structured_events_keep_every_date_and_observation_separate(env):
    s,_,did,_=env
    with s.sessions.begin() as db:
        source=sr.current(db,'document_evidence',did)
        row,_=upsert_revision(db,'document_evidence','seoul_press_watch','test',dict(source.payload,facts=[
            dict(stage='APPROVAL',kind='ACTUAL',date='2020-01-01',milestone='최초인가'),
            dict(stage='APPROVAL',kind='ACTUAL',date='2021-01-01',milestone='변경인가'),
            dict(stage='APPROVAL',kind='ACTUAL',date='2022-01-01',date_basis='OBSERVED_BY')]),'test')
        ref=sr.reference(row)
    row=dict(subject='STA_test',result=dict(source_ref=ref,stage='APPROVAL'))
    pkg=package(row,[row],load_registry(s,[ref]));events=pkg['structured_events']
    assert len(events)==3 and [e['event_type'] for e in events[:2]]==['최초인가','변경인가']
    assert events[2]['event_date'] is None and events[2]['observed_on']=='2022-01-01'
    assert not any(e['merge_authorized'] for e in events)


def test_business_completion_keeps_pinned_reanalysis_task_visible():
    from backend.ai_agents_inbox import attach_reviews
    record=dict(subject='DOC_test',state='DONE',business_status='REGISTRATION_REQUIRED')
    review=dict(current=True,revalidation_reasons=['복구 본문과 이전 AI 분석 동기화 필요'])
    with patch('backend.hold_review.load',return_value={'DOC_test':review}):
        row=attach_reviews(None,[record])[0]
    assert row['reanalysis_required'] and row['state']=='DONE'
    with patch('backend.hold_review.load',return_value={'DOC_test':dict(review,current=False)}):
        assert not attach_reviews(None,[dict(subject='DOC_test')])[0].get('reanalysis_required')
