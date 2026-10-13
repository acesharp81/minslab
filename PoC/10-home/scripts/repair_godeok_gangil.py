"""Verified Godeok-Gangil captures, persistent review candidates and repair history."""
import argparse
import hashlib
import io
import json
import re
from pathlib import Path
from bs4 import BeautifulSoup
from pypdf import PdfReader
from backend.service import HomeService
from backend.db import Audit,engine_for,upsert_revision
from backend.seoul_project_documents import parse_construction_overview,parse_godeok_pre_notice_text
from scripts.repair_reviewed_project_cases import explicit_link,repair

CODE='7042023051599'
NAME='고덕강일 공공주택지구 3단지 아파트 건설공사'
TARGET_ID='PRO_1fbf5c7629634fa05be7652a'


def prepare(root):
    manifest=json.loads((root/'manifest.json').read_text());parsed=[]
    for key in ('cis','sh-pdf','sh-second-pdf','eum','cis-photo'):
        metadata=manifest[key];body=(root/key).read_bytes()
        if hashlib.sha256(body).hexdigest()!=metadata['sha256']:raise ValueError('원문 해시 불일치: '+key)
        pdf=key.endswith('pdf')
        if pdf and not body.startswith(b'%PDF'):raise ValueError('공고문 PDF 형식 미확인')
        if key=='cis':
            payload=parse_construction_overview(body,CODE,NAME)
            payload.update(region='서울특별시',municipality='강동구')
        elif pdf:
            text='\n'.join(p.extract_text(extraction_mode='layout') or '' for p in PdfReader(io.BytesIO(body)).pages)
            payload=parse_godeok_pre_notice_text(text,'2022-12-30' if key=='sh-pdf' else '2023-06-13',1 if key=='sh-pdf' else 2)
        else:
            soup=BeautifulSoup(body,'html.parser');text=re.sub(r'\s+',' ',soup.get_text(' ',strip=True))
            if key=='eum':
                if not all(t in text for t in ('서울고덕강일','지구계획 변경(14차)','제2025-593호','2025-10-24')):
                    raise ValueError('고덕강일 지구계획 변경 고시 확인 실패')
                payload=dict(name='서울고덕강일 지구계획 변경(14차) · 국토부 제2025-593호',
                    region='서울특별시',municipality='강동구',planned_units=None,approval_scope='DISTRICT',
                    facts=[dict(stage='APPROVAL',kind='DOCUMENT',date='2025-10-24',event_type='DISTRICT_PLAN_CHANGE',
                        scope_partial=True,scope_label='고덕강일 지구 전체 · 3단지 개별 승인과 구분',
                        basis='국토부 제2025-593호 지구지정·지구계획 변경 승인 고시 원문 확보 · 3단지 개별 주택건설사업계획 승인일로 집계하지 않음')],
                    unit_basis='지구 전체 계획 고시 · 개별 단지 승인 물량·날짜 대체 금지')
            else:
                if NAME not in text:raise ValueError('건설알림이 사진 사업명 불일치')
                stamps=re.findall(r'\((20\d{2}-\d{2}-\d{2})\)',text)
                if not stamps:raise ValueError('건설알림이 사진 등록일 미확인')
                latest=max(stamps)
                payload=dict(name=NAME+' · 공정사진 등록 목록',region='서울특별시',municipality='강동구',planned_units=None,
                    latest_photo_date=latest,source_object_id=CODE,
                    facts=[dict(stage='CONSTRUCTION',kind='DOCUMENT',date=latest,
                        basis='서울 건설알림이 공정사진 목록 확보 · 최근 사진 등록일 '+latest+' · 공정률 관측일이나 실제 준공일을 뜻하지 않음')],
                    unit_basis='공정사진 목록 보조 근거 · 호수 합산 없음')
        parsed.append((key,metadata,body,pdf,payload))
    return parsed


def apply(service,root):
    prepared=prepare(root)
    project=next(p for p in service.rows('project') if p['id']==TARGET_ID)
    if project['source_id']!='sh_inventory' or project['name']!='고덕강일 3단지' or project['planned_units']!=1305:
        raise ValueError('고덕강일 기존 사업 범위 변경 · 담당자 검토 필요')
    results=[]
    for key,metadata,body,pdf,parsed in prepared:
        file=service.data_dir/'raw'/'official_document'/(metadata['sha256']+('.pdf' if pdf else '.html'))
        file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(body)
        payload=dict(parsed,sample_kind='document_evidence',evidence_url=metadata['url'],
            original_sha256=metadata['sha256'],original_file=str(file.relative_to(service.data_dir)),
            verification_status='SOURCE_CONTENT_CHECKED',base_date='2026-10-13',date_precision='COLLECTION',
            registration_set='SEOUL_GODEOK_20261013')
        with service.sessions.begin() as db:
            row,outcome=upsert_revision(db,'document_evidence','official_document','godeok-gangil-3:'+key,payload,'godeok_gangil_review')
            if outcome!='unchanged':db.add(Audit(entity_id=row.entity_id,action='OFFICIAL_DOCUMENT_CAPTURE',before={},after=payload))
        source=dict(payload,id=row.entity_id,revision_no=row.revision_no,source_id='official_document')
        linked=explicit_link(service,project,source,source['facts'],
            '고덕강일 3단지 SH 사업 1,305호와 공식 사업명·주택형 구성·공사 코드를 대조한 연결 후보. 사전예약·지구 전체 고시·기준일 미확인 공정률의 범위를 구분하며 담당자 최종 검토 필요')
        results.append(dict(key=key,id=row.entity_id,document=outcome,link=linked))
    repair(service,'sh-official-detail-coverage-gap','SH 공개파일 계획과 건설알림이·모집공고 상세 연결 누락',
        '고덕강일 3단지는 SH 최신 공급계획에서 총 1,305호와 2026-08 예정만 수집됐다. 기존 SH 사업 수집기는 공급계획/재개발 공개파일만 읽고, 건설알림이 코드와 공식 모집공고 PDF를 가져오지 않는다. LH 지구·숫자 블록 기반 매칭은 SH 3단지 명칭에 적용되지 않아 조회 시 연결될 수 없다.',
        '건설알림이 공사코드 '+CODE+' 및 SH 1·2차 공고문 PDF를 검증해 기존 사업에 영구 DB 연결 후보로 저장했다. 착공 2023-05-15, 준공 예정 2026-11-06, 주택형별 입주 예정 2027-03과 사전예약 1차 500호·2차 590호를 분리했다. 공고 원본/해시/고정 판본을 보존해 표·다이어그램·상세에 함께 표시한다.',
        'SH 전체 사업 전수 수집은 별도 확장 과제. 2026년 본청약 연기 및 최종 공고·입주 일정은 최신 공식 공고 추가 대조 필요. 원 공개파일 2026-08 계획을 실적으로 전환하지 않는다. 9·7 정책 귀속 검토는 기존 담당자 판정을 유지한다.',[project],['CONSTRUCTION','SUPPLY','MOVE_IN'])
    repair(service,'sh-pre-reservation-district-scope','지구 승인·사전예약과 단지 인허가·본청약의 범위 구분',
        '제보 고시 제2025-593호는 고덕강일 지구 전체 지정·계획 변경이고 SH seq256974 공고는 2022-12-30 사전예약이다. 이를 3단지 최초 건축 승인·현재 본청약 실적으로 쓰면 범위와 시점이 잘못된다.',
        '지구 고시는 인허가 문서 확보로 연결하고 개별 승인 실적에는 넣지 않았다. 총 건설호수 1,305=59㎡715+49㎡590을 대조했으며 사전예약 500+590=1,090호와 본청약 신규 215호를 구분했다. 본청약 때 사전예약 당첨자의 재신청을 신규 물량으로 합산하지 않는다.',
        '3단지 개별 주택건설사업계획 승인 고시·사용승인, 최신 본청약 공고 및 계약 실적 확보 필요. 모든 예정월은 공식 원문의 당시 계획으로 표시하며 실제 입주는 미확보 상태를 유지한다.',[project],['APPROVAL','SUPPLY','MOVE_IN'],'SCOPE_QUANTITY')
    repair(service,'seoul-undated-construction-progress','서울 건설알림이 공정률 기준일 미표기',
        '건설알림이 공사개요에 계획 2.75%·실적 2.49%·달성 90.55%가 있으나 해당 공정률의 관측 기준일이 없다. 사진 목록에는 2026-09-01 등 등록일이 있으나 그 날짜가 공정률 기준일이라는 근거는 없다.',
        '화면 수치를 원문 확보 기록으로 보존하고 공정률 관측일은 null로 저장했다. 현재 공정률·계획 대비 지연 계산에는 사용하지 않았다. 공정사진 목록을 별도 보조 근거로 연결했다.',
        'SH 또는 서울시의 기준일 있는 월별 계획·실제 공정률 확보 필요. 달성률 90.55%를 실제 공정률로 변환하지 않고 사진 등록일을 공정률 날짜로 대체하지 않는다.',[project],['CONSTRUCTION'],'AVAILABILITY_STATE')
    return dict(project_id=project['id'],documents=results,project_units=project['planned_units'],policy_mapping_preserved=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--snapshot-dir',type=Path,required=True);p.add_argument('--apply',action='store_true');args=p.parse_args()
    if not args.apply:
        print(json.dumps([dict(key=k,name=v['name'],facts=v['facts']) for k,_,_,_,v in prepare(args.snapshot_dir)],ensure_ascii=False,indent=2))
    else:print(json.dumps(apply(HomeService(engine_for(),'/app/data'),args.snapshot_dir),ensure_ascii=False,indent=2))
