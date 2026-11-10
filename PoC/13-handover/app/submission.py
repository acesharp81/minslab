"""Public synthetic demonstration material; never exports a user's workspace."""
import io
import zipfile
from xml.etree import ElementTree
from .demo import demo_archive

SAMPLE_VERSION = 'submission-1'

def submission_archive():
    from docx import Document
    from openpyxl import Workbook
    with zipfile.ZipFile(io.BytesIO(demo_archive())) as z:
        files = {n: z.read(n) for n in z.namelist()}
    # Use a real editable DOCX for the participant pack, rather than a minimal parser HWPX fixture.
    with zipfile.ZipFile(io.BytesIO(files.pop('01_사업현황.hwpx'))) as z:
        section = ElementTree.fromstring(z.read('Contents/section0.xml'))
    document = Document()
    document.add_heading('문화기획 업무 현황 및 인계 사항', 0)
    for p in section:
        document.add_paragraph(''.join(p.itertext()))
    b = io.BytesIO(); document.save(b); files['01_사업현황.docx'] = b.getvalue()
    files['06_계약담당_전달메모.txt'] = '''합성자료 · 가상 한빛시 계약담당 전달 메모
홍보물 제작 계약은 홍보지원팀이 담당하며, 디자인 시안 검토 단계에 있다.
완료한 일은 과업지시서 작성과 견적서 3건 접수이다.
남은 업무는 시안 확정 후 계약 체결이다. 현안은 저작권 사용 동의서 미접수이다.
기한은 2026-12-04이다. 후임자는 제작사에 저작권 사용 동의서를 요청한다.
협의 부서는 계약심사팀이며, 연락처는 publicity@example.invalid이다.
계약심사팀은 협의 부서이고 업무 담당 부서가 아니다. 예산 집행과 계약 체결은 아직 완료되지 않았다.
'''.encode()
    wb = Workbook(); ws = wb.active; ws.title = '담당업무'
    ws.append(['합성자료 · 가상 한빛시']); ws.append(['업무명','담당 부서','상태','기한','완료한 일','남은 업무','현안','다음 행동','협의 부서','연락처'])
    ws.append(['문화시설 예약 시스템 개선','디지털지원팀','사용자 시험 중','2026-12-14','요구사항 12건 정리 및 화면 초안 완성','접근성 점검 후 운영 반영','키보드 탐색 오류 2건 미해결','개발사에 오류 재현 절차 전달','시설운영팀','digital@example.invalid'])
    for col in ws.columns: ws.column_dimensions[col[0].column_letter].width = 26
    ws.freeze_panes='A3'; b=io.BytesIO();wb.save(b);files['07_시스템개선_업무표.xlsx']=b.getvalue()
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w',zipfile.ZIP_DEFLATED) as z:
        for name, raw in sorted(files.items()):
            info=zipfile.ZipInfo(name,(2026,11,9,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,raw)
    return b.getvalue()
