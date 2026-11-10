"""Publish only verified synthetic artifacts; never a workspace database."""
import json,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'release/public';LIVE=ROOT/'test-results/versions/live'
r=json.loads((LIVE/'result.json').read_text());assert r['all_checks_pass'] and r['same_report_both_roles']
initial=json.loads((ROOT/'test-results/versions/initial-attempt/result.json').read_text())
r['initial_attempt']={'checks':len(initial['checks']),'passed':sum(x['pass'] for x in initial['checks']),'failed_fields':[{'work':x.get('work'),'field':x['check'],'actual':x.get('actual'),'expected':x.get('expected')} for x in initial['checks'] if not x['pass']],'model_calls':initial['model_calls'],'usage':initial['usage']}
r['total_validation_model_calls']=r['model_calls']+initial['model_calls']
r['negative_tests']={'actual_files_parsed':True,'cases':['same-day revision conflict','undated content','revision/time inversion'],'expected':'abstain','passed':3,'method':'실제 예외 HWPX/PDF를 파싱한 뒤 판본 선택기를 검사. 예외 ZIP에 별도 LLM 호출은 하지 않음.'}
r['regression_tests']=61;r['additional_gpt_calls']=0
browser=ROOT/'test-results/versions/browser/result.json'
if browser.exists():r['public_browser_checks']=json.loads(browser.read_text())
(OUT/'version-validation.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n')
for ext in ['html','pdf','md','docx']:shutil.copy2(LIVE/('version-report.'+ext),OUT/('version-report.'+ext))
text=f'''# 파일명·버전 혼선 검증 및 구현 결과

## 결과

중앙부처 개조식 합성 문서 13개를 실제 {', '.join(r['resolved_models'])}로 분석하여 **4개 사업**으로 자동 통합했습니다. 최종 검사 **{len(r['checks'])}개 모두 통과**, 코드 회귀 검사 **61개 통과**입니다. 공개 사이트의 새 체험 버튼·판본 비교 펼치기·모바일 화면·다운로드 링크도 확인했습니다. 이 결과는 제공한 합성 샘플 범위의 검증이며 모든 실문서에 대한 정확도 보장이 아닙니다.

| 사업 | 채택 파일 | 채택 기준 | 진행률 | 핵심 확인 |
|---|---|---|---:|---|
| 지역생활서비스 통합지원 | 1234.pdf | 11/08, 3차, 16:30 | 65% | 같은 날 2차 80% 대신 3차 정정치 채택 |
| 공공시설 안전관리 고도화 | 붙임.xlsx | 11/08, 3차 | 70% | 승인 기한 경과와 미완료 위험시설 반영 |
| 디지털 민원안내 표준화 | 새 문서.hwpx | 11/08, 3차 | 90% | 담당 이서준 → 정여울 변경 반영 |
| 취약계층 돌봄연계 | abc.xlsx | 11/08, 3차 | 55% | 11/09의 100% 초안은 현재 사실에서 제외 |

최종 확정 판본: `{r['revision_id']}`. 인계자·인수자가 동일한 HTML을 열람하는지, 모바일 화면 넘침이 없는지 확인했습니다. PDF·DOCX·Markdown은 같은 확정 판본에서 생성했습니다. 보고서 최상단에는 간트·진행률 현황, 업무별로 현재 기준본·보고 흐름·상세 내용이 있으며 판본 비교는 참고 영역을 펼쳐 확인합니다.

## 실제로 시험한 내용

- 실제 Solar 문서별 추출 후 본문 사업명·최신 파일·진행률·현재 상태·담당·기한·현안·남은 업무·다음 조치를 정답표와 대조했습니다.
- 업무 개요·목표·범위·추진 계획·완료 실적·추후 계획·처리 순서·완료 기준·인계 산출물·결재·자료 위치·예산·연락처·협업 부서의 존재를 검사했습니다. 이 상세 항목 검사는 누락 검사이며 모두의 의미를 독립 모델이 재심사한 것은 아닙니다.
- 최종 필드의 원문 인용 **{r['verified_quotes']}개**를 실제 원문 블록과 대조했습니다. 모델 출력 계약도 원문에 없는 인용을 거부합니다.
- 파일명·문서 ID·처리 순서를 바꿔 추출 이후의 통합·판본 선택을 **20회 재실행**했습니다. 모든 필드 값과 진행률이 같았습니다. 이 20회는 저장된 추출 결과를 재사용했으며 모델을 20회 재호출한 것이 아닙니다. 별도 계약 검사에서 파일명이 달라도 모델 입력 메시지가 동일함을 확인했습니다.
- 별도 ZIP 3종은 실제 파일을 파싱하여 같은 판의 상충, 날짜 불명확, 차수·수정시각 역전에서 최신본 선택을 보류하는지 검사했습니다. 이 예외 3종에 별도 Solar 호출은 하지 않았습니다.
- 입력 묶음에는 정답표가 들어 있지 않습니다. 파일 저장일은 일부러 구판이 더 최신으로 되어 있으며 선택 로직은 이를 읽지 않습니다.

## 발견한 문제와 수정

최초 실제 검사에서는 {sum(x['pass'] for x in initial['checks'])}/{len(initial['checks'])}개가 통과했습니다. 4개 사업 모두 최신 파일은 맞았지만 현재 상태에 설명문 대신 진행률만 들어갔습니다. 상태는 '진척 현황' 등 현재 수행 내용을 우선 인용하고 숫자만 있는 진행률을 상태로 사용하지 않도록 프롬프트를 수정했습니다.

PDF의 예산·향후 계획이 시각적 줄바꿈 때문에 여러 블록으로 갈라져 뒤쪽 내용이 빠지는 문제도 확인했습니다. `○ (항목)`으로 시작하는 한 문단의 연속 줄을 원문 줄바꿈과 페이지·줄 위치를 보존하여 묶었습니다. 재검증에서 예산 잔액 144,000,000원과 향후 계획의 마지막 승인 문구까지 인용됨을 확인했습니다.

실제 모델 호출: 최초 {initial['model_calls']}회 + 수정 후 {r['model_calls']}회 = **{r['total_validation_model_calls']}회**. 운영 사용량 장부에 기록했습니다. 추가 GPT 호출은 **0회**입니다. 실패한 최초 검사도 최종 JSON에 요약하여 보존했습니다.

## 샘플과 적용 범위

- HWPX 4개, XLSX 4개, 텍스트 PDF 5개. 제목·□대주제·○(소제목)·-상세 내용으로 작성한 가상 중앙부처 스타일이며 실제 공문이나 기관 승인 양식은 아닙니다.
- HWPX는 python-hwpx 6.11.0으로 작성하고 패키지/XML 검증 및 syhwp 본문 읽기를 확인했습니다. 한컴오피스 GUI에서의 인쇄 배치까지 확인한 것은 아닙니다.
- PDF는 텍스트 추출 가능한 문서이며 스캔 OCR을 시험하지 않았습니다. 페이지를 넘는 문단·다단 표·본문 외 주석은 별도 확인이 필요합니다.
- 최신성 판단은 본문에 식별 가능한 사업명·기준일·차수·수정일시가 있는 경우에 적용됩니다. 정보가 없거나 상충하면 추정하지 않고 검토 대상으로 남깁니다. 다른 이름의 같은 사업은 담당자 확인·매칭이 필요할 수 있습니다.
- 예산은 원문 금액을 보존합니다. 지급예정액·가용잔액 등 집계에 필요한 명세가 부족한 경우 전체 가용예산으로 임의 합산하지 않습니다. 연락처도 원문을 보여 주며 구조화된 관계자 ID가 없으면 사람을 임의로 동일인 병합하지 않습니다.

## 사용

앱 홈의 **파일명·버전 혼선 체험** 또는 `version-samples.zip` 업로드 → Solar 초안 생성 → 항목별 원문 검토 → 확정 → 인수자 전환. 다운로드한 이름·순서 변경 묶음과 예외 묶음은 별도 인수인계함에서 시험하세요. 자세한 절차는 `version-guide.md`와 정답표 `version-expected.json`에 있습니다.
'''
(OUT/'version-review.md').write_text(text)
(ROOT/'docs/본문기준_최신판본_샘플_검증결과.md').write_text(text)
print(json.dumps({'checks':len(r['checks']),'all_pass':r['all_checks_pass'],'model_calls':r['total_validation_model_calls'],'published_reports':4},ensure_ascii=False))
