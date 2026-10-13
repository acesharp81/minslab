"""Apply reviewed SH originals and record the Seoul collection/sequence audit."""
import hashlib,io,json
from pathlib import Path
from pypdf import PdfReader
from backend.service import HomeService
from backend.db import engine_for,upsert_revision,Audit
from backend.api_samples import today
from backend.project_collection import collection_matrix
from scripts.repair_reviewed_project_cases import explicit_link,repair


def magok(service,root):
    p=next(p for p in service.rows('project') if p['source_id']=='sh_inventory' and p['name']=='마곡지구 17단지')
    assert p['planned_units']==381
    documents=[]
    for key,seq in [('magok-notice','301479'),('magok-complete','307836'),('magok-move','310750')]:
        body=(root/(key+'.pdf')).read_bytes()
        text='\n'.join(page.extract_text(extraction_mode='layout') or '' for page in PdfReader(io.BytesIO(body)).pages)
        compact=''.join(text.split());facts=[]
        if key=='magok-notice':
            assert all(t in compact for t in ['마곡지구17단지','381','577','동일한단지입니다','2026.02.27.'])
            facts=[dict(stage='SUPPLY',kind='ACTUAL',date='2026-02-27',units=381,
                basis='SH 본 입주자모집공고 원문 · 전체 단지 577호 중 토지임대부 381호 · 사전청약 175호 포함, 재합산 금지')]
            facts.append(dict(stage='BUSINESS',kind='STATE',date='2026-02-27',basis='공식 본청약 대상 사업 확인 · 사업화 사건일 별도 확인'))
        elif key=='magok-complete':
            assert all(t in compact for t in ['마곡지구10-2단지','577','2026년07월31일','2020-공공주택과-주택건설사업계획승인-3'])
            facts=[dict(stage='CONSTRUCTION',kind='ACTUAL',milestone='COMPLETION',date='2026-07-31',units=381,
                        basis='SH가 마곡17단지로 게시한 사용검사 확인증 · 구 명칭 10-2, 전체 577호 중 해당 분양 381호에 적용'),
                   dict(stage='APPROVAL',kind='DOCUMENT',date=None,
                        basis='사용검사 확인증의 사업계획승인번호 2020-공공주택과-주택건설사업계획승인-3 확보 · 최초 승인일 원문 추가 필요')]
        else:
            assert all(t in compact for t in ['마곡17단지','2026.8.28.','11.25.','입주예정시기'])
            facts=[dict(stage='MOVE_IN',kind='PLAN',date='2026-08-28',units=381,
                basis='SH 안내문의 입주지정기간 시작 예정일 2026-08-28 · 기간 종료 2026-11-25 · 실제 최초 입주일 별도 확인'),
                dict(stage='MOVE_IN',kind='DOCUMENT',date='2026-08-31',
                basis='SH 입주·소유권 이전 조건 변경 안내 원문 확보 · 기입주자 안내 포함, 실제 최초 입주일/입주 호수는 미확인')]
        sha=hashlib.sha256(body).hexdigest();file=service.data_dir/'raw'/'official_document'/(sha+'.pdf');file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(body)
        url='https://www.i-sh.co.kr/app/lay2/program/S48T561C562/www/brd/m_244/view.do?multi_itm_seq=1&seq='+seq
        payload=dict(name={'magok-notice':'마곡17단지 본청약 모집공고','magok-complete':'마곡17단지(구 10-2) 사용검사 확인증','magok-move':'마곡17단지 입주·등기 조건 안내'}[key],
            region='서울특별시',municipality='강서구',address='서울특별시 강서구 마곡동 747-1',sample_kind='document_evidence',
            planned_units=577,scope_breakdown={'토지임대부':381,'장기전세':196},project_aliases=['마곡지구 17단지','마곡지구 10-2단지'],
            facts=facts,evidence_url=url,original_sha256=sha,original_file=str(file.relative_to(service.data_dir)),
            base_date=today().isoformat(),verification_status='SOURCE_CONTENT_CHECKED',date_precision='COLLECTION',
            unit_basis='전체 단지 577호 중 SH 기존 사업 381호만 적용 · 장기전세 196호 별도')
        with service.sessions.begin() as db:
            row,outcome=upsert_revision(db,'document_evidence','official_document',key,payload,'seoul_source_repair')
            if outcome!='unchanged':db.add(Audit(entity_id=row.entity_id,action='OFFICIAL_DOCUMENT_CAPTURE',before={},after=payload))
        source=dict(payload,id=row.entity_id,revision_no=row.revision_no,source_id='official_document')
        status=explicit_link(service,p,source,facts,'공식 공고의 17단지=10-2단지 명칭 변경 확인. 577호 전체와 분양 381호 범위를 구분한 연결 후보 · 담당자 검토')
        documents.append(dict(key=key,document=outcome,link=status))
    repair(service,'sh-name-change-and-notice-gap','SH 단지명 변경·모집공고 및 사용검사 수집 누락',
        '공급계획 API만 읽어 실제 모집공고와 사용검사·입주안내를 놓침. 마곡10-2→17 명칭 변경으로 이름만 비교하면 연결되지 않음.',
        '공식 모집공고·사용검사·입주 조건 안내 3건을 원문 해시와 판본으로 저장하고 DB 연결 후보 등록. 381호 본청약과 전체 577호 사용검사 범위 구분. 입주 지정기간은 실제 입주일로 변경하지 않음.',
        '최초 사업계획승인 고시와 실제 착공일·최초 입주일 확인 필요. 사전청약 175호를 본청약 381호에 다시 더하지 않음.',[p],['BUSINESS','APPROVAL','CONSTRUCTION','SUPPLY','MOVE_IN'],'IDENTITY_LINK')
    return documents


def link_seoul_lh_notices(service):
    projects=[p for p in service.rows('project') if p.get('region')=='서울특별시' and p['source_id'].startswith('lh_')]
    notices=[n for n in service.rows('notice') if n.get('region')=='서울특별시'];linked=[];affected=[]
    # Distinct named districts are explicit in the official LH site code/title and notice.
    aliases=[('서울공릉','서울공릉'),('서울대방','서울대방'),('수방사군부지','동작구수방사')]
    for p in projects:
        identity=str(p.get('district') or p['name'])
        names=[n for n,label in aliases if n in identity]
        if len(names)!=1:continue
        term=next(label for n,label in aliases if n==names[0])
        for n in notices:
            if term not in n['name'].replace(' ',''):continue
            # Shared complex evidence locates rental components, never turns a sale notice into rent delivery.
            kind='DOCUMENT' if p['source_id']=='lh_rent' else 'ACTUAL'
            fact=dict(stage='SUPPLY',kind=kind,date=n.get('source_date'),units=n.get('units'),scope_partial=True,
                scope_label='분양 공고 일부 유형 · 전체 건설/임대 물량 대체 금지',
                basis='청약홈 공식 모집공고의 동일 지구명·주소 연결 · 잔여/추가모집과 본청약 물량 합산 금지')
            if kind=='ACTUAL' and not fact['date']:continue
            state=explicit_link(service,p,n,[fact],
                '서울 LH 지구명 및 공고 주소 대조 후보. 숫자 블록·복합공사명 연결 누락 보완. 공고 물량은 일부 유형 참고이며 기존 담당자 최종 판정 유지')
            linked.append(state);affected.append(p)
    if affected:repair(service,'seoul-lh-numeric-block-notice-gap','서울 LH 숫자 블록·복합공사명과 기존 모집공고 미연결',
        '서울공릉·서울대방·수방사는 숫자 블록 또는 복합공사명으로 저장되어 영문+숫자 블록만 비교하는 규칙에서 빠짐. 청약홈 원천 공고와 실제 주소는 이미 수집되어 있었음.',
        '동일 지구명·서울 주소가 확인된 기존 청약홈 공고를 DB 연결 후보로 저장. 부분 분양 물량과 임대 유형을 구분해 전체 사업 공급 실적으로 확대하지 않음. 공고 주소는 근사 지도 위치 근거로 사용.',
        '최초 인허가·착공 사건 원문 및 전체/부분 물량 확정 필요. 추가모집을 본청약 물량에 재합산하지 않음. 임대 사업은 분양공고를 임대 실적으로 사용하지 않음.',list({p['id']:p for p in affected}.values()),['SUPPLY','APPROVAL','CONSTRUCTION'],'IDENTITY_LINK')
    return dict(links=len(linked),added=linked.count('added'))


def sh_renewal_report(service,path):
    body=path.read_bytes();reader=PdfReader(io.BytesIO(body));plan=reader.pages[38].extract_text(extraction_mode='layout') or '';annual=reader.pages[84].extract_text(extraction_mode='layout') or ''
    compact=''.join((plan+annual).split())
    assert all(t in compact for t in ('상계마들','하계5','사업승인및이주완료','2026년추진계획','건설공사착공'))
    sha=hashlib.sha256(body).hexdigest();file=service.data_dir/'raw'/'official_document'/(sha+'.pdf');file.write_bytes(body)
    projects=[p for p in service.rows('project') if p['source_id']=='policy_907' and p['name'] in ('하계5단지','상계마들')];out=[]
    for p in projects:
        facts=[dict(stage=stage,kind='STATE',date=None,date_label='2026년 3월 업무보고',
            basis='SH 제334회 업무보고 PDF 39쪽: 하계5·상계마들 사업승인 및 이주 완료 확인 · 각 사건일 미확보') for stage in ('BUSINESS','APPROVAL')]
        facts.append(dict(stage='CONSTRUCTION',kind='PLAN',date='2026-12',date_label='2026년 건설공사 착공',
            milestone='CONSTRUCTION',date_conversion='PERIOD_END',
            basis='SH 제334회 업무보고 PDF 85쪽 2026년 착공 계획 · 연도 범위를 마지막 달 12월로 표시 · 실제 착공 아님'))
        payload=dict(name=p['name']+' · SH 2026년 3월 업무보고',sample_kind='document_evidence',region='서울특별시',municipality='노원구',
            facts=facts,planned_units=None,evidence_url='https://mas.smc.seoul.kr/attach/record/SEOUL/appendix/a11/A0071006.pdf',
            original_file=str(file.relative_to(service.data_dir)),original_sha256=sha,base_date=today().isoformat(),date_precision='COLLECTION',
            verification_status='SOURCE_CONTENT_CHECKED',unit_basis='기존 재고·철거 물량을 신규 공급 물량으로 사용하지 않음 · 신규 호수 별도 검토')
        with service.sessions.begin() as db:
            r,state=upsert_revision(db,'document_evidence','official_document','sh-202603-renewal:'+p['id'],payload,'seoul_source_repair')
            if state!='unchanged':db.add(Audit(entity_id=r.entity_id,action='OFFICIAL_DOCUMENT_CAPTURE',before={},after=payload))
        out.append(explicit_link(service,p,dict(payload,id=r.entity_id,revision_no=r.revision_no,source_id='official_document'),facts,
            '9·7 명시 선도단지와 SH 공식 업무보고의 사업명 일치 · 개별 승인일·신규 물량 담당자 검토'))
    repair(service,'sh-renewal-report-stage-gap','노후 공공임대 선도사업의 업무보고 연결 누락',
        '9·7 정책 원문의 사업명만 등록하여 SH 시의회 업무보고에 공개된 승인·이주 상태와 착공 계획을 가져오지 못함.',
        '제334회 공식 SH 업무보고 39·85쪽을 대조해 하계5·상계마들 승인 및 이주 완료 상태, 2026년 착공 계획을 연결. 2026년 범위는 12월 목표로 표기.',
        '보고서의 사업승인 완료 상태를 개별 승인 날짜로 만들지 않음. 실제 착공·준공·공급·입주 사건과 신규 목표 호수 추가 확인 필요. 기존 임대 재고는 신규 물량으로 합산하지 않음.',projects,['BUSINESS','APPROVAL','CONSTRUCTION'],'COLLECTION_GAP')
    return dict(documents=len(out),added=out.count('added'))


def audit(service):
    projects=service.projects();seoul=[p for p in projects if p['region']=='서울특별시']
    docs=[d for d in service.rows('document_evidence') if d['source_id']=='seoul_cleanup'];ids={pid for d in docs for pid in d.get('matched_project_ids',[])}
    repair(service,'seoul-cleanup-collection-gap','서울 정비사업 추진경과 수집 경로 누락',
        'SH 재개발 최신 공개본은 과거 기준이며 정비사업 정보몽땅 사업장·추진경과가 수집 대상에서 빠져 있었음. 블록 없는 서울 사업과 주소의 일대/번지 표기도 기존 규칙에서 누락.',
        '서울 공개 사업장 목록 전체를 대조해 자치구·대표 지번 또는 단일 고유명 일치 사업의 추진경과 수집. 인가 신청과 인가 완료, 일반분양 승인과 실제 모집공고를 구분. 연결을 DB에 저장하고 담당자 기존 판정 보존.',
        '목록에 없는 공공택지·유휴부지·공공임대는 서울시보·자치구 고시·SH 공고·건설알림이 별도 경로 필요. 동명이사업 복수 후보 및 공개되지 않은 추진경과는 미확보 유지.',[p for p in seoul if p['id'] in ids],['BUSINESS','APPROVAL','CONSTRUCTION','SUPPLY'])
    repair(service,'seoul-official-source-route-audit','서울 공식 수집처 재점검·API 연결 범위',
        '기존 SH 공급계획/재개발 파일 외 서울 건설알림이 OA-1222, SH 공사계약 OA-2207, 서울시보·자치구 고시, SH 본청약 및 사용검사 첨부, 정보몽땅 추진경과 경로 미활용.',
        '정보몽땅 수집기 추가 및 SH 원본 보완. 서울 API 키는 이미 등록됨. ListConstructionWorkService와 ConstructionContractCondition 명세 확인. 실행 환경의 openapi.seoul.go.kr HTTPS 연결 실패를 확인해 완료 수집으로 표시하지 않음. 계약 시작일은 착공일로 자동 변환하지 않음.',
        '서울 API 정상 HTTPS 접속 경로 확인 필요(추가 키 신청 불필요). 건설알림이 개별 웹 상세는 접근 가능. 시보 및 자치구 개별 승인 고시 수집 확대, SH 임대·분양 공고판 전체와 첨부 자동 분류는 추가 필요.',seoul,['BUSINESS','APPROVAL','CONSTRUCTION','SUPPLY'],'COLLECTION_GAP')
    matrix=collection_matrix(service)
    counts={}
    for code,title in [('PREDECESSOR_SOURCE_GAP','후속 실적 대비 선행 단계 근거 누락'),('PLAN_PREDECESSOR_CHECK','후속 예정 일정의 선행 원문 확인')]:
        affected=[p for p in matrix['items'] if any(c['code']==code for c in p.get('sequence_checks',[]))]
        members=[p for p in projects if p['id'] in {a['id'] for a in affected}];counts[code]=len(members)
        if members:repair(service,'sequence-'+code.lower(),title,
            '후속 단계 자료가 있는데 선행 단계의 직접 근거가 연결되지 않음. 미래 입주 예정·사전예약과 실제 입주·본청약을 구분하지 않고 완료 처리하면 오류.',
            '전체 사업의 입주→공급/인허가/건설, 공급→인허가/건설, 건설→사업화/인허가 자료 존재를 점검. 사업 상세에 우선 확인 단계와 이유 표시. 실제 후속 실적은 HIGH, 예정만 있는 경우 NORMAL 우선순위로 분리.',
            '공식 사건일·고시·공고 역추적 우선. 임대사업은 분양이 아니라 임대모집 확인. 선분양은 착공보다 앞설 수 있음. 추정 선행 상태는 담당자 검토 후보이며 과거 날짜/물량 자동 생성 금지.',members,['BUSINESS','APPROVAL','CONSTRUCTION','SUPPLY','MOVE_IN'],'AVAILABILITY_STATE')
    located=[p for p in projects if p.get('coordinate_basis','').startswith('APPROXIMATE')]
    repair(service,'area-coordinates-period-end','범위 주소·일정의 지도 및 월별 집계 기준',
        '일대/일원 주소와 분기·반기 일정은 정확값만 허용하는 처리에서 누락됐음.',
        '대표 지번 근사 좌표 우선, 실패하거나 주소 없으면 공식 시군구 내부 대표점으로 표시. DB에 원문주소/조회주소/근사등급 저장. 분기·반기·연도·기간 일정은 마지막 달 말일로 집계하고 원문·정밀도 보존.',
        '시군구 대표점은 해당 사업의 실제 부지 위치가 아님. 지도에 근사 위치 명시. PNU·법적 경계·실제 승인일은 이 값으로 생성하지 않음. 위치 확인 안 되는 사업은 미확보 유지.',located,['POLICY','CONSTRUCTION','SUPPLY','MOVE_IN'],'STAGE_DATE')
    return dict(seoul_projects=len(seoul),cleanup_linked=len(ids),seoul_located=sum(p.get('latitude') is not None for p in seoul),sequence=counts)

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--snapshot-dir',type=Path,required=True);args=parser.parse_args()
    service=HomeService(engine_for(),'/app/data')
    print(json.dumps(magok(service,args.snapshot_dir),ensure_ascii=False))
    print(json.dumps(link_seoul_lh_notices(service),ensure_ascii=False))
    print(json.dumps(audit(service),ensure_ascii=False))
