import hashlib,json
from copy import deepcopy
import pytest
from sqlalchemy import select,func
from backend.db import Revision,Audit,upsert_revision
from backend import publication_evidence as evidence
from backend.publication_review_export import export_json,export_csv
from backend.publication_supplements import save as collect
from test_publication_reviews import env,csv_rows,approve

BODY='유니버설디자인하우스 장안 입주자 모집. 모집 세대는 405호(총 1호)입니다. 405는 호실번호이고 모집호수는 1호입니다. 현재 보유 주택의 잔여세대를 모집하며 신규 건설 공급 실적이 아닙니다.'

def finding():
 return dict(actor='시험 업무담당자',reason='원문 모집 구분 확인',external_recommendation={'code':'A','opinion':'참고 의견'},unknown_fields=['실제 입주 완료일'],facts=[dict(kind='QUANTITY',value=1,unit='호',scope='EXISTING_STOCK_RECRUITMENT',temporality='SCHEDULED',source_type='MANUAL',quote='모집 세대는 405호(총 1호)입니다.',body_sha256=hashlib.sha256(BODY.encode()).hexdigest(),aggregate_allowed=False)])

def test_current_manual_body_supersedes_ai_shell_and_old_revisions():
 item=dict(id='DOC',title='입주자 모집',source_revision_no=2,review_revision_no=0,status='HOLD')
 result=evidence.evidence(item,{},dict(body_text=BODY,source_revision_no=2),dict(body_text='페이스북 트위터 카카오 공유하기 URL 복사 '*5,source_revision_no=2),{})
 assert result['effective_origin']=='MANUAL' and result['effective_text']==BODY
 assert result['candidates'][2]['quality']=='BOILERPLATE'
 result=evidence.evidence(item,{},dict(body_text=BODY,source_revision_no=1),{}, {})
 assert result['quality']=='STALE_ONLY' and not result['effective_text']
 assert evidence.text_quality('본문 내용 바로가기 서울소식 보도자료 검색 분야선택 전체 경제 주택 문화 ' * 5)=='BOILERPLATE'
 assert evidence.text_quality('2026.11.02 K-Artprice 프라임뉴시스 [속보] 신규택지 정부 발표 '*15)=='BOILERPLATE'


def test_assessment_is_revision_pinned_idempotent_and_never_aggregates(env):
 s,doc,pid=env
 collect(s,doc,1,BODY,'본문 확인',[],'담당자','b'*64)
 with s.sessions() as db:before=db.scalar(select(Revision).where(Revision.entity_id==pid)).payload_hash
 payload=finding();evidence.save(s,doc,1,0,payload)
 assert evidence.save(s,doc,1,0,payload)['outcome']=='unchanged'
 row,=export_json(s)['items'];assert row['effective_origin']=='MANUAL'
 assert row['facts'][0]['value']==1 and not row['aggregate_allowed'] and not row['linkage_confirmed']
 csv,=csv_rows(export_csv(s));assert '보유' in csv['본문보유여부'] and csv['통합유효본문']==BODY
 assert json.loads(csv['구조화사실_JSON'])[0]['scope']=='EXISTING_STOCK_RECRUITMENT'
 with s.sessions() as db:
  assert db.scalar(select(Revision).where(Revision.entity_id==pid)).payload_hash==before
  assert db.scalar(select(func.count()).select_from(Audit).where(Audit.action=='PUBLICATION_EVIDENCE_REVIEW'))==1
 bad=deepcopy(payload);bad['facts'][0]['quote']='405호를 새로 공급했습니다.'
 with pytest.raises(ValueError,match='인용'):evidence.save(s,doc,1,0,bad)
 with pytest.raises(ValueError,match='판본'):evidence.save(s,doc,2,0,payload)
 approve(s,doc,pid)
 row,=export_json(s)['items'];assert not row['assessment_current'] and not row['facts']
 assert row['linkage_confirmed'] and not row['aggregate_allowed']


def test_exports_redact_rosters_and_filter_without_mutation(env):
 s,doc,pid=env
 collect(s,doc,1,BODY+'\n성명 | 생년월일 | 연락처\n김가나 | 900101-1234567 | 010-1234-5678\n\n계약기간: 2026-11-02\nabc@example.com','검증',[],'담당자','b'*64)
 with s.sessions() as db:before=db.scalar(select(func.count()).select_from(Revision))
 encoded=json.dumps(export_json(s),ensure_ascii=False);csv=export_csv(s)
 for text in [encoded,csv]:
  assert '김가나' not in text and '900101-1234567' not in text and '010-1234-5678' not in text and 'abc@example.com' not in text
  assert '계약기간' in text
 assert export_json(s,status='APPROVED')['count']==0
 assert export_json(s,search='존재하지않는검색')['count']==0
 with s.sessions() as db:assert db.scalar(select(func.count()).select_from(Revision))==before


def test_json_download_contract_and_changed_manual_text_invalidates_findings(env,monkeypatch):
 from fastapi.testclient import TestClient
 from backend.app import create_app
 s,doc,pid=env;monkeypatch.setenv('POC10_DATA_DIR',str(s.data_dir))
 collect(s,doc,1,BODY,'확인',[],'담당자','b'*64)
 evidence.save(s,doc,1,0,finding())
 with TestClient(create_app(s.engine,auto_collect=False)) as client:
  path='/poc/home/api/publication-reviews/export.json'
  response=client.get(path,params={'status':'REVIEW'})
  assert response.status_code==200 and response.json()['count']==1
  assert response.headers['content-type'].startswith('application/json')
  assert 'attachment;' in response.headers['content-disposition'] and '.json' in response.headers['content-disposition']
  assert response.headers['cache-control']=='no-store'
  assert client.get(path,params={'status':'INVALID'}).status_code==422
  assert client.get(path,params={'priority':5}).status_code==422
 collect(s,doc,1,BODY+' 정정: 추후 모집공고 재확인 필요.','정정',[],'담당자','c'*64)
 row,=export_json(s)['items']
 assert not row['assessment_current'] and row['facts']==[] and row['event_group'] is None
