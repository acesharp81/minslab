import io
import zipfile
from docx import Document
from app.submission import submission_archive
from test_flow import client, seed, new_case, generate
from test_reports import confirm


def test_public_guide_and_synthetic_samples_but_no_private_file(client, monkeypatch):
    c=client
    assert c.get('/guide').status_code==200
    archive=c.get('/samples/submission.zip')
    assert archive.status_code==200
    with zipfile.ZipFile(io.BytesIO(archive.content)) as z:
        assert len(z.namelist())==7
        assert all(n.endswith(('.docx','.xlsx','.txt','.pdf')) for n in z.namelist())
        assert '합성자료' in '\n'.join(p.text for p in Document(io.BytesIO(z.read('01_사업현황.docx'))).paragraphs)
    assert c.get('/downloads/.env').status_code==404
    assert c.get('/downloads/unknown.zip').status_code==404
    assert c.get('/downloads/%2e%2e%2f.env').status_code==404
    base=new_case(c)
    assert c.post(base+'/documents',files={'file':('samples.zip',archive.content)}).status_code==200
    generate(c,base)
    docs=c.get(base).json()['documents']
    assert len(docs)==7 and all(d['status'] in ('SUCCESS','PARTIAL') for d in docs)


def test_docx_uses_exact_confirmed_revision_for_both_parties(client):
    c=client;base,rev=seed(c)
    url=base+f"/exports/{rev['id']}.docx"
    assert c.get(url).status_code==403
    confirm(c,base,rev)
    a=c.get(url);b=c.get(url,headers={'X-Role':'successor'})
    assert a.status_code==200 and 'wordprocessingml' in a.headers['content-type']
    with zipfile.ZipFile(io.BytesIO(a.content)) as z1,zipfile.ZipFile(io.BytesIO(b.content)) as z2:
        assert z1.read('word/document.xml')==z2.read('word/document.xml')
    doc=Document(io.BytesIO(a.content));text='\n'.join(p.text for p in doc.paragraphs)
    for term in ['당장 확인·처리할 현안','남은 업무','완료한 일','주민 수요조사','부록. 원문 근거','내용 해시:',rev['hash']]:assert term in text
    generate(c,base)
    with zipfile.ZipFile(io.BytesIO(c.get(url).content)) as new,zipfile.ZipFile(io.BytesIO(a.content)) as old:
        assert new.read('word/document.xml')==old.read('word/document.xml')


def test_cross_document_merge_keeps_conflicts_and_stage_provenance(client):
    # The final GPT reviewer suggested splitting these records. Product contract requires
    # merging the same explicit task/owner while preserving each source observation.
    c=client;base,rev=seed(c)
    items=rev['payload']['items']
    plan=next(i for i in items if i['fields']['title']['value']=='2027년 생활문화 사업계획')
    due=plan['fields']['due_date']
    assert due['review_status']=='CONFLICT'
    assert {o['value'] for o in due['observations']}=={'2026-11-20','2026-11-25'}
    assert len({e['document_revision_id'] for e in due['evidence']})==2
    facility=next(i for i in items if i['fields']['title']['value']=='시설 안전점검')
    assert facility['business_status']!='COMPLETED'
    assert {o['value'] for o in facility['fields']['status']['observations']}=={'점검 예정','사전 점검 완료'}
    for field in facility['fields'].values():
        for ref in field['evidence']:
            source=c.get(base+'/blocks/'+ref['block_id']).json()
            assert source['doc_id']==ref['document_revision_id'] and ref['quote'] in source['text']


def test_download_materials_public_while_workspace_stays_protected(tmp_path,monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import create_app
    monkeypatch.setenv('HANDOVER_ACCESS_TOKEN','synthetic-download-boundary-token')
    with TestClient(create_app(tmp_path,{'url':'https://example.invalid','model':'solar-pro4','key':''})) as c:
        assert c.get('/api/cases').status_code==401
        assert c.get('/guide').status_code==200
        assert c.get('/samples/submission.zip').status_code==200
        assert c.get('/downloads/.env').status_code==404
        assert c.get('/api/health').json()['version']=='1.6.7'


def test_public_preview_style_policy_and_private_boundary(client,tmp_path,monkeypatch):
    import json
    import app.main
    directory=tmp_path/'release/public';directory.mkdir(parents=True)
    (directory/'manifest.json').write_text(json.dumps({'files':[{'file':'flow-report.html'}]}))
    (directory/'flow-report.html').write_text('<style>body{color:green}</style><h1>합성 보고서</h1>')
    monkeypatch.setattr(app.main,'ROOT',tmp_path)
    response=client.get('/downloads/flow-report.html')
    assert response.status_code==200
    assert response.headers['content-disposition'].startswith('inline')
    assert "default-src 'none'" in response.headers['content-security-policy']
    assert "style-src 'unsafe-inline'" in response.headers['content-security-policy']
    assert client.get('/downloads/.env').status_code==404
