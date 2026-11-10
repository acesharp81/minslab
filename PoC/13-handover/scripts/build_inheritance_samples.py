"""Three-work continuation fixture: HWPX baseline, XLSX update, PDF new assignment."""
import json,zipfile
from pathlib import Path
from build_employee_samples import write
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'release/public';WORK=ROOT/'test-results/inheritance-materials';WORK.mkdir(parents=True,exist_ok=True)

def rows(title,code,day,progress,status,done,left,issue,next_action,owner):
 return [title+' 추진상황 보고','합성 시연자료 · 실제 기관·인물과 무관','□ 보고 개요',f'보고일: {day}',f'사업관리번호: {code}',f'문서관리번호: {code}-RPT',f'수정차수: {2 if day.endswith("11-10") else 1}차',f'수정일시: {day} 09:00','문서상태: 확정','보고단계: 중간보고','계획 시작일: 2026-01-01',f'전체 진행률: {progress}%','□ 업무 개요',f'○ (업무) {title}',f'○ (담당) {owner}','○ (기한) 2026-11-20',f'○ (현재 상태) {status}',f'○ (업무 개요) {title}의 신청 접수, 기관 협의, 증빙 검토와 최종 결과보고를 관리한다.','○ (목표) 대상 10개 기관의 조치와 실적 검토를 완료한다.','○ (추진 계획) 1월 | 대상 확정 | 운영계획\n11월 | 기관별 실적 검토 | 검토표\n11월 20일 | 최종 결과보고 | 결재 문서','□ 추진 현황',f'○ (완료한 일) {done}',f'○ (남은 업무) {left}',f'○ (현안·장애 사항) {issue}',f'○ (다음 행동) {next_action}','□ 후속 조치',f'○ (추후 계획) 2026-11-15 | {owner} | 잔여 자료 대조 | 검토표 | 예정\n2026-11-20 | {owner} | 결과보고 상신 | 결재 문서 | 예정','○ (업무 처리 절차) 자료 접수 → 담당 대조 → 팀장 검토 → 결과보고 상신','○ (완료 기준) 모든 대상의 증빙 검토 및 최종 결과보고 결재 완료','○ (비고) 공무원 업무보고 형식의 합성 시연자료. 계획은 완료 실적이 아니다.','- 문서 내 기준일과 사업관리번호를 기준으로 기존 업무와 연결한다.']
fixtures=[('01_이전인계_원본.zip',[
 ('a17.hwpx',rows('지역생활서비스 운영','CONT-A','2026-01-08',20,'계획 수립 완료','대상 10개 기관 확정','10개 기관 협약 체결','협약 일정 협의 필요','기관별 협약 일정을 확정','직원 1')),
 ('b03.hwpx',rows('공공시설 정기점검','CONT-B','2026-01-08',30,'점검 준비 중','대상 시설 목록 확정','점검표 수합과 현장 점검','점검 담당 협의 필요','시설별 점검 일정을 협의','직원 1'))]),
 ('02_현행화_신규업무.zip',[
 ('z91.xlsx',rows('지역생활서비스 운영','CONT-A','2026-11-10',80,'8개 기관 협약 체결 완료','10개 기관 중 8개 기관 협약 체결','잔여 2개 기관 협약과 결과보고','2개 기관 날인본 미접수','잔여 2개 기관 날인본을 11월 15일까지 요청','직원 2')),
 ('m04.pdf',rows('겨울철 취약계층 지원','CONT-C','2026-11-10',10,'신규 사업 착수','지원 대상 조사표 배포','대상자 명단 수합과 지원 일정 확정','3개 기관 조사표 회신 대기','3개 기관 담당자에게 회신을 요청','직원 2'))])]
for name,docs in fixtures:
 with zipfile.ZipFile(OUT/name,'w',zipfile.ZIP_DEFLATED) as z:
  for file,lines in docs:
   path=WORK/file;write(path,lines);z.writestr(file,path.read_bytes())
guide='''# 이전 인계 보고서 이어서 작성 체험

합성 시연자료입니다. 전체 ZIP을 그대로 업로드하지 말고 아래 단계별 ZIP을 사용합니다.

## 빠른 체험
1. 홈 → ‘시연 및 샘플 데이터 다운’ → 샘플3 ‘업무연결 시연’ → ‘시연 수행’을 누르고 인계자 직원 2, 인수자 직원 3을 선택합니다. 직원 2 화면으로 전환되며 이전 완료 보고서와 새 자료가 준비됩니다. 재클릭해도 중복 생성하지 않습니다.
2. ‘초안 생성’에서 ‘이전에 인수한 보고서 이어서 작성’을 체크합니다.
3. ‘직원 1 → 직원 2 · 업무연결 시연 (번호) · 이전 인계 보고서’를 선택합니다. 로컬 규칙 추출만으로도 샘플을 확인할 수 있습니다.
4. 생성 후 3개 업무를 확인합니다. 지역생활서비스 운영은 20%→80%로 갱신, 공공시설 정기점검은 이전 30% 유지, 겨울철 취약계층 지원 10% 신규 추가입니다. 유지된 정기점검은 1월 기준이며 현재 상태를 재확인해야 합니다.
5. 검토·확정 후 보고서 상단 ‘직원 1 → 직원 2 (\'26.1.10., 인수인계완료)’와 ‘직원 2 → 직원 3 (이번 확정일, 이번 인계)’를 확인합니다. 시연 준비 날짜와 실제 확정 날짜는 구분됩니다.
6. ‘원문 기록 확인’을 눌러 인용 팝업을 열고 닫습니다. 보고서 읽던 위치가 유지됩니다.
7. 직원 3으로 바꿔 같은 확정 보고서를 읽고 인수 확인합니다.

## 직접 구성
- 직원 1 → 직원 2 인계함에 01_이전인계_원본.zip을 올리고 생성·확정합니다. 직원 2로 전환해 인수 완료합니다. 직접 만든 경우 완료일은 실제 클릭한 날입니다.
- 직원 2 → 직원 3 인계함을 새로 만들어 02_현행화_신규업무.zip을 등록하고 이어서 작성 옵션을 선택합니다.
- 현행화 원문의 기준일은 이전 보고서 인수일 이후여야 합니다. 과거 자료나 미승인 초안은 최신 내용으로 덮어쓰지 않습니다.
- 체크하지 않고 생성하면 새 자료에 있는 2개 업무만 생성됩니다.

## 확인 기준
이전 보고서의 수동 보완·근거는 보존됩니다. 기존 업무의 최신 자료에 기재된 항목만 현행화하고 누락 항목은 이전 내용을 유지합니다. 사업번호 또는 모순 없는 동일 업무명으로 연결하며 중복·불명확한 후보는 자동 확정하지 않습니다. 보고서 계승은 기관 전자결재·법적 승계 기능이 아닙니다.
'''
(OUT/'inheritance-guide.md').write_text(guide)
(OUT/'inheritance-expected.json').write_text(json.dumps({'old_tasks':2,'updated':1,'carried':1,'new':1,'result_tasks':3,'progress':{'지역생활서비스 운영':80,'공공시설 정기점검':30,'겨울철 취약계층 지원':10},'chain':['직원 1 → 직원 2 (2026-01-10 인수인계완료)','직원 2 → 직원 3 (이번 확정일)']},ensure_ascii=False,indent=2))
with zipfile.ZipFile(OUT/'inheritance-kit.zip','w',zipfile.ZIP_DEFLATED) as z:
 for name in ['01_이전인계_원본.zip','02_현행화_신규업무.zip','inheritance-expected.json']:z.write(OUT/name,name)
 z.writestr('시작하기.md',guide)
print('Continuation sample kit built: 2 HWPX + 1 XLSX + 1 PDF')
