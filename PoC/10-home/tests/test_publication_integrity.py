"""Fixed 11/04 examples and independent integrity invariants; no live services."""
import csv,io,json,hashlib
from pathlib import Path
import pytest
from backend.publication_evidence import evidence,redact
from backend.publication_evidence_integrity import sha,export_anchor,body_kind
from backend.publication_review_export import export_csv,export_json
from backend.publication_supplements import save as supplement
from test_publication_reviews import env

CASES=json.loads((Path(__file__).parent/'fixtures/publication_integrity_20261104/cases.json').read_text())

def evaluate(case,**kwargs):
 return evidence(case['item'],case['source'],case['manual'],case['ai'],case['assessment'],**kwargs)

@pytest.mark.parametrize('case',CASES,ids=lambda c:f"document-{c['no']:03}")
def test_fixed_111_evidence_references_hashes_quotes_and_no_metric_approval(case):
 result=evaluate(case)
 assert sha(result['effective_text'])==result['effective_text_sha256']
 assert result['aggregate_allowed'] is False and result['verification_stages']['APPROVED_FOR_METRIC'] is False
 assert not result['linkage_confirmed']
 sources={c['origin']:c for c in result['candidates']}
 for c in sources.values():assert redact(c['text'])==c['text']
 for f in result['evidence_records']:assert redact(f['quote'])==f['quote']
 for f in result['evidence_records']:
  assert f['evidence_id'].startswith('EV_') and f['claim_id'].startswith('CLAIM_')
  assert f['aggregate_allowed'] is False
  if f['verification_status']=='QUOTE_MATCHED':
   c=sources[f['source_type']];a=f['quote_anchor']
   assert f['body_sha256']==sha(c['text'])
   assert c['text'][a['start']:a['end']]==f['quote']
 assert evaluate(case)['evidence_set_id']==result['evidence_set_id']


def test_report_regression_cases_have_independent_expected_outcomes():
 by_no={c['no']:evaluate(c) for c in CASES}
 a=by_no[1];assert a['effective_origin']=='MANUAL' and a['quality']=='SUMMARY_ONLY'
 assert a['candidates'][2]['document_kind']=='LIST_PAGE' and not a['usable_detail_body']
 for n in [23,30]:
  assert by_no[n]['needs_revalidation'] and not by_no[n]['assessment_current'] and not by_no[n]['facts']
  assert by_no[n]['officer_assessment']['facts'] # retain historical evidence
 for n in [70,85,88,102]:
  assert by_no[n]['raw_text_present'] and not by_no[n]['effective_text'] and not by_no[n]['usable_detail_body']
 for n,event in [(42,'CONTRACT'),(66,'APPLICATION')]:
  assert any(f['event_type']==event for f in by_no[n]['business_event_dates'])
  assert event not in by_no[n]['stage_dates'] # original four-stage contract retained
 facts=by_no[84]['facts'];room=next(f for f in facts if f.get('value')==405)
 assert room['quantity_role']=='IDENTIFIER' and not room['aggregate_allowed']
 rental=next(f for f in by_no[41]['facts'] if f.get('value')==426)
 total=next(f for f in by_no[41]['facts'] if f.get('value')==2200)
 assert rental['subset_of_claim_id']==total['claim_id'] and not rental['aggregate_allowed']
 assert {(f['value'],f['unit']) for f in by_no[53]['facts'] if f['kind']=='QUANTITY'}=={(868,'가구'),(987,'실')}
 for n in [78,79]:assert by_no[n]['related_documents'][0]['relation_type']=='FOLLOW_UP_TO'
 for n in [108,109]:assert not by_no[n]['related_documents'][0]['duplicate_publication_confirmed']


def test_email_cut_inside_quote_is_anchored_in_whole_redacted_body():
 body='모집은 6세대입니다. 문의 이메일: example.person@sample.test 접수 후 확인합니다.\r\n'
 quote=body[:body.index('@')+5]
 text=redact(body);a=export_anchor(body,quote,text)
 assert a and 'example.person' not in a['quote'] and '@' not in a['quote']
 assert text[a['start']:a['end']]==a['quote'] and a['redaction_context_expanded']
 assert sha(body)!=sha(text)
 assert redact(text)==text


def test_csv_hashes_are_for_exact_cells_including_formula_escape(env):
 service,did,_=env
 body='= 사업 공고 본문입니다. 전체 모집은 12호이며 기존 재고 모집이고 새로운 착공 실적은 아닙니다. 담당 문의 example.person@sample.test\r\n'
 supplement(service,did,1,body,'본문 확보',[],'시험 담당자','b'*64)
 rows=list(csv.DictReader(io.StringIO(export_csv(service).lstrip('\ufeff'))));r=rows[0]
 assert r['통합유효본문'].startswith("'=") and sha(r['통합유효본문'])==r['통합본문_SHA256']
 for c in json.loads(r['본문판본별상태_JSON']):
  if c['chars']:assert sha(r[c['hash_input_field']])==c['sha256']
 result=export_json(service)['items'][0]
 assert result['effective_text'].startswith('=') and sha(result['effective_text'])==result['effective_text_sha256']
 assert 'example.person' not in json.dumps(r,ensure_ascii=False)


def test_quote_failure_and_source_hash_mismatch_are_not_silently_current():
 import copy
 c=copy.deepcopy(CASES[0]);c['assessment']['facts'][0]['quote']='존재하지 않는 인용'
 assert 'QUOTE_MISMATCH' in evaluate(c)['revalidation_reasons']
 c=copy.deepcopy(CASES[0]);c['item']['source_hash']='different'
 r=evaluate(c);assert 'SOURCE_HASH_CHANGED' in r['revalidation_reasons'] and not r['facts']


def test_pdf_trailing_formfeeds_and_quote_newlines_remain_idempotent():
 body='공식 공고문\n공급 안내 12호\n\n\f\n'
 text=redact(body)
 assert text=='공식 공고문\n공급 안내 12호' and redact(text)==text
 a=export_anchor(body,'공식 공고문\n',text)
 assert a['quote']=='공식 공고문' and text[a['start']:a['end']]==a['quote']


def test_digest_numeric_runs_are_not_redacted_as_personal_identifiers():
 digest='95c08ebb0f7b28f5bf7e95e4663902803174ee681c1dd1d6953287fb919d3c7f'
 assert redact(digest)==digest
 assert redact('문의 010-1234-5678')=='문의 [개인 연락처 제외]'
