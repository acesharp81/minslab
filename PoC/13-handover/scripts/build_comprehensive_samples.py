"""Offline, synthetic civil-service reports for the integrated demo. No model calls."""
import html,io,json,zipfile,hashlib
from pathlib import Path
from hwpx import HwpxDocument
from openpyxl import Workbook
from openpyxl.styles import Font,Alignment,PatternFill,Border,Side
from playwright.sync_api import sync_playwright
from app.engine import FIELDS
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'release/public';WORK=ROOT/'test-results/comprehensive/materials'
TITLES=['지역생활서비스 통합지원','문화시설 통합예약 개선','보조금 정산 승인','공공시설 안전점검','공공데이터 개방 품질개선']
OWNERS=['생활지원팀 김가온(가상)','디지털지원팀 한새봄(가상)','사업지원팀 박이음(가상)','시설관리팀 이한결(가상)','데이터정책팀 윤다정(가상)']
BUDGETS=[(120000000,48000000,12000000,60000000),(60000000,30000000,24000000,6000000),(150000000,140000000,0,10000000),(18000000,18000000,0,0),(42000000,21000000,8000000,13000000)]
DUE=['2026-11-13','2026-11-24','2026-11-06','2026-01-08','2026-11-18']

def budget(code,name,amounts,day):
 a,b,c,d=amounts
 return f'예산코드: {code} | 명칭: {name} | 편성액: {a:,}원 | 집행액: {b:,}원 | 지급예정액: {c:,}원 | 가용잔액: {d:,}원 | 기준일: {day} | 범위: 2026년 사업'

def fields(i,pct,day,alias=None):
 if i==4:
  f=fields(1,pct,day,alias)
  done='대상 20종 중 메타데이터 정비 12종 완료' if pct==60 else f'전체 진척 {pct}% 기록; 해당 판의 당시 검토 범위'
  f.update(title=alias or TITLES[i],owner=OWNERS[i],due_date=DUE[i],status=f'{pct}% 진행 중',
   overview='공공데이터 20종의 메타데이터·결측값·개방 권한을 정비하고 공개 전 품질 검증을 수행하는 사업이다.',
   objectives='데이터 20종을 동일 품질 기준으로 점검하고 공개 승인과 오류 정정 이력을 남긴다.',
   scope='CP-005 사업 전체. 데이터 정비와 외부 공개 승인은 별도 단계로 확인한다.',
   implementation_plan='2026-11-01 | 대상 20종 확정 | 목록표\n2026-11-06~11-08 | 메타데이터 정비·오류 대조 | 품질점검표\n2026-11-12 | 이용제한 항목 협의 | 부서 회신\n2026-11-18 | 잔여 검증·공개 승인 | 결재 기록',
   completed_work=done,remaining_work='잔여 8종 정비, Q17·Q18 이용제한 확인, 20종 공개 전 검증 및 승인',
   issues='Q17·Q18 이용제한 항목의 소관 부서 회신 대기',
   next_action='Q17·Q18 소관 부서에 이용제한 해제 가능 여부를 11월 12일까지 확인 요청',
   performance=f'지표: 전체 진행률 | 실적: {pct} | 목표: 100 | 단위: %',
   future_plan='2026-11-12 | 데이터정책팀 윤다정(가상) | Q17·Q18 이용제한 회신 확보 | 협의 기록 | 내부 관리 목표\n2026-11-18 | 데이터정책팀 윤다정(가상) | 잔여 검증 및 공개 승인 | 품질검증표·결재문 | 계획',
   issue_history='11/08 오전 잠정 집계를 원자료와 대조한 뒤 같은 날 17:30 3차 정정본으로 확정. 검토중·폐기 판본은 실적으로 쓰지 않는다.' if day=='2026-11-08' and pct==60 else '해당 판의 접수·점검 범위를 기록하며 이후 승인 여부는 후속 자료로 확인한다.',
   budget=budget('CP-B5',TITLES[i],(42000000,0,0,42000000) if pct<40 else BUDGETS[i],day)+'\n'+budget('CP-COM','공통 회의·자료 관리',(10000000,2000000,1000000,7000000),'2026-11-08' if day>='2026-11-08' else '2026-11-01'),
   contacts=f'관계자ID: CP-P5 | 성명: {OWNERS[i]} | 소속: 가상 데이터정책팀 | 역할: 실무 담당 | 연락: 내선 3151(시연용), work5@example.invalid | 협의사항: 개방 품질·이용제한\n관계자ID: CP-P90 | 성명: 서도윤(가상) | 소속: 가상 기획재정팀 | 역할: 회계 협의 | 연락: 내선 3190(시연용), finance@example.invalid | 협의사항: 집행·정산',
   document_locations='합성 공유함 / CP-005 / 개방 목록·품질점검·승인 기록',collaborators='가상 데이터정책팀·원천데이터 소관 부서·기획재정팀')
  return f
 done=['협약 원본 5건 확인 및 운영 매뉴얼 초안 작성','요구사항 12건 구현 및 일반 기능 시험','10개 단체 중 4개 단체 검토 완료','5개 시설 점검 및 보수 8건 조치·결과 결재 완료'][i]
 left=['잔여 3개 기관 협약, 담당자 교육 및 결과보고','D01·D02 접근성 오류 보완·재시험 및 운영 반영','누락 영수증 수령 후 잔여 6개 단체 검토·승인','완료 증빙 인수 및 차기 정기점검 일정 확인'][i]
 issue=['협약 원본 3건 미접수','키보드 탐색 오류 D01·D02 미해결','2개 단체 영수증 누락으로 11월 6일 승인 기한 경과','없음. 1월 8일 점검·보수 완료; 이후 신규 점검 상황은 별도 확인'][i]
 if pct<40:done='대상 목록과 추진계획 확정';left='현장 이행, 증빙 대조와 결과보고';issue='관계기관 일정 조율 필요'
 if i==0 and pct==80:done='협약 사본 6건 수령, 원본 대조 전 잠정 집계';issue='원본 대조 전 사본 집계이며 확정 실적 아님'
 if pct==100 and i!=3:done='전체 완료 예정 (미승인 계획)';issue='미승인 초안의 예상 실적이며 확정 실적이 아님'
 f={'title':alias or TITLES[i],'owner':OWNERS[i],'status':f'{pct}% 진행 중' if pct<100 else '사업 완료' if i==3 else '완료 예정 (미승인)', 'due_date':DUE[i],
 'overview':[ '8개 시범기관의 신청·협약·서비스 연계 절차를 통일하고 증빙과 교육 결과를 관리하는 업무다.','12개 요구사항의 예약 기능 개선과 접근성 검수, 운영 반영을 하나의 범위로 관리한다. 세 별칭 보고는 모두 같은 사업 전체 범위다.','10개 보조사업자의 집행 증빙을 대조하고 보완·반납 여부를 검토하여 정산 승인하는 업무다.','5개 공공시설 안전점검 및 보수 8건을 완료하고 증빙과 차기 점검 기준을 후임자에게 전달하는 업무다.'][i],
 'objectives':['8개 기관 협약 원본과 교육 이수 결과를 확보하고 운영 결과보고를 승인받는다.','요구사항 12건 구현, 접근성 오류 2건 해소·재시험, 운영 반영 승인을 완료한다.','10개 단체의 적정성 검토·정산 승인과 반납 필요 여부 기록을 모두 마무리한다.','5개 시설 점검, 보수 8건 검증, 결과 결재 기록을 보관하고 차기 점검을 준비한다.'][i],
 'scope':f'CP-{i+1:03d} 사업 전체. 보고서 제목이 달라도 동일 범위인지는 담당 확인 기록과 대조한다.',
 'implementation_plan':'2026-11-01~11-03 | 계획·대상 확정 | 대상 목록\n2026-11-04~11-08 | 현장 이행·증빙 검토 | 실적 대장\n2026-11-10~11-13 | 보완·관계기관 협의 | 요청·회신 기록\n'+DUE[i]+' | 결과보고 승인 | 결재 문서' if i!=3 else '2026-01-02 | 점검계획 확정 | 대상 목록\n2026-01-03~01-07 | 현장 점검·보수 | 점검표\n2026-01-08 | 재점검·결과 승인 | 결재대장',
 'completed_work':done,'remaining_work':left,'issues':issue,'next_action':['미접수 3개 기관에 날인 원본 회신을 요청','개발사에 D01·D02 재현 기록을 전달하고 재시험 일정을 협의','G05·G06 누락 영수증을 즉시 요청하고 승인 지연 경위·재일정을 협의','점검·보수 완료 증빙과 차기 점검 일정 인수 여부를 확인'][i],
 'performance':f'지표: 전체 진행률 | 실적: {pct} | 목표: 100 | 단위: %\n'+['지표: 협약 원본 확보 | 실적: 5 | 목표: 8 | 단위: 기관','지표: 접근성 오류 해소 | 실적: 0 | 목표: 2 | 단위: 건','지표: 단체 검토 완료 | 실적: 4 | 목표: 10 | 단위: 단체','지표: 시설 점검 완료 | 실적: 5 | 목표: 5 | 단위: 곳'][i],
 'future_plan':f'즉시 | {OWNERS[i]} | {left} | 조치 목록 | 원문 후속조치\n2026-11-11 | {OWNERS[i]} | 관계부서 진행 상황 재확인 | 회신 기록 | 내부 관리 목표·대외 기한 변경 아님' if i!=3 else '인수 직후 | 시설관리팀 | 1월 완료 증빙 대조 | 인수 확인 기록 | 완료 사업 유지\n차기 점검계획 수립 시 | 시설관리팀 | 신규 이상 여부 확인 | 신규 점검계획 | 일정 미확정',
 'operating_steps':'1. 실적대장에서 대상별 접수 여부 확인\n2. 원본 증빙과 수치를 대조하고 누락 건 재요청\n3. 담당 검토와 팀장 확인\n4. 과장 결재 후 결과 통보\n5. 원본·결재 기록·미결 목록을 함께 인계',
 'completion_criteria':'남은 이행·증빙 대조·담당 검토·결과 결재가 모두 끝나야 완료로 표시한다. 계획이나 사본 접수만으로 완료 처리하지 않는다.',
 'deliverables':'계획·진행 보고, 실적대장, 담당 확인 기록(합성 자료 제공). 향후 생성할 최종 결재문·재시험 결과는 제공된 증빙으로 표시하지 않는다.' if i!=3 else '시설별 점검 5건·보수 8건·1월 8일 결과 승인 기록(합성 대장). 실제 현장 사진은 제공하지 않는다.',
 'issue_history':['11/06 사본 기준 80% 잠정 보고 → 11/08 원본 대조 후 65%로 정정. 미접수 원본 3건은 계속 미해결.','11/03 화면 개발 착수 → 11/06 기능 시험 → 11/08 접근성 오류 2건 미해결. 업무명 불일치는 담당 확인 기록으로 해소한다.','11/06 승인 기한 경과 → 11/08 G05·G06 영수증 보완 대기. 기한 변경 승인은 아직 없다.','1월 7일 유도등 2개 교체 → 1월 8일 재점검·결재로 해소. 이후 실적을 추정하지 않는다.'][i],
 'approval_route':'실무 담당 → 팀장 검토 → 과장 승인. 기한·예산 변경은 별도 협의·결재가 필요하다.',
 'document_locations':'합성 공유함 / CP 사업코드 / 계획·실적·결재. 시연 패키지의 q77.xlsx는 증빙대장, memo.pdf는 동일업무 담당 확인 기록이다.',
 'collaborators':'가상 기획재정팀·문서지원팀·사업별 수행기관',
 'budget':budget(f'CP-B{i+1}',TITLES[i],(BUDGETS[i][0],0,0,BUDGETS[i][0]) if pct<40 else BUDGETS[i],day)+(('\n'+budget('CP-COM','공통 회의·자료 관리',(10000000,2000000,1000000,7000000),'2026-01-08' if day<'2026-11-01' else '2026-11-01' if day<'2026-11-08' else '2026-11-08')) if i!=3 else ''),
 'contacts':f'관계자ID: CP-P{i+1} | 성명: {OWNERS[i]} | 소속: 가상 사업팀 | 역할: 실무 담당 | 연락: 내선 31{i+1}1(시연용), work{i+1}@example.invalid | 협의사항: 현안·보완·일정\n관계자ID: CP-P90 | 성명: 서도윤(가상) | 소속: 가상 기획재정팀 | 역할: 회계 협의 | 연락: 내선 3190(시연용), finance@example.invalid | 협의사항: 집행·정산',
 'notes':'실제 기관·인물과 무관한 합성 시연자료. 현황은 원문 기준일 당시 기록이며 현재 사실을 뜻하지 않는다.'}
 # Historical reports must not contain later events as completed facts.
 if day<'2026-11-08' and i!=3:
  f['issue_history']='계획 및 대상 목록을 확정하고 관계기관의 일정과 증빙 제출 범위를 협의 중이다. 이후 실적은 이 보고서에 포함하지 않는다.'
  f['document_locations']=f'가상 업무공유함 / CP-{i+1:03d} / 해당 기준일의 계획·실적 자료. 이후 생성되는 증빙과 결재문은 별도 확인한다.'
  if pct<40:
   f['performance']=f'지표: 전체 진행률 | 실적: {pct} | 목표: 100 | 단위: %'
   f['future_plan']=f'계획 확정 후 | {OWNERS[i]} | 기관별 증빙 접수 및 실적 검토 | 접수·검토대장 | 계획\n결과보고 시 | {OWNERS[i]} | 최종 조치 결과 결재 | 승인 기록 | 계획'
  if i==0 and day=='2026-11-06':
   f['issue_history']='11/06 협약 사본 6건 수령을 기준으로 80%를 잠정 보고했다. 날인 원본 대조가 남아 있으며 실제 원본 실적은 재확인한다.'
   f['performance']='지표: 전체 진행률(잠정) | 실적: 80 | 목표: 100 | 단위: %\n지표: 협약 사본 접수 | 실적: 6 | 목표: 8 | 단위: 기관'
   f['remaining_work']='날인 원본 대조와 미접수 기관 확인, 담당자 교육 및 결과보고'
  if i==1 and day=='2026-11-06':
   f['completed_work']='요구사항 12건 구현 중 6건 일반 기능 시험 완료'
   f['issues']='잔여 6건 기능 시험과 접근성 점검이 남아 있음'
   f['issue_history']='11/03 계획 확정 후 개발에 착수했고 11/06 기능 시험 6건을 마쳤다. 접근성 결함 여부는 후속 점검에서 확인한다.'
   f['next_action']='잔여 기능 시험과 키보드 접근성 점검 일정을 확정'
   f['remaining_work']='잔여 6건 기능 시험, 접근성 점검·보완 및 운영 반영'
 return f

def content(i,pct,day,rev,stage='중간보고',alias=None,draft=False):
 f=fields(i,pct,day,alias);rows=[('title',(alias or TITLES[i])+' '+stage),('small','가상 생활서비스정책국 | 인수인계 담당 검토용 | 합성 자료'),('heading','□ 보고 개요')]
 for k,v in [('보고일',day),('사업관리번호',f'CP-{i+1:03d}'),('문서관리번호',f'CP-{i+1:03d}-RPT'),('수정차수',f'{rev}차'),('수정일시',day+' 16:00'),('문서상태','초안' if draft else '확정'),('보고단계',stage),('계획 시작일','2026-01-02' if i in [0,3] else '2026-11-01'),('전체 진행률',f'{pct}%')]:rows.append(('meta',f'{k}: {v}'))
 if i==3:rows.append(('meta','실제 완료일: 2026-01-08'))
 rows.append(('heading','□ 업무 개요 및 추진 현황'))
 for k in ['title','owner','due_date','status','overview','objectives','scope','implementation_plan','completed_work','performance','issues','issue_history']:
  rows.append(('body',f'○ ({FIELDS[k]}) {f[k]}'))
 rows.append(('detail','- 아래 실적은 보고 기준일 당시 기록이며 승인 전 예상치와 구분한다.'))
 table=[['구분','목표·대상','현재 확인','후속 조치'],['전체 진척','100%',f'{pct}%','증빙·결재 확인'],['이행 내역',f['objectives'],f['completed_work'],f['remaining_work']]]
 rows.append(('heading','□ 향후 조치 및 인수인계 사항'))
 for k in ['remaining_work','next_action','future_plan','operating_steps','completion_criteria','deliverables','approval_route','document_locations','collaborators','contacts','budget','notes']:rows.append(('body',f'○ ({FIELDS[k]}) {f[k]}'))
 # Add five real matrices per report. Detail codes exist ONLY in table cells.
 tables=[('진척 및 이행 대조표',table),('추진 일정 관리표',[
  ['관리코드','단계·예정일','해당 판 실적','점검 자료'],
  [f'TBL-CP{i+1}-S1','계획 확정', '대상 범위와 승인 경로 확인','계획 결재 기록'],
  [f'TBL-CP{i+1}-S2',DUE[i],f'보고 당시 {pct}%','세부 완료 여부는 현황 문단과 대조'],
  [f'TBL-CP{i+1}-S3','인수 직후','증빙·후속 조치 재확인','인수 확인 기록']]),
 ('미결 및 조치 대장',[
  ['관리코드','확인 사항','처리 부서','종결 조건'],
  [f'TBL-CP{i+1}-R1',f['issues'],OWNERS[i],f['completion_criteria']],
  [f'TBL-CP{i+1}-R2',f['remaining_work'],'협업 부서','회신·결재 원본 대조']]),
 ('예산 집행 대조표',[
  ['예산코드','편성 / 집행 (원)','지급예정 / 가용 (원)','금액 기준'],
  [f'CP-B{i+1}',f'{BUDGETS[i][0]:,} / {0 if pct<40 else BUDGETS[i][1]:,}',f'{0 if pct<40 else BUDGETS[i][2]:,} / {BUDGETS[i][0] if pct<40 else BUDGETS[i][3]:,}',day],
  ['검산 원칙','집행+지급예정+가용=편성','공통 CP-COM은 중복 합산 금지',f'TBL-CP{i+1}-B1']]),
 ('담당 및 협의 창구',[
  ['관리코드','담당 부서·성명','연락 수단','협의 범위'],
  [f'TBL-CP{i+1}-P1',OWNERS[i],f'work{i+1}@example.invalid','일정·증빙·현안'],
  [f'TBL-CP{i+1}-P2','가상 기획재정팀 서도윤','finance@example.invalid','공통 예산·정산']])]
 return rows,tables

def write(path,rows,tables,browser,pic=None):
 # Compatibility for the single table in the owner confirmation attachment.
 if tables and isinstance(tables[0],list):tables=[('확인 내역',tables)]
 if path.suffix=='.hwpx':
  d=HwpxDocument.new();styles={k:d.ensure_run_style(font='함초롬바탕',size=s,bold=b) for k,s,b in [('title',18,True),('heading',13,True),('body',10,False),('meta',9,False),('small',9,False),('detail',9,False)]}
  for kind,text in rows:
   d.add_paragraph(text,char_pr_id_ref=styles[kind])
   if kind=='detail':
    for caption,table in tables:
     d.add_paragraph('□ '+caption,char_pr_id_ref=styles['heading'])
     t=d.add_table(len(table),4,width=47000,height=max(7000,len(table)*2200),char_pr_id_ref=styles['small'])
     for r,cells in enumerate(table):
      for c,value in enumerate(cells):t.set_cell_text(r,c,value)
  if pic:d.add_paragraph('붙임: 협약 접수현황 그림(합성)');d.add_picture(pic,'png',width_mm=155,height_mm=75)
  d.save_to_path(path);assert not HwpxDocument.open(path).validate().issues
 elif path.suffix=='.xlsx':
  w=Workbook();s=w.active;s.title='추진상황 보고';s.column_dimensions['A'].width=22
  for col in 'BCDEF':s.column_dimensions[col].width=14
  row=1
  for kind,text in rows:
   s.merge_cells(start_row=row,start_column=1,end_row=row,end_column=6);c=s.cell(row,1,text);c.font=Font(name='맑은 고딕',size=16 if kind=='title' else 11,bold=kind in ['title','heading'],color='203D51');c.alignment=Alignment(wrap_text=True,vertical='center');s.row_dimensions[row].height=max(25,18*(text.count('\n')+1)+16*(len(text)//85))
   if kind in ['title','heading']:c.fill=PatternFill('solid',fgColor='E8EFF4')
   row+=1
  for caption,table in tables:
   matrix=w.create_sheet(caption)
   for r in table:matrix.append(r)
   for col in 'ABCD':matrix.column_dimensions[col].width=30
   for cells in matrix:
    matrix.row_dimensions[cells[0].row].height=100 if cells[0].row>1 else 32
    for c in cells:
     c.alignment=Alignment(wrap_text=True,vertical='top');c.border=Border(bottom=Side(style='thin',color='CCD8DA'))
     if c.row==1:c.font=Font(name='맑은 고딕',bold=True);c.fill=PatternFill('solid',fgColor='E8EFF4')
  for sheet in w:
   sheet.freeze_panes='A2';sheet.sheet_properties.pageSetUpPr.fitToPage=True;sheet.page_setup.orientation='portrait';sheet.page_setup.paperSize=sheet.PAPERSIZE_A4;sheet.page_setup.fitToWidth=1;sheet.page_setup.fitToHeight=0
  w.save(path)
 else:
  parts=[]
  for kind,text in rows:
   rendered='<br>'.join(' | '.join('<span class="record-piece">'+html.escape(part)+'</span>' for part in line.split(' | ')) for line in text.split('\n')) if ' | ' in text else html.escape(text)
   parts.append(f'<p class="{kind}">{rendered}</p>')
   if kind=='detail':
    for caption,table in tables:parts.append('<p class="heading">□ '+html.escape(caption)+'</p><table>'+''.join('<tr>'+''.join('<td>'+html.escape(t)+'</td>' for t in row)+'</tr>' for row in table)+'</table>')
  page=browser.new_page();page.set_content('<!doctype html><html lang="ko"><meta charset="utf-8"><style>@page{size:A4;margin:17mm}body{font:10pt/1.7 "Noto Serif CJK KR";color:#182f40;font-variant-ligatures:none}.record-piece{white-space:nowrap}p{margin:6px 0;white-space:pre-wrap;break-inside:avoid}.title{font-size:19pt;font-weight:bold;text-align:center;border-bottom:3px double;padding-bottom:10px}.heading{font-size:13pt;font-weight:bold;background:#edf2f5;padding:5px;break-after:avoid}.meta,.small{font-size:9pt}.detail{padding-left:12px}table{border-collapse:collapse;table-layout:fixed;width:100%;font-size:9pt}td:first-child{width:19%;white-space:nowrap;font-size:8pt}td{border:1px solid #9cacb5;padding:6px;vertical-align:top}tr:first-child{background:#e3ecf0;font-weight:bold}tr{break-inside:avoid}tr:first-child{break-after:avoid}</style>'+''.join(parts));page.evaluate('document.fonts.ready');page.pdf(path=str(path),prefer_css_page_size=True,print_background=True);page.close()

def main():
 WORK.mkdir(parents=True,exist_ok=True);pics={}
 for k,n in [('latest','01_최신본_먼저등록.zip'),('old','02_구판_나중등록.zip'),('draft','03_미승인초안_마지막등록.zip')]:
  with zipfile.ZipFile(OUT/n) as z:
   with zipfile.ZipFile(io.BytesIO(z.read('직원1/보고서.hwpx'))) as doc:pics[k]=doc.read(next(x for x in doc.namelist() if x.startswith('BinData/') and x.endswith('.png')))
 stages={'comprehensive-base.zip':[], 'comprehensive-current.zip':[], 'comprehensive-old.zip':[], 'comprehensive-draft.zip':[]};manifest=[]
 with sync_playwright() as pw:
  browser=pw.chromium.launch(headless=True,args=['--no-sandbox'])
  specs=[('comprehensive-base.zip','a17.hwpx',0,20,'2026-01-08',1,'계획보고',None,None),('comprehensive-base.zip','b03.hwpx',3,100,'2026-01-08',1,'완료보고',None,None),('comprehensive-current.zip','자료/보고서.hwpx',0,65,'2026-11-08',3,'중간보고',None,'latest'),('comprehensive-current.zip','p08.hwpx',1,20,'2026-11-03',1,'계획보고',None,None),('comprehensive-current.zip','r42.xlsx',1,50,'2026-11-06',2,'착수보고','예약 화면 이용편의 개선',None),('comprehensive-current.zip','scan_003.pdf',1,75,'2026-11-08',3,'중간보고','예약포털 접근성 보완',None),('comprehensive-current.zip','aa00.pdf',2,20,'2026-11-02',1,'계획보고',None,None),('comprehensive-current.zip','zz99.xlsx',2,40,'2026-11-08',2,'중간보고',None,None),('comprehensive-old.zip','자료/보고서.hwpx',0,80,'2026-11-06',2,'중간보고',None,'old'),('comprehensive-old.zip','첨부.hwpx',0,20,'2026-11-01',1,'계획보고',None,None),('comprehensive-draft.zip','자료/보고서.hwpx',0,100,'2026-11-09',4,'완료보고',None,'draft')]
  specs += [
   ('comprehensive-current.zip','r11.pdf',4,60,'2026-11-08',3,'중간보고',None,None),
   ('comprehensive-current.zip','k20.xlsx',4,10,'2026-11-01',1,'계획보고',None,None),
   ('comprehensive-old.zip','zz99.xlsx',2,35,'2026-11-08',1,'중간보고',None,None),
   ('comprehensive-old.zip','r11.pdf',4,45,'2026-11-08',3,'중간보고',None,None),
   ('comprehensive-old.zip','x01.hwpx',4,30,'2026-11-06',2,'착수보고',None,None),
   ('comprehensive-draft.zip','zz99.xlsx',2,90,'2026-11-09',4,'중간보고',None,None),
   ('comprehensive-draft.zip','r11.pdf',4,100,'2026-11-09',4,'완료보고',None,None),
   ('comprehensive-draft.zip','x01.hwpx',4,100,'2026-11-10',5,'완료보고',None,None)]
  for n,(pack,name,i,pct,day,rev,stage,alias,pic) in enumerate(specs):
   state='초안' if pic=='draft' else '확정'
   if pack=='comprehensive-draft.zip' and i==2:state='대체됨'
   if pack=='comprehensive-draft.zip' and i==4:state='검토중' if name=='r11.pdf' else '폐기'
   time='17:30' if i==4 and pct==60 else '10:00' if i==4 and pct==45 else '16:00'
   path=WORK/(str(n)+Path(name).suffix);rows,tables=content(i,pct,day,rev,stage,alias,state!='확정')
   rows=[(k,('문서상태: '+state) if v.startswith('문서상태:') else ('수정일시: '+day+' '+time) if v.startswith('수정일시:') else v) for k,v in rows]
   write(path,rows,tables,browser,pics.get(pic));stages[pack].append((name,path.read_bytes()));manifest.append({'pack':pack,'file':name,'title':alias or TITLES[i],'progress':pct,'date':day,'revision':rev,'issued_at':day+'T'+time,'state':state,'tables':len(tables),'table_markers':[f'TBL-CP{i+1}-{suffix}' for suffix in ['S1','R1','B1','P1']],'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
  w=Workbook();s=w.active;s.title='증빙 및 예산 대장';s.append(['문서역할: 증빙대장']);s.append(['합성 자료 · 2026-11-08 기준']);s.append(['사업코드','대상/실적','미결 사항','다음 확인']);
  for row in [('CP-001','협약 원본 5/8','미접수 3건','협약 원본 재요청'),('CP-002','요구사항 구현 12/12','D01·D02 미해결','키보드 재시험'),('CP-003','검토 4/10','G05·G06 영수증 누락','승인 재일정 협의'),('CP-004','1월 점검 5/5·보수 8/8','당시 미결 없음','이후 신규 점검 여부 확인'),('CP-005','메타데이터 12/20','Q17·Q18 이용제한 회신 대기','잔여 8종·공개 승인')]:s.append(row)
  b=w.create_sheet('예산 검산');b.append(['문서역할: 증빙대장']);b.append(['코드','편성','집행','지급예정','가용잔액'])
  for i,vals in enumerate(BUDGETS):b.append([f'CP-B{i+1}',*vals])
  b.append(['CP-COM',10000000,2000000,1000000,7000000]);b.append(['합계',400000000,259000000,45000000,96000000])
  for sheet in w:
   sheet.freeze_panes='A3';sheet.auto_filter.ref=f'A2:{sheet.cell(2,sheet.max_column).column_letter}{sheet.max_row}'
   for col in sheet.columns:sheet.column_dimensions[col[0].column_letter].width=28
   for cells in sheet:
    sheet.row_dimensions[cells[0].row].height=38
    for c in cells:c.font=Font(name='맑은 고딕',size=11,bold=c.row<=2);c.alignment=Alignment(wrap_text=True,vertical='center')
  buf=io.BytesIO();w.save(buf);stages['comprehensive-current.zip'].append(('q77.xlsx',buf.getvalue()))
  rows=[('title','동일업무 및 인수인계 범위 확인서'),('meta','문서역할: 증빙대장'),('small','2026-11-09 | 가상 디지털지원팀 | 합성 확인 기록'),('heading','□ 확인 결과'),('body','○ (확인 대상) 문화시설 통합예약 개선 / 예약 화면 이용편의 개선 / 예약포털 접근성 보완'),('body','○ (확인 내용) CP-002 같은 사업의 전체 범위이며 각각의 20%·50%·75%는 부분사업 합계가 아닌 다른 기준일의 전체 진행률이다.'),('body','○ (책임 부서) 디지털지원팀 한새봄(가상). 3개 후보를 문화시설 통합예약 개선으로 묶고 최신 75%를 채택한다.'),('detail','- 기준일·범위를 대조하고 사람이 묶음을 저장한다. 이 확인서는 사업의 실제 장애 사항이 아니다.')];path=WORK/'memo.pdf';write(path,rows,[['문서','시점','전체 진척','처리'],['p08 / r42 / scan_003','11/03 → 11/06 → 11/08','20 → 50 → 75%','하나의 업무로 묶기']],browser);stages['comprehensive-current.zip'].append(('memo.pdf',path.read_bytes()));browser.close()
 for pack,entries in stages.items():
  with zipfile.ZipFile(OUT/pack,'w',zipfile.ZIP_DEFLATED) as z:
   for name,data in entries:z.writestr(name,data)
 expected={'synthetic_only':True,'original_documents':21,'target_documents_before_inheritance':19,'draft_candidates_with_inheritance':7,'final_work_count':5,'progress':dict(zip(TITLES,[65,75,40,100,60])),'same_filename':'자료/보고서.hwpx','same_filename_versions':3,'selected_revision':3,'excluded_draft_revision':4,'latest_only_images':1,'excluded_images':2,'manual_group_titles':[TITLES[1],'예약 화면 이용편의 개선','예약포털 접근성 보완'],'inherited_unchanged':TITLES[3],'updated_from_previous':TITLES[0],'unique_budgets':6,'unique_contacts':6,'report_tables':95,'source_formats':{'hwpx':9,'xlsx':6,'pdf':6},'version_scenarios':['서로 다른 기준일','동일 기준일·다른 수정차수','동일 기준일·동일 차수·다른 수정시각','초안·검토중·대체됨·폐기 제외'],'version_selections':{TITLES[2]:{'revision':2,'progress':40},TITLES[4]:{'revision':3,'issued_at':'2026-11-08T17:30','progress':60}},'budget_review_required':{'title':TITLES[3],'evidence':'q77.xlsx / 예산 검산','field':'budget','old_date':'2026-01-08','new_date':'2026-11-08'},'budget_totals':{'편성':400000000,'집행':259000000,'지급예정':45000000,'가용잔액':96000000},'files':manifest,'manual_ai_only':True}
 (OUT/'comprehensive-expected.json').write_text(json.dumps(expected,ensure_ascii=False,indent=2))
 guide='''# 샘플1 · 종합 인수인계 실무 시연

실제 기관·인물과 무관한 합성 자료입니다. 한글(HWPX)·엑셀·텍스트 PDF의 개조식 보고와 표를 제공합니다. AI나 그림 분석은 시연 선택만으로 실행되지 않습니다.

## 확장한 복합 사례
원본 21개(HWPX 9 / XLSX 6 / PDF 6), 사업 5개입니다. 19개 사업 보고서마다 실적·일정·조치·예산·연락망 표 5개씩 총 95개를 넣었습니다. 별도 증빙대장과 담당 확인서의 표는 이 수에서 제외합니다.

|사업|최종 진행률|판본·검토 포인트|
|---|---:|---|
|지역생활서비스 통합지원|65%|구판 80%, 최신 확정 65%, 더 늦은 초안 100%|
|문화시설 통합예약 개선|75%|서로 다른 업무명 3개를 담당 확인 후 묶기|
|보조금 정산 승인|40%|같은 기준일 1차 35% / 2차 40%; 대체됨 90% 제외|
|공공시설 안전점검|100%|이전 완료 기록 유지, 예산 기준일만 대조|
|공공데이터 개방 품질개선|60%|같은 날·3차의 10:00 45% / 17:30 60%; 검토중 100%·폐기 100% 제외|

최신본은 진행률 최대값이나 업로드 순서로 고르지 않습니다. 표에만 있는 TBL-CP5-R1 등 관리코드를 원문 팝업에서 찾아 표 내용과 위치가 보존되었는지 확인할 수 있습니다. PDF는 텍스트 PDF이며 표의 병합·OCR 전체 지원을 뜻하지 않습니다.

## 빠른 실행
1. 홈 → 시연 및 샘플 데이터 다운 → 샘플1 ‘종합 인수인계 실무 시연’ → 시연 수행. 인계자·인수자를 선택합니다.
2. 이전에 인수 완료한 2개 업무 보고서와 현행 자료 19개가 준비됩니다. 생성 창에서 ‘이전에 인수한 보고서 이어서 작성’을 체크하고 이 시연의 이전 보고서를 고릅니다. 로컬 규칙으로 먼저 점검할 수 있습니다. Solar 문서 해석은 사용자가 선택·동의할 때 실행합니다.
3. 7개 업무 후보를 확인합니다. 생활서비스는 이전 20%에서 65%로 갱신, 안전점검은 이전 100%를 유지합니다. 안전점검의 완료 기록은 1월 기준이며 이후 현황을 추측하면 안 됩니다.
4. ‘업무 전체 보고 묶기’에서 문화시설 통합예약 개선, 예약 화면 이용편의 개선, 예약포털 접근성 보완을 하나로 묶습니다. memo.pdf의 담당·동일 범위를 대조하고 기준 업무명은 문화시설 통합예약 개선, 담당은 디지털지원팀 한새봄(가상)으로 저장합니다. 7개 후보가 5개 업무로 줄어들며 진척은 65% / 75% / 40% / 100% / 60%입니다. 두 별칭을 한 번에 차례로 끌어 넣거나 ‘이동’을 사용하세요.
5. 자료/보고서.hwpx라는 같은 이름의 세 파일을 비교합니다. 최신 확정 3차(11/08, 65%)를 먼저 올렸고 구판 2차(11/06, 80%)와 미승인 4차(11/09, 100%)를 나중에 올렸습니다. 업로드 순서·파일명·최대 진행률·높은 차수만으로 선택하면 실패입니다. 계획본 첨부.hwpx도 함께 보존됩니다.
6. 안전점검의 ‘예산 현황’ 옆 연필을 눌러 q77.xlsx의 예산 검산 시트(11월 8일 잔액)를 대조합니다. 금액이 동일함을 확인하고 예산의 기준일만 2026-01-08에서 2026-11-08로 바꾼 뒤 사유에 ‘q77.xlsx 예산 검산 시트 대조’를 기록하세요. 대조 전에는 예산 기준일이 달라 전체 합계를 보류하는 것이 정상입니다. 안전점검의 1월 완료일·진척은 바꾸지 않습니다. 이어서 참고 사항에 ‘인수자와 11월 11일 오전 진행상황 재확인 예정’이라는 사용자 입력을 추가해 보세요. 원문 실적으로 바꾸지 않고 변경 이력·수정 사유가 남는지 확인합니다.
7. 검토·확정 후 보고서를 엽니다. 상단 간트·지연·달성률, 업무별 개요·목표·추진 흐름·현안·추후 계획, 공통 예산·연락망, 이전 인수 이력을 확인합니다. 예산 6개 코드의 합계는 편성 400,000,000 / 집행 259,000,000 / 지급예정 45,000,000 / 가용 96,000,000원입니다. 공통 예산은 여러 보고에 반복되어도 한 번만 합산합니다. 연락망은 6명입니다.
8. 원문 기록 확인 팝업을 열고 닫아 읽던 위치가 유지되는지 확인합니다. 목차 트리를 펼치고 보고서 챗봇에서 ‘기한이 지난 업무와 지금 해야 할 일은?’을 질문합니다. 키워드 검색은 무과금; Solar 답변은 별도 동의 후 실행합니다. 우선 현안은 보조금 정산 승인 지연이며 업무명 불일치는 참고 사항입니다.
9. 변경 이력 오른쪽 ‘인계하기’에서 의견을 적고 최종본을 전달합니다. 받을 직원으로 전환해 같은 판본·의견을 읽고 인수 확인합니다. 완료 목록으로 이동하며 보고서·전달 기록이 유지되어야 합니다.
10. HTML·MD·DOCX 다운로드 및 인쇄/PDF 저장을 확인합니다. 그림 분석을 시험하려면 생성 창에서 직접 선택합니다. 최신 HWPX의 그림 1개만 대상이며 구판·초안 그림 2개는 제외됩니다. 예상 판독은 ‘확인 완료 5건 / 미서명 1건 / 추가 요청 3건’입니다. 실제 판독 정확도는 사용자가 실행한 결과로 확인합니다. GPT 일일 소진 시 공용 월 무료 예산 전환도 현재 운영 정책을 따릅니다.

## 다운로드 자료로 직접 등록
이 전체 KIT ZIP은 설명·정답·내부 ZIP을 담고 있습니다. 전체 KIT를 업무자료로 올리지 마세요.

- comprehensive-base.zip: 이전 인계자의 원본 2개. 별도 인수인계함에서 생성·확정·인수 확인합니다.
- comprehensive-current.zip: 새 인계함에 첫 번째로 업로드(10개). 최신본·다른 업무·실적대장·담당 확인서입니다.
- comprehensive-old.zip: 같은 인계함에 두 번째로 업로드(5개). 같은 파일명 구판을 나중에 등록합니다.
- comprehensive-draft.zip: 세 번째로 업로드(4개). 같은 파일명의 초안·검토중·대체됨·폐기 판본입니다.
- 초안 생성 시 이전에 인수한 보고서를 선택합니다. 체크하지 않으면 이전 점검 업무가 빠져 6개 후보 → 최종 4개 업무가 됩니다.

## 점검 범위와 한계
자동 검증은 합성 원문의 라벨 추출·최신 판본·계승·그룹·수정·확정·전달·인수·출력과 그림 선택 범위를 점검합니다. 임의의 스캔 OCR, 모든 복잡한 한글 배치, 실제 기관 인증·전자결재·서명, 외부 모델의 응답 정확도를 보증하지 않습니다. AI 그림 판독과 대화는 자동 검증에서 유료 호출하지 않습니다. PDF는 텍스트 PDF이며 HWPX 원본은 한글 호환 편집기에서 열어 표와 문단을 확인하세요.
'''
 (OUT/'comprehensive-guide.md').write_text(guide)
 with zipfile.ZipFile(OUT/'comprehensive-kit.zip','w',zipfile.ZIP_DEFLATED) as z:
  for name in [*stages,'comprehensive-expected.json']:z.write(OUT/name,name)
  z.writestr('시작하기.md',guide)
 print(json.dumps({'packs':{k:len(v) for k,v in stages.items()},'expected_final':expected['progress']},ensure_ascii=False))
if __name__=='__main__':main()
