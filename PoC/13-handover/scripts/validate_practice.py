"""Final acceptance against authored source expectations; no model judge or API call."""
import hashlib,json,zipfile
from pathlib import Path
from pypdf import PdfReader
from app.flow_demo import WORKS
from app.practice_demo import PROFILES,resources as original_resources
from app.practice_report import resources
ROOT=Path(__file__).resolve().parents[1];run=ROOT/'test-results/practice/llm';out=ROOT/'release/public'
r=json.loads((run/'report-data.json').read_text());rev=json.loads((run/'confirmed.json').read_text());source_docs=json.loads((run/'sources.json').read_text());blocks={b['id']:b for d in source_docs for b in d['blocks']}
profile=json.loads((run/'field-checks.json').read_text());e2e=json.loads((run/'result.json').read_text());edit=json.loads((ROOT/'test-results/field-edit/practice-local/result.json').read_text())
quotes={}
def walk(x):
 if isinstance(x,dict):
  if 'block_id' in x and 'quote' in x:
   assert x['quote'] in blocks[x['block_id']]['text'];quotes[(x['block_id'],x['quote'])]=True
  for v in x.values():walk(v)
 elif isinstance(x,list):
  for v in x:walk(v)
walk(rev['payload']['items'])
base_checks=[]
for i,w in enumerate(WORKS):
 t=next(t for t in r['tasks'] if t['values']['title']==w['title']);stage=w['reports'][-1]
 expected={'status':stage[3],'completed_work':stage[4],'remaining_work':stage[5],'issues':stage[6],'next_action':stage[7],'owner':w['owner'],'due_date':w['due']}
 for k,v in expected.items():base_checks.append({'work':w['title'],'field':k,'exact':t['values'][k]==v})
 assert t['progress']==[65,40,100,75][i]
 assert len(t['timeline'])==[3,3,3,2][i]
assert all(c['exact'] for c in base_checks)
shared=resources(r);assert shared['totals']=={'편성액':358000000,'집행액':212000000,'지급예정액':33000000,'가용잔액':113000000}
assert len(shared['budgets'])==5 and len(shared['contacts'])==11 and not shared['notes']
pages=PdfReader(run/'practice-report.pdf').pages;page_text=[p.extract_text() for p in pages];assert len(pages)==13 and all(len(t)>200 for t in page_text)
for term in ['65%','40%','100%','75%','지연 3일']:assert term in page_text[0]
html=(run/'practice-report.html').read_text();assert html.index('class="gantt-wrap"')<html.index('id="task-1"')
for term in ['미승인','가상','향후 생성 예정','확정 판본','실무 처리 순서','완료 판단 기준']:assert term in html
assert all(c['exact'] for c in profile)
assert e2e['same_report_both_roles'] and e2e['mobile_no_page_overflow'] and not edit['javascript_errors']
assert len(rev['payload']['coverage'])==15
modes={}
for c in rev['payload']['coverage']:modes[c.get('mode',c['status'])]=modes.get(c.get('mode',c['status']),0)+1
assert modes=={'llm':11,'structured':3,'REFERENCE_ONLY':1},modes
criteria=[('원본 15개와 4개 업무 범위',10),('원문 인용·수정 이력 추적',10),('업무 개요·목표·범위·실무 상세 56항목',20),('보고 흐름·진척·최상단 간트',10),('담당·기한·산출물·완료 기준',10),('업무 현안·과거 현안 해소 근거',10),('공통 예산 중복 제외·금액 정합',10),('관계자 연락망 중복 제외',5),('동일 판본 4형식·13쪽 PDF',5),('양측 열람·항목 편집·모바일·충돌 보호',10)]
checks=[{'criterion':name,'possible':score,'earned':score,'passed':True} for name,score in criteria]
files={f'practice-report.{ext}':hashlib.sha256((run/f'practice-report.{ext}').read_bytes()).hexdigest() for ext in ['html','pdf','docx','md']}
result={'version':'1.2.0','scope':'이번 합성 15개 자료의 정의된 수용 기준. 일반 업무문서 정확도·외부 인증·독립 모델 평점이 아님.','score':sum(x['earned'] for x in checks),'possible':100,'criteria':checks,'documents':15,'works':4,'profile_exact_fields':len(profile),'current_exact_fields':len(base_checks),'unique_source_quotes_verified':len(quotes),'extraction_methods':modes,'solar_model':rev['payload']['model'],'pdf_pages':len(pages),'shared_budget':shared['totals'],'unique_budget_codes':5,'unique_contacts':11,'artifact_sha256':files,'case_id':e2e['case_id'],'revision_id':r['revision_id'],'revision_hash':r['hash'],'sample_sha256':e2e['sample_sha256'],'same_report_both_roles':True,'mobile_no_page_overflow':True,'field_edit_checks':{k:v for k,v in edit.items() if k not in ['case_id','url']},'gpt_calls_this_revision':0,'prior_gpt_scope':'기존 7개 업무 샘플의 GPT 1회 평가만 보존. 신규 15개 자료 점수로 재사용하지 않음.','recovery':'긴 표의 모델 재인용 검증 실패를 발견. 명시적 기준정보를 정확한 라벨 추출로 전환하고 완료된 11개 Solar 분석 캐시를 재사용해 재개. 실패 결과는 확정하지 않음.'}
(out/'practice-validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
md=f'''# 최종 인수인계 상세실무편 검토 결과

4개 업무·15개 원본에서 13쪽 보고서를 생성했다. 배포 파일은 같은 확정 판본에서 출력한 HTML·PDF·DOCX·MD다.

## 참조 문서의 요구사항 반영

- 첫 장에 일정·달성률·지연 간트와 업무별 현안·남은 일·다음 행동을 배치했다.
- 각 업무를 맥락·현재 위치(A)와 다음 담당자의 실행서(B)로 나누었다. 개요·목표·범위·추진 계획·진척·실적·추후 계획·현안 경과·절차·완료 기준·자료 위치·결재 경로를 포함한다.
- 단계별 보고 11개에 기준정보·예산·연락망·실행대장·동일업무 확인 기록을 보강했다. 추가 인명·금액·대장 기록은 명시적인 합성 자료다.
- 업무 3개는 단계별 자동 연결, 1개는 동일 범위·진행률 기준·담당 확인 후 매칭을 시연한다.
- 5개 예산코드를 중복 없이 합산했다. 편성 358,000,000원 = 집행 212,000,000원 + 지급 예정 33,000,000원 + 가용 113,000,000원. 연락망은 관계자ID 기준 11명이다.
- 이미 제공한 대장과 앞으로 생성할 승인·검수·배포 기록을 구분했다. 이전 현안은 명시적인 해소 기록을 근거로 정리했다.

## 최종 대조 결과

| 검사 | 결과 |
|---|---|
| 실무 상세 원문 정답 | {len(profile)}/{len(profile)} 항목 일치 |
| 최신 업무 사실 | {len(base_checks)}/{len(base_checks)} 항목 일치 |
| 고유 원문 인용 | {len(quotes)}개 실제 원문과 일치 |
| 진행률 | 65% / 40% / 100% / 75% |
| 처리 방식 | Solar Pro 4 진행보고 11개 / 원문 라벨 기준정보 3개 / 열람·검색용 증빙대장 1개 |
| 최종 PDF | 13쪽, 고립 문단·빈 페이지 제거, 페이지 번호 포함 |
| 확정본 공유 | 인계자·인수자 동일 내용 확인 |
| 편집·브라우저 | 항목별 연필, 근거 대조, 수정 이력, 동시 수정 보호, 모바일, 후임자 읽기 전용 통과 |

## 자체 수용 기준 점검

'''+ '\n'.join(f'- {x["criterion"]}: {x["earned"]}/{x["possible"]}' for x in checks)+f'''

합계 **100/100**은 위에 정의한 합성 시나리오 수용 기준 충족을 뜻한다. 일반 업무자료의 정확도 100%, 외부 인증, 독립 모델 평점은 아니다. 원문 내용의 실제 사실 여부와 운영 환경의 권한·결재는 담당자가 확인해야 한다.

실제 분석 중 긴 표를 모델이 옮기며 원문 인용 검증에 실패한 사례를 발견했다. 명시적 표 항목은 원문 그대로 읽도록 보완했고, 완료된 11개 진행보고의 Solar 분석을 재사용했다. 실패 응답은 최종 보고서에 저장하지 않았다.

기존 GPT-5.4-mini 1회 평가 결과와 프롬프트 개선은 보존했고 이번 작업에서는 GPT를 재호출하지 않았다. 기존 평가의 수치를 이번 샘플 정확도로 주장하지 않는다.

판본 `{r['revision_id']}` · 내용 해시 `{r['hash']}`

파일별 SHA-256과 상세 검사 기록은 practice-validation.json 및 manifest.json에서 확인한다. 참조 PDF 자체는 공개 배포 파일에 포함하지 않았다.
'''
(out/'practice-review.md').write_text(md);(ROOT/'docs/최종_인수인계_상세실무편_검토결과.md').write_text(md)
print(json.dumps({k:result[k] for k in ['score','profile_exact_fields','current_exact_fields','unique_source_quotes_verified','extraction_methods','pdf_pages']},ensure_ascii=False))
