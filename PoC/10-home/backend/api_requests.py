"""Reviewed acquisition backlog and officer request tracking; never submits externally."""
from sqlalchemy import select
from .db import Revision, Audit, entity_id, upsert_revision
from .api_samples import today

PROVIDE_URL='https://www.data.go.kr/tcs/dor/insertDataOfferReqstProcssView.do'
CATALOG=[
 dict(id='building_hub',name='건축HUB 주택인허가',org='국토교통부',requirements=['F-03','F-06','F-10'],mode='API',url='https://www.data.go.kr/data/15136560/openapi.do',priority='우선',fields='mgmHsrgstPk, 법정동·지번, 최초/변경 허가일, 착공일, 대상 호수',keys='원천 PK + 사업·블록·PNU 대응',limitation='공통 사업 ID는 별도 대응 필요. 오래된 PK와 건축HUB PK 전환을 검증.',steps='기존 키의 서비스 승인과 월별 갱신·전체 법정동 조회를 확인하고, 호출량 부족 시 운영 트래픽 증설 신청.'),
 dict(id='building_register',name='건축HUB 건축물대장',org='국토교통부',requirements=['F-03','F-06'],mode='API',url='https://www.data.go.kr/data/15134735/openapi.do',priority='우선',fields='mgmBldrgstPk, 총괄/동별 대장, 사용승인일, 세대수, 부속지번',keys='대장 PK ↔ 허가 PK ↔ 사업·동',limitation='사용승인은 실제 입주 세대수가 아님.',steps='활용신청 후 표제부·총괄표제부·부속지번의 관계 및 기존 PK 전환표 확인.'),
 dict(id='lh_notice',name='LH 분양·임대 공고',org='한국토지주택공사',requirements=['F-05','F-09'],mode='API',url='https://www.data.go.kr/data/15058530/openapi.do',priority='우선',fields='공고 ID·유형·지역, 공고일, 대상 호수, 입주 예정월, 정정·취소 계보',keys='PAN_ID + 유형·지역 등 복합키 / 사업·임대유형 범위',limitation='목록에 없는 상세·첨부 일정은 별도 수집. 예정월은 실입주 아님.',steps='기존 연계의 유형39·지역28·상세 수집을 유지하고 누락 첨부 및 정정공고 관계 요청.'),
 dict(id='cheongyak',name='청약홈 분양정보',org='한국부동산원',requirements=['F-05','F-09'],mode='API',url='https://www.data.go.kr/data/15098547/openapi.do',priority='우선',fields='주택관리번호·공고번호, 모집·계약 일정, 공급호수, 입주 예정월, 잔여/추가공고',keys='HOUSE_MANAGE_NO + PBLANC_NO',limitation='공고 건수와 호수 구분. 정책 귀속·인허가 대응은 별도.',steps='개발 활용신청 → 테스트 → 운영계정 심의. 동일 공고의 정정·추가 공급 중복 제외.'),
 dict(id='kapt_basic',name='공동주택 기본정보(K-apt)',org='국토교통부',requirements=['F-04','F-10'],mode='API',url='https://www.data.go.kr/data/15058453/openapi.do',priority='보완',fields='단지 식별정보, 주소·세대수·동수, 관리 및 주변시설 정보',keys='단지 코드 ↔ 건축물대장·기관 사업 대응',limitation='현재 수집기 미구현. 준공·입지 교차 확인용이며 실입주·공가 전수 API로 간주하지 않음.',steps='활용신청 후 단지 식별 필드·주소·세대 범위 확인, 건축물대장 대응 검증 뒤 연계.'),
 dict(id='ih_supply',name='iH 임대 공급대상·실적',org='인천도시공사',requirements=['F-08','F-11'],mode='API',url='https://www.data.go.kr/data/15168460/openapi.do',priority='우선',fields='사업·주택유형·기준월·공급/계약 정보, 응답 내 주거/상가 구분',keys='기관 사업·단지 식별자 + 주택유형 + 기준월',limitation='기존 파서의 재고·계약·공가 구조와 최신 기술문서 차이를 먼저 검증. 계약을 실거주로 대체하지 않음.',steps='서비스 승인·응답 점검 및 최신 기술문서 대조 후 필요한 주거 집계만 연계.'),
 dict(id='unsold_statistics',name='미분양·준공 후 미분양 월별 통계',org='국토교통부·지자체',requirements=['F-09','F-11'],mode='PUBLIC_API',url='https://stat.molit.go.kr/portal/api/info.do',priority='우선',fields='통계 기준월, 시도·시군구, 전체 미분양, 준공 후 미분양, 전월값, 공표일·정정판',keys='지역코드 + 기준월 + 지표 + 원천 판본',limitation='준공 후는 전체 미분양의 일부. 지역 통계를 개별 사업 미분양으로 기입하지 않음. 실제 입주 여부와도 다름.',steps='통계누리 2082(시군구)·5328(공사완료후)의 공개 양식 확인 및 API 조회. API 미제공 시 공식 파일 원문 검증.'),
 dict(id='gg_unsold',name='경기도 사업장별 미분양 현황',org='경기도 주택정책과',requirements=['F-04','F-11'],mode='API',url='https://www.data.go.kr/data/15057206/openapi.do',priority='우선',fields='시군·주소·시행/시공·총분양·당월 미분양·준공여부·입주예정·기준월',keys='원천 사업장 키 또는 주소·시행사·사업범위의 검토 대응',limitation='소계/면적행/중복 사업장은 제외. 숨김 시트의 구형 제목·월과 실제 수치를 대조. 승인된 단건 대응 전 지역 참고로 사용.',steps='경기데이터드림 API 신청 또는 경기도 월별 공식 엑셀 수집. API와 파일의 기준월·합계 대조.'),
 dict(id='occupancy_aggregate',name='사업·유형별 실입주·미입주 집계 제공 요청',org='LH·SH·GH·iH·관리기관',requirements=['F-05','F-11'],mode='DATA_REQUEST',url=PROVIDE_URL,priority='우선',fields='공통/기관 사업·단지·유형 ID, 기준월, 입주가능·실입주·미입주 세대수, 정의·확인기관',keys='사업·단지·유형 + 기준월',limitation='현재 공개 API에서 전국·사업별 실입주 전수는 확인되지 않음. 개인·동호별 자료 대신 집계 요청.',steps='기관별 보유 여부 확인 → 공공데이터 제공신청 또는 기관 자료 협의. 예정·계약·준공과 구분한 월별 집계 요구.'),
 dict(id='agency_targets',name='기관별 목표·역할·최초 일정 원장 요청',org='정책 총괄·사업 담당기관',requirements=['F-02','F-06','F-08'],mode='DATA_REQUEST',url=PROVIDE_URL,priority='우선',fields='정책·프로그램·사업 ID, 주관/협력/승인기관, 지역·단계·연월 누적목표, 최초 기준선·변경승인·근거',keys='정책/프로그램/사업 + 기관코드 + 단계 + 기간 + 판본',limitation='기관별 공식 배정량을 사업규모 비례로 자동 생성하지 않음.',steps='담당자 입력으로 먼저 관리하고, 정책 총괄의 승인 배정표·최초 계획판·변경사유 제공 협의.'),
 dict(id='project_crosswalk',name='기관 원천번호 ↔ 공통 사업·범위 대응표',org='사업 주관·원천 제공기관',requirements=['F-01','F-03','F-10'],mode='DATA_REQUEST',url=PROVIDE_URL,priority='우선',fields='공통사업 ID, 기관코드·원천번호, 블록·공급범위, 유효기간, 정정/취소, 확인근거',keys='기관 + 원천 복합키 ↔ 공통사업 + 범위',limitation='정책 ID만으로 사업 동일성이 해결되지 않음. HPR 후보를 기관 공식 ID로 자동 승격하지 않음.',steps='정비 방안 보고서 3번 탭 명세를 활용하여 API 필드 추가 또는 공식 대응표 제공 요청.')]


def board(service):
    sources={s['id']:s for s in service.sources(compact=True)}
    stored={r['request_id']:r for r in service.rows('api_request')}
    return dict(checked_date='2026-10-13',items=[dict(c,collector=dict(status=sources.get(c['id'],{}).get('status','NOT_IMPLEMENTED'),
         key_configured=sources.get(c['id'],{}).get('key_configured',False),last_success=sources.get(c['id'],{}).get('last_success')),
         task=stored.get(c['id'])) for c in CATALOG],
         notice='공식 제공 범위 점검과 HOME의 신청 과제 관리입니다. 신청 초안을 내려받아 공식 사이트에서 로그인·제출하고 접수번호를 기록합니다. 키 설정·담당자 승인·수집 성공은 서로 다릅니다.')


def draft(service, request_id):
    item=next((c for c in CATALOG if c['id']==request_id),None)
    if not item:raise ValueError('신청 과제를 찾을 수 없습니다')
    return '\n'.join([f"[HOME 데이터 연계 신청 초안] {item['name']}",f"제공기관: {item['org']}",
        f"활용 목적: 주택공급 정책의 계획 대비 이행·지역 입지 지표 분석 ({', '.join(item['requirements'])})",
        '요청 범위: 우선 서울·경기·인천, 2025년 이후 월별 자료와 정정 이력. 가능한 전국 범위·과거 제공기간 별도 확인.',
        f"요청 항목: {item['fields']}",f"연계 기준: {item['keys']}",
        '요청 형식: 기존 API 응답 확장 또는 UTF-8 CSV 대응표. 기준월·갱신일·정정/취소·집계 정의 포함.',
        f"확인할 제한: {item['limitation']}",f"진행 방법: {item['steps']}",f"공식 확인·신청 URL: {item['url']}",
        '신청 기관·담당자·연락처·일일 호출량·서비스 URL은 제출자가 기관 정책에 맞춰 기입합니다.',
        '실제 입주·미분양 정보는 개인 식별 없이 사업·유형·지역 단위 집계로 요청합니다.',
        '이 파일은 신청 초안이며 외부 접수 완료를 의미하지 않습니다.'])


def save(service, request_id, revision_no, values):
    item=next((c for c in CATALOG if c['id']==request_id),None)
    if not item:raise ValueError('등록된 연계 과제를 선택하세요')
    if values['status'] in ('SUBMITTED','APPROVED','CONNECTED') and not values.get('receipt_no','').strip():
        raise ValueError('신청·승인 상태에는 외부 접수번호 또는 확인 문서번호가 필요합니다')
    if values['status']=='CONNECTED':
        source=next((s for s in service.sources(compact=True) if s['id']==request_id),{})
        if source.get('status')!='SUCCESS':raise ValueError('연결 완료는 실제 수집 성공을 확인한 뒤 등록하세요')
    if values.get('due_date'):
        from datetime import date
        date.fromisoformat(values['due_date'])
    eid=entity_id('api_request','officer',request_id)
    with service.sessions.begin() as db:
        if service.engine.dialect.name=='postgresql':
            from sqlalchemy import text
            db.execute(text('SELECT pg_advisory_xact_lock(1019080)'))
        old=db.scalar(select(Revision).where(Revision.entity_id==eid,Revision.superseded_at.is_(None)).with_for_update())
        if (old.revision_no if old else 0)!=revision_no:return dict(conflict=True)
        value=dict(values,request_id=request_id,name=item['name'],org=item['org'],base_date=today().isoformat())
        row,outcome=upsert_revision(db,'api_request','officer',request_id,value,'manual')
        if outcome!='unchanged':db.add(Audit(entity_id=eid,action='API_REQUEST_REVIEW',before=old.payload if old else {},after=value))
        return dict(value,id=eid,revision_no=row.revision_no)
