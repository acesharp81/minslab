"""Publish the multistage synthetic demonstration, keeping the one-time GPT audit scoped."""
import hashlib, json, shutil
from pathlib import Path
from docx import Document
from app.flow_demo import WORKS,flow_archive
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'release/public';run=ROOT/'test-results/flow/local'
OUT.mkdir(parents=True,exist_ok=True)
sample=run/'downloaded-samples.zip'
(OUT/'flow-samples.zip').write_bytes(sample.read_bytes() if sample.exists() else flow_archive())
expected={'version':'flow-1','documents':11,'draft_tasks':5,'final_tasks':4,'reference_date':'2026-11-09','sample_sha256':hashlib.sha256((OUT/'flow-samples.zip').read_bytes()).hexdigest(),'works':WORKS,'manual_match':{'source':'예약포털 접근성 보완','target':'문화시설 통합예약 개선','owner':'디지털지원팀','work_code':'HB-004'},'expected_progress':[65,40,100,75],'expected_due_state_at_reference':['D-3','지연 3일','완료','D-15'],'quality_scope':'새 샘플은 Solar 및 기능 테스트로 검사. 기존 GPT 1회 검증 결과는 이전 7개 업무 샘플에 한정되며 재호출하지 않음.'}
(OUT/'flow-expected.json').write_text(json.dumps(expected,ensure_ascii=False,indent=2)+'\n')
md='''# 업무바통 사용·시연 안내서 v1.1.1

## 1. 시작과 모델 연결

https://www.minslab.kr/handover/ 에서 접속 코드를 입력합니다. 홈페이지 PoC → 13. 업무바통으로도 열 수 있습니다. 사용법·샘플 자료실은 로그인 없이 열립니다.

‘4개 업무 흐름 체험’ 버튼은 합성 보고서 11개를 등록하고 Solar Pro 4 분석을 시작합니다. 직접 체험하려면 자료실의 flow-samples.zip을 내려받아 새 인수인계함에 올리세요. 실제 자료·개인정보가 없는 가상 한빛시 자료입니다. example.invalid는 가상 연락처입니다.

직접 설치할 때 .env.example을 .env로 복사해 HANDOVER_LLM_KEY에 자신의 Upstage 키를 넣습니다. AI 모델 연결 화면에서도 설정할 수 있습니다. 공유 접속 코드는 운영자에게 별도로 받습니다.

## 2. 11개 보고서가 4개 업무로 이어지는 샘플

| 업무 | 보고 흐름 | 최신 달성률 | 2026-11-09 기준 |
|---|---|---|---|
| 생활문화 공모사업 추진 | 계획 → 착수 → 중간 | 65% | 11/12 기한, D-3 |
| 보조금 정산 승인 | 계획 → 착수 → 중간 | 40% | 11/06 기한, 3일 경과 |
| 문화시설 안전점검 | 계획 → 착수 → 완료 | 100% | 11/05 완료, 과거 고장 해소 |
| 문화시설 통합예약 개선 | 계획 → 담당자 확인 → 중간 | 75% | 11/24 기한, D-15 |

DOCX 4개·XLSX 3개·텍스트 PDF 3개·TXT 1개입니다. 앞의 세 업무는 같은 업무명·담당 부서로 자동 연결됩니다. 마지막 중간보고는 ‘예약포털 접근성 보완’, 담당 ‘미정’으로 작성되어 있어 자동으로 같은 업무로 단정하지 않습니다.

새 인수인계 → 여러 파일 선택 → flow-samples.zip 등록 → 초안 생성 → AI 문서 해석 → 공개·합성 자료 외부 전송 동의 → 생성 순서로 진행합니다. 로컬 규칙 모드에서도 명시적 라벨이 있는 이 샘플을 체험할 수 있지만 비정형 의미 해석과는 다릅니다.

## 3. 담당자 확인과 문서 매칭

초안에는 5개 업무 후보가 나타납니다. ‘예약포털 접근성 보완’ 카드에서 ‘같은 업무로 매칭’을 선택하세요. 기준 업무를 ‘문화시설 통합예약 개선’으로 정하고, 양쪽 문서의 연계관리번호 HB-004를 대조합니다.

확인한 담당 부서에 ‘디지털지원팀’, 사유에 ‘HB-004 동일 사업·담당을 전임자에게 확인한 합성 시나리오’를 입력하고 확인 체크 후 저장합니다. 실제 업무에서는 담당자에게 직접 확인한 결과를 적어야 합니다. 동일 관리번호만으로 자동 합치지 않습니다.

결과는 4개 업무입니다. 매칭 사유·담당자 입력·기존 판본·각 보고일의 원문 근거가 보존됩니다. 최신 보고의 현황을 보여주고 이전 현황은 진행 이력에서 확인합니다. 보고일이 없거나 겹치면 최신 값을 임의 선택하지 않습니다.

### 항목별 확인과 수정

초안 검토에서 담당·기한·현안 등 각 항목 옆 연필을 누릅니다. 업무명도 제목 옆 연필로 수정합니다. 편집 창 왼쪽에서 현재 값과 수정할 값·변경 사유를 입력하고, 오른쪽에서 파일명·원문 인용·주변 본문·이전 보고를 대조합니다. 같은 관리번호의 별도 업무는 관련 후보로 표시되며 자동으로 매칭하지 않습니다.

‘이 항목 저장’은 선택한 항목만 새 판본으로 기록합니다. 이전 값과 근거는 다시 연필을 눌러 수정 이력에서 확인합니다. 기존 확정 보고서에 반영하려면 저장 후 다시 확정하세요. 직접 연결된 근거가 없는 항목에서는 업무 자료 전체를 열거나 전임자에게 확인한 내용을 사유에 기록합니다. 미기재 안내에서도 항목별 연필로 바로 보완할 수 있습니다.

## 4. 확정 보고서에서 볼 내용

검토 완료 · 확정하기 → 확인 체크 → 이 판본 확정. 보고서 최상단에 항상 간트 차트가 있습니다. 회색은 계획 기간, 색 막대는 원문 전체 달성률, 붉은 연장은 기한이 지난 미완료 업무, 세로선은 확정 기준일, ◆는 실제 완료일입니다.

간트 아래 표에서 현안·남은 일·다음 조치를 함께 읽습니다. 업무 상세에는 보고일별 추이 그래프와 계획·착수·중간·완료 보고 흐름이 있습니다. 정산 기한 경과와 공모 심사자료 보완은 업무 현안입니다. 자료 불일치·미확인 값은 사전 검토 및 보고서 참고에 표시합니다. 안전점검의 과거 유도등 고장은 완료보고의 해소 상태로 표시됩니다.

달성률은 문서 수나 기간 경과로 계산하지 않습니다. 보고일·계획 시작일·전체 진행률 등 명시적 라벨과 유일한 값이 있는 단일 업무 문서에서 읽습니다. 여러 업무가 들어 있거나 날짜·진행률이 불명확하면 추정하지 않습니다. 일정 기한은 확정값을 사용합니다. 기존 구버전 보고서는 보존되며 시간 이력을 보려면 자료에서 새 초안을 생성해야 합니다.

현안 기준일은 확정일로 고정되므로 인계자와 인수자가 같은 내용을 봅니다. 위 샘플의 D-n·지연 일수는 2026-11-09 기준 예시이며 다른 날 새로 확정하면 달라집니다.

## 5. 출력과 후임자 확인

HTML·PDF에는 간트와 보고 추이 그래프가 들어갑니다. DOCX에는 간트 이미지와 편집 가능한 업무·이력 표가 들어갑니다. DOCX 차트의 번호는 바로 아래 업무명 표와 대응합니다. MD는 같은 사실을 표로 제공합니다.

인쇄 / PDF 저장을 누르거나 보고서 새 창에서 인쇄합니다. 자료실에는 실제 Solar 분석·담당자 매칭·확정 후 저장한 flow-report.html/pdf/docx/md가 있습니다. 외부에서 DOCX를 편집해도 앱의 확정본은 바뀌지 않습니다.

오른쪽 위 역할을 후임자로 바꾸고 같은 최종 보고서와 인수 확인을 체험합니다. ‘보고서에 질문’에서는 ‘보조금 정산 승인 남은 업무는 무엇인가요?’를 물어 확정본 내용과 근거를 확인합니다. 새 초안은 이미 전달한 확정본을 자동 교체하지 않습니다.

## 6. 직접 실행·품질·지원 범위

Python 3.12: 소스 ZIP 해제 → python3 -m venv .venv → .venv/bin/pip install -r requirements.lock → .env.example을 .env로 복사 → 키·접속 코드 설정 → bash scripts/run.sh. 기본 주소 http://127.0.0.1:18130/ 입니다.

Docker: docker build -t poc13-handover:1.1.1 . → docker compose up -d. 전용 볼륨이 자료를 보존합니다. 운영 키와 DB는 소스 ZIP에 포함하지 않습니다. 외부 모델 없이 검사하려면 bash scripts/verify.sh를 실행합니다.

이전 7개 업무 샘플에서 수행한 GPT-5.4-mini 1회 평가 결과와 프롬프트 개선을 유지하며 재호출하지 않았습니다. 신규 4개 업무 샘플은 별도 Solar 분석·원문 일치·매칭·출력·브라우저 검사 결과를 flow-validation.json에 기록합니다. 이전 평가 수치를 신규 샘플의 정확도로 주장하지 않습니다.

텍스트 PDF·DOCX·XLSX·TXT 및 HWP/HWPX 본문을 지원합니다. 스캔 OCR·복잡한 한글 서식 재현·기관 SSO·개인별 권한·전자서명은 포함하지 않습니다. 역할 선택은 시연 기능입니다. 접속 코드를 공유하면 같은 워크스페이스를 봅니다. 라이선스는 docs/THIRD_PARTY_NOTICES.md를 참고하세요.

시연 영상은 이번 작업에 포함하지 않습니다. 참가자 정보·기관 서류·공공 GitLab 등록·대회 접수는 별도입니다.
'''
(OUT/'handover-guide.md').write_text(md);(ROOT/'docs/submission/USER_GUIDE.md').write_text(md)
doc=Document()
for line in md.splitlines():
 if line.startswith('# '):doc.add_heading(line[2:],0)
 elif line.startswith('## '):doc.add_heading(line[3:],1)
 elif line:doc.add_paragraph(line)
doc.save(OUT/'handover-guide.docx')
for fmt in ['html','md','pdf','docx']:
 p=run/('flow-report.'+fmt)
 if p.exists():shutil.copyfile(p,OUT/p.name)
print('Flow sample and guide prepared')
