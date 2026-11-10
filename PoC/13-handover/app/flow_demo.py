"""Eleven synthetic stage reports; three exact work links and one human-owned link."""
import io
import zipfile

WORKS = [
 {'title':'생활문화 공모사업 추진','owner':'문화기획팀','start':'2026-10-15','due':'2026-11-12','reports':[
 ('계획','2026-10-15',10,'추진계획 수립','사업 범위와 심사 기준 초안 작성','공고 후 신청 접수와 심사','없음','공고문 검토 요청'),
 ('착수','2026-10-26',35,'공고 및 신청 접수 중','공고 게시와 설명회 개최','접수 마감과 심사위원 확정','심사위원 1명 섭외 대기','심사위원 참석 여부 확인'),
 ('중간','2026-11-08',65,'신청 검토 및 심사 준비','신청 20건 접수와 자격 검토 완료','11월 12일 심사 개최와 선정 결과 결재','심사자료 2건 보완 미접수','11월 10일까지 보완자료 요청 후 심사자료 배포')]},
 {'title':'보조금 정산 승인','owner':'사업지원팀','start':'2026-10-20','due':'2026-11-06','reports':[
 ('계획','2026-10-20',0,'정산 검토 계획 수립','제출 목록과 검토 기준 작성','증빙 접수와 적정성 검토 후 승인','없음','단체별 정산자료 제출 안내'),
 ('착수','2026-10-28',20,'정산서 접수 중','10개 단체 중 6개 단체 정산서 접수','나머지 자료 접수와 증빙 대조','4개 단체 자료 미접수','미제출 단체에 제출 독려'),
 ('중간','2026-11-08',40,'증빙 보완 대기로 승인 지연','10개 단체 정산서 접수 및 4개 단체 검토 완료','누락 증빙 보완 후 6개 단체 검토와 승인','2개 단체 영수증 누락으로 11월 6일 승인 기한 경과','누락 영수증을 즉시 요청하고 승인 일정 재협의')]},
 {'title':'문화시설 안전점검','owner':'시설운영팀','start':'2026-10-12','due':'2026-11-07','completed':'2026-11-05','reports':[
 ('계획','2026-10-12',10,'점검 계획 수립','대상 시설과 점검표 확정','현장 점검과 보수 후 최종 확인','없음','시설별 점검 일정 공지'),
 ('착수','2026-10-25',70,'현장 점검 후 보수 중','시설 5곳 점검 및 보수 8건 중 6건 처리','유도등 2개 교체 후 재점검','지하 비상구 유도등 2개 고장','보수업체에 교체 일정 확인'),
 ('완료','2026-11-05',100,'업무 완료','유도등 교체와 재점검 및 최종 결과 결재 완료','없음','해소 완료: 유도등 2개 교체 확인','점검 결과서를 보관하고 다음 정기 점검 때 참고')]},
 {'title':'문화시설 통합예약 개선','owner':'디지털지원팀','start':'2026-10-22','due':'2026-11-24','reports':[
 ('계획','2026-10-22',20,'요구사항 분석 완료','요구사항 12건 정리와 화면 초안 작성','개발과 접근성 점검 후 운영 반영','없음','개발사와 구현 범위 확정'),
 ('중간','2026-11-08',75,'사용자 시험 중','예약 화면 개발과 기능 시험 완료','접근성 오류 수정 후 운영 반영','키보드 탐색 오류 2건 미해결','개발사에 오류 재현 절차 전달 후 재시험')]}]

def flow_archive():
 from docx import Document
 from openpyxl import Workbook
 from reportlab.pdfbase import pdfmetrics
 from reportlab.pdfbase.cidfonts import UnicodeCIDFont
 from reportlab.pdfgen import canvas
 files={}
 for wi,w in enumerate(WORKS,1):
  for si,(stage,reported,pct,status,done,left,issue,action) in enumerate(w['reports'],1):
   alias=wi==4 and si==2
   title='예약포털 접근성 보완' if alias else w['title']
   metadata=['합성자료 · 가상 한빛시 · 실제 업무자료 아님',f'연계관리번호: HB-{wi:03d}',f'보고일: {reported}',f'보고단계: {stage}',f'계획 시작일: {w["start"]}',f'전체 진행률: {pct}%']
   if stage=='완료':metadata.append(f'실제 완료일: {w["completed"]}')
   lines=metadata+[f'업무: {title}',f'담당: {"미정" if alias else w["owner"]}',f'상태: {status}',f'기한: {w["due"]}',f'완료한 일: {done}',f'남은 업무: {left}',f'현안: {issue}',f'다음 행동: {action}', '협의 부서: 행정지원팀',f'연락처: work{wi}@example.invalid', '참고: '+('담당 부서는 전임자 확인 필요. 계획보고의 연계관리번호와 비교 후 동일 업무인지 확인.' if alias else '이 보고의 진행률은 전체 업무 기준이며 보고일 현재 상태를 기록함.')]
   ext=['docx','xlsx','pdf'][si-1] if wi<4 else ('docx' if si==1 else 'txt')
   name=f'{wi:02d}_{si:02d}_{title}_{stage}보고.{ext}'
   b=io.BytesIO()
   if ext=='docx':
    doc=Document();doc.add_heading(title+' '+stage+'보고',0)
    for line in lines:doc.add_paragraph(line)
    doc.save(b)
   elif ext=='xlsx':
    wb=Workbook();ws=wb.active;ws.title='보고사항';ws.column_dimensions['A'].width=100
    for line in lines:ws.append([line])
    ws.freeze_panes='A8';wb.save(b)
   elif ext=='pdf':
    pdfmetrics.registerFont(UnicodeCIDFont('HYSMyeongJo-Medium'))
    pdf=canvas.Canvas(b,invariant=1);pdf.setFont('HYSMyeongJo-Medium',10)
    for n,line in enumerate(lines):pdf.drawString(35,800-29*n,line)
    pdf.save()
   else:b.write(('\n'.join(lines)+'\n').encode())
   files[name]=b.getvalue()
 b=io.BytesIO()
 with zipfile.ZipFile(b,'w',zipfile.ZIP_DEFLATED) as z:
  for name,raw in files.items():
   info=zipfile.ZipInfo(name,(2026,11,9,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,raw)
 return b.getvalue()
