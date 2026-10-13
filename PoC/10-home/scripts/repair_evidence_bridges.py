"""Capture checked A31 official documents and persist review-only source links."""
import argparse,hashlib,io,json
from pathlib import Path
from urllib.parse import quote
from html import escape
import httpx
from bs4 import BeautifulSoup
from pypdf import PdfReader
from backend.db import engine_for,upsert_revision,Audit
from backend.service import HomeService
from backend.evidence_bridge import reconcile
from backend.api_samples import today

LH='https://www.lh.or.kr/board.es?mid=a10601020000&bid=0034&list_no=720881&act=view'
ANYANG='https://www.anyang.go.kr/manan/selectBbsNttView.do?bbsNo=157&key=3315&nttNo=446074'
PDF='https://www.molit.go.kr/LCMS/DWN.jsp?fold=/N01_B/&fileName='+quote('변경승인_고시문(평택고덕_A-31BL).pdf')


def capture(service,snapshot_dir=None):
    root=service.data_dir/'raw'/'official_document';root.mkdir(parents=True,exist_ok=True)
    documents=[]
    specs=[('lh-a31-business',LH,['A-31BL','2024-09-05'],[
        dict(stage='BUSINESS',kind='STATE',date='2024-09-05',basis='LH 민간참여사업 우선협상대상자 공고 · 최초 사업화일 아님')]),
        ('anyang-a31-schedule',ANYANG,['A31BL','690','2029년 7월','2026.06.25'],[
        dict(stage='SUPPLY',kind='PLAN',date='2026-06-25',milestone='SUPPLY',basis='지자체 특별공급 안내의 모집공고 예정일 · 실제 공고 확인 아님'),
        dict(stage='MOVE_IN',kind='PLAN',date='2029-07',milestone='MOVE_IN',basis='지자체 특별공급 안내의 입주 예정월 · 실제 입주 아님')]),
        ('molit-a31-change-draft',PDF,['A-31BL','690','2025-000'],[
        dict(stage='APPROVAL',kind='DOCUMENT',date=None,date_label='고시번호·승인일 미확정',basis='국토부 사업계획 변경승인 첨부문서 확보 · 제2025-000호/일자 공란 · 최종 고시 검증 필요')])]
    with httpx.Client(timeout=40,follow_redirects=True) as client:
        for key,url,terms,facts in specs:
            if snapshot_dir:
                manifest=json.loads((Path(snapshot_dir)/'manifest.json').read_text())[key]
                body=(Path(snapshot_dir)/key).read_bytes()
                if manifest['url']!=url or manifest['sha256']!=hashlib.sha256(body).hexdigest():raise ValueError('원문 URL/해시 불일치')
            else:
                response=client.get(url);response.raise_for_status();body=response.content
            is_pdf=body.startswith(b'%PDF')
            text=' '.join(p.extract_text() for p in PdfReader(io.BytesIO(body)).pages) if is_pdf else BeautifulSoup(body.decode('utf-8'),'html.parser').get_text(' ',strip=True)
            if not all(t in text for t in terms):raise ValueError('공식 원문 검증 실패: '+key)
            digest=hashlib.sha256(body).hexdigest();file=root/(digest+('.pdf' if is_pdf else '.html'));file.write_bytes(body)
            payload=dict(name='평택고덕 A31 · '+{'lh-a31-business':'LH 우선협상대상자 공고','anyang-a31-schedule':'기관추천 특별공급 안내','molit-a31-change-draft':'사업계획 변경승인 첨부문서'}[key],
                sample_kind='document_evidence',region='경기도',municipality='평택시',district='평택고덕',block='A31',
                planned_units=690,unit_basis='A31 사업범위 대조용 690호 · 별도 공급량 합산 금지',
                facts=facts,evidence_url=url,original_sha256=digest,original_file=str(file.relative_to(service.data_dir)),
                base_date=today().isoformat(),date_precision='COLLECTION',verification_status='FILE_CAPTURED_EVENT_UNVERIFIED' if is_pdf else 'SOURCE_CONTENT_CHECKED')
            with service.sessions.begin() as db:
                row,outcome=upsert_revision(db,'document_evidence','official_document',key,payload,'official_document_capture')
                if outcome!='unchanged':db.add(Audit(entity_id=row.entity_id,action='OFFICIAL_DOCUMENT_CAPTURE',before={},after=payload))
            documents.append(dict(id=row.entity_id,sha256=digest,url=url,file=str(file)))
    return documents


def report_html(result):
    esc=lambda x:escape(str(x if x is not None else '미확인'))
    rows=''.join('<tr><td>'+esc(p['name'])+'</td><td>'+esc(p['source_name'])+'</td><td>'+esc(', '.join(sorted({f['stage'] for f in p['facts']})))+'</td><td>'+esc(p['basis'])+'</td></tr>' for p in result['proposals'])
    held=''.join('<tr><td>'+esc(p['name'])+'</td><td>'+esc(p['source_name'])+'</td><td>'+esc(p['reason'])+'</td><td>'+esc(p.get('project_units'))+' / '+esc(p.get('source_units'))+'</td></tr>' for p in result['held'])
    return '<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>사업 원천 연결 정비 기록</title><link rel="stylesheet" href="/poc/home/assets/evidence-repair-report.css"><main><a href="/poc/home/#project-collection">← 사업별 수집·연계</a><h1>사업 원천 연결 정비 기록</h1><p>'+esc(result['as_of_date'])+' · 저장된 '+str(result['project_records'])+'개 사업 기록 점검</p><section><h2>이번에 반영한 내용</h2><p>'+str(result['added_links'])+'개 연결 · '+str(result['affected_projects'])+'개 사업 기록. 연결 건수는 고유 사업 수나 공급 호수가 아닙니다.</p><p>서로 다른 원천의 지역·지구·사업명 블록·총세대수가 일치하면 검토 후보로 DB에 저장했습니다. 원천 원본과 판본을 보존하며 화면 조회 시 재매칭하지 않습니다.</p><p>자료 수집 완료 시 새 연결만 추가합니다. 담당자 확정·해제와 기존 고정 판본은 유지합니다. 새 판본은 검토 후 반영해야 합니다.</p></section><section><h2>평택고덕 A31</h2><ul><li>LH 공급계획과 건설현황의 A31 / Ab31 표기 차이: 제목의 A-31BL 및 690호 일치로 검토 연결. 원천 블록 값은 보존.</li><li>사업화: 2024-09-05 LH 우선협상대상자 공고. 최초 사업화일을 의미하지 않음.</li><li>인허가: 국토부 PDF 원문 확보. 제2025-000호 및 일자 공란이므로 최종 고시·승인일 확인 필요. 확정 허가 실적 반영 없음.</li><li>입주 예정: 지자체 안내의 2029-07. 공급 예정: 같은 안내의 2026-06-25. 기존 LH 2026-05 공급계획과 함께 이력 근거로 표시. 실제 공고·입주 확인 필요.</li></ul><p><a href="'+esc(LH)+'">LH 공고</a> · <a href="'+esc(ANYANG)+'">지자체 안내</a> · <a href="'+esc(PDF)+'">국토부 첨부문서</a></p></section><section><h2>조회·검토 방법</h2><p>데이터 현황 → 사업별 수집·연계에서 사업 검색 → 단계 칸 선택 → 추가 연결 근거에서 원문·판본·매칭 사유 조회. 관리자로 로그인하면 검토 후보/확정/연결 해제 및 사유를 저장할 수 있습니다.</p><p>이번 반영 범위는 수집·연계 표와 다이어그램의 근거 보완입니다. 정책·지도 총량의 사업 통합이나 목표값 우선순위를 자동 변경하지 않습니다. 서로 다른 일정은 최종 원문 확인 후 담당자가 목표 편집에서 선택해야 합니다.</p></section><section><h2>추가 연결 목록</h2><div class="scroll"><table><tr><th>대상 사업</th><th>추가 원천</th><th>단계</th><th>이유</th></tr>'+rows+'</table></div></section><section><h2>보류·추가 확인 목록</h2><p>세대수 차이는 오류라고 단정할 수 없습니다. 부분 분양·임대, 복합시설 또는 계약 범위를 확인해야 합니다. 다중 블록·브랜드명만 일치하는 자료는 자동 연결하지 않습니다.</p><div class="scroll"><table><tr><th>대상 사업</th><th>원천</th><th>보류 이유</th><th>사업/원천 호수</th></tr>'+held+'</table></div></section><section><h2>남은 수집 과제</h2><p>국토부·지자체 고시 전수 수집 및 최종 고시번호 검증, 브랜드명·블록 별칭 관리, 부분 공급량 관계 검토, 최신 본 모집공고와 실제 입주 근거 확보. 이번 공식 문서 수집은 확인한 A31 자료 3건이며 전국 고시 전수 수집이 아닙니다.</p></section></main></html>'


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');parser.add_argument('--capture-documents',action='store_true');parser.add_argument('--snapshot-dir');parser.add_argument('--output',default='/tmp/home-evidence-repair.json');args=parser.parse_args()
    service=HomeService(engine_for(),'/app/data')
    documents=capture(service,args.snapshot_dir) if args.apply and args.capture_documents else []
    result=reconcile(service,apply=args.apply);result['captured_documents']=documents
    Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2));Path(args.output+'.html').write_text(report_html(result))
    print(json.dumps({k:v for k,v in result.items() if k not in ('proposals','held','captured_documents')},ensure_ascii=False));print('held',len(result['held']))
