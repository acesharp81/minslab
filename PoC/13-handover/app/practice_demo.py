"""Authored synthetic operational records, not a prebuilt AI report.
The reference PDF supplies structure only. Added amounts/people/evidence are explicitly fictional.
"""
import copy,io,zipfile
from .flow_demo import WORKS,flow_archive
from .practice_fields import PRACTICE_FIELDS

PROFILES=[
 dict(overview='생활문화 단체의 공모 신청을 접수·심사하여 2027년 지원 대상을 선정하는 업무다. 이번 인계 범위는 선정 결과 결재까지이며, 이후 교부·사업 집행은 다음 단계로 별도 관리한다.',
 objectives='신청 20건을 동일 심사 기준으로 검토하고 지원 대상 8개 단체를 선정하는 것이 목표다. 2026-11-12 심사 개최·선정 결과 결재를 완료하고 심사 기록을 남긴다. 선정 수는 목표이며 현재 선정 완료 건수는 0건이다.',
 scope='공고·설명회 → 신청 접수 → 자격 검토 → 심사자료 보완·배포 → 심사 → 선정 결과 결재. 교부금 지급과 선정 이후 사업 집행은 이 업무의 완료 범위에 포함하지 않는다.',
 implementation_plan='2026-10-15~10-25 | 사업 범위·심사 기준 수립 | 계획서·심사표\n2026-10-26~11-05 | 공고·설명회·신청 접수 | 공고문·접수대장\n2026-11-06~11-10 | 자격 검토·보완·자료 배포 | 검토대장·배포본\n2026-11-12 | 심사 개최·선정 결과 결재 | 심사기록·선정 결재문',
 performance='지표: 신청 접수 | 실적: 20 | 목표: 20 | 단위: 건\n지표: 자격 검토 | 실적: 20 | 목표: 20 | 단위: 건\n지표: 선정 결재 | 실적: 0 | 목표: 8 | 단위: 단체',
 future_plan='2026-11-09 | 문화기획팀 김가온 | A07·A14 보완요청 이력 점검·대상 재통보 | 보완요청대장 | 실행 예정\n2026-11-10 | 문화기획팀 김가온 | 보완자료 2건 수령·대조 후 심사자료 배포 | 접수 확인·배포본 | 원문 목표\n2026-11-12 | 문화기획팀 김가온 | 심사 개최·결과 결재 상신 | 심사기록·결재문 | 원문 기한\n2026-11-13 | 문화기획팀 윤서연 | 선정 이후 교부 업무 담당에게 결과 전달 | 전달 기록 | 내부 계획',
 operating_steps='1. 08_실행증빙대장.xlsx의 공모접수 시트에서 A01~A20 자격 검토를 확인한다.\n2. A07·A14의 미비자료를 요청하고 수령 시 파일명·확인자를 대장에 기록한다.\n3. 보완자료를 포함한 심사자료와 11/07 확정된 위원 명단을 대조해 배포한다.\n4. 심사기록과 선정 명단을 문화정책과장에게 상신한다.\n5. 결재번호·결과 파일을 기록하고 교부 담당에게 넘긴다.',
 completion_criteria='20건 자격 검토, 보완자료 2건 수령, 심사 개최 기록, 선정 결과 결재 문서가 모두 확보되어야 이 업무를 완료로 처리한다. 선정 후 교부금 지급까지 완료했다는 뜻은 아니다.',
 deliverables='공모접수·보완대장(제공) / 심사위원 확정대장(제공) / 심사기준 초안(계획보고에 기재) / 심사 배포본·심사기록·선정 결재문(향후 생성 예정)',
 issue_history='10/26 심사위원 1명 섭외 대기 → 11/07 위원 수락 확인으로 해소(08_실행증빙대장.xlsx / 위원확정). 11/08 A07·A14 심사자료 보완 미접수는 계속 미해결이다. 보완 수령 전에는 심사자료 완결로 표시하지 않는다.'),
 dict(overview='전년도 생활문화 보조사업을 수행한 10개 단체의 정산서를 받아 증빙과 지출 적정성을 검토하고 최종 승인하는 업무다. 정산서 접수, 증빙 완비, 검토, 승인 상태를 각각 관리한다.',
 objectives='대상 10개 단체 모두에 대해 적정성 검토와 정산 승인을 완료하고 승인·반납 필요 여부를 기록한다. 11/06 승인 기한을 지났으므로 누락 증빙 확보와 승인 재일정 협의가 현재 우선 과제다.',
 scope='정산서 접수 → 증빙 대조 → 보완 요청 → 적정성 검토 → 승인 결재. 보조금은 이미 교부됐으며 정산 진행률과 예산 집행률은 서로 다른 지표다.',
 implementation_plan='2026-10-20~10-27 | 기준·제출 목록 안내 | 정산 안내문\n2026-10-28~11-02 | 정산서 접수·미제출 독려 | 단체별 접수대장\n2026-11-03~11-06 | 증빙·적정성 검토 및 승인 | 검토표·승인문\n2026-11-09 이후 | 지연 정상화·재일정 협의 | 보완자료·협의기록',
 performance='지표: 정산서 접수 | 실적: 10 | 목표: 10 | 단위: 단체\n지표: 적정성 검토 | 실적: 4 | 목표: 10 | 단위: 단체\n지표: 최종 승인 | 실적: 0 | 목표: 10 | 단위: 단체',
 future_plan='즉시 | 사업지원팀 박이음 | G05·G06 누락 영수증 재요청 | 요청·회신 기록 | 원문 조치\n2026-11-10 | 사업지원팀 박이음 | 승인 지연 경위 보고와 재일정 협의 | 협의 기록 | 내부 관리 목표·기한 변경 미승인\n2026-11-11~11-13 | 사업지원팀 최다온 | 잔여 6개 단체 검토·보완 대조 | 단체별 검토표 | 증빙 수령 전제 잠정 계획\n검토 완료 후 | 사업지원팀 박이음 | 최종 승인 결재 상신 | 승인 문서 | 실제 완료일 미확정',
 operating_steps='1. 08_실행증빙대장.xlsx의 정산검토 시트에서 G01~G10을 확인한다.\n2. 접수 10건과 검토 완료 4건을 구분하고 G05·G06 영수증 누락을 먼저 처리한다.\n3. G07~G10의 검토 대기와 G05·G06의 증빙 보완 대기를 구분해 작업 순서를 정한다.\n4. 회계협의 담당에게 쟁점과 새 일정안을 전달하고 사업지원과장에게 보고한다.\n5. 검토표와 승인 결재를 모두 확보한 뒤 승인 상태를 갱신한다.',
 completion_criteria='누락 영수증 확보, 10개 단체 적정성 검토, 최종 승인 결재 및 결과 통지가 모두 기록돼야 완료다. 재일정이 승인되기 전에는 당초 11/06 기한을 유지한다.',
 deliverables='단체별 정산·검토대장(제공) / G05·G06 보완요청 목록(제공) / 개별 영수증 원본·최종 승인문(아직 미확보 또는 생성 전으로 명시)',
 issue_history='10/28 정산서 4개 단체 미접수 → 11/08 10개 단체 정산서 접수로 해소. G05·G06 영수증 누락, 잔여 6개 단체 검토, 최종 승인 0건은 미해결이다. 11/10 재일정 협의는 예정이며 기한 연장 승인으로 취급하지 않는다.'),
 dict(overview='문화시설 5곳을 점검하고 발견된 보수 8건을 조치한 뒤 재점검과 결과 결재로 종료한 업무다. 인수자는 완료 작업을 반복하기보다 완료 증빙의 열람 가능 여부와 다음 정기점검 연계를 확인한다.',
 objectives='대상 시설 5곳 점검과 보수 8건을 모두 마치고 최종 결과 결재를 남긴다. 11/05 실제 완료로 보고했으며 다음 정기점검은 2027-02-05로 내부 계획에 등록했다.',
 scope='대상·점검표 확정 → 현장 점검 → 보수 → 재점검 → 결과 결재·보관. 차기 점검 주기는 이 합성 기관의 내부 계획이며 법정 주기를 의미하지 않는다.',
 implementation_plan='2026-10-12~10-24 | 대상·점검표 확정 | 시설목록·점검표\n2026-10-25~11-04 | 현장 점검·보수·재점검 | 점검·보수 기록\n2026-11-05 | 최종 결과 결재 | 안전점검 결과대장\n2027-02-05 | 차기 정기점검 | 내부 일정 등록',
 performance='지표: 시설 점검 | 실적: 5 | 목표: 5 | 단위: 곳\n지표: 보수 조치 | 실적: 8 | 목표: 8 | 단위: 건\n지표: 결과 결재 | 실적: 1 | 목표: 1 | 단위: 건',
 future_plan='인계 당일 | 시설운영팀 이한결 | F01~F05·R01~R08 완료대장 열람 확인 | 인수 확인 기록 | 완료 증빙 인수\n2026-11-13 | 시설운영팀 정하람 | 차기 점검 알림·담당 등록 점검 | 점검 일정대장 | 내부 계획\n2027-02-05 | 시설운영팀 정하람 | 이전 보수 이력을 반영한 정기점검 | 차기 점검표 | 내부 계획',
 operating_steps='1. 08_실행증빙대장.xlsx의 시설점검·보수내역 시트를 연다.\n2. F01~F05와 R01~R08의 완료·재점검 기록을 대조한다.\n3. R07·R08 유도등 교체 및 11/05 재점검 결과를 확인한다.\n4. 결과 결재대장의 HB-003-20261105를 확인하고 접근 경로를 인수자에게 안내한다.\n5. 다음 점검 알림에 지하 비상구 이력을 연결한다.',
 completion_criteria='11/05 완료보고와 점검·보수·결재대장의 일치로 완료 상태를 확인한다. 후임자의 남은 일은 완료 증빙 인수와 차기 점검 준비이며 현재 사업을 미완료로 재분류하지 않는다.',
 deliverables='시설 5곳 점검대장·보수 8건 기록·결과 결재대장(합성 기록 제공) / 현장 사진은 이 시연 패키지에 포함하지 않으며 현장 증빙 원본으로 오인하지 않는다.',
 issue_history='10/25 지하 비상구 유도등 2개 고장 → R07·R08 교체 및 11/05 재점검으로 해소. 현재 미결 보수는 없다. 사진 미첨부는 자료 참고 사항이며 진행 장애 현안으로 분류하지 않는다.'),
 dict(overview='문화시설 통합예약의 요구사항 12건을 구현하고 접근성 오류를 제거한 뒤 운영 환경에 반영하는 개선 업무다. 예약포털 접근성 보완 중간보고는 같은 사업의 전체 범위를 보고한 별칭 문서이며, 담당자 확인 기록에 따라 연결한다.',
 objectives='요구사항 12건 구현, 키보드 탐색 오류 2건 해소·재시험, 운영 반영 승인 기록 확보가 목표다. 최종 기한은 11/24이며 화면 개발·일반 기능 시험 완료만으로 전체 완료 처리하지 않는다.',
 scope='요구사항·화면 초안 → 개발 → 일반 기능 시험 → 접근성 보완·재시험 → 운영 승인·반영. 09_업무동일성_담당확인.txt는 두 보고의 진행률이 동일한 전체 업무 범위임을 명시한다.',
 implementation_plan='2026-10-22~10-28 | 요구사항·개발 범위 확정 | Q01~Q12 명세\n2026-10-29~11-08 | 개발·일반 기능 시험 | 기능 시험대장\n2026-11-09~11-20 | 접근성 보완·재시험 | D01·D02 결함대장\n2026-11-24 | 운영 승인·반영 | 운영 반영 기록',
 performance='지표: 요구사항 구현 | 실적: 12 | 목표: 12 | 단위: 건\n지표: 접근성 결함 해결 | 실적: 0 | 목표: 2 | 단위: 건\n지표: 운영 반영 | 실적: 0 | 목표: 1 | 단위: 건',
 future_plan='즉시 | 디지털지원팀 한새봄 | D01·D02 재현 절차를 개발사에 전달 | 접수 회신 | 원문 조치\n2026-11-16 | 개발사 오누리 | 수정 버전 제출 | 변경내역·시험용 버전 | 개발 협의 목표\n2026-11-20 | 디지털지원팀 문지우 | 키보드만으로 2건 재시험 | 결함별 시험 결과 | 내부 검수 목표\n2026-11-24 | 디지털지원팀 한새봄 | 검수 결과 보고·운영 반영 승인 | 승인·배포 기록 | 원문 기한',
 operating_steps='1. 09_업무동일성_담당확인.txt를 대조하고 두 업무 후보를 사람이 매칭한다.\n2. 08_실행증빙대장.xlsx의 요구사항·접근성결함 시트에서 Q01~Q12 및 D01·D02를 확인한다.\n3. D01은 날짜 선택 후 초점 이탈, D02는 확인 창의 키보드 닫기 실패로 재현한다.\n4. 수정 버전에서 동일 절차를 키보드만으로 반복하고 두 건 모두 통과해야 검수한다.\n5. 디지털정책과장 승인과 운영 반영 기록을 남긴 뒤 전체 완료로 갱신한다.',
 completion_criteria='요구사항 12건 구현, D01·D02 재시험 통과, 운영 반영 승인·배포 기록을 모두 확인해야 완료다. 개발사 수정 제출은 검수 통과나 운영 완료와 다르다.',
 deliverables='요구사항 12건·접근성 결함 2건 대장·동일업무 확인 기록(제공) / 수정 버전·재시험 결과·운영 승인문(향후 생성 예정)',
 issue_history='10/22 계획 단계 현안 없음 → 11/08 D01·D02 키보드 탐색 오류 발견·미해결. 11/09 동일 업무·담당·진행률 기준을 확인했으며 실제 연결은 전임자 검토·매칭으로 기록한다.')]

LEADS=[('김가온','윤서연','문화정책과장'),('박이음','최다온','사업지원과장'),('이한결','정하람','시설관리과장'),('한새봄','문지우','디지털정책과장')]
BUDGETS=[(120000000,12000000,8000000,100000000),(150000000,150000000,0,0),(18000000,18000000,0,0),(60000000,30000000,24000000,6000000)]

def budget_line(code,name,values,scope):
 a,b,c,d=values
 return f'예산코드: {code} | 명칭: {name} | 편성액: {a:,}원 | 집행액: {b:,}원 | 지급예정액: {c:,}원 | 가용잔액: {d:,}원 | 기준일: 2026-11-09 | 범위: {scope}'

def contact_line(pid,name,dept,role,extension,email,purpose):
 return f'관계자ID: {pid} | 성명: {name}(가상) | 소속: {dept} | 역할: {role} | 연락: 내선 {extension}(시연용), {email}@example.invalid | 협의사항: {purpose}'

def resources(index):
 w=WORKS[index];lead,backup,approver=LEADS[index];code=f'HB-{index+1:03d}'
 budget=budget_line(f'B-{index+1:03d}',w['title'],BUDGETS[index],code)+'\n'+budget_line('B-COM','공통 회의·자료 관리',(10000000,2000000,1000000,7000000),'전체 4개 업무 공동 사용·중복 합산 금지')
 contacts=[contact_line(f'P{index+1}1',lead,w['owner'],'실무 담당',f'21{index+1}1',f'lead{index+1}','업무 현황·보완·인계'),contact_line(f'P{index+1}2',backup,w['owner'],'대체 담당',f'21{index+1}2',f'backup{index+1}','담당 부재 시 자료·일정 확인'),contact_line('P90','서도윤','행정지원팀','회계 협의','2190','finance','집행·지급예정·정산 쟁점'),contact_line('P91','강온유','행정지원팀','문서 접근 지원','2191','records','패키지 파일 열람·권한 요청')]
 if index==3:contacts.append(contact_line('P43','오누리','가상 누리개발','개발사 담당','2143','vendor','D01·D02 수정 버전·재현 회신'))
 return {'budget':budget,'contacts':'\n'.join(contacts),'approval_route':f'실무 {w["owner"]} {lead}(가상) → 팀장 검토 → {approver} 승인. 예산 변경은 회계 협의 후 별도 승인한다. 대체 담당은 {backup}(가상)이며 이 경로는 합성 기관의 시연 규칙이다.', 'document_locations':f'패키지 최상위의 01~04 진행보고, 06_업무실무기준정보.xlsx, 07_공통예산연락망.xlsx, 08_실행증빙대장.xlsx에서 {code}를 조회한다. 앱에서는 업무자료 → 해당 파일 → 본문 보기/원본 받기를 사용한다. 첨부가 없는 예정 산출물은 인계 산출물에 구분했다. 접근 문제는 행정지원팀 강온유에게 요청한다.'}


def workbook_bytes(sheets):
 from openpyxl import Workbook
 from openpyxl.styles import Font,PatternFill,Alignment
 wb=Workbook();wb.remove(wb.active)
 for name,rows in sheets.items():
  ws=wb.create_sheet(name)
  for row in rows:ws.append(row)
  ws.freeze_panes='A2'
  for col in ws.columns:ws.column_dimensions[col[0].column_letter].width=110 if ws.max_column==1 else 25
  for cell in ws[1]:cell.font=Font(bold=True,color='FFFFFF');cell.fill=PatternFill('solid',fgColor='245344')
  for row in ws:
   for cell in row:cell.alignment=Alignment(wrap_text=True,vertical='top')
  if ws.max_column==1:
   for row in ws:ws.row_dimensions[row[0].row].height=max(25,min(220,18*(str(row[0].value).count('\n')+1)+18*(len(str(row[0].value))//80)))
 b=io.BytesIO();wb.save(b);return b.getvalue()


def practice_archive():
 from docx import Document
 with zipfile.ZipFile(io.BytesIO(flow_archive())) as z:files={n:z.read(n) for n in z.namelist()}
 # Original reports remain real source files; plans gain the durable work brief.
 for index,w in enumerate(WORKS):
  name=next(n for n in files if n.startswith(f'{index+1:02d}_01_'))
  doc=Document(io.BytesIO(files[name]))
  for key in ['overview','objectives','scope','implementation_plan','completion_criteria']:
   doc.add_paragraph(PRACTICE_FIELDS[key]+': '+PROFILES[index][key])
  b=io.BytesIO();doc.save(b);files[name]=b.getvalue()
 metadata=[['합성자료 · 가상 한빛시 · 추가 금액·인명·기록은 시연을 위해 작성한 가상 정보'],['문서역할: 업무기준정보'],['보고일: 2026-11-09']]
 sheets={}
 for index,w in enumerate(WORKS):
  rows=copy.deepcopy(metadata)+[[f'업무: {w["title"]}'],[f'담당: {w["owner"]}']]
  for key,value in PROFILES[index].items():rows.append([PRACTICE_FIELDS[key]+': '+value])
  sheets[f'HB-{index+1:03d}']=rows
 files['06_업무실무기준정보.xlsx']=workbook_bytes(sheets)
 sheets={}
 for index,w in enumerate(WORKS):
  rows=copy.deepcopy(metadata)+[[f'업무: {w["title"]}'],[f'담당: {w["owner"]}']]
  for key,value in resources(index).items():rows.append([('연락처' if key=='contacts' else PRACTICE_FIELDS[key])+': '+value])
  sheets[f'HB-{index+1:03d}']=rows
 files['07_공통예산연락망.xlsx']=workbook_bytes(sheets)
 sheets={'안내':[['합성자료 · 아래 대장은 시연용 기록이며 실제 공문·영수증·현장 사진이 아님'],['문서역할: 증빙대장'],['보고일: 2026-11-09'],['모든 일련번호는 합성 자료. 향후 산출물의 존재나 완료를 주장하지 않음.']]}
 sheets['공모접수']=[['관리번호','신청번호','접수','자격 검토','보완자료','선정 결재']]+[['HB-001',f'A{i:02d}','접수 완료','검토 완료','보완 미접수' if i in [7,14] else '완비','예정'] for i in range(1,21)]
 sheets['위원확정']=[['관리번호','위원 식별','수락일','상태']]+[['HB-001',f'J{i:02d}','2026-11-07','참석 수락 확인 (가상 기록)'] for i in range(1,6)]
 sheets['정산검토']=[['관리번호','단체번호','정산서','영수증','적정성 검토','최종 승인']]+[['HB-002',f'G{i:02d}','접수 완료','누락' if i in [5,6] else '완비','완료' if i<=4 else '증빙 대기' if i in [5,6] else '검토 대기','미승인'] for i in range(1,11)]
 sheets['시설점검']=[['관리번호','시설번호','가상 시설명','점검','재점검']]+[['HB-003',f'F{i:02d}',f'한빛 문화시설 {i}호','2026-10-25 완료','2026-11-05 확인'] for i in range(1,6)]
 sheets['보수내역']=[['관리번호','보수번호','내용','상태','확인일']]+[['HB-003',f'R{i:02d}','유도등 교체' if i>=7 else f'경미 보수 {i}','완료','2026-11-05' if i>=7 else '2026-10-25'] for i in range(1,9)]
 sheets['결과결재']=[['관리번호','기록 식별','날짜','상태','유의'],['HB-003','HB-003-20261105','2026-11-05','최종 결과 결재 완료','시연용 대장 기록. 실제 기관 전자결재 문서 아님']]
 sheets['요구사항']=[['관리번호','요구번호','요구사항','일반 기능시험']]+[['HB-004',f'Q{i:02d}',name,'구현·기능시험 완료'] for i,name in enumerate(['시설 검색','날짜 조회','시간대 조회','예약 신청','신청 확인','예약 취소','관리자 목록','휴무일 설정','중복 예약 방지','신청 알림','이력 조회','권한 구분'],1)]
 sheets['접근성결함']=[['관리번호','결함번호','재현 절차','기대 결과','실제 결과','상태'],['HB-004','D01','키보드 Tab으로 날짜 선택 → Enter → 다음 입력칸 이동','초점이 다음 입력칸으로 이동','초점이 화면 밖으로 이탈','미해결'],['HB-004','D02','키보드로 확인 창 열기 → Esc 입력','확인 창 닫힘·원래 초점 복귀','창이 닫히지 않음','미해결']]
 files['08_실행증빙대장.xlsx']=workbook_bytes(sheets)
 files['09_업무동일성_담당확인.txt']='''합성자료 · 가상 한빛시 전임자 확인 기록
문서역할: 업무기준정보
보고일: 2026-11-09
업무: 문화시설 통합예약 개선
담당: 디지털지원팀
참고: 확인자 한새봄(가상). HB-004 문화시설 통합예약 개선 계획보고와 예약포털 접근성 보완 중간보고는 같은 사업의 전체 범위를 보고한 문서다. 20%와 75%는 같은 전체 범위를 기준으로 한 서로 다른 시점의 보고치다. 실제 담당은 디지털지원팀이며 중간보고의 담당 미정은 문서 작성 당시 누락이다. 전임자가 이 기록을 대조한 뒤 같은 업무로 매칭한다. 관리번호만 같다는 이유로 자동 연결하거나 두 진행률을 합산하지 않는다.
'''.encode()
 b=io.BytesIO()
 with zipfile.ZipFile(b,'w',zipfile.ZIP_DEFLATED) as z:
  for name,raw in sorted(files.items()):
   info=zipfile.ZipInfo(name,(2026,11,9,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,raw)
 return b.getvalue()
