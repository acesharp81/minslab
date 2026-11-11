"""Guardrail tests on archived real LH text. Crafted proposals are tests, not AI outcomes."""
from copy import deepcopy
from pathlib import Path
import hashlib
import pytest
from backend.evidence_chain import document_snapshot, validate_assessment, save_case, cases
from backend.ai_collection_store import Store
from backend.attachment_rule import extract_attachment

ROOT=Path(__file__).resolve().parents[1]
BODY=(Path(__file__).parent/'fixtures/evidence_chain/lh-siheung-s1.txt').read_text()
QUOTE='한국토지주택공사(LH), 시흥거모지구 S-1블록 공공분양주택 300호 공급'
URL='https://www.lh.or.kr/gallery.es?mid=a10502000000&bid=0003&act=view&list_no=12169'
RAW=(Path(__file__).parent/'fixtures/evidence_chain/lh-siheung-s1.html').read_bytes()
PID='PRO_5fd2115e976e1d5bb4e90456'


def proposal():
    ref=dict(document_id='DOC_87cca7787d542e5eb6512549',quote=QUOTE)
    return dict(project_id=PID,conflicts=[],findings=[dict(stage='SUPPLY',basis='DIRECT',occurrence=True,
        event_date=None,units=300,scope='PARTIAL',scope_description='시흥거모 S-1 공공분양 모집 범위',
        evidence=[ref],identity_evidence=[ref],inference_from_stage=None,
        reasoning='실제 원문 인용과 부분 물량을 검사하는 개발 시험',missing_information=['정확한 사건일'])])


def sources():
    return [document_snapshot('DOC_87cca7787d542e5eb6512549','시흥거모 S-1',URL,1,BODY,'OFFICIAL')]


def test_partial_evidence_survives_missing_date_without_becoming_actual():
    data=proposal();before=deepcopy(data);source=sources();result=validate_assessment(data,PID,source)
    assert result['linked']==1 and result['findings'][0]['event_date'] is None
    assert result['findings'][0]['semantic_review']=='REQUIRED'
    assert result['findings'][0]['official_actuals_eligible'] is False
    assert result['official_actuals_changed']==0 and data==before
    span=result['findings'][0]['evidence_spans'][0]
    assert source[0]['text'][span['start']:span['end']]==QUOTE


@pytest.mark.parametrize('change',['hash','quote','identity','units','date','scope','authority'])
def test_inconsistent_or_unproven_fields_remain_on_hold(change):
    data=proposal();source=sources();f=data['findings'][0]
    if change=='hash':source[0]['text']+='\n'  # Deliberate corruption test, not a source revision.
    if change=='quote':f['evidence'][0]['quote']='원문에 없는 문장을 차단하는 시험 입력입니다'
    if change=='identity':f['identity_evidence']=[]
    if change=='units':f['units']=301
    if change=='date':f['event_date']='2099-01-01'
    if change=='scope':f['scope']='UNKNOWN'
    if change=='authority':source[0]['authority']='NONOFFICIAL'
    checked=validate_assessment(data,PID,source)
    assert checked['held']==1 and checked['findings'][0]['validation_errors']


def test_supply_does_not_prove_construction_and_inference_cannot_invent_date():
    data=proposal();inferred=deepcopy(data['findings'][0])
    inferred.update(stage='CONSTRUCTION',basis='INFERRED',inference_from_stage='SUPPLY',event_date='2026-10-23',units=None)
    data['findings'].append(inferred)
    result=validate_assessment(data,PID,sources())
    assert result['findings'][1]['status']=='HOLD'
    assert any('정확한 일자' in x for x in result['findings'][1]['validation_errors'])
    assert any('선행관계' in x for x in result['findings'][1]['validation_errors'])


def test_duplicate_or_wrong_project_rejected():
    data=proposal()
    with pytest.raises(ValueError):validate_assessment(data,'different-project',sources())
    data['findings']*=2
    assert validate_assessment(data,PID,sources())['held']==2
    with pytest.raises(ValueError):validate_assessment(proposal(),PID,sources()*2)


def test_cases_are_append_only_and_empty_read_does_not_create_table(tmp_path):
    store=Store(tmp_path)
    assert cases(store)==[]
    with store.db() as db:assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='evidence_chain_cases'").fetchone()
    a=save_case(store,dict(project_id=PID,assessment=validate_assessment(proposal(),PID,sources())))
    b=save_case(store,dict(project_id=PID,assessment=validate_assessment(proposal(),PID,sources())))
    assert a['id']!=b['id'] and len(cases(store))==2
    assert cases(store,a['id'])==[a]


@pytest.mark.parametrize('selector,url',[
    ('a.btn_line',URL),
    ('a[href*="attachApiPreview"]',URL),
    ('a[title*=".hwpx"][href*="galleryDownload"]',URL),
    ('a[title*=".pdf"][href*="galleryDownload"]','https://example.com/'),
])
def test_attachment_invalid_selection_stops_before_network(selector,url):
    class NoNetwork:
        last={}
        def get(self,*args,**kwargs):raise AssertionError('검증 전에 네트워크 접근')
    with pytest.raises(ValueError):extract_attachment(RAW,url,selector,NoNetwork())


def test_real_archived_html_sha_is_pinned():
    assert hashlib.sha256(RAW).hexdigest()=='12373da773eaca256292528faa9527e02418cddf33f7985ec10b5ce7655e3011'


def test_metadata_only_pdf_viewer_is_not_a_successful_html_body():
    from backend.algorithm_review import extract
    with pytest.raises(ValueError,match='PDF iframe'):
        extract(RAW,'#contents_body')


def test_case_api_is_read_only_and_preserves_review_origin(tmp_path):
    from types import SimpleNamespace
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.evidence_chain_api import install
    store=Store(tmp_path)
    saved=save_case(store,dict(project_id=PID,project_name='시흥거모 S1',run_id='LOCAL_TEST_ONLY',
        summary={'official_actuals_changed':0},rule_review={'origin':'REVIEWED_AI_PROPOSAL'},
        assessment=validate_assessment(proposal(),PID,sources()),sources=sources()))
    app=FastAPI();install(app,SimpleNamespace(data_dir=tmp_path),'/poc/home')
    with TestClient(app) as client:
        root='/poc/home/api/ai-agents/evidence-cases'
        assert client.get(root).json()['items'][0]['id']==saved['id']
        assert client.get(root+'/'+saved['id']).json()['rule_review']['origin']=='REVIEWED_AI_PROPOSAL'
        view=client.get(root+'/'+saved['id']).json()
        assert 'text' not in view['sources'][0] and view['sources'][0]['text_omitted']
        assert view['sources'][0]['text_sha256']==sources()[0]['text_sha256']
        assert cases(store,saved['id'])[0]['sources'][0]['text']==BODY
        assert client.get(root+'/unknown').status_code==404
        assert client.post(root,json={}).status_code==405
    with store.db() as db:assert db.execute('SELECT COUNT(*) FROM calls').fetchone()[0]==0


def test_pdf_whitespace_alignment_keeps_exact_source_offsets():
    data=proposal();q=data['findings'][0]['evidence'][0]
    unique_quote=BODY.splitlines()[0]
    assert BODY.count(unique_quote)==1
    q['quote']=unique_quote.replace(' ', '  ')
    result=validate_assessment(data,PID,sources())
    span=result['findings'][0]['evidence_spans'][0]
    assert span['match_method']=='WHITESPACE_ONLY'
    assert BODY[span['start']:span['end']]==unique_quote
    assert span['model_quote']!=span['quote']


def test_ellipsis_is_not_repaired_into_a_quote():
    data=proposal();data['findings'][0]['evidence'][0]['quote']=QUOTE[:20]+'…'+QUOTE[-10:]
    assert validate_assessment(data,PID,sources())['held']==1


def test_ambiguous_whitespace_alignment_remains_on_hold():
    data=proposal()
    assert BODY.count(QUOTE)>1
    data['findings'][0]['evidence'][0]['quote']=QUOTE.replace(' ', '  ')
    result=validate_assessment(data,PID,sources())
    assert result['held']==1
    assert any('모호함' in error for error in result['findings'][0]['validation_errors'])
