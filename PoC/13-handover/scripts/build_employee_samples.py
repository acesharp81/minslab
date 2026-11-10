"""Reproducible ring-persona sample kit: same names, reverse upload, latest-only images."""
import io,json,zipfile,sys
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
from hwpx import HwpxDocument
from openpyxl import Workbook
from openpyxl.styles import Font,Alignment,PatternFill
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'release/public';WORK=ROOT/'test-results/employee-materials';WORK.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(ROOT))
from app.engine import FIELDS
FONT='/usr/share/fonts/truetype/nanum/NanumGothic.ttf'
if not Path(FONT).exists():FONT='/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'

def picture(text):
 im=Image.new('RGB',(1100,530),'#f5f8f3');d=ImageDraw.Draw(im);f=ImageFont.truetype(FONT,36);d.rectangle((20,20,1080,510),outline='#366849',width=3)
 for i,line in enumerate(text.split('\n')):d.text((55,55+i*90),line,font=f,fill='#163b2a')
 o=io.BytesIO();im.save(o,format='PNG');return o.getvalue()

TITLES=['지역생활서비스 통합지원','공공시설 안전관리','디지털 민원안내 표준화','취약계층 돌봄연계']
PROGRESS=[65,70,90,55]
def lines(i,version):
 latest=version=='latest';draft=version=='draft';day='2026-11-09' if draft else '2026-11-08' if latest else '2026-11-02';pct=100 if draft else PROGRESS[i-1] if latest else 20
 fields={'title':TITLES[i-1],'owner':f'직원 {i}','status':f'{pct}% 진행 중' if not draft else '완료 예정 (미승인 초안)','due_date':['2026-11-13','2026-11-06','2026-11-12','2026-11-16'][i-1],
 'overview':'관계기관의 현장 업무 절차를 정비하고 원본 증빙에 따라 사업 실적을 확정하는 업무입니다.',
 'objectives':'계획된 현장 과업을 완료하고 증빙 대조·담당 검토·결재까지 마무리합니다.',
 'scope':f'2026년 {TITLES[i-1]} 사업의 계획 수립부터 결과 보고까지',
 'implementation_plan':'11월 1~2일 | 계획 확정 | 운영계획\n11월 3~8일 | 현장 이행·점검 | 실적표\n11월 10~13일 | 증빙 보완·결재 | 결과보고',
 'completed_work':['협약 원본 5건 확인 및 운영 매뉴얼 초안 작성','20개 시설 중 14개 점검표 접수','안내문 30종 중 27종 검토','5개 지역 협약 및 실적 55건 대조'][i-1] if latest else '기초 대상 목록 정리',
 'remaining_work':['잔여 3개 기관 협약과 담당자 교육','6개 시설 추가 점검 및 위험시설 3곳 조치','3종 법무 검토 및 표준안 배포 결재','추가 45건 연계 및 성과보고 검토'][i-1],
 'issues':['협약 원본 3건 미접수','11월 6일 승인 기한 경과; 위험시설 3곳 조치 미완료','법무 검토 3종 회신 미접수','실적 증빙 8건 추가 확인 필요'][i-1],
 'next_action':'미접수 증빙을 요청하고 담당 부서와 회신 기한을 확인합니다.',
 'future_plan':f'즉시 | 직원 {i} | 보완 요청 | 요청 기록 | 원문 조치\n2026-11-11 | 직원 {i} | 회신 대조 | 대조표 | 잠정 계획',
 'operating_steps':'자료 접수 → 증빙 대조 → 담당 검토 → 과장 결재 → 결과 통보',
 'completion_criteria':'증빙이 확보되고 담당 검토 및 결과보고 결재가 끝난 경우 완료합니다.',
 'deliverables':'운영계획, 실적표, 미완료 목록, 결과보고',
 'performance':f'본문 기준일 현재 진행률 {pct}%; 예상 실적은 제외',
 'issue_history':'계획 단계의 수요 확인 후 현재 미접수 증빙을 보완 중',
 'approval_route':'담당자 → 팀장 → 과장',
 'document_locations':f'가상 업무공유함 / RING-{i} / 원본·실적',
 'collaborators':'가상 기획재정팀, 법무팀',
 'budget':f'예산코드: RING-B{i} | 명칭: {TITLES[i-1]} | 편성액: 100,000,000원 | 집행액: 40,000,000원 | 지급예정액: 10,000,000원 | 가용잔액: 50,000,000원 | 기준일: {day} | 범위: 2026년 사업',
 'contacts':f'관계자ID: RING-P{i} | 성명: 직원 {i} | 소속: 가상 사업팀 | 역할: 사업 담당 | 연락: 070-0000-100{i} | 협의사항: 증빙 보완',
 'notes':'합성 시연자료이며 실제 기관·개인·전화번호가 아닙니다.'}
 rows=[TITLES[i-1]+' 추진상황 보고','합성 시연자료 · 직원 순환 체험','□ 판본 정보',f'보고일: {day}',f'문서관리번호: RING-{i}-RPT',f'사업관리번호: RING-{i}',f'수정차수: {4 if draft else 3 if latest else 1}차',f'수정일시: {day} 16:30',f'문서상태: {"초안" if draft else "확정"}','보고단계: 중간보고' if latest else '보고단계: 계획보고','계획 시작일: 2026-11-01',f'전체 진행률: {pct}%','□ 사업 개요와 추진 현황']
 # Clear labels plus ○ paragraphs retain the genuine outline while remaining inspectable offline.
 for key,value in fields.items():rows.append('○ ('+FIELDS[key]+') '+value)
 rows+=['- 실적은 원본 증빙을 대조하여 확정하며 미승인 초안은 실적으로 채택하지 않습니다.']
 return rows

def write(path,rows,pic=None):
 if path.suffix=='.hwpx':
  d=HwpxDocument.new();style=d.ensure_run_style(font='함초롬바탕',size=11)
  for row in rows:d.add_paragraph(row,char_pr_id_ref=style)
  if pic:d.add_picture(pic,'png',width_mm=160,height_mm=77)
  d.save_to_path(path);assert not HwpxDocument.open(path).validate().issues
 elif path.suffix=='.xlsx':
  w=Workbook();s=w.active;s.title='추진상황';s.column_dimensions['A'].width=105
  for n,row in enumerate(rows,1):c=s.cell(n,1,row);c.font=Font(name='맑은 고딕',size=11,bold=row.startswith('□'));c.alignment=Alignment(wrap_text=True);s.row_dimensions[n].height=max(28,25*(1+len(row)//65))
  s.freeze_panes='A14';w.save(path)
 else:
  import html
  from playwright.sync_api import sync_playwright
  with sync_playwright() as pw:
   browser=pw.chromium.launch(headless=True,args=['--no-sandbox']);page=browser.new_page()
   page.set_content('<html lang="ko"><meta charset="utf-8"><style>@page{size:A4;margin:18mm}body{font:11pt/1.7 "Noto Sans CJK KR"}p{white-space:pre-wrap;break-inside:avoid}</style>'+''.join('<p>'+html.escape(row)+'</p>' for row in rows))
   page.evaluate('document.fonts.ready');page.pdf(path=str(path),prefer_css_page_size=True);browser.close()

def main():
 stages={'01_최신본_먼저등록.zip':'latest','02_구판_나중등록.zip':'old','03_미승인초안_마지막등록.zip':'draft'};expected=[]
 for zipname,version in stages.items():
  with zipfile.ZipFile(OUT/zipname,'w',zipfile.ZIP_DEFLATED) as z:
   for i,ext in enumerate(['.hwpx','.xlsx','.pdf','.hwpx'],1):
    path=WORK/(f'{version}-{i}'+ext)
    pic=picture('협약 원본 확인\n확인 완료: 5건\n미서명: 1건\n추가 요청: 3건' if version=='latest' else '구판 그림 · 전송 제외\n이전 집계: 2건' if version=='old' else '초안 그림 · 전송 제외\n예상 실적: 100%') if i==1 else None
    write(path,lines(i,version),pic);z.writestr(f'직원{i}/보고서'+ext,path.read_bytes())
 for i,pct in enumerate(PROGRESS,1):expected.append({'employee':i,'recipient':i%4+1,'title':TITLES[i-1],'progress':pct,'selected_version':3,'reported_at':'2026-11-08'})
 (OUT/'employee-expected.json').write_text(json.dumps({'expected':expected,'latest_images':1,'excluded_images':2,'active_cases':4,'completed_cases':2},ensure_ascii=False,indent=2))
 guide='''# 직원 순환·동일 파일명·그림 후처리 체험

1. 앱 오른쪽 위에서 직원 1을 선택합니다. 홈의 ‘직원 1→2→3→4 순환 체험’을 누르면 4개 진행 건과 2개 완료 이력이 준비됩니다. 재클릭해도 중복 생성하지 않습니다.
2. 직원 1은 직원 4에게 받을 인수함과 직원 2에게 보낼 인계함을 봅니다. 다른 직원으로 바꿔 각각의 화면과 완료 목록 확장을 확인합니다.
3. 직접 시험하려면 새 인수인계함을 만들고 아래 ZIP 세 개를 순서대로, 같은 인수인계함에 각각 업로드합니다. **이 전체 묶음 ZIP 자체를 업무자료로 올리지 마세요.**
   - 01_최신본_먼저등록.zip: 11월 8일, 3차 확정본
   - 02_구판_나중등록.zip: 같은 경로·파일명, 11월 2일 1차 구판
   - 03_미승인초안_마지막등록.zip: 같은 경로·파일명, 11월 9일 4차 미승인 초안
4. 초안 생성에서 로컬 규칙 또는 Solar를 선택합니다. 최신본 그림 후처리 체크박스에 동의하면 최신 HWPX의 그림 하나만 GPT-5.4로 보냅니다. 구판과 초안 그림 2개는 전송하지 않습니다. 같은 그림은 저장 결과를 재사용합니다.
5. 12개 원문 판본이 보존되고 4개 업무의 진행률은 **65%, 70%, 90%, 55%**여야 합니다. 파일명이 모두 ‘보고서’여도 제목은 본문 사업명으로 나옵니다.
6. 판본 비교에서 3차를 현재 기준본, 1차를 이전 기록, 4차를 제외 초안으로 확인하세요. 그림 참고에는 ‘확인 완료 5건 / 미서명 1건 / 추가 요청 3건’이 보여야 합니다.
7. 원문을 확인하고 확정한 뒤 인수 직원으로 전환합니다. 같은 최종 보고서를 읽고 인수 확인하면 완료 목록으로 이동합니다.

별도 업무 묶기 시험: grouping-samples.zip을 새 인수인계함에 등록하고 로컬 초안을 생성합니다. 자동 매칭 1개와 별도 후보 4개가 표시됩니다. GROUP-B 3개 후보를 끌어 하나로 묶으면 전체 3개 업무가 됩니다.

이 자료는 중앙부처 개조식 양식을 참고해 만든 합성 HWPX·XLSX·PDF입니다. 완료 이력은 인수인계 절차 완료이며 사업 100% 완료를 뜻하지 않습니다. 자동 시연함은 비용 없는 로컬 라벨 추출로 준비되며, 그림 후처리는 사용자가 별도로 실행합니다.
'''
 (OUT/'employee-guide.md').write_text(guide)
 with zipfile.ZipFile(OUT/'employee-kit.zip','w',zipfile.ZIP_DEFLATED) as z:
  for name in [*stages,'employee-expected.json','grouping-samples.zip']:z.write(OUT/name,name)
  z.writestr('시작하기.md',guide)
 print('employee-kit.zip: 12 versions / 4 works / latest-only image sample')
if __name__=='__main__':main()
