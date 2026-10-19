"""Register reviewed public comparison documents without business or event writes."""
import hashlib
import json
from sqlalchemy import select
from backend.db import engine_for, upsert_revision, Audit, Revision
from backend.service import HomeService
from scripts.review_policy_readmission_20261019 import protected, digest


def main():
    s=HomeService(engine_for()); folder=s.data_dir/'closure-review-20261019'
    before=protected(s)
    manifests={r['name']:r for n in ['fetch-2.json','fetch-3.json'] for r in json.loads((folder/n).read_text()) if r.get('file')}
    specs=[
        ('pps-oct-evaluation','조달청 2026년 10월 대형사업 평가 · 왕숙2 A6/A7 감리 선정','2026-09-30',[],
         '감리 사업자 선정 평가 일정. 주택의 실제 착공일이나 착공량으로 전환하지 않음'),
        ('seoul-investment','서울시 SH 출자 검토 · 방화차고지75호·독산동20호',None,[],
         'PDF 9~12·21쪽 대조. 방화차고지 마곡동1410-10, 독산동331-38 식별. 2018년 정책 계보이며 9·7 귀속 자동 확정 안 함'),
        ('doksan-cis','독산동 산업문화 어울림센터 전기공사 · 서울 건설알림이',None,['AGE_ef586d2e6126132d8358375f'],
         '보유 계약과 공사명·SH·서희이앤씨·2025-01-11이 일치. 전기공사 기간을 주택 전체 착공 사건으로 복사하지 않음'),
        ('yeonhui-yeonnam-cis','연희 및 연남동 공공주택 건설공사 · 서울 건설알림이',None,['AGE_453d66171a940e9edc4d0809'],
         '보유 계약과 공사명·현대아산·2025-06-26~2027-08-03 일치. 원문96호는 합본 표기이며 공식 연남동8호에 전체 호수 전용 안 함'),
        ('private-rental-disclosure-attachment','LH 2026-03 사업실명제 · 공공지원 민간임대주택사업',None,[],
         '사업절차·기금/리츠·지정/공모 누계 확인. 2026년 수도권 착공5,600호 사업별 명세는 이 문서에 없음'),
    ]
    results=[]
    with s.sessions.begin() as db:
        for key,name,stamp,source_ids,basis in specs:
            m=manifests[key]; file=folder/m['file']; sha=hashlib.sha256(file.read_bytes()).hexdigest()
            if sha!=m['sha256']:raise ValueError('원문 해시 변경: '+key)
            for sid in source_ids:
                row=db.scalar(select(Revision).where(Revision.entity_id==sid,Revision.superseded_at.is_(None)))
                if not row or row.kind!='agency_contract':raise ValueError('계약 원천 미확보: '+sid)
            payload=dict(name=name,sample_kind='document_evidence',source_object_id='closure-review-20261019:'+key,
                source_date=stamp,base_date=stamp or '2026-10-19',date_precision='DAY' if stamp else 'COLLECTION',
                source_date_label='문서 발표일' if stamp else '확인일 · 발표일/착공일 아님',
                evidence_url=m['url'],original_sha256=sha,original_file='closure-review-20261019/'+file.name,
                content_text=(folder/(key+'.txt')).read_text(),review_basis=basis,
                confirmed_source_identity_ids=source_ids,matched_project_ids=[],facts=[],units=None,planned_units=None,
                exclude_from_project_totals=True,verification_status='SOURCE_CONTENT_CHECKED',
                review_actor='담당자 대행 · 잔여 검증 지시 2026-10-19')
            row,action=upsert_revision(db,'document_evidence','official_document',payload['source_object_id'],payload,'closure-review-20261019')
            if action!='unchanged':db.add(Audit(entity_id=row.entity_id,action='CLOSURE_SOURCE_REVIEW',before={},after=payload))
            results.append(dict(id=row.entity_id,name=name,action=action,source_identity_ids=source_ids,evidence_url=m['url'],basis=basis))
    after=protected(s)
    if before!=after:raise RuntimeError('보호 대상 값 변경')
    result=dict(documents=results,protected_records=len(before),before_hash=digest(before),after_hash=digest(after),
                new_business_events=0,new_project_mappings=0)
    (folder/'registered-evidence.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
