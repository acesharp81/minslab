"""Build public synthetic samples and five-page guide; no workspace data or secrets."""
import hashlib,html,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.submission import submission_archive
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'release/public';OUT.mkdir(parents=True,exist_ok=True)
p=OUT/'handover-samples.zip'
if not p.exists():p.write_bytes(submission_archive())
EXPECTED={
'2027년 생활문화 사업계획':{'owner':'문화기획팀','status':'초안 검토 중','due_date':['2026-11-20','2026-11-25'],'completed_work':'주민 수요조사 120건 취합 및 사업계획 초안 작성','remaining_work':'예산 협의와 사업계획 결재 상신','issues':'예산팀 검토 의견 미회신으로 사업비 확정 보류','collaborators':'예산팀','contacts':'culture@example.invalid'},
'주민참여 워크숍 운영':{'owner':'주민협력팀','status':'장소 예약 완료','due_date':'2026-12-03','completed_work':'주민센터 대강당 예약 및 강사 섭외 완료','remaining_work':'참가자 모집 마감과 행사 운영표 작성','issues':'수어 통역 지원 여부 미확정','next_action':'참여자 안내문 발송'},
'보조금 정산 검토':{'owner':'사업지원팀','status':'증빙 수집 중','due_date':'11월 말','completed_work':'참여 단체 10곳 중 7곳의 정산서 접수','remaining_work':'나머지 3곳 자료 수집과 지출 적정성 검토','issues':'2개 단체의 영수증 누락으로 정산 승인 불가','next_action':'누락된 영수증 제출 요청'},
'월간 실적 보고':{'owner':'성과관리팀','status':'자료 취합 중','due_date':'매월 5일','completed_work':'5개 부서 중 4개 부서의 지표 수령','remaining_work':'누락 부서 지표 취합 후 총괄표 제출','issues':'시설운영팀 이용자 수 지표 미제출','next_action':'부서별 지표 확인'},
'시설 안전점검':{'owner':'시설운영팀','status':['점검 예정','사전 점검 완료'],'due_date':'2026-12-10','completed_work':'소화기 위치와 비상구 적치물 사전 점검','remaining_work':'보수 완료 확인 후 본 점검 실시','issues':'지하 비상구 유도등 2개 고장으로 보수 요청 중','next_action':'본 점검 전 보수 결과 확인'},
'홍보물 제작 계약':{'owner':'홍보지원팀','status':'디자인 시안 검토 단계','due_date':'2026-12-04','completed_work':'과업지시서 작성과 견적서 3건 접수','remaining_work':'시안 확정 후 계약 체결','issues':'저작권 사용 동의서 미접수','next_action':'제작사에 저작권 사용 동의서를 요청','collaborators':'계약심사팀','contacts':'publicity@example.invalid'},
'문화시설 예약 시스템 개선':{'owner':'디지털지원팀','status':'사용자 시험 중','due_date':'2026-12-14','completed_work':'요구사항 12건 정리 및 화면 초안 완성','remaining_work':'접근성 점검 후 운영 반영','issues':'키보드 탐색 오류 2건 미해결','next_action':'개발사에 오류 재현 절차 전달','collaborators':'시설운영팀','contacts':'digital@example.invalid'}}
expected={'sample_version':'submission-1','sample_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'expected_tasks':EXPECTED,'expected_count':7,'forbidden_owner':{'홍보물 제작 계약':'계약심사팀'},'all_tasks_incomplete':True,'human_edit':{'task':'2027년 생활문화 사업계획','field':'due_date','value':'2026-11-27','reason':'전임자 확인 · 최종 협의 일정 반영'},'notes':'원문에 명시된 값의 포함 여부를 검사하는 합성 정답표. GPT 결과 자체를 정답으로 취급하지 않음.'}
(OUT/'expected.json').write_text(json.dumps(expected,ensure_ascii=False,indent=2)+'\n')
PAGES=[('1. 시작하기 · 실행 환경',[
('업무바통이 하는 일','혼합 업무자료에서 진행 현황·완료 실적·남은 업무·현안·다음 조치를 추출합니다. 전임자가 수정·확정하면 인계자와 인수자가 같은 최종 보고서를 봅니다. 자료가 없는 사실과 연락처는 추측하지 않습니다.'),
('웹 실행','https://www.minslab.kr/handover/ 에 접속하거나 홈페이지 PoC → 13. 업무바통을 선택합니다. 운영자가 별도로 전달한 공유 접속 코드를 입력합니다. /handover/guide 자료실은 로그인 없이 열립니다.'),
('권장 환경','최신 데스크톱 Chrome 또는 Edge를 권장하며 모바일 열람도 지원합니다. 직접 설치에는 Python 3.12 또는 Docker, 메모리 2GB·디스크 2GB 이상을 권장합니다. 서버는 단일 프로세스로 실행합니다.'),
('모델 연결','현재 웹 앱은 Upstage Solar Pro 4를 사용합니다. 직접 설치할 때 .env.example을 .env로 복사하고 HANDOVER_LLM_KEY에 본인의 키를 설정합니다. AI 모델 연결 화면에서도 입력할 수 있습니다. 공개·합성 자료만 외부 전송 동의 후 분석합니다.'),
('품질 검증','GPT-5.4-mini는 최종 참조 검증에서 한 번 호출하며 결과를 보존·재사용합니다. 일상 생성 모델은 Solar Pro 4입니다. 수치와 한계는 별도 품질 보고서를 참고하세요.')]),
('2. 샘플 다운로드 · 자료 등록',[
('다운로드 파일','handover-samples.zip에는 DOCX 2개·XLSX 2개·텍스트 PDF 1개·TXT 2개가 있습니다. 가상 한빛시의 합성 자료이며 실제 개인정보가 없습니다. example.invalid 이메일은 시연용 주소입니다.'),
('파일 구성','01 사업현황: 사업계획·워크숍. 02 협의메모: 기한 변경 제안·정산. 03 운영목록: 실적·시설점검. 04 회의결과: 사전점검과 고장 현안. 05 이미지안내: 업무가 아닌 안내. 06 전달메모: 서술형 계약 업무. 07 업무표: 일반 엑셀 표.'),
('등록 순서','새 인수인계 → 이름 입력 → 만들기 → 여러 파일 선택 → ZIP 등록. 압축을 풀어 여러 파일이나 폴더로 등록해도 됩니다. 파일당 20MB, ZIP 전체 80MB, 최대 100개입니다.'),
('AI 분석','초안 생성 → AI 문서 해석 → 공개·합성 자료 외부 전송 동의 → 생성. 예상 결과는 7개 업무입니다. 모델 출력은 달라질 수 있으므로 expected.json과 원문을 대조합니다. 로컬 규칙 추출은 비정형 문장·일반 표의 대체 AI가 아닙니다.'),
('처리 실패','사유를 확인해 연결이나 파일을 수정하고 다시 시도합니다. 완료된 문서 단계는 보존됩니다. 이미지 PDF는 OCR되지 않으므로 텍스트 자료를 추가합니다. 새 분석은 기존 확정본을 자동 교체하지 않습니다.')]),
('3. 전임자 검토 · 수정 · 확정',[
('기한 대조','2027년 생활문화 사업계획의 2026-11-20과 2026-11-25를 확인합니다. 원문 근거에서 파일명·본문 위치·인용을 대조합니다. 변경 제안 날짜를 자동 확정하지 않습니다.'),
('기한 수정','업무 수정 → 기한 2026-11-27 → 사유 “전임자 확인 · 최종 협의 일정 반영” → 새 판본으로 저장. 이 값은 원문이 아닌 사람의 입력으로 표시됩니다. 이전 근거와 사유가 보존됩니다.'),
('내용 점검','완료한 일·남은 업무·현안·다음 행동·담당·기한·협의 부서·연락처를 확인합니다. 시설 사전 점검 완료를 전체 완료로 표시하면 안 됩니다. 계약심사팀은 협의 부서이고 홍보지원팀이 업무 담당입니다.'),
('빠진 내용 보완','초안 검토의 업무 추가·수정으로 누락 업무와 확인한 사실을 보완합니다. 미기재 안내에서 비어 있는 필드를 찾습니다. 자료가 없는 값은 확인 필요로 남길 수 있습니다.'),
('최종 확정','검토 완료 · 확정하기 → 경고 확인 → 이 판본 확정. 문서 확정은 모든 사실의 검증 완료와 다릅니다. 미확인 항목은 보고서에 남으며, 동시 수정 충돌은 덮어쓰지 않고 다시 확인하도록 안내합니다.')]),
('4. 최종 보고서 · 후임자 확인',[
('보고서 내용','전체 요약 → 당장 확인·처리할 현안 → 업무별 진행·완료·잔여 업무 → 후속 실행 계획 → 남은 확인 사항 → 원문·변경 이력 부록 순서입니다. 양측이 같은 판본과 내용 해시를 봅니다.'),
('파일 출력','HTML은 서식 있는 오프라인 열람본, MD는 텍스트, DOCX는 편집용 사본입니다. 인쇄 / PDF 저장으로 PDF도 출력합니다. DOCX를 외부에서 편집해도 앱의 확정본은 변경되지 않습니다.'),
('후임자 인수','오른쪽 위 시연 역할을 후임자로 바꾸고 인수 확인을 누릅니다. 같은 최종 보고서가 표시되는지 확인합니다. 이 역할 선택은 본인 인증이나 전자서명이 아닙니다.'),
('확정본 질의','보고서에 질문에서 “생활문화 사업계획의 최종 기한은 언제인가요?”를 묻습니다. 확정된 2026-11-27이 우선입니다. AI 조회는 외부 전송 동의 후 사용합니다. 모델은 근거 ID를 선택하고 서버가 확정값을 표시합니다.'),
('일정과 연락망','일정·연락망은 현재 한국 날짜를 기준으로 기한 경과 확인·7일 이내·반복·미확인 일정을 구분합니다. “월말”, “매월 5일”을 임의의 특정 날짜로 바꾸지 않습니다.')]),
('5. 직접 설치 · 한계 · 개발 경위',[
('Python 설치','소스 ZIP 압축 해제 → python3 -m venv .venv → .venv/bin/pip install -r requirements.lock → .env.example을 .env로 복사 → 자신의 접속 코드·Upstage 키 설정 → bash scripts/run.sh. http://127.0.0.1:18130/ 에 접속합니다.'),
('Docker 실행','docker build -t poc13-handover:1.0.0 . 실행 후 docker compose up -d. 종료는 docker compose down. 전용 볼륨이 자료를 보존합니다. -v 옵션은 자료를 삭제하므로 사용하지 않습니다. 운영 키·사용자 자료·DB는 배포 ZIP에서 제외됩니다.'),
('검증','bash scripts/verify.sh로 외부 모델 없이 파서·근거·판본·확정·인수·질의·출력을 확인합니다. 합성 정답표에 대한 평가는 일반 기관 자료의 정확도를 보장하지 않습니다.'),
('지원 한계','스캔 OCR, 복잡한 한글 서식 재현, 자유 HWPX 출력, 기관 SSO·개인별 권한·전자서명·ERP는 제외합니다. 접속 코드를 공유한 사용자는 같은 워크스페이스를 봅니다. 인용의 문자 일치는 의미 정확도와 다릅니다.'),
('개발 경위와 라이선스','자료 분산과 후속조치 누락을 줄이기 위해 문서별 추출 → 원문 근거 검증 → 사람의 확정 → 후임자 활용 흐름을 독립 앱으로 구현했습니다. FastAPI·SQLite·syhwp·python-docx·openpyxl·pypdf 등을 사용하며 docs/THIRD_PARTY_NOTICES.md에 고지합니다.')])]
css='@page{size:A4;margin:17mm}body{font-family:"Noto Sans CJK KR",sans-serif;color:#203a31;font-size:10.5pt;line-height:1.8;margin:0}section{break-after:page}section:last-child{break-after:auto}h2{font-size:18pt;border-bottom:2px solid #40684e;padding-bottom:4mm}h3{font-size:12pt;margin:6mm 0 1mm}p{margin:0 0 3mm}small,footer{font-size:9pt;color:#61725f}footer{margin-top:7mm;border-top:1px solid #ccc;padding-top:3mm}'
body='';md='# 업무바통 사용·구동 안내서\n\n'
from docx import Document
from docx.shared import Pt
from docx.oxml.ns import qn
d=Document();d.styles['Normal'].font.name='맑은 고딕';d.styles['Normal'].font.size=Pt(10);d.styles['Normal'].element.rPr.rFonts.set(qn('w:eastAsia'),'맑은 고딕')
for n,(title,sections) in enumerate(PAGES,1):
 body+='<section><small>업무바통 · v1.0.0 · 합성 자료 E2E 체험</small><h2>'+html.escape(title)+'</h2>';md+='## '+title+'\n\n'
 if n>1:d.add_page_break()
 d.add_heading(title,1)
 for heading,text in sections:
  body+='<h3>'+html.escape(heading)+'</h3><p>'+html.escape(text)+'</p>';md+='### '+heading+'\n\n'+text+'\n\n';d.add_heading(heading,2);d.add_paragraph(text)
 body+=f'<footer>업무바통 사용·구동 안내서 · {n} / 5</footer></section>'
(OUT/'handover-guide.html').write_text('<!doctype html><html lang="ko"><meta charset="utf-8"><title>업무바통 구동안내서</title><style>'+css+'</style>'+body+'</html>')
(OUT/'handover-guide.md').write_text(md);(ROOT/'docs/submission/USER_GUIDE.md').write_text(md);d.save(OUT/'handover-guide.docx')
print('Prepared samples, expected.json, HTML/MD/DOCX guide')
