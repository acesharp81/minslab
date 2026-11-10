"""Author synthetic civil-service style HWPX/XLSX/PDF; no model calls."""
import json,html,zipfile,hashlib
from pathlib import Path
from hwpx import HwpxDocument
from openpyxl import Workbook
from openpyxl.styles import Font,PatternFill,Alignment,Border,Side
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'release/public';WORK=ROOT/'test-results/versions/materials'
OUT.mkdir(parents=True,exist_ok=True);WORK.mkdir(parents=True,exist_ok=True)
PROJECTS=[
 dict(title='2026년 지역생활서비스 통합지원 사업',team='생활서비스정책과',owner='생활서비스정책과 김나래',scope='시범 지자체 8곳의 생활서비스 신청·연계 절차',goal='8개 지자체의 접수·연계 기준을 통일하고 시범 운영 결과를 확정한다.',budget=240000000,due='2026-11-13',progress=[20,80,65],statuses=['운영계획 수립 및 참여 수요 조사 중','8곳 중 6곳 협약 체결로 집계','협약 원본 대조 결과 8곳 중 5곳 체결 확인'],done=['참여 의향 8곳 접수','협약서 6건 사본 수령','협약 원본 5건 확인 및 운영 매뉴얼 초안 작성'],remain=['협약 체결 및 담당자 교육','잔여 2곳 협약과 교육 결과 취합','잔여 3곳 협약 및 8곳 담당자 교육'],issue=['협약 문구에 대한 법무 검토 대기','교육 일정 2곳 미확정','1건은 미서명 사본으로 실적에서 제외; 3곳 협약 미체결'],action='미서명 지자체 3곳에 협약 원본 제출을 요청한다.',reason='미서명 사본 1건을 체결 실적에서 제외하여 진행률을 80%에서 65%로 정정함.'),
 dict(title='2026년 공공시설 안전관리 고도화 사업',team='시설안전과',owner='시설안전과 박도윤',scope='소관 공공시설 20곳의 안전점검 및 보완 조치',goal='20개 시설의 점검을 완료하고 위험시설 3곳의 보완 조치 결과를 확인한다.',budget=180000000,due='2026-11-06',progress=[15,45,70],statuses=['점검 대상과 현장 일정 조율 중','20곳 중 9곳 점검 완료','20곳 중 14곳 점검 완료; 승인 기한 경과'],done=['대상 시설 목록 20곳 확정','현장 점검표 9건 작성','점검표 14건 및 위험시설 통제 안내문 발송'],remain=['20곳 점검과 결과 보고','11곳 점검과 위험시설 보완','6곳 추가 점검 및 위험시설 3곳 조치 확인'],issue=['현장 출입 승인 4곳 대기','위험시설 3곳 보완 예산 협의 지연','11월 6일 결과 승인 기한 경과; 위험시설 3곳 조치 미완료'],action='위험시설 3곳의 임시 통제를 재확인하고 지연 경위를 과장에게 보고한다.',reason='시설 관리기관의 점검표 추가 제출분을 반영함.'),
 dict(title='2026년 디지털 민원안내 표준화 사업',team='디지털행정지원과',owner='디지털행정지원과 이서준',scope='민원안내 30종의 쉬운 문장·접근성 표준',goal='30종 안내문의 접근성 점검과 부서 승인을 마치고 표준안을 배포한다.',budget=95000000,due='2026-11-12',progress=[10,50,90],statuses=['안내문 현황과 개선 수요 조사 중','30종 중 15종 검토 완료','30종 중 27종 검토 완료; 최종 결재 준비'],done=['안내문 원본 30종 확보','쉬운 문장 개정안 15종 작성','27종 검토 및 접근성 시험 결과 정리'],remain=['30종 개정안 작성과 접근성 시험','15종 검토 및 최종 배포','3종 법무 검토와 표준안 배포 결재'],issue=['용어 통일 기준 협의 필요','법무 검토 회신 5종 대기','법무 검토 회신 3종 미접수'],action='법무담당관에게 3종 검토 회신을 요청하고 배포 결재안을 준비한다.',reason='11월 8일 담당자 인사이동 및 검토 완료 27종을 반영함.'),
 dict(title='2026년 취약계층 돌봄연계 시범사업',team='돌봄연계정책과',owner='돌봄연계정책과 최하린',scope='시범지역 5곳의 돌봄 수요 발굴·기관 연계',goal='시범지역 5곳의 연계 절차를 검증하고 실적 100건을 확보한다.',budget=320000000,due='2026-11-16',progress=[10,35,55],statuses=['시범지역 선정 기준 검토 중','5곳 중 3곳 협약 체결','5곳 협약 체결 및 연계 실적 55건 확인'],done=['시범지역 후보 7곳 조사','3곳 협약 체결 및 실무 교육','5곳 협약 및 개인정보 처리 협의 완료'],remain=['5곳 협약과 실적 확인','2곳 협약 및 100건 실적 확인','추가 45건 연계 및 성과보고서 검토'],issue=['개인정보 제공 동의 문구 미확정','2곳 협약과 동의서 검토 대기','실적 증빙 8건 추가 대조 필요'],action='시범지역 담당자에게 실적 증빙 8건을 보완 요청한다.',reason='5곳 협약 체결 및 증빙 대조가 끝난 55건 실적을 반영함.')]
NAMES=[['최종최종_999.hwpx','복사본(7).xlsx','1234.pdf'],['스캔_0008.pdf','회의메모.hwpx','붙임.xlsx'],['자료.xlsx','tmp_002.pdf','새 문서.hwpx'],['다운로드.hwpx','비용정리.pdf','abc.xlsx']]

def specimen(i,j,state='확정',edge=None):
 p=PROJECTS[i];day='2026-11-02' if j==0 else '2026-11-08' if i==0 else '2026-11-06' if j==1 else '2026-11-08'
 owner='디지털행정지원과 정여울' if i==2 and j==2 else p['owner']
 progress=p['progress'][j];status=p['statuses'][j];revision=j+1
 if state=='초안':day='2026-11-09';progress=100;status='전 지역 실적 목표 달성 및 종료 예정';revision=4
 if edge=='conflict':status='현장 확인이 중단되어 실적 재조사 필요';progress=25
 if edge=='reversed':revision=4
 date_text=lambda v:v.replace('-','. ')+'.'
 meta=[('문서관리번호',f'MB26-{i+1:02d}-RPT'),('사업관리번호',f'MB26-{i+1:02d}'),('내용 기준일',date_text(day) if edge!='undated' else '확인 필요'),('수정차수',f'{revision}차'),('수정일시',date_text(day)+' '+('09:00' if edge=='reversed' else '16:30' if j==2 else '10:00')),('문서상태',state),('보고단계',['계획','착수','중간'][j]+'보고'),('계획 시작일','2026. 11. 1.'),('전체 진행률',str(progress)+'%')]
 lines=[('title',p['title']+' 추진상황 보고'),('small','합성 시연자료 · 실제 부처 보고서 아님 · 연락처 및 기관은 가상'),('small',p['team']+' / '+date_text(day))]
 lines += [('meta',f'○ ({k}) {v}') for k,v in meta]
 def section(title,pairs):
  lines.append(('heading','□ '+title))
  for label,value in pairs:lines.append(('body',f'○ ({label}) {value}'))
 section('사업 개요',[('사업명',p['title']),('추진 배경','지역 현장의 업무 편차를 줄이고 국민에게 일관된 서비스를 제공하기 위한 시범사업이다.'),('사업 범위',p['scope']),('추진 목표',p['goal']),('주관 담당',owner),('완료 기한',p['due'])])
 lines.append(('detail','- 관련 기관의 제출 자료를 담당자가 대조한 후 단계별 실적을 확정한다.'))
 section('추진 계획 및 실적',[('추진 일정','11.1.~11.2. 계획 확정 → 11.3.~11.8. 현장 이행 → '+p['due']+' 결과 보고'),('진척 현황',status),('완료 실적',p['done'][j]),('성과 관리',f'담당자 확인 기준 진행률 {progress}%; 예상 실적은 완료 건수에 포함하지 않는다.'),('수정 사유',p['reason'] if j==2 else '해당 기준일에 접수된 자료와 담당자 확인 결과를 반영함.')])
 lines.append(('detail','- 진행률은 본문 기준일의 담당자 보고 수치이며 기간 경과율과 다르다.'))
 section('현안 및 향후 조치',[('주요 현안',p['issue'][j]),('남은 과업',p['remain'][j]),('우선 조치',p['action'] if j==2 else '미완료 사항을 관련 기관과 협의하고 증빙 제출 일정을 확인한다.'),('추후 계획','11월 10일 보완 요청 → 11월 11일 회신 대조 → 완료 기한 내 결과 보고. 지연 시 과장 보고 후 변경 일정 별도 승인.'),('처리 순서','자료 접수 → 증빙 대조 → 담당 검토 → 과장 결재 → 관련 기관 통보'),('완료 판단','잔여 과업 이행과 증빙 확인 후 결과보고 결재 및 배포까지 마친 경우 완료로 처리한다.')])
 lines.append(('detail','- 미접수·미서명 자료는 완료 실적에서 제외하고 다음 담당자에게 보완 목록을 전달한다.'))
 section('예산 및 업무 인계',[('예산 현황',f'예산코드: MB26-{i+1:02d} | 편성액: {p["budget"]:,}원 | 집행액: {int(p["budget"]*.4):,}원 | 잔액: {int(p["budget"]*.6):,}원'),('협조 부서','기획재정담당관, 법무담당관 및 시범지역 담당부서'),('연락망',owner+' / '+f'070-0000-26{i+1:02d}'+' (가상 연락처)'),('결재 체계','담당자 → 사무관 → 과장; 예산 변경은 기획재정담당관 사전 협의'),('인계 산출물','운영계획, 기관별 실적대장, 보완 요청 목록 및 최종 결과보고'),('자료 위치','기관 내부 업무공유함 / '+f'MB26-{i+1:02d}'+' / 실적·증빙 폴더 (시연용 가상 경로)'),('인수 시 유의','현재 미완료 사항과 승인 기한을 먼저 확인하고 기존 담당자의 구두 설명은 증빙과 대조한다.')])
 return lines,dict(title=p['title'],work_code=f'MB26-{i+1:02d}',reported_at=day,revision_no=revision,progress=progress,status=status,owner=owner,due_date=p['due'],issues=p['issue'][j],next_action=p['action'],remaining_work=p['remain'][j])

def write_file(path,lines,browser):
 if path.suffix=='.hwpx':
  d=HwpxDocument.new()
  styles={k:d.ensure_run_style(font='함초롬바탕',size=size,bold=k in {'title','heading'}) for k,size in [('title',18),('heading',14),('body',12),('detail',11),('meta',10),('small',9)]}
  for kind,text in lines:d.add_paragraph(text,char_pr_id_ref=styles[kind])
  report=d.validate();assert not report.issues,report
  d.save_to_path(path)
  assert not HwpxDocument.open(path).validate().issues
 elif path.suffix=='.xlsx':
  w=Workbook();s=w.active;s.title='추진상황 보고';s.column_dimensions['A'].width=115
  for n,(kind,text) in enumerate(lines,1):
   c=s.cell(n,1,text);c.font=Font(name='맑은 고딕',size=17 if kind=='title' else 13 if kind=='heading' else 11,bold=kind in {'title','heading'},color='203D51')
   c.alignment=Alignment(wrap_text=True,vertical='center');s.row_dimensions[n].height=40 if len(text)>72 else 27
   if kind=='heading':c.fill=PatternFill('solid',fgColor='E8EFF4')
  s.freeze_panes='A14';s.sheet_properties.pageSetUpPr.fitToPage=True;s.page_setup.orientation='portrait';s.page_setup.paperSize=s.PAPERSIZE_A4;s.page_setup.fitToWidth=1;s.page_setup.fitToHeight=0;s.print_options.horizontalCentered=True;s.print_area=f'A1:A{len(lines)}';w.save(path)
 else:
  page=browser.new_page();page.set_content('<html lang="ko"><meta charset="utf-8"><style>@page{size:A4;margin:17mm}body{font:11pt/1.6 "Noto Serif CJK KR";color:#152c3d}p{margin:5px 0;break-inside:avoid}.title{font-size:18pt;text-align:center;font-weight:bold;border-bottom:2px solid;padding-bottom:12px}.heading{font-size:14pt;font-weight:bold;margin-top:18px;break-after:avoid}.small,.meta{font-size:9pt}.detail{padding-left:16px;font-size:10pt}</style><body>'+''.join(f'<p class="{k}">{html.escape(t)}</p>' for k,t in lines)+'</body></html>');page.evaluate('document.fonts.ready');page.pdf(path=str(path),print_background=True,prefer_css_page_size=True);page.close()


def archive(name,entries,renamed=False):
 with zipfile.ZipFile(OUT/name,'w',zipfile.ZIP_DEFLATED) as z:
  for n,(path,meta) in enumerate(reversed(entries) if renamed else entries):
   filename=f'{999-n:04d}_무관한파일'+path.suffix if renamed else path.name
   # The oldest report deliberately has the latest ZIP timestamp.
   info=zipfile.ZipInfo(filename,(2026,11,9 if meta['revision_no']==1 else 2,9,0,0));info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,path.read_bytes())


def main():
 entries=[];expected=[];negative=[]
 with sync_playwright() as p:
  browser=p.chromium.launch(headless=True,args=['--no-sandbox'])
  for i in range(4):
   for j in range(3):
    lines,meta=specimen(i,j);path=WORK/NAMES[i][j];write_file(path,lines,browser);meta.update(file=path.name,sha256=hashlib.sha256(path.read_bytes()).hexdigest());entries.append((path,meta))
    if j==2:expected.append(meta)
  lines,meta=specimen(3,2,'초안');path=WORK/'제출용_진짜최종.pdf';write_file(path,lines,browser);meta.update(file=path.name,sha256=hashlib.sha256(path.read_bytes()).hexdigest());entries.append((path,meta))
  for edge in ['conflict','undated','reversed']:
   lines,meta=specimen(0,2,edge=edge);path=WORK/('확인필요_'+edge+'.hwpx');write_file(path,lines,browser);meta.update(file=path.name);negative.append((path,meta))
  browser.close()
 archive('version-samples.zip',entries);archive('version-samples-shuffled.zip',entries,True)
 for i,edge in enumerate(['conflict','undated','reversed']):archive('version-edge-'+edge+'.zip',[entries[2],negative[i]])
 (OUT/'version-expected.json').write_text(json.dumps({'synthetic_only':True,'expected_works':expected,'excluded_draft':entries[-1][1],'inputs':[m for _,m in entries],'negative_cases':{'conflict':'동일 기준일·수정차수·수정일시에서 내용 상충 → 자동 선택 보류','undated':'내용 기준일 불명확 → 자동 선택 보류','reversed':'차수는 높지만 수정일시는 이전 → 자동 선택 보류'}},ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'reports':len(entries),'hwpx':sum(p.suffix=='.hwpx' for p,_ in entries),'xlsx':sum(p.suffix=='.xlsx' for p,_ in entries),'pdf':sum(p.suffix=='.pdf' for p,_ in entries),'negative_reports':len(negative)},ensure_ascii=False))
if __name__=='__main__':main()
